"""Serves the public /demo and /lab pages."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app import config, injection, qa_lab
from app.demo_page import DEMO_HTML
from app.lab_page import LAB_HTML

router = APIRouter()


@router.get("/demo", response_class=HTMLResponse)
def demo() -> str:
    return DEMO_HTML.replace("__AGENT_ID__", config.ELEVENLABS_AGENT_ID)


@router.get("/lab", response_class=HTMLResponse)
def lab() -> str:
    return LAB_HTML


@router.get("/api/lab")
def lab_results() -> dict:
    """Agent QA Lab: the latest regression-test results from ElevenLabs Agent Testing."""
    return qa_lab.lab_results()


@router.post("/api/lab/inject/{name}")
def inject(name: str) -> dict:
    """Agent QA Lab: replay a known failure through the real server code, in a sandbox."""
    scenario = injection.SCENARIOS.get(name)
    if not scenario:
        raise HTTPException(status_code=404, detail="No such scenario.")
    return scenario()
