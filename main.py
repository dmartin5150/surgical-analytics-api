from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Load API_SECRET from environment
API_SECRET = os.getenv("API_SECRET")

# ✅ Middleware to check x-api-key
# @app.middleware("http")
# async def verify_token(request: Request, call_next):
#     if request.method == "OPTIONS":
#         return await call_next(request)

#     # Allow unauthenticated access to the root or ping for health checks
#     if request.url.path in ["/", "/ping"]:
#         return await call_next(request)

#     token = request.headers.get("x-api-key")
#     if token != API_SECRET:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")
    
#     return await call_next(request)



@app.get("/ping")
def ping():
    return {"message": "pong"}


@app.get("/blocks")
def get_blocks(request: Request):
    return {"message": "block utilization will go here"}