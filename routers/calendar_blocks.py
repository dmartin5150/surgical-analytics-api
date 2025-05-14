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
        parsed_date = parser.isoparse(date)
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=pytz.UTC)
        central_date_str = parsed_date.astimezone(central).strftime("%Y-%m-%d")
    except Exception as e:
        return {"error": f"Invalid date format: {e}"}

    doc = calendar_collection.find_one({
        "date": central_date_str,
        "hospitalId": hospitalId,
        "unit": unit,
        "room": room
    })

    return {
        "date": central_date_str,
        "room": room,
        "blocks": doc.get("blocks", []) if doc else []
    }
