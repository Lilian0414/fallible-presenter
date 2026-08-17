import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.challenges import router as challenges_router
from .api.sessions import router as sessions_router

load_dotenv()
app = FastAPI(title="Fallible Presenter", version="1.0.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(sessions_router)
app.include_router(challenges_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
