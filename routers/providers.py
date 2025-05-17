from fastapi import APIRouter
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

router = APIRouter()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
providers_collection = db["providers"]

@router.get("/providers/list")
def get_providers():
    """
    Returns a list of all unique primary providers (NPI + name).
    """
    return list(providers_collection.find({}, {"_id": 0}))
