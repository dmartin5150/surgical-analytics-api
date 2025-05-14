# routers/calendar_qa.py
from datetime import datetime, timedelta
from pymongo import MongoClient
from fastapi import APIRouter, Query
from dotenv import load_dotenv
import calendar
import os

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]


def get_weekday_name(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return calendar.day_name[dt.weekday()]


def check_block_overlap(blocks):
    intervals = []
    for b in blocks:
        try:
            start = datetime.fromisoformat(b["startTime"])
            end = datetime.fromisoformat(b["endTime"])
            intervals.append((start, end))
        except Exception:
            continue

    intervals.sort()
    for i in range(1, len(intervals)):
        if intervals[i][0] < intervals[i - 1][1]:
            return True
    return False


@router.get("/calendar/qa")
def get_calendar_qa_view(
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

    calendar_docs = list(calendar_collection.find({
        "date": {"$gte": start_date_str, "$lte": end_date_str},
        "hospitalId": hospitalId,
        "unit": unit
    }))

    by_date = {doc["date"]: doc for doc in calendar_docs}

    current_day = start_date
    week_idx = 0

    first_weekday = current_day.weekday()
    if first_weekday < 5:
        for i in range(first_weekday):
            days_grid[week_idx].append({
                "date": None,
                "weekday": calendar.day_name[i],
                "isCurrentMonth": False,
                "schedule": [],
                "hasMultipleBlocks": False,
                "hasBlockOverlap": False,
            })

    while current_day <= end_date:
        if current_day.weekday() < 5:
            date_str = current_day.strftime("%Y-%m-%d")
            weekday_name = calendar.day_name[current_day.weekday()]

            if len(days_grid[week_idx]) == 5:
                week_idx += 1

            if date_str in by_date:
                doc = by_date[date_str]
                blocks = doc.get("blocks", [])
                has_multiple = len(blocks) > 1
                has_overlap = check_block_overlap(blocks)

                days_grid[week_idx].append({
                    "date": doc["date"],
                    "weekday": weekday_name,
                    "isCurrentMonth": True,
                    "schedule": doc.get("schedule", []),
                    "hasMultipleBlocks": has_multiple,
                    "hasBlockOverlap": has_overlap
                })
            else:
                days_grid[week_idx].append({
                    "date": date_str,
                    "weekday": weekday_name,
                    "isCurrentMonth": True,
                    "schedule": [],
                    "hasMultipleBlocks": False,
                    "hasBlockOverlap": False
                })

        current_day += timedelta(days=1)

    return days_grid[:6]