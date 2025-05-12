from fastapi import APIRouter, Query
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, Any
import calendar
import os
import logging
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
        "rooms": {}
    }

@router.get("/calendar/view")
def get_calendar_view(
    month: str = Query(..., example="2024-05"),
    hospitalId: str = Query(...),
    unit: str = Query(...),
):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    days_grid = [[] for _ in range(6)]

    start_date_str = f"{month}-01"
    year, month_num = map(int, month.split("-"))
    end_day = calendar.monthrange(year, month_num)[1]
    end_date_str = f"{month}-{end_day:02d}"

    logger.info(f"Fetching calendar for {month}, hospitalId={hospitalId}, unit={unit}")
    logger.info(f"Date range (string): {start_date_str} to {end_date_str}")

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
                "rooms": {}
            }

        if room not in grouped_by_date[date_str]["rooms"]:
            grouped_by_date[date_str]["rooms"][room] = []

        for proc in doc.get("procedures", []):
            grouped_by_date[date_str]["rooms"][room].append({
                "type": "case",
                "time": proc.get("time", ""),
                "provider": proc.get("providerName", "")
            })

        for blk in doc.get("blocks", []):
            grouped_by_date[date_str]["rooms"][room].append({
                "type": "block",
                "time": blk.get("time", ""),
                "provider": blk.get("providerName", "")
            })

    current_day = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    week_idx = 0

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
                    "rooms": {}
                })

        current_day += timedelta(days=1)

    for week in days_grid:
        while len(week) < 5:
            week.append(empty_day(weekdays[len(week)]))

    logger.info("✅ Calendar grid created successfully")
    return days_grid[:6]
