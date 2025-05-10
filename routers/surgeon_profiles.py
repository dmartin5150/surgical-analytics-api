from fastapi import APIRouter
from pymongo import MongoClient
from statistics import mean, stdev
from collections import defaultdict
from datetime import datetime
import os

router = APIRouter()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
cases_collection = db["cases"]
profiles_collection = db["surgeon_profiles"]

def get_week_of_month(date):
    first_day = date.replace(day=1)
    return ((date.day + first_day.weekday() - 1) // 7) + 1

@router.get("/surgeons/profiles")
def generate_profiles(start_date: str, end_date: str):
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    print(f"⏳ Generating profiles from {start} to {end}")
    cases = list(cases_collection.find({
        "procedureDate": {"$gte": start, "$lte": end}
    }))
    print(f"📦 {len(cases)} cases found in date range")

    provider_profiles = {}

    for case in cases:
        procedure_date = case.get("procedureDate")
        date_created = case.get("dateCreated")

        if not (procedure_date and date_created):
            print("⚠️ Skipping case without procedureDate or dateCreated")
            continue

        if isinstance(procedure_date, dict):
            procedure_date = datetime.fromisoformat(procedure_date["$date"])
        if isinstance(date_created, dict):
            date_created = datetime.fromisoformat(date_created["$date"])

        lead_time = (procedure_date - date_created).days
        duration = int(case.get("duration", 0))

        for proc in case.get("procedures", []):
            if not proc.get("primary"):
                continue

            npi = proc.get("primaryNpi")
            pid = proc.get("procedureId")
            name = proc.get("providerName", "Unknown")

            if not (npi and pid):
                print(f"⚠️ Skipping procedure with missing fields in case {case.get('caseNumber')}")
                continue

            if npi not in provider_profiles:
                print(f"👤 New surgeon found: {npi} ({name})")
                provider_profiles[npi] = {
                    "surgeonId": npi,
                    "providerName": name,
                    "leadTimeByProcedure": defaultdict(lambda: {"leadTimes": [], "durations": []}),
                    "timeUsageByDayAndWeek": defaultdict(list),
                    "totalProcedureCount": 0
                }

            provider_profiles[npi]["leadTimeByProcedure"][pid]["leadTimes"].append(lead_time)
            provider_profiles[npi]["leadTimeByProcedure"][pid]["durations"].append(duration)
            provider_profiles[npi]["totalProcedureCount"] += 1

            key = f"{procedure_date.weekday()}-{get_week_of_month(procedure_date)}"
            provider_profiles[npi]["timeUsageByDayAndWeek"][key].append(duration)

    print(f"🧠 Profiles gathered for {len(provider_profiles)} surgeons")

    results = []

    for profile in provider_profiles.values():
        stat_profile = {
            "surgeonId": profile["surgeonId"],
            "providerName": profile["providerName"],
            "profileMonth": start.strftime("%Y-%m"),
            "leadTimeByProcedure": {},
            "timeUsageByDayAndWeek": {}
        }

        total = profile["totalProcedureCount"]

        for pid, data in profile["leadTimeByProcedure"].items():
            if len(data["leadTimes"]) > 1:
                stat_profile["leadTimeByProcedure"][pid] = {
                    "mean": round(mean(data["leadTimes"]), 2),
                    "std": round(stdev(data["leadTimes"]), 2),
                    "frequency": len(data["leadTimes"]),
                    "relativeFrequency": round(len(data["leadTimes"]) / total, 3),
                    "avgDuration": round(mean(data["durations"]), 2)
                }

        for key, mins in profile["timeUsageByDayAndWeek"].items():
            if len(mins) > 1:
                stat_profile["timeUsageByDayAndWeek"][key] = {
                    "meanMinutes": round(mean(mins), 2),
                    "stdMinutes": round(stdev(mins), 2)
                }

        if stat_profile["leadTimeByProcedure"] or stat_profile["timeUsageByDayAndWeek"]:
            profiles_collection.insert_one(stat_profile)
            print(f"✅ Inserted profile for {profile['surgeonId']}")
            results.append(stat_profile)
        else:
            print(f"⚠️ Skipping profile for {profile['surgeonId']} — no valid stats")

    print(f"🎯 {len(results)} profiles inserted")
    return {"profilesCreated": len(results)}

surgeon_profiles_router = router
