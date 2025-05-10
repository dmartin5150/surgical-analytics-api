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

    cases = list(cases_collection.find({
        "procedureDate": {"$gte": start, "$lte": end}
    }))

    provider_profiles = {}

    for case in cases:
        procedure_date = case.get("procedureDate")
        date_created = case.get("dateCreated")

        if not (procedure_date and date_created):
            continue

        procedure_date = datetime.fromisoformat(
            procedure_date["$date"] if isinstance(procedure_date, dict) else procedure_date
        )
        date_created = datetime.fromisoformat(
            date_created["$date"] if isinstance(date_created, dict) else date_created
        )


        if not (procedure_date and date_created):
            continue

        procedure_date = procedure_date["$date"] if isinstance(procedure_date, dict) else procedure_date
        date_created = date_created["$date"] if isinstance(date_created, dict) else date_created

        lead_time = (datetime.fromisoformat(procedure_date) - datetime.fromisoformat(date_created)).days
        duration = int(case.get("duration", 0))

        for proc in case.get("procedures", []):
            if not proc.get("primary"):
                continue

            npi = proc["primaryNpi"]
            pid = proc["procedureId"]
            name = proc.get("providerName", "Unknown")

            if npi not in provider_profiles:
                provider_profiles[npi] = {
                    "surgeonId": npi,
                    "providerName": name,
                    "leadTimeByProcedure": defaultdict(list),
                    "timeUsageByDayAndWeek": defaultdict(list)
                }

            # Lead time per procedure
            provider_profiles[npi]["leadTimeByProcedure"][pid].append(lead_time)

            # Time usage per (weekday, weekOfMonth)
            dt = datetime.fromisoformat(procedure_date)
            key = f"{dt.weekday()}-{get_week_of_month(dt)}"
            provider_profiles[npi]["timeUsageByDayAndWeek"][key].append(duration)

    # Convert to stats and save
    results = []

    for profile in provider_profiles.values():
        stat_profile = {
            "surgeonId": profile["surgeonId"],
            "providerName": profile["providerName"],
            "profileMonth": start.strftime("%Y-%m"),
            "leadTimeByProcedure": {},
            "timeUsageByDayAndWeek": {}
        }

        for pid, times in profile["leadTimeByProcedure"].items():
            if len(times) > 1:
                stat_profile["leadTimeByProcedure"][pid] = {
                    "mean": round(mean(times), 2),
                    "std": round(stdev(times), 2)
                }

        for key, mins in profile["timeUsageByDayAndWeek"].items():
            if len(mins) > 1:
                stat_profile["timeUsageByDayAndWeek"][key] = {
                    "meanMinutes": round(mean(mins), 2),
                    "stdMinutes": round(stdev(mins), 2)
                }

        # Save to DB
        profiles_collection.insert_one(stat_profile)
        results.append(stat_profile)

    return {"profilesCreated": len(results)}
surgeon_profiles_router = router
