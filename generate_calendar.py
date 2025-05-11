from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
import pytz
import os

# Load environment variables from .env
load_dotenv()

# Get MongoDB URI from environment
MONGO_URI = os.getenv("MONGODB_URI")
if not MONGO_URI:
    raise EnvironmentError("MONGODB_URI not found in .env file")

client = MongoClient(MONGO_URI)
db = client["surgical-analytics"]

cases_collection = db["cases"]
calendar_collection = db["calendar"]

def to_cst(dt_raw) -> datetime:
    """Convert UTC datetime to US Central Time."""
    if isinstance(dt_raw, str):
        dt_utc = datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).astimezone(pytz.UTC)
    elif isinstance(dt_raw, datetime):
        dt_utc = dt_raw.astimezone(pytz.UTC)
    else:
        raise TypeError(f"Unsupported type: {type(dt_raw)}")
    return dt_utc.astimezone(pytz.timezone("US/Central"))

grouped_data = defaultdict(lambda: {
    "procedures": [],
    "blocks": []
})

print("🔍 Fetching primary procedures...")
cursor = cases_collection.find({
    "procedures.primary": True,
    "startTime": {"$exists": True},
    "endTime": {"$exists": True}
})

total = 0

for case in cursor:
    hospitalId = case.get("hospitalId")
    unit = case.get("unit")
    room = case.get("room")
    fin = case.get("fin")
    createdAt = case.get("createdAt")

    for proc in case.get("procedures", []):
        if not proc.get("primary"):
            continue

        start_cst = to_cst(case["startTime"])
        end_cst = to_cst(case["endTime"])
        duration = int((end_cst - start_cst).total_seconds() / 60)
        date_key = start_cst.strftime("%Y-%m-%d")

        key = (date_key, hospitalId, unit, room)
        grouped_data[key]["procedures"].append({
            "procedureId": proc.get("procedureId"),
            "procedureName": proc.get("procedureName"),
            "primaryNpi": proc.get("primaryNpi"),
            "procedureLabel": proc.get("procedureLabel"),
            "providerName": proc.get("providerName"),
            "startTime": start_cst.isoformat(),
            "endTime": end_cst.isoformat(),
            "duration": duration,
            "fin": fin,
            "createdAt": createdAt
        })
        total += 1

print("🧹 Clearing old calendar data...")
calendar_collection.delete_many({})

print("📝 Inserting calendar data...")
for (date, hospitalId, unit, room), data in grouped_data.items():
    calendar_collection.insert_one({
        "date": date,
        "hospitalId": hospitalId,
        "unit": unit,
        "room": room,
        "procedures": data["procedures"],
        "blocks": []
    })

print(f"✅ Done. {len(grouped_data)} calendar entries created for {total} procedures.")
