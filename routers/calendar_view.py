from fastapi import APIRouter, Query
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, Any
import calendar
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendars"]

def get_weekday(date_str: str) -> str:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return calendar.day_name[date_obj.weekday()]

def empty_day(weekday: str) -> Dict[str, Any]:
    return {
        "date": None,
        "weekday": weekday,
        "isCurrentMonth": False,
        "schedule": []
    }

@router.get("/calendar/view")
def get_calendar_view(
    month: str = Query(..., example="2024-05"),
    hospitalId: str = Query(...),
    unit: str = Query(...),
):
    logger.info(f"Fetching calendar for {month}, hospitalId={hospitalId}, unit={unit}")

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    days_grid = [[] for _ in range(6)]

    start_date = f"{month}-01"
    end_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
    end_date = f"{month}-{end_day:02d}"

    logger.info(f"Date range: {start_date} to {end_date}")

    matching_days = list(calendar_collection.find({
        "date": {"$gte": start_date, "$lte": end_date},
        "hospitalId": hospitalId,
        "unit": unit
    }))

    logger.info(f"Found {len(matching_days)} matching documents")

    day_map = {}
    for doc in matching_days:
        date_str = doc["date"]
        weekday = get_weekday(date_str)
        schedule = []

        # log raw room/procedure structure
        logger.debug(f"Document for {date_str}: {doc}")

        for proc in doc.get("procedures", []):
            logger.debug(f"Adding procedure: {proc}")
            schedule.append({
                "type": "case",
                "time": proc.get("time"),
                "provider": proc.get("providerName"),
                "room": proc.get("room")
            })
        for blk in doc.get("blocks", []):
            logger.debug(f"Adding block: {blk}")
            schedule.append({
                "type": "block",
                "time": blk.get("time"),
                "provider": blk.get("providerName"),
                "room": blk.get("room")
            })

        day_map[date_str] = {
            "date": date_str,
            "weekday": weekday,
            "isCurrentMonth": True,
            "schedule": schedule
        }

    month_start = datetime.strptime(start_date, "%Y-%m-%d")
    day_iter = month_start
    week_idx = 0

    while day_iter.strftime("%Y-%m-%d") <= end_date:
        wd = day_iter.weekday()
        if wd >= 5:
            day_iter += timedelta(days=1)
            continue

        weekday_name = calendar.day_name[wd]
        date_str = day_iter.strftime("%Y-%m-%d")

        if len(days_grid[week_idx]) == 5:
            week_idx += 1

        if date_str in day_map:
            days_grid[week_idx].append(day_map[date_str])
        else:
            days_grid[week_idx].append({
                "date": date_str,
                "weekday": weekday_name,
                "isCurrentMonth": True,
                "schedule": []
            })

        day_iter += timedelta(days=1)

    for week in days_grid:
        while len(week) < 5:
            week.append(empty_day(weekdays[len(week)]))

    logger.info("Calendar grid generated successfully")
    return days_grid[:4]  # Truncate to preview in browser
