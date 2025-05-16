from fastapi import APIRouter
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]
block_collection = db["block"]

class BlockUpdateRequest(BaseModel):
    blockId: str
    inactive: bool
    date: str  # YYYY-MM-DD format (e.g., 2025-04-01)

@router.patch("/calendar/blocks/inactive")
def patch_block_inactive(data: BlockUpdateRequest):
    # Update the embedded block inside the correct calendar document
    calendar_result = calendar_collection.update_one(
        {"date": data.date, "blocks.blockId": data.blockId},
        {"$set": {"blocks.$.inactive": data.inactive}}
    )

    # Update top-level block document
    block_result = block_collection.update_one(
        {"_id": ObjectId(data.blockId)},
        {"$set": {"inactive": data.inactive}}
    )

    return {
        "calendarUpdated": calendar_result.modified_count,
        "blockUpdated": block_result.modified_count,
        "blockId": data.blockId,
        "date": data.date,
        "inactive": data.inactive
    }
