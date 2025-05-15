from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pymongo import MongoClient
import os

# Import router
from routers.surgeon_profiles import surgeon_profiles_router
from routers.room_profiles import room_profiles_router
from routers.block_utilization import block_utilization_router
from routers import calendar_qa 
from routers import calendar_view
from routers import calendar_blocks  
from routers import calendar_patch
# Load env variables
load_dotenv()

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://surgical-analytics.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Env variables
API_SECRET = os.getenv("API_SECRET")
MONGODB_URI = os.getenv("MONGODB_URI")

# Global DB client
mongo_client = None

def get_db():
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(MONGODB_URI)
    return mongo_client["surgical-analytics"]

# API key middleware (commented out for now)
# @app.middleware("http")
# async def verify_token(request: Request, call_next):
#     if request.method == "OPTIONS" or request.url.path in ["/", "/ping"]:
#         return await call_next(request)
#
#     token = request.headers.get("x-api-key")
#     if token != API_SECRET:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")
#
#     return await call_next(request)

# Health check
@app.get("/ping")
def ping():
    return {"message": "pong"}

# MongoDB test
@app.get("/cases/test")
def test_cases():
    try:
        db = get_db()
        cases = list(db["cases"].find().limit(5))
        for case in cases:
            case["_id"] = str(case["_id"])
        return {"cases": cases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {str(e)}")

# Placeholder
@app.get("/blocks")
def get_blocks():
    return {"message": "block utilization will go here"}

# Include surgeon profile router
app.include_router(surgeon_profiles_router)
app.include_router(room_profiles_router)
app.include_router(block_utilization_router)
app.include_router(calendar_view.router)
app.include_router(calendar_qa.router, prefix="/api")
app.include_router(calendar_blocks.router,prefix="/api")
app.include_router(calendar_patch.router,prefix="/api")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))  # Render sets this to 10000
    uvicorn.run("main:app", host="0.0.0.0", port=port)