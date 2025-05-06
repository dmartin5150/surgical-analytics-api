from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()


app = FastAPI()

# Allow CORS from your Vercel frontend
origins = ["https://surgical-analytics.vercel.app"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://surgical-analytics.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    return {"message": "pong"}
