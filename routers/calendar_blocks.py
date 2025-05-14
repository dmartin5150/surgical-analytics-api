from datetime import datetime
from pymongo import MongoClient
from fastapi import APIRouter, Query
from dotenv import load_dotenv
from dateutil import parser
import os
import pytz

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]

central = pytz.timezone("US/Central")
@router.get("/calendar/blocks", tags=["Calendar"])
def get_blocks_for_day(
    date: str = Query(..., example="2024-05-08"),
    room: str = Query(...),
    hospitalId: str = Query(...),
    unit: str = Query(...)
):
    """
    Return all blocks for a given facility, unit, room, and date.
    """
    try:
        # Parse as naive local date, no timezone conversion
        central_date_str = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception as e:
        return {"error": f"Invalid date format: {e}"}

    cursor = calendar_collection.find({
        "date": central_date_str,
        "hospitalId": hospitalId,
        "unit": unit,
        "room": room
    })

    blocks = []
    for doc in cursor:
        blocks.extend(doc.get("blocks", []))

    return {
        "date": central_date_str,
        "room": room,
        "blocks": blocks
    }
