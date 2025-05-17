from pymongo import MongoClient
from datetime import datetime, timedelta
from dateutil import parser
import pytz
import os
import sys

# Connect to MongoDB
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]
cases_collection = db["cases"]

# Helpers
def to_cst_safe(dt):
    """Convert datetime or string to US/Central timezone-aware datetime."""
    cst = pytz.timezone("US/Central")
    if isinstance(dt, str):
        dt = parser.isoparse(dt)
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(cst)

def merge_intervals(intervals):
    """Merge overlapping time intervals."""
    intervals.sort()
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged

# Main Function
def generate_block_utilization(start_str, end_str, test_npi=None):
    start_date = datetime.fromisoformat(start_str).date()
    end_date = datetime.fromisoformat(end_str).date()
    print(f"📅 Calculating block utilization from {start_date} to {end_date}")

    # Query calendar docs in range
    calendar_docs = list(calendar_collection.find({
        "date": {"$gte": start_str, "$lte": end_str}
    }))

    for doc in calendar_docs:
        calendar_id = str(doc["_id"])
        date_str = doc.get("date")
        room = doc.get("room")
        hospitalId = doc.get("hospitalId")
        unit = doc.get("unit")
        blocks = doc.get("blocks", [])

        for i, block in enumerate(blocks):
            npi = block.get("npi") or block.get("primaryNpi")
            if not npi or block.get("inactive") == True:
                print(f"⚠️ Skipping block {i} in doc {calendar_id} due to missing NPI or inactive")
                continue
            if test_npi and npi != test_npi:
                continue

            block_start = parser.isoparse(block["startTime"])
            block_end = parser.isoparse(block["endTime"])
            block_minutes = block.get("duration", 0)

            print(f"\n📅 {date_str} | Room: {room} | Block: {block_start.strftime('%H:%M')}–{block_end.strftime('%H:%M')} | NPI: {npi}")

            # Get matching cases
            try:
                matching_cases = list(cases_collection.find({
                    "procedureDate": {
                        "$gte": datetime.fromisoformat(f"{date_str}T00:00:00"),
                        "$lt": datetime.fromisoformat(f"{date_str}T23:59:59")
                    },
                    "procedures": {
                        "$elemMatch": {
                            "primary": True,
                            "primaryNpi": npi
                        }
                    }
                }))
            except Exception as e:
                print(f"❌ Error querying cases for doc {calendar_id}: {e}")
                continue

            print(f"📂 Found {len(matching_cases)} matching cases")

            overlaps_anywhere = []
            overlaps_in_room = []

            for case in matching_cases:
                try:
                    case_start = to_cst_safe(case["startTime"])
                    case_end = to_cst_safe(case["endTime"])
                    print(f"   📌 Procedure from {case_start.strftime('%H:%M')} to {case_end.strftime('%H:%M')} | Room: {case.get('room')}")
                except Exception as e:
                    print(f"❌ Error parsing procedure time in doc {calendar_id}: {e}")
                    continue

                # Clip to block window
                overlap_start = max(case_start, block_start)
                overlap_end = min(case_end, block_end)

                if overlap_end <= overlap_start:
                    print("      ⛔️ No overlap with block")
                    continue

                overlaps_anywhere.append((overlap_start, overlap_end))
                if case.get("room") == room:
                    overlaps_in_room.append((overlap_start, overlap_end))

            # Merge and calculate minutes
            merged_in_room = merge_intervals(overlaps_in_room)
            merged_anywhere = merge_intervals(overlaps_anywhere)
            minutes_in_room = sum(int((e - s).total_seconds() / 60) for s, e in merged_in_room)
            minutes_anywhere = sum(int((e - s).total_seconds() / 60) for s, e in merged_anywhere)

            block["inRoomUtilization"] = round(minutes_in_room / block_minutes, 3) if block_minutes else 0
            block["anywhereUtilization"] = round(minutes_anywhere / block_minutes, 3) if block_minutes else 0

            print(f"📊 In-room: {minutes_in_room} mins, Anywhere: {minutes_anywhere} mins")
            print(f"📈 Utilization → In-room: {block['inRoomUtilization']*100:.1f}%, Anywhere: {block['anywhereUtilization']*100:.1f}%")

        # Update doc
        calendar_collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"blocks": blocks}}
        )

# CLI
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_block_utilization.py 2025-04-01 2025-04-30 [optional_npi]")
        sys.exit(1)

    start = sys.argv[1]
    end = sys.argv[2]
    test_npi = sys.argv[3] if len(sys.argv) > 3 else None
    generate_block_utilization(start, end, test_npi)
