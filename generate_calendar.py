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

def to_cst(dt_raw) -> datetime:
    cst = pytz.timezone("US/Central")

    if isinstance(dt_raw, str):
        dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
    elif isinstance(dt_raw, datetime):
        dt = dt_raw
    else:
        raise TypeError(f"Unsupported type: {type(dt_raw)}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)

    return dt.astimezone(cst)

def get_week_of_month(date: datetime) -> int:
    first_day = date.replace(day=1)
    adjusted_dom = date.day + first_day.weekday()
    return ((adjusted_dom - 1) // 7) + 1

def merge_intervals(intervals):
    intervals.sort()
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged

# Date window
cst_tz = pytz.timezone("US/Central")
APRIL_START_CST = cst_tz.localize(datetime(2025, 4, 1, 0, 0))
APRIL_END_CST = cst_tz.localize(datetime(2025, 5, 1, 0, 0))
APRIL_START_UTC = APRIL_START_CST.astimezone(pytz.UTC)
APRIL_END_UTC = APRIL_END_CST.astimezone(pytz.UTC)

grouped_data = defaultdict(lambda: {"procedures": [], "blocks": []})

# 🔢 Pre-compute total rooms per hospitalId + unit
room_sets = defaultdict(set)
for case in cases_collection.find({}, {"hospitalId": 1, "unit": 1, "room": 1}):
    hosp = case.get("hospitalId")
    unit = case.get("unit")
    room = case.get("room")
    if hosp and unit and room:
        room_sets[(hosp, unit)].add(room)

room_counts = {key: len(rooms) for key, rooms in room_sets.items()}

print("🔍 Fetching procedures...")
cursor = cases_collection.find({
    "procedures.primary": True,
    "startTime": {"$gte": APRIL_START_UTC, "$lt": APRIL_END_UTC},
    "endTime": {"$exists": True}
})

total = 0
all_procs_by_surgeon_day = defaultdict(list)

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

        proc_doc = {
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
        }

        grouped_data[key]["procedures"].append(proc_doc)
        if proc.get("primaryNpi"):
            all_procs_by_surgeon_day[(date_key, proc["primaryNpi"])].append({
                "start": start_cst,
                "end": end_cst,
                "room": room
            })

        total += 1

print("📦 Fetching blocks...")
blocks_cursor = blocks_collection.find({})

for block in blocks_cursor:
    if not block.get("frequencies") or not block.get("hospital") or not block.get("room") or not block.get("unit"):
        continue

    hospitalId = f"W1-{block['hospital']}"
    unit = block["unit"]
    room = block["room"]
    inactive = block.get("inactive", False)

    owner = block.get("owner", [{}])[0]
    npi = owner.get("npis", [None])[0]
    provider_name = owner.get("providerNames", [None])[0]
    if not npi:
        continue

    for freq in block["frequencies"]:
        dow = freq.get("dowApplied") - 1
        weeks = freq.get("weeksOfMonth", [])
        block_start_time = freq.get("blockStartTime")
        block_end_time = freq.get("blockEndTime")
        date_start = to_cst(freq.get("blockStartDate"))
        date_end = to_cst(freq.get("blockEndDate"))

        current = APRIL_START_CST
        while current < APRIL_END_CST:
            date_key = current.strftime("%Y-%m-%d")
            if (
                current.weekday() == dow and
                get_week_of_month(current) in weeks and
                date_start.date() <= current.date() <= date_end.date()
            ):
                day_start = datetime.combine(current.date(), block_start_time.time()).replace(tzinfo=cst_tz)
                day_end = datetime.combine(current.date(), block_end_time.time()).replace(tzinfo=cst_tz)
                block_minutes = int((day_end - day_start).total_seconds() / 60)

                all_procs = all_procs_by_surgeon_day.get((date_key, npi), [])

                total_intervals = [
                    (max(p["start"], day_start), min(p["end"], day_end))
                    for p in all_procs if min(p["end"], day_end) > max(p["start"], day_start)
                ]
                total_minutes = sum(
                    (e - s).total_seconds() // 60 for s, e in merge_intervals(total_intervals)
                )

                in_room_intervals = [
                    (max(p["start"], day_start), min(p["end"], day_end))
                    for p in all_procs if p["room"] == room and min(p["end"], day_end) > max(p["start"], day_start)
                ]
                in_room_minutes = sum(
                    (e - s).total_seconds() // 60 for s, e in merge_intervals(in_room_intervals)
                )

                grouped_data[(date_key, hospitalId, unit, room)]["blocks"].append({
                    "blockId": str(block["_id"]),
                    "startTime": day_start.isoformat(),
                    "endTime": day_end.isoformat(),
                    "duration": block_minutes,
                    "primaryNpi": npi,
                    "providerName": provider_name,
                    "inactive": inactive,
                    "inRoomUtilization": round(in_room_minutes / block_minutes, 3) if block_minutes else 0.0,
                    "totalUtilization": round(total_minutes / block_minutes, 3) if block_minutes else 0.0
                })
            current += timedelta(days=1)

print("📝 Upserting calendar documents...")
for (date, hospitalId, unit, room), data in grouped_data.items():
    day_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=7, minute=0, tzinfo=cst_tz)
    day_end = day_start.replace(hour=15, minute=30)

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

    merged = merge_intervals(intervals)
    utilization_minutes = sum(end - start for start, end in merged)
    utilization_rate = round(utilization_minutes / 510, 3)

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
                "blocks": data["blocks"],
                "utilizationMinutes": utilization_minutes,
                "availableMinutes": 510,
                "utilizationRate": utilization_rate,
                "totalRooms": room_counts.get((hospitalId, unit), 0)
            }
        },
        upsert=True
    )

print(f"✅ Done. {len(grouped_data)} calendar entries processed with procedures and blocks.")
