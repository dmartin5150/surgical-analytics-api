from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
calendar_collection = db["calendar"]
block_collection = db["block"]

def get_week_of_month(date: datetime) -> int:
    first_day = date.replace(day=1)
    adjusted_dom = date.day + first_day.weekday()
    return ((adjusted_dom - 1) // 7) + 1

def has_overlap(blocks):
    def parse_time(t): return datetime.strptime(t, "%Y-%m-%dT%H:%M:%S-05:00")
    sorted_blocks = sorted(blocks, key=lambda b: parse_time(b["startTime"]))
    for i in range(len(sorted_blocks) - 1):
        end_current = parse_time(sorted_blocks[i]["endTime"])
        start_next = parse_time(sorted_blocks[i + 1]["startTime"])
        if start_next < end_current:
            return True
    return False

april_start = datetime(2025, 4, 1)
april_end = datetime(2025, 5, 31)

calendar_docs = list(calendar_collection.find({
    "date": {"$gte": april_start.strftime("%Y-%m-%d"), "$lte": april_end.strftime("%Y-%m-%d")}
}))

blocks = list(block_collection.find({"type": "Surgeon"}))

for doc in calendar_docs:
    date_str = doc["date"]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    dow = date_obj.weekday()
    wom = get_week_of_month(date_obj)
    unit = doc.get("unit")
    room = doc.get("room")

    matching_blocks = []

    for block in blocks:
        if block.get("unit") != unit or block.get("room") != room:
            continue

        owner_list = block.get("owner", [])
        if not owner_list or not isinstance(owner_list, list):
            continue

        owner = owner_list[0]
        npis = owner.get("npis", [])
        names = owner.get("providerNames", [])
        if not npis or not names:
            continue

        npi = npis[0]
        providerName = names[0]

        for freq in block.get("frequencies", []):
            if freq.get("dowApplied") != dow:
                continue
            if wom not in freq.get("weeksOfMonth", []):
                continue
            if not (freq["blockStartDate"].date() <= date_obj.date() <= freq["blockEndDate"].date()):
                continue

            start_time_obj = freq["blockStartTime"]
            end_time_obj = freq["blockEndTime"]

            # Attach the date and timezone
            block_start = datetime.combine(date_obj.date(), start_time_obj.time())
            block_end = datetime.combine(date_obj.date(), end_time_obj.time())
            duration = int((block_end - block_start).total_seconds() // 60)

            block_entry = {
                "startTime": block_start.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                "endTime": block_end.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                "providerName": providerName,
                "npi": npi,
                "date": date_str,
                "dow": dow,
                "wom": wom,
                "duration": duration,
                "blockId": str(block.get("_id")) if block.get("_id") else "missing",
                "status": "unknown",
                "source": "cerner"
            }

            print(f"✅ Adding block for {providerName} on {date_str} with duration {duration} mins")
            matching_blocks.append(block_entry)

    if matching_blocks:
        calendar_collection.update_one(
            {"_id": doc["_id"]},
            {"$unset": {
                "blocks": "",
                "hasMultipleBlocks": "",
                "hasBlockOverlap": ""
            }}
        )
        calendar_collection.update_one(
            {"_id": doc["_id"]},
            {"$push": {"blocks": {"$each": matching_blocks}}}
        )

        flags = {}
        if len(matching_blocks) > 1:
            flags["hasMultipleBlocks"] = True
            if has_overlap(matching_blocks):
                flags["hasBlockOverlap"] = True

        if flags:
            calendar_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": flags}
            )

print("✅ Finished updating calendar documents with block data including duration.")
