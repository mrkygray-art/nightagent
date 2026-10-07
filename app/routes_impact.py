"""NightAgent Business Impact: demo metrics counted from the app's own records.

No revenue figures. Every definition, and the two after-call-work assumptions, live in app/metrics.py,
which the page prints in its "How these are counted" panel.
"""
from fastapi import APIRouter

from app import metrics
from app.store import get_store

router = APIRouter(prefix="/api")


@router.get("/impact")
def impact() -> dict:
    # All three views (Live, Synthetic, All) in one response, so the page switches without a round trip.
    return metrics.impact(get_store().impact_rows())
