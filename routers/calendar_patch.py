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

@router.patch("/calendar/blocks/inactive")
def patch_block_inactive(data: BlockUpdateRequest):
    # Update embedded block inside calendar
    calendar_result = calendar_collection.update_one(
        {"blocks.blockId": data.blockId},
        {"$set": {"blocks.$.inactive": data.inactive}}
    )

    # Update block document in the block collection
    block_result = block_collection.update_one(
        {"_id": ObjectId(data.blockId)},
        {"$set": {"inactive": data.inactive}}
    )

    return {
        "calendarUpdated": calendar_result.modified_count,
        "blockUpdated": block_result.modified_count,
        "blockId": data.blockId,
        "inactive": data.inactive
    }
