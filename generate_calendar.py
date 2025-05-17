from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import pytz
import os

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
if not MONGO_URI:
    raise EnvironmentError("MONGODB_URI not found in .env file")

client = MongoClient(MONGO_URI)
db = client["surgical-analytics"]
cases_collection = db["cases"]
blocks_collection = db["block"]
calendar_collection = db["calendar"]

# Constants
cst_tz = pytz.timezone("US/Central")
APRIL_START = cst_tz.localize(datetime(2025, 4, 1))
MAY_START = cst_tz.localize(datetime(2025, 5, 1))

# Precompute total rooms per (hospitalId, unit)
room_sets = defaultdict(set)
for case in cases_collection.find({}, {"hospitalId": 1, "unit": 1, "room": 1}):
    hosp = case.get("hospitalId")
    unit = case.get("unit")
    room = case.get("room")
    if hosp and unit and room:
        room_sets[(hosp, unit)].add(room)

room_counts = {key: len(rooms) for key, rooms in room_sets.items()}

# Build grouped structure
grouped_data = defaultdict(lambda: {"procedures": [], "blocks": []})

print("🔍 Fetching procedures...")
cursor = cases_collection.find({
    "procedures.primary": True,
    "startTime": {"$gte": APRIL_START, "$lt": MAY_START},
    "endTime": {"$exists": True}
})

for case in cursor:
    hospitalId = case.get("hospitalId")
    unit = case.get("unit")
    room = case.get("room")
    date = case.get("startTime")

    if not (hospitalId and unit and room and date):
        continue

    date_key = date.astimezone(cst_tz).strftime("%Y-%m-%d")
    key = (date_key, hospitalId, unit, room)

    for proc in case.get("procedures", []):
        if not proc.get("primary"):
            continue

        # Prefer frequency.duration if available
        duration = 0
        if proc.get("frequencies"):
            for freq in proc["frequencies"]:
                duration = max(duration, freq.get("duration", 0))

        if duration == 0:
            # Fallback: compute from case start and end time
            start = case.get("startTime")
            end = case.get("endTime")
            if start and end:
                duration = int((end - start).total_seconds() / 60)

        # Always store startTime and endTime from the case level
        start = case.get("startTime")
        end = case.get("endTime")

        grouped_data[key]["procedures"].append({
            **proc,
            "duration": duration,
            "startTime": start,
            "endTime": end
        })

print("📅 Calculating utilization and updating calendar...")
for (date, hospitalId, unit, room), data in grouped_data.items():
    procedures = data["procedures"]
    total_minutes = sum(proc.get("duration", 0) for proc in procedures)
    utilization_rate = round(total_minutes / 510, 3)

    calendar_collection.update_one(
        {"date": date, "hospitalId": hospitalId, "unit": unit, "room": room},
        {"$set": {
            "procedures": procedures,
            "utilizationMinutes": total_minutes,
            "availableMinutes": 510,
            "utilizationRate": utilization_rate,
            "totalRooms": room_counts.get((hospitalId, unit), 0)
        }},
        upsert=True
    )

print(f"✅ Done. {len(grouped_data)} calendar entries processed.")
