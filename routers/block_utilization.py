from fastapi import APIRouter
from pymongo import MongoClient
from datetime import datetime, timedelta
from utils.time_utils import to_cst, minutes_within_block_window
import os

router = APIRouter()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
block_collection = db["block"]
cases_collection = db["cases"]
util_collection = db["block_utilization"]

def get_week_of_month(date: datetime) -> int:
    return ((date.day + date.replace(day=1).weekday() - 1) // 7) + 1

def daterange(start_date, end_date):
    delta = end_date - start_date
    for i in range(delta.days + 1):
        yield start_date + timedelta(days=i)

@router.get("/blocks/utilization")
def generate_block_utilization(start_date: str, end_date: str):
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    print(f"📅 Calculating block utilization from {start.date()} to {end.date()}")

    blocks = list(block_collection.find({"type": "Surgeon"}))
    print(f"🔍 {len(blocks)} surgeon blocks loaded")

    total_inserted = 0

    for block in blocks:
        block_start = datetime.fromisoformat(block["blockStartDate"].replace("Z", "+00:00"))
        block_end = datetime.fromisoformat(block["blockEndDate"].replace("Z", "+00:00"))
        room = block.get("room")
        owner_npis = block.get("owner", {}).get("npis", [])

        for freq in block.get("frequencies", []):
            dow = freq.get("dowApplied")  # 0 = Sunday
            weeks = freq.get("weeksOfMonth", [])

            # Extract block start/end times (ignore the date portion)
            block_start_time = to_cst(freq["blockStartTime"]).time()
            block_end_time = to_cst(freq["blockEndTime"]).time()
            block_duration = int((datetime.combine(datetime.today(), block_end_time) - datetime.combine(datetime.today(), block_start_time)).total_seconds() / 60)

            for day in daterange(start, end):
                if not (block_start.date() <= day.date() <= block_end.date()):
                    continue
                if day.weekday() != dow:
                    continue
                if get_week_of_month(day) not in weeks:
                    continue

                # Define actual block datetime range (in CST)
                block_start_cst = datetime.combine(day.date(), block_start_time).astimezone(to_cst("2024-01-01T00:00:00Z").tzinfo)
                block_end_cst = datetime.combine(day.date(), block_end_time).astimezone(to_cst("2024-01-01T00:00:00Z").tzinfo)

                # Fetch all cases on that day with overlapping time
                day_start = datetime.combine(day.date(), datetime.min.time())
                day_end = datetime.combine(day.date(), datetime.max.time())

                matching_cases = list(cases_collection.find({
                    "procedureDate": {
                        "$gte": day_start,
                        "$lte": day_end
                    },
                    "procedures.primary": True
                }))

                in_room_minutes = 0
                anywhere_minutes = 0

                for case in matching_cases:
                    for proc in case.get("procedures", []):
                        if not proc.get("primary") or proc.get("primaryNpi") not in owner_npis:
                            continue

                        start = to_cst(case.get("startTime"))
                        end = to_cst(case.get("endTime"))

                        overlap_minutes = minutes_within_block_window(start, end, block_start_cst, block_end_cst)

                        anywhere_minutes += overlap_minutes
                        if case.get("room") == room:
                            in_room_minutes += overlap_minutes

                utilization_doc = {
                    "room": room,
                    "date": day.strftime("%Y-%m-%d"),
                    "surgeons": owner_npis,
                    "dow": dow,
                    "weekOfMonth": get_week_of_month(day),
                    "blockStartTime": block_start_time.strftime("%H:%M"),
                    "blockEndTime": block_end_time.strftime("%H:%M"),
                    "blockMinutes": block_duration,
                    "usedInRoom": in_room_minutes,
                    "usedAnywhere": anywhere_minutes,
                    "inRoomUtilization": round(in_room_minutes / block_duration, 3) if block_duration else 0,
                    "anywhereUtilization": round(anywhere_minutes / block_duration, 3) if block_duration else 0
                }

                util_collection.replace_one(
                    {"room": room, "date": utilization_doc["date"], "surgeons": owner_npis},
                    utilization_doc,
                    upsert=True
                )
                total_inserted += 1

    print(f"✅ {total_inserted} block utilization records inserted or updated.")
    return {"recordsWritten": total_inserted}

block_utilization_router = router
