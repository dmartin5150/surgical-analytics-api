# create_provider_list.py
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["surgical-analytics"]
cases = db["cases"]
providers = db["providers"]

pipeline = [
    {"$unwind": "$procedures"},
    {"$match": {"procedures.primary": True}},
    {
        "$group": {
            "_id": "$procedures.primaryNpi",
            "providerName": {"$first": "$procedures.providerName"}
        }
    },
    {"$project": {"npi": "$_id", "providerName": 1, "_id": 0}}
]

result = list(cases.aggregate(pipeline))
if result:
    providers.delete_many({})
    providers.insert_many(result)
    print(f"✅ Inserted {len(result)} unique providers")
else:
    print("⚠️ No providers found.")
