"""A small read-only dashboard showing tickets the agent created and the call summaries."""
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.store import get_store

router = APIRouter()

BADGE = {"emergency": "#c62828", "urgent": "#ef6c00", "routine": "#2e7d32"}


def _mask(number: str | None) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return f"(•••) •••-{digits[-4:]}" if len(digits) >= 4 else "—"


@router.get("/api/tickets")
def api_tickets() -> list[dict]:
    store = get_store()
    tickets = store.recent_tickets()
    calls = store.calls_by_ids([t["conversation_id"] for t in tickets if t.get("conversation_id")])
    for t in tickets:
        t["callback_number"] = _mask(t.get("callback_number"))
        call = calls.get(t.get("conversation_id") or "")
        t["call_summary"] = call.get("summary") if call else None
    return tickets


@router.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    rows = []
    for t in api_tickets():
        color = BADGE.get(t["priority"], "#555")
        rows.append(
            "<tr>"
            f"<td><strong>{escape(t['ticket_id'])}</strong><br><small>{escape(str(t.get('created_at', ''))[:16].replace('T', ' '))} UTC</small></td>"
            f"<td><span class='badge' style='background:{color}'>{escape(t['priority'])}</span><br><small>{escape(t.get('priority_reason') or '')}</small></td>"
            f"<td>{escape(t.get('caller_name') or '')}<br><small>{escape(t['callback_number'])}</small></td>"
            f"<td>{escape(t.get('issue_summary') or '')}</td>"
            f"<td>{escape(t.get('status') or '')}</td>"
            f"<td><small>{escape(t.get('call_summary') or 'Waiting for post-call webhook…')}</small></td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='6'>No tickets yet. Talk to the agent to create one.</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NightShift Dispatch – Tickets</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f6f7f9; color: #1d1f23; }}
  h1 {{ margin: 0 0 4px; font-size: 22px; }}
  p.sub {{ margin: 0 0 20px; color: #5b616e; }}
  .wrap {{ overflow-x: auto; background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  table {{ border-collapse: collapse; width: 100%; min-width: 820px; }}
  th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #eceef1; vertical-align: top; font-size: 14px; }}
  th {{ background: #fafbfc; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #5b616e; }}
  small {{ color: #6b7280; }}
  .badge {{ color: #fff; padding: 2px 8px; border-radius: 999px; font-size: 12px; text-transform: uppercase; }}
</style></head>
<body>
<h1>NightShift Dispatch</h1>
<p class="sub">After-hours voice agent demo built on ElevenLabs Agents and Python/FastAPI. Demo data only. <a href="/demo">Try the live demo</a></p>
<div class="wrap"><table>
<tr><th>Ticket</th><th>Priority</th><th>Caller</th><th>Issue</th><th>Status</th><th>Call summary</th></tr>
{body}
</table></div>
</body></html>"""
