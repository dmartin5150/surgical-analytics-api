from fastapi import APIRouter
from pymongo import MongoClient
from collections import defaultdict
from statistics import mean, stdev
from datetime import datetime
import os

router = APIRouter()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
cases_collection = db["cases"]
room_profiles_collection = db["room_profiles"]

def get_week_of_month(date):
    first_day = date.replace(day=1)
    return ((date.day + first_day.weekday() - 1) // 7) + 1

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

        if not room or not procedure_date:
            continue

        if isinstance(procedure_date, dict):
            procedure_date = datetime.fromisoformat(procedure_date["$date"])

        key = f"{procedure_date.weekday()}-{get_week_of_month(procedure_date)}"

        if room not in room_profiles:
            room_profiles[room] = {
                "room": room,
                "profileMonth": start.strftime("%Y-%m"),
                "usageByDayAndWeek": defaultdict(lambda: {
                    "durations": [],
                    "surgeonCounts": defaultdict(int),
                    "procedureCounts": defaultdict(int)
                })
            }

        bucket = room_profiles[room]["usageByDayAndWeek"][key]
        bucket["durations"].append(duration)

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

    # Finalize and insert
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

            if len(durations) > 1:
                usage_entry["meanMinutes"] = round(mean(durations), 2)
                usage_entry["stdMinutes"] = round(stdev(durations), 2)

            total_cases = len(durations)

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

            finalized["usageByDayAndWeek"][key] = usage_entry

        room_profiles_collection.insert_one(finalized)
        print(f"✅ Profile saved for room {profile['room']}")
        results.append(finalized)

    print(f"🎯 {len(results)} room profiles inserted")
    return {"profilesCreated": len(results)}

room_profiles_router = router
