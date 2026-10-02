"""NightAgent backend (deployed as nightshift-dispatch).

Run locally:   uvicorn main:app --reload
Deploy:        Vercel detects the FastAPI `app` in main.py automatically.
"""
import logging

from fastapi import FastAPI

from app.routes_dashboard import router as dashboard_router
from app.routes_demo import router as demo_router
from app.routes_impact import router as impact_router
from app.routes_lifecycle import router as lifecycle_router
from app.routes_tools import router as tools_router
from app.routes_webhooks import router as webhooks_router
from app.store import get_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="NightAgent",
    description="Backend for an AI service lifecycle agent built on ElevenLabs Agents.",
    version="0.1.0",
)
app.include_router(tools_router)
app.include_router(webhooks_router)
app.include_router(dashboard_router)
app.include_router(demo_router)
app.include_router(lifecycle_router)
app.include_router(impact_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "store": get_store().name}
