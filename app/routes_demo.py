"""Serves the public /demo and /lab pages."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app import config, fix_log, injection, qa_lab, scorecard
from app.demo_page import DEMO_HTML
from app.lab_page import LAB_HTML

router = APIRouter()

# The lab source stays focused on evaluation content. These small presentation
# overrides turn its section navigator into explicit cards with real CTA buttons
# and phone-friendly touch targets without duplicating the evaluation logic.
LAB_CARD_CSS = r"""
<style>
.lab-nav{gap:16px}
.nav-card{min-height:205px;padding:20px;border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.12)}
.nav-card:hover{border-color:var(--line);transform:none;background:var(--panel)}
.nav-card h2{font-size:24px;margin:0 0 9px}
.nav-card p{font-size:15px;line-height:1.5;margin:0 0 20px}
.nav-card .go{display:inline-flex;align-items:center;justify-content:center;align-self:flex-start;margin-top:auto;min-height:46px;padding:10px 17px;border-radius:999px;background:var(--sodium);color:#1a1200;font-weight:700;text-decoration:none;transition:filter .15s ease,transform .15s ease}
.nav-card .go:hover{filter:brightness(1.08);transform:translateY(-1px)}
.nav-card .go:focus-visible{outline:2px solid var(--text);outline-offset:3px}
.nav-card.future{border-style:dashed}
.nav-card.future .go{background:transparent;color:var(--sodium);border:1px solid var(--sodium)}
@media(max-width:640px){
  .wrap{padding-left:14px;padding-right:14px}
  .lab-nav{grid-template-columns:1fr;gap:14px}
  .nav-card{min-height:0;padding:18px}
  .nav-card h2{font-size:23px}
  .nav-card p{font-size:15px;margin-bottom:18px}
  .nav-card .go{width:100%;min-height:48px;padding:11px 16px}
  .top{align-items:flex-start}
  .top nav{gap:6px 14px}
}
@media(max-width:390px){
  .nav-card{padding:16px}
  .nav-card h2{font-size:22px}
  .nav-card .go{border-radius:12px}
}
</style>
"""

LAB_CARD_REPLACEMENTS = {
    '<a class="nav-card" href="#scorecard"><h2>Scorecard</h2><p>A high-level view of current quality across controlled tests and real calls. Use it to see whether agent behavior is improving, stable, or regressing.</p><span class="go">View scorecard ↓</span></a>':
    '<article class="nav-card"><h2>Scorecard</h2><p>See how NightAgent performs across controlled tests and real calls. This section keeps the evidence behind each metric visible so you can tell whether agent behavior is improving, stable, or regressing.</p><a class="go" href="#scorecard">View Scorecard ↓</a></article>',
    '<a class="nav-card" href="#incidents"><h2>Engineering Incidents</h2><p>Problems uncovered by live calls, tests, or deliberate breakage—plus the cause, the fix, and proof that the fix is still holding.</p><span class="go">See what broke &amp; how we fixed it ↓</span></a>':
    '<article class="nav-card"><h2>What Broke &amp; How We Fixed It</h2><p>Review real problems uncovered by live calls, tests, or deliberate breakage. See what caused each issue, what changed, and whether the fix is still holding today.</p><a class="go" href="#incidents">View Engineering Incidents ↓</a></article>',
    '<a class="nav-card" href="#regression"><h2>Regression Tests</h2><p>Known scenarios replayed against the live agents to make sure new prompts, models, tools, and workflow changes don\'t bring old failures back.</p><span class="go">View regression tests ↓</span></a>':
    '<article class="nav-card"><h2>Regression Tests</h2><p>Replay known scenarios against the live agents to make sure changes to prompts, models, tools, or workflows do not bring previously solved failures back.</p><a class="go" href="#regression">View Regression Tests ↓</a></article>',
    '<a class="nav-card" href="#failure"><h2>Failure Injection</h2><p>Controlled sandbox tests that intentionally break parts of the workflow to verify NightAgent fails safely and recovers correctly.</p><span class="go">Run failure tests ↓</span></a>':
    '<article class="nav-card"><h2>Failure Injection</h2><p>Intentionally break parts of the workflow in a controlled sandbox. These tests verify that NightAgent fails safely, avoids duplicate actions, and recovers when a dependency comes back.</p><a class="go" href="#failure">Run Failure Tests ↓</a></article>',
    '<a class="nav-card" href="#gaps"><h2>Known Measurement Gaps</h2><p>An explicit record of what the lab cannot reliably prove yet. This keeps measured results separate from assumptions and future instrumentation.</p><span class="go">View what isn\'t measured yet ↓</span></a>':
    '<article class="nav-card"><h2>Not Measured Yet</h2><p>See where the Evaluation Lab still has blind spots. This section separates what NightAgent can actually prove from assumptions and identifies where better instrumentation is still needed.</p><a class="go" href="#gaps">View Measurement Gaps ↓</a></article>',
    '<a class="nav-card future" href="#next"><h2>Next: Test Inspector <span class="soon">planned</span></h2><p>The next engineering layer will explain why an individual test passed or failed by exposing expected behavior, actual behavior, tool decisions, and execution details.</p><span class="go">See what\'s next ↓</span></a>':
    '<article class="nav-card future"><h2>Test Inspector <span class="soon">planned</span></h2><p>Coming next: drill into an individual evaluation to compare expected and actual behavior, inspect tool decisions, and understand exactly why a test passed or failed.</p><a class="go" href="#next">See What\'s Coming Next ↓</a></article>',
}


def _lab_html() -> str:
    html = LAB_HTML.replace("</head>", LAB_CARD_CSS + "</head>")
    for old, new in LAB_CARD_REPLACEMENTS.items():
        html = html.replace(old, new)
    return html


@router.get("/demo", response_class=HTMLResponse)
def demo() -> str:
    return DEMO_HTML.replace("__AGENT_ID__", config.ELEVENLABS_AGENT_ID)


@router.get("/lab", response_class=HTMLResponse)
def lab() -> str:
    return _lab_html()


@router.get("/api/lab")
def lab_results() -> dict:
    """Evaluation Lab: the latest regression-test results from ElevenLabs Agent Testing, plus the scorecard and the fixes log."""
    data = qa_lab.lab_results()
    return {**data, "scorecard": scorecard.scorecard(data), "fixes": fix_log.fixes(data)}


@router.post("/api/lab/inject/{name}")
def inject(name: str) -> dict:
    """Evaluation Lab: replay a known failure through the real server code, in a sandbox."""
    scenario = injection.SCENARIOS.get(name)
    if not scenario:
        raise HTTPException(status_code=404, detail="No such scenario.")
    return scenario()
