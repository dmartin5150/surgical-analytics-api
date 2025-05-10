from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pymongo import MongoClient
import os

load_dotenv()

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://surgical-analytics.vercel.app"],  # exact match only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
API_SECRET = os.getenv("API_SECRET")
MONGODB_URI = os.getenv("MONGODB_URI")

# Global Mongo client
mongo_client = None

def get_db():
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(MONGODB_URI)
    return mongo_client["surgical-analytics"]

# API Key middleware
@app.middleware("http")
async def verify_token(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in ["/", "/ping"]:
        return await call_next(request)

    token = request.headers.get("x-api-key")
    if token != API_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")

    return await call_next(request)

# Health check
@app.get("/ping")
def ping():
    return {"message": "pong"}

# MongoDB test route
@app.get("/cases/test")
def test_cases():
    try:
        db = get_db()
        cases = list(db["cases"].find().limit(5))
        for case in cases:
            case["_id"] = str(case["_id"])  # make ObjectId JSON-serializable
        return {"cases": cases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {str(e)}")

# Placeholder route
@app.get("/blocks")
def get_blocks():
    return {"message": "block utilization will go here"}
