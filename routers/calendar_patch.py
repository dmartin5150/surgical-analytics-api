from fastapi import APIRouter
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]

class BlockUpdateRequest(BaseModel):
    blockId: str
    inactive: bool

@router.patch("/calendar/blocks/inactive")
def patch_block_inactive(data: BlockUpdateRequest):
    result = calendar_collection.update_one(
        {"blocks.blockId": data.blockId},
        {"$set": {"blocks.$.inactive": data.inactive}}
    )

    if result.modified_count == 0:
        return {"status": "no changes made", "blockId": data.blockId}

    return {
        "status": "updated",
        "blockId": data.blockId,
        "inactive": data.inactive
    }
