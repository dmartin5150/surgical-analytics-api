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
    year, month_num = map(int, month.split("-"))
    start_date = datetime(year, month_num, 1).date()
    last_day = calendar.monthrange(year, month_num)[1]
    end_date = datetime(year, month_num, last_day).date()

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    calendar_docs = list(calendar_collection.find({
        "date": {"$gte": start_str, "$lte": end_str},
        "hospitalId": hospitalId,
        "unit": unit
    }))

    all_rooms = set()
    rooms_with_overlap = {}
    rooms_with_multiple = {}

    for doc in calendar_docs:
        date = parse_to_central_date(doc["date"])
        room = doc.get("room")
        blocks = doc.get("blocks", [])

        if not room or not blocks:
            continue

        all_rooms.add(room)

        if len(blocks) > 1:
            rooms_with_multiple.setdefault(room, []).append(date)
            if check_block_overlap(blocks):
                rooms_with_overlap.setdefault(room, []).append(date)

    return {
        "allRooms": sorted(all_rooms),
        "roomsWithOverlap": rooms_with_overlap,   # {room: [date, ...]}
        "roomsWithMultiple": rooms_with_multiple  # {room: [date, ...]}
    }
