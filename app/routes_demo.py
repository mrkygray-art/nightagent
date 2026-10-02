"""Serves the public /demo page."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app import config
from app.demo_page import DEMO_HTML

router = APIRouter()


@router.get("/demo", response_class=HTMLResponse)
def demo() -> str:
    return DEMO_HTML.replace("__AGENT_ID__", config.ELEVENLABS_AGENT_ID)
