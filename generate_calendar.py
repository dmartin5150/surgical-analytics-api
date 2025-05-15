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

# Setup CST boundaries for May 2024
cst_tz = pytz.timezone("US/Central")
MAY_START_CST = cst_tz.localize(datetime(2024, 5, 1, 0, 0))
MAY_END_CST = cst_tz.localize(datetime(2024, 6, 1, 0, 0))

# Convert to UTC for querying MongoDB
MAY_START_UTC = MAY_START_CST.astimezone(pytz.UTC)
MAY_END_UTC = MAY_END_CST.astimezone(pytz.UTC)

grouped_data = defaultdict(lambda: {
    "procedures": [],
    "blocks": []
})

print("🔍 Fetching primary procedures for May 2024...")
cursor = cases_collection.find({
    "procedures.primary": True,
    "startTime": {"$gte": MAY_START_UTC, "$lt": MAY_END_UTC},
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

print("📝 Upserting calendar data...")
for (date, hospitalId, unit, room), data in grouped_data.items():
    # Define the day boundaries in CST
    day_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=7, minute=0, tzinfo=cst_tz)
    day_end = day_start.replace(hour=15, minute=30)
    available_minutes = 510

    # Clip procedures to surgical day and collect intervals
    intervals = []
    for proc in data["procedures"]:
        proc_start = to_cst(proc["startTime"])
        proc_end = to_cst(proc["endTime"])

        clipped_start = max(proc_start, day_start)
        clipped_end = min(proc_end, day_end)

        if clipped_end > clipped_start:
            start_min = int((clipped_start - day_start).total_seconds() / 60)
            end_min = int((clipped_end - day_start).total_seconds() / 60)
            intervals.append((start_min, end_min))

    # Merge overlapping intervals
    intervals.sort()
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    # Calculate total unique minutes used
    utilization_minutes = sum(end - start for start, end in merged)
    utilization_rate = round(utilization_minutes / available_minutes, 3)

    # Upsert the document
    calendar_collection.update_one(
        {
            "date": date,
            "hospitalId": hospitalId,
            "unit": unit,
            "room": room
        },
        {
            "$set": {
                "procedures": data["procedures"],
                "blocks": [],
                "utilizationMinutes": utilization_minutes,
                "availableMinutes": available_minutes,
                "utilizationRate": utilization_rate
            }
        },
        upsert=True
    )

print(f"✅ Done. {len(grouped_data)} calendar entries processed for {total} procedures.")
