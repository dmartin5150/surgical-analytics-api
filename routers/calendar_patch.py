from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]

class InactiveUpdateRequest(BaseModel):
    date: str
    room: str
    hospitalId: str
    unit: str
    blockId: str
    inactive: bool

@router.patch("/calendar/blocks/inactive", tags=["Calendar"])
def update_block_inactive_status(payload: InactiveUpdateRequest):
    """
    Update the `inactive` status of a specific block in the calendar document.
    """
    result = calendar_collection.update_one(
        {
            "date": payload.date,
            "room": payload.room,
            "hospitalId": payload.hospitalId,
            "unit": payload.unit,
            "blocks.blockId": payload.blockId
        },
        {
            "$set": {
                "blocks.$.inactive": payload.inactive
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Block not found or already set")

    return {"message": "Block inactive status updated successfully"}
