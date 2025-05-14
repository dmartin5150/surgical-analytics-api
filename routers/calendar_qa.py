from datetime import datetime, timedelta
from pymongo import MongoClient
from fastapi import APIRouter, Query
from dotenv import load_dotenv
import calendar
import os
from dateutil import parser
import pytz

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]

central = pytz.timezone("US/Central")

def parse_to_central_date(dt_str: str) -> str:
    try:
        dt = parser.isoparse(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.UTC)
        return dt.astimezone(central).strftime("%Y-%m-%d")
    except Exception:
        return dt_str[:10]  # fallback just in case

def check_block_overlap(blocks):
    intervals = []
    for b in blocks:
        try:
            start = parser.isoparse(b["startTime"])
            end = parser.isoparse(b["endTime"])
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

    by_date = {}
    rooms_with_overlap = set()

    for doc in calendar_docs:
        central_date = parse_to_central_date(doc["date"])
        by_date[central_date] = doc

        blocks = doc.get("blocks", [])
        if len(blocks) > 1 and check_block_overlap(blocks):
            rooms_with_overlap.add(doc.get("room"))

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
                    "date": date_str,
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

    unique_rooms = sorted({
        sched_entry["room"]
        for week in days_grid
        for day in week
        if day["date"] is not None
        for sched in day["schedule"]
        for sched_entry in [sched]
    })

    return {
        "calendar": days_grid[:6],
        "allRooms": unique_rooms,
        "roomsWithOverlap": sorted(rooms_with_overlap)
    }
