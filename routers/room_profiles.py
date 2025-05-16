from fastapi import APIRouter
from pymongo import MongoClient
from collections import defaultdict
from statistics import mean, stdev
from datetime import datetime
import os

from utils.time_utils import to_cst, minutes_within_block_window

router = APIRouter()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
cases_collection = db["cases"]
room_profiles_collection = db["room_profiles"]

# def get_week_of_month(date):
#     first_day = date.replace(day=1)
#     return ((date.day + first_day.weekday() - 1) // 7) + 1

def get_week_of_month(date: datetime) -> int:
    first_day = date.replace(day=1)
    first_day_dow = first_day.weekday()  # Monday=0
    offset = date.day + first_day_dow - 1
    return (offset // 7) + 1

@router.get("/rooms/profiles")
def generate_room_profiles(start_date: str, end_date: str):
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    print(f"📊 Generating room profiles from {start} to {end}")
    cases = list(cases_collection.find({
        "procedureDate": {"$gte": start, "$lte": end}
    }))
    print(f"📦 {len(cases)} cases found")

    room_profiles = {}

    for case in cases:
        room = case.get("room")
        procedure_date = case.get("procedureDate")
        duration = int(case.get("duration", 0))

        start_raw = case.get("startTime")
        end_raw = case.get("endTime")
        print("procedure_date", procedure_date)
        if not room or not procedure_date or not start_raw or not end_raw:
            continue

        if isinstance(procedure_date, dict):
            procedure_date = datetime.fromisoformat(procedure_date["$date"])

        weekday_key = f"{procedure_date.weekday()}-{get_week_of_month(procedure_date)}"

        if room not in room_profiles:
            room_profiles[room] = {
                "room": room,
                "profileMonth": start.strftime("%Y-%m"),
                "usageByDayAndWeek": defaultdict(lambda: {
                    "durations": [],
                    "utilizationMinutes": 0,
                    "surgeonCounts": defaultdict(int),
                    "procedureCounts": defaultdict(int)
                })
            }

        bucket = room_profiles[room]["usageByDayAndWeek"][weekday_key]

        # Add total case duration
        bucket["durations"].append(duration)

        # Add utilization time (converted to CST and clipped to 7:00–15:30)
        start_cst = to_cst(start_raw)
        end_cst = to_cst(end_raw)
        util_minutes = minutes_within_block_window(start_cst, end_cst)
        bucket["utilizationMinutes"] += util_minutes

        for proc in case.get("procedures", []):
            if not proc.get("primary"):
                continue

            npi = proc.get("primaryNpi")
            pid = proc.get("procedureId")

            if npi:
                bucket["surgeonCounts"][npi] += 1
            if pid:
                bucket["procedureCounts"][pid] += 1

    print(f"🧠 Building stats for {len(room_profiles)} rooms")

    results = []

    for profile in room_profiles.values():
        finalized = {
            "room": profile["room"],
            "profileMonth": profile["profileMonth"],
            "usageByDayAndWeek": {}
        }

        for key, data in profile["usageByDayAndWeek"].items():
            usage_entry = {}
            durations = data["durations"]
            total_cases = len(durations)

            if total_cases > 1:
                usage_entry["meanMinutes"] = round(mean(durations), 2)
                usage_entry["stdMinutes"] = round(stdev(durations), 2)

            usage_entry["surgeonFrequency"] = {
                npi: {
                    "count": count,
                    "relative": round(count / total_cases, 3)
                }
                for npi, count in data["surgeonCounts"].items()
            }

            usage_entry["procedureFrequency"] = {
                pid: {
                    "count": count,
                    "relative": round(count / total_cases, 3)
                }
                for pid, count in data["procedureCounts"].items()
            }

            # Add utilization rate (based on 510 available minutes)
            usage_entry["utilizationRate"] = round(data["utilizationMinutes"] / (total_cases * 510), 3)

            finalized["usageByDayAndWeek"][key] = usage_entry

        room_profiles_collection.replace_one({"room": finalized["room"], "profileMonth": finalized["profileMonth"]},
            finalized, upsert=True)

        print(f"✅ Profile saved for room {profile['room']}")
        results.append(finalized)

    print(f"🎯 {len(results)} room profiles inserted")
    return {"profilesCreated": len(results)}

room_profiles_router = router
