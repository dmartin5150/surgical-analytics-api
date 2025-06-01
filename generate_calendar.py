from pymongo import MongoClient
from datetime import datetime
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
calendar_collection = db["calendar"]

# Constants
cst_tz = pytz.timezone("US/Central")
APRIL_START = datetime(2025, 4, 1, tzinfo=pytz.UTC)
MAY_START = datetime(2025, 5, 1, tzinfo=pytz.UTC)

# Precompute total rooms per (hospitalId, unit)
room_sets = defaultdict(set)
for case in cases_collection.find({}, {"hospitalId": 1, "unit": 1, "room": 1}):
    hosp = case.get("hospitalId")
    unit = case.get("unit")
    room = case.get("room")
    if hosp and unit and room:
        room_sets[(hosp, unit)].add(room)

room_counts = {key: len(rooms) for key, rooms in room_sets.items()}

# Group cases
grouped_data = defaultdict(lambda: {"procedures": []})

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
    start = case.get("startTime")

    if not (hospitalId and unit and room and start):
        continue

    date_key = start.astimezone(cst_tz).strftime("%Y-%m-%d")
    key = (date_key, hospitalId, unit, room)

    for proc in case.get("procedures", []):
        if not proc.get("primary"):
            continue

        start_utc = case.get("startTime").replace(tzinfo=pytz.UTC)
        end_utc = case.get("endTime").replace(tzinfo=pytz.UTC)

        duration = int((end_utc - start_utc).total_seconds() / 60)

        grouped_data[key]["procedures"].append({
            **proc,
            "duration": duration,
            "startTime": start_utc,
            "endTime": end_utc
        })

print("📅 Calculating utilization and updating calendar...")
for (date, hospitalId, unit, room), data in grouped_data.items():
    procedures = data["procedures"]

    prime_time_start = cst_tz.localize(datetime.strptime(f"{date} 07:00", "%Y-%m-%d %H:%M"))
    prime_time_end = cst_tz.localize(datetime.strptime(f"{date} 15:30", "%Y-%m-%d %H:%M"))

    clipped_ranges = []
    for proc in procedures:
        start_cst = proc["startTime"].astimezone(cst_tz)
        end_cst = proc["endTime"].astimezone(cst_tz)

        latest_start = max(start_cst, prime_time_start)
        earliest_end = min(end_cst, prime_time_end)

        if latest_start < earliest_end:
            clipped_ranges.append((latest_start, earliest_end))

    clipped_ranges.sort()
    merged_ranges = []
    for start, end in clipped_ranges:
        if not merged_ranges or start > merged_ranges[-1][1]:
            merged_ranges.append((start, end))
        else:
            merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], end))

    total_minutes = sum(int((end - start).total_seconds() / 60) for start, end in merged_ranges)
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
