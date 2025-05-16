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
    """Calculate Cerner-style week of month (week 1 starts on the 1st, even if before Sunday)."""
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

    matching_blocks = []

    for block in blocks:
        if block.get("unit") != doc.get("unit"):
            continue
        if block.get("room") != doc.get("room"):
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

            block_start = freq["blockStartTime"].strftime("%H:%M")
            block_end = freq["blockEndTime"].strftime("%H:%M")
            matching_blocks.append({
                "startTime": f"{date_str}T{block_start}:00-05:00",
                "endTime": f"{date_str}T{block_end}:00-05:00",
                "providerName": providerName,
                "npi": npi,
                "date": date_str,
                "dow": dow,
                "wom": wom,
                "blockId": str(block["_id"]),
                "status": "unknown",
                "source": "cerner"
            })

    if matching_blocks:
        # Clear old blocks and flags
        calendar_collection.update_one(
            {"_id": doc["_id"]},
            {"$unset": {
                "blocks": "",
                "hasMultipleBlocks": "",
                "hasBlockOverlap": ""
            }}
        )

        # Push new blocks
        calendar_collection.update_one(
            {"_id": doc["_id"]},
            {"$push": {"blocks": {"$each": matching_blocks}}}
        )

        # Set flags if needed
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

print("✅ Finished updating calendar documents with block data.")
