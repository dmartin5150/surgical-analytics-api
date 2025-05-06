from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

# Allow CORS from your Vercel frontend
origins = ["https://surgical-analytics.vercel.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Load API_SECRET from environment
API_SECRET = os.getenv("API_SECRET")

# ✅ Middleware to check x-api-key
@app.middleware("http")
async def verify_token(request: Request, call_next):
    token = request.headers.get("x-api-key")
    if token != API_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")
    return await call_next(request)

@app.get("/ping")
def ping():
    return {"message": "pong"}
