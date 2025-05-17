from fastapi import APIRouter, Query
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, Any
import calendar
import os
import logging
from collections import defaultdict
from dateutil import parser
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def get_weekday(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    return calendar.day_name[dt.weekday()]

def empty_day(weekday: str, all_rooms: list) -> Dict[str, Any]:
    return {
        "date": None,
        "weekday": weekday,
        "isCurrentMonth": False,
        "totalRooms": len(all_rooms),
        "schedule": [
            {"room": room, "schedule": []} for room in all_rooms
        ],
        "utilization": {
            "overall": 0.0,
            "rooms": {room: 0.0 for room in all_rooms}
        }
    }

def format_time_range(start: Any, end: Any) -> str:
    try:
        start_dt = parser.parse(start) if isinstance(start, str) else start
        end_dt = parser.parse(end) if isinstance(end, str) else end

        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            raise ValueError("Invalid datetime format")

        return f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
    except Exception as e:
        logger.warning(f"Time format error: {e}")
        return ""


@router.get("/calendar/view")
def get_calendar_view(
    month: str = Query(..., example="2025-04"),
    hospitalId: str = Query(...),
    unit: str = Query(...)
):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    year, month_num = map(int, month.split("-"))
    start_date = datetime(year, month_num, 1).date()
    last_day = calendar.monthrange(year, month_num)[1]
    end_date = datetime(year, month_num, last_day).date()

    matching_docs = list(calendar_collection.find({
        "date": {"$gte": start_date.strftime("%Y-%m-%d"), "$lte": end_date.strftime("%Y-%m-%d")},
        "hospitalId": hospitalId,
        "unit": unit
    }))

    all_rooms = sorted({
        doc["room"].strip().upper()
        for doc in matching_docs
        if doc.get("room") and isinstance(doc["room"], str)
    })

    days_grid = [[] for _ in range(6)]
    grouped_by_date: Dict[str, Dict[str, Any]] = {}

    for doc in matching_docs:
        date_str = doc["date"]
        weekday = get_weekday(date_str)
        room = doc.get("room", "").strip().upper()

        if date_str not in grouped_by_date:
            grouped_by_date[date_str] = {
                "date": date_str,
                "weekday": weekday,
                "isCurrentMonth": True,
                "totalRooms": len(all_rooms),
                "schedule": defaultdict(list),
                "utilization": {
                    "overall": 0.0,
                    "rooms": {r: 0.0 for r in all_rooms}
                }
            }

        # Add procedures
        for proc in doc.get("procedures", []):
            time_str = format_time_range(proc.get("startTime", ""), proc.get("endTime", ""))
            grouped_by_date[date_str]["schedule"][room].append({
                "type": "case",
                "time": time_str,
                "provider": proc.get("providerName", ""),
                "room": room,
                "duration": proc.get("duration", 0),
                "primaryNpi": proc.get("primaryNpi", None)
            })

        # Add blocks
        for blk in doc.get("blocks", []):
            time_str = format_time_range(blk.get("startTime", ""), blk.get("endTime", ""))
            grouped_by_date[date_str]["schedule"][room].append({
                "type": "block",
                "time": time_str,
                "provider": blk.get("providerName", ""),
                "room": room,
                "inactive": blk.get("inactive", False),
                "inRoomUtilization": blk.get("inRoomUtilization", 0.0),
                "anywhereUtilization": blk.get("anywhereUtilization", 0.0),
                "duration": blk.get("duration", 0),
                "primaryNpi": blk.get("npi", None)
            })

        # Populate per-room utilization (for room view, not block)
        room_util = doc.get("utilizationRate")
        if room_util is not None:
            grouped_by_date[date_str]["utilization"]["rooms"][room] = round(room_util, 3)

    # Calculate overall utilization and flatten schedule
    for date_str, data in grouped_by_date.items():
        room_values = list(data["utilization"]["rooms"].values())
        if room_values:
            data["utilization"]["overall"] = round(sum(room_values) / len(room_values), 3)

        room_schedule_map = {
            room: sched for room, sched in data["schedule"].items()
        }

        data["schedule"] = [
            {"room": room, "schedule": room_schedule_map.get(room, [])}
            for room in all_rooms
        ]

    # Grid setup
    week_idx = 0
    current_day = start_date

    first_weekday = current_day.weekday()
    if first_weekday < 5:
        for i in range(first_weekday):
            days_grid[week_idx].append(empty_day(calendar.day_name[i], all_rooms))

    while current_day <= end_date:
        if current_day.weekday() < 5:
            date_str = current_day.strftime("%Y-%m-%d")
            weekday_name = calendar.day_name[current_day.weekday()]

            if len(days_grid[week_idx]) == 5:
                week_idx += 1

            if date_str in grouped_by_date:
                days_grid[week_idx].append(grouped_by_date[date_str])
            else:
                days_grid[week_idx].append(empty_day(weekday_name, all_rooms))

        current_day += timedelta(days=1)

    # Ensure each week has 5 weekdays
    for week in days_grid:
        while len(week) < 5:
            week.append(empty_day(weekdays[len(week)], all_rooms))

    return days_grid[:6]
