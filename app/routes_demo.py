"""Serves the public /demo and /lab pages."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app import config, injection, qa_lab, scorecard
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
    """Evaluation Lab: the latest regression-test results from ElevenLabs Agent Testing, plus the scorecard."""
    data = qa_lab.lab_results()
    return {**data, "scorecard": scorecard.scorecard(data)}


@router.post("/api/lab/inject/{name}")
def inject(name: str) -> dict:
    """Evaluation Lab: replay a known failure through the real server code, in a sandbox."""
    scenario = injection.SCENARIOS.get(name)
    if not scenario:
        raise HTTPException(status_code=404, detail="No such scenario.")
    return scenario()
