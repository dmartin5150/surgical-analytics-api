from fastapi import APIRouter, Query
from pymongo import MongoClient
from datetime import datetime, timedelta, time
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

def empty_day(weekday: str) -> Dict[str, Any]:
    return {
        "date": None,
        "weekday": weekday,
        "isCurrentMonth": False,
        "schedule": [],
        "utilization": {
            "overall": 0.0,
            "rooms": {}
        }
    }

def format_time_range(start: str, end: str) -> str:
    try:
        start_dt = parser.parse(start)
        end_dt = parser.parse(end)
        return f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
    except Exception as e:
        logger.warning(f"Time format error: {e}")
        return ""

def get_minutes_in_window(start_str: str, end_str: str) -> int:
    try:
        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt).time()
        end = datetime.strptime(end_str, fmt).time()

        window_start = time(7, 0)
        window_end = time(15, 30)

        actual_start = max(start, window_start)
        actual_end = min(end, window_end)

        if actual_start >= actual_end:
            return 0

        delta = (
            datetime.combine(datetime.today(), actual_end) -
            datetime.combine(datetime.today(), actual_start)
        ).seconds // 60
        return delta
    except Exception:
        return 0

@router.get("/calendar/view")
def get_calendar_view(
    month: str = Query(..., example="2024-05"),
    hospitalId: str = Query(...),
    unit: str = Query(...),
):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    days_grid = [[] for _ in range(6)]

    year, month_num = map(int, month.split("-"))
    start_date = datetime(year, month_num, 1).date()
    last_day = calendar.monthrange(year, month_num)[1]
    end_date = datetime(year, month_num, last_day).date()

    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    logger.info(f"Fetching calendar for {month}, hospitalId={hospitalId}, unit={unit}")
    logger.info(f"Date range: {start_date_str} to {end_date_str}")

    matching_docs = list(calendar_collection.find({
        "date": {"$gte": start_date_str, "$lte": end_date_str},
        "hospitalId": hospitalId,
        "unit": unit
    }))

    logger.info(f"Found {len(matching_docs)} matching documents")

    grouped_by_date: Dict[str, Dict[str, Any]] = {}

    for doc in matching_docs:
        date_str = doc["date"]
        weekday = get_weekday(date_str)
        room = doc.get("room", "")

        if date_str not in grouped_by_date:
            grouped_by_date[date_str] = {
                "date": date_str,
                "weekday": weekday,
                "isCurrentMonth": True,
                "schedule": defaultdict(list)
            }

        for proc in doc.get("procedures", []):
            time_str = format_time_range(proc.get("startTime", ""), proc.get("endTime", ""))
            grouped_by_date[date_str]["schedule"][room].append({
                "type": "case",
                "time": time_str,
                "provider": proc.get("providerName", ""),
                "room": room
            })

        for blk in doc.get("blocks", []):
            time_str = format_time_range(blk.get("startTime", ""), blk.get("endTime", ""))
            grouped_by_date[date_str]["schedule"][room].append({
                "type": "block",
                "time": time_str,
                "provider": blk.get("providerName", ""),
                "room": room
            })

    for date_str, data in grouped_by_date.items():
        data["schedule"] = [
            {"room": room, "schedule": sched}
            for room, sched in data["schedule"].items()
        ]

        total_room_minutes = 510
        room_minutes = {}
        total_minutes = 0

        for entry in data["schedule"]:
            room = entry["room"]
            items = entry["schedule"]
            minutes = sum(
                get_minutes_in_window(*item["time"].split(" - "))
                for item in items if item["type"] == "case"
            )
            room_minutes[room] = minutes
            total_minutes += minutes

        room_utilization = {
            room: round(minutes / total_room_minutes, 3)
            for room, minutes in room_minutes.items()
        }

        overall_util = (
            round(total_minutes / (len(room_minutes) * total_room_minutes), 3)
            if room_minutes else 0.0
        )

        data["utilization"] = {
            "overall": overall_util,
            "rooms": room_utilization
        }

    week_idx = 0
    current_day = start_date

    first_weekday = current_day.weekday()
    if first_weekday < 5:
        for i in range(first_weekday):
            weekday_name = calendar.day_name[i]
            days_grid[week_idx].append(empty_day(weekday_name))

    while current_day <= end_date:
        if current_day.weekday() < 5:
            date_str = current_day.strftime("%Y-%m-%d")
            weekday_name = calendar.day_name[current_day.weekday()]

            if len(days_grid[week_idx]) == 5:
                week_idx += 1

            if date_str in grouped_by_date:
                days_grid[week_idx].append(grouped_by_date[date_str])
            else:
                days_grid[week_idx].append({
                    "date": date_str,
                    "weekday": weekday_name,
                    "isCurrentMonth": True,
                    "schedule": [],
                    "utilization": {
                        "overall": 0.0,
                        "rooms": {}
                    }
                })

        current_day += timedelta(days=1)

    for week in days_grid:
        while len(week) < 5:
            week.append(empty_day(weekdays[len(week)]))

    logger.info("✅ Calendar grid created successfully")
    return days_grid[:6]