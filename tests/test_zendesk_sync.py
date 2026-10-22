"""Zendesk -> NightAgent: the signed status/assignee webhook (Zendesk itself is never called here)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import config, zendesk_sync
from app.store import get_store

SECRET = "test-zendesk-webhook-secret"
URL = "/webhooks/zendesk/ticket-updated"
INTEGRATION_USER = "900"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "ZENDESK_INTEGRATION_USER_ID", INTEGRATION_USER)


def _stamp(delta: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _send(client, payload, *, stamp=None, secret=SECRET, signature=None):
    body = json.dumps(payload).encode()
    stamp = stamp or _stamp()
    headers = {zendesk_sync.TIMESTAMP_HEADER: stamp,
               zendesk_sync.SIGNATURE_HEADER: signature or zendesk_sync.sign(body, stamp, secret)}
    return client.post(URL, content=body, headers=headers)


def _board_ticket(tool, zendesk_id=5001, conv="conv_sync_1", priority="emergency", category="entry_blocked"):
    made = tool("create-ticket", {"customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "4245550119",
                                  "issue_summary": "Main entrance won't unlock", "category": category,
                                  "suggested_priority": priority, "conversation_id": conv})
    get_store().update_ticket(made["ticket_id"], {"zendesk_ticket_id": zendesk_id})
    return made["ticket_id"]


def _payload(tid, status="Open", minutes_ago=0, assignee_id="7001", assignee_name="Morgan Reyes", zendesk_id=5001,
             by="7001", tags="nightagent priority_urgent", **extra):
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"zendesk_ticket_id": str(zendesk_id), "nightagent_ticket_id": tid, "status": status,
            "assignee_id": assignee_id, "assignee_name": assignee_name, "updated_by_id": by,
            "updated_at": at, "tags": tags, **extra}


def _set_status(tid, status):
    get_store().update_ticket(tid, {"status": status})


# --- Signature, replay window, configuration -------------------------------------------------------------

def test_signature_matches_zendesks_method():
    # base64(HMAC-SHA256(secret, timestamp + body)), as in Zendesk's "Verifying webhook authenticity"
    import base64, hashlib, hmac
    body, stamp = b'{"a":1}', "2026-10-22T01:02:03Z"
    expected = base64.b64encode(hmac.new(b"s3cret", stamp.encode() + body, hashlib.sha256).digest()).decode()
    assert zendesk_sync.sign(body, stamp, "s3cret") == expected


def test_signed_delivery_is_applied(client, tool):
    tid = _board_ticket(tool)
    res = _send(client, _payload(tid))
    assert res.status_code == 200 and res.json()["result"] == "applied"
    assert get_store().get_ticket(tid)["status"] == "technician_assigned"


@pytest.mark.parametrize("kwargs", [{"secret": "wrong-secret"}, {"signature": "bm90IGl0"}])
def test_bad_signature_is_rejected_before_anything_is_read(client, tool, kwargs):
    tid = _board_ticket(tool)
    assert _send(client, _payload(tid), **kwargs).status_code == 401
    assert get_store().get_ticket(tid)["status"] == "awaiting_dispatch"


def test_missing_headers_are_rejected(client, tool):
    tid = _board_ticket(tool)
    assert client.post(URL, content=json.dumps(_payload(tid)).encode()).status_code == 401


def test_body_changed_after_signing_is_rejected(client, tool):
    tid = _board_ticket(tool)
    body = json.dumps(_payload(tid)).encode()
    stamp = _stamp()
    sig = zendesk_sync.sign(body, stamp, SECRET)
    tampered = body.replace(b'"Open"', b'"Solved"')
    res = client.post(URL, content=tampered, headers={zendesk_sync.TIMESTAMP_HEADER: stamp,
                                                      zendesk_sync.SIGNATURE_HEADER: sig})
    assert res.status_code == 401


@pytest.mark.parametrize("delta", [timedelta(minutes=-11), timedelta(minutes=2)])
def test_stale_or_future_timestamp_is_rejected(client, tool, delta):
    tid = _board_ticket(tool)
    assert _send(client, _payload(tid), stamp=_stamp(delta)).status_code == 401


def test_timestamp_inside_the_window_is_accepted(client, tool):
    tid = _board_ticket(tool)
    assert _send(client, _payload(tid), stamp=_stamp(timedelta(minutes=-9))).status_code == 200


@pytest.mark.parametrize("unset", ["ZENDESK_WEBHOOK_SECRET", "ZENDESK_INTEGRATION_USER_ID"])
def test_off_until_both_settings_are_there(client, tool, monkeypatch, unset):
    tid = _board_ticket(tool)
    monkeypatch.setattr(config, unset, "")
    assert _send(client, _payload(tid)).status_code == 503


def test_signed_but_not_json_is_a_400(client):
    stamp = _stamp()
    res = client.post(URL, content=b"not json", headers={zendesk_sync.TIMESTAMP_HEADER: stamp,
                                                        zendesk_sync.SIGNATURE_HEADER: zendesk_sync.sign(b"not json", stamp, SECRET)})
    assert res.status_code == 400


def test_store_failure_asks_zendesk_to_retry(client, tool, monkeypatch):
    tid = _board_ticket(tool)
    monkeypatch.setattr(get_store(), "update_ticket", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    res = _send(client, _payload(tid))
    # Zendesk retries a 503 only with a Retry-After under 60 seconds
    assert res.status_code == 503 and int(res.headers["Retry-After"]) < 60


# --- Which deliveries count --------------------------------------------------------------------------------

def test_untagged_ticket_is_ignored(client, tool):
    tid = _board_ticket(tool)
    res = _send(client, _payload(tid, tags="vip billing"))
    assert res.status_code == 200 and res.json()["result"] == "ignored"
    assert get_store().get_ticket(tid)["status"] == "awaiting_dispatch"


def test_own_integration_users_change_is_ignored(client, tool):
    tid = _board_ticket(tool)
    res = _send(client, _payload(tid, by=INTEGRATION_USER))
    assert res.json() == {"status": "ok", "result": "ignored", "reason": "Made by NightAgent's own integration user"}
    assert not get_store().get_ticket(tid).get("zendesk_status")


def test_field_must_name_the_board_ticket_for_this_zendesk_ticket(client, tool):
    tid = _board_ticket(tool, zendesk_id=5001)
    # The NightAgent ID typed onto some other Zendesk ticket
    assert _send(client, _payload(tid, zendesk_id=6666)).json()["result"] == "ignored"
    assert _send(client, _payload("NS-0000")).json()["result"] == "ignored"
    assert _send(client, _payload("")).json()["result"] == "ignored"
    assert get_store().get_ticket(tid)["status"] == "awaiting_dispatch"


def test_unknown_status_is_ignored(client, tool):
    tid = _board_ticket(tool)
    assert _send(client, _payload(tid, status="Awaiting parts")).json()["result"] == "ignored"


# --- The allow-list ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("board, zd_status, assignee, expected, event", [
    ("awaiting_dispatch", "Open", "7001", "technician_assigned", "technician_assigned"),
    ("dispatched", "Open", "7001", "technician_assigned", "technician_assigned"),
    ("escalated", "Open", "7001", "technician_assigned", "technician_assigned"),
    ("onsite", "Solved", "", "work_completed", "work_completed"),
    ("resolved", "Closed", "", "closed", "ticket_closed"),
    ("resolved", "Open", "", "reopened", "ticket_reopened"),
    ("closed", "Open", "", "reopened", "ticket_reopened"),
])
def test_allowed_moves(client, tool, board, zd_status, assignee, expected, event):
    tid = _board_ticket(tool)
    _set_status(tid, board)
    res = _send(client, _payload(tid, status=zd_status, assignee_id=assignee)).json()
    assert res["result"] == "applied" and res["moved"] == [expected]
    assert get_store().get_ticket(tid)["status"] == expected
    last = get_store().list_events(tid)[-1]
    assert last["event_type"] == event and last["source"] == "zendesk"
    assert "Morgan" not in last["description"]  # history is public; the name stays off it


@pytest.mark.parametrize("board, zd_status, assignee", [
    ("awaiting_dispatch", "Solved", ""),       # would skip technician_assigned, en_route, onsite
    ("technician_assigned", "Solved", "7001"),  # would skip en_route and onsite
    ("awaiting_dispatch", "Closed", ""),
    ("follow_up_pending", "Closed", ""),        # closing needs the check-in to resolve it first
    ("reopened", "Open", "7001"),               # reopened goes back to awaiting dispatch before anyone's assigned
])
def test_skips_are_refused_and_recorded(client, tool, board, zd_status, assignee):
    tid = _board_ticket(tool)
    _set_status(tid, board)
    res = _send(client, _payload(tid, status=zd_status, assignee_id=assignee))
    assert res.status_code == 200 and res.json()["result"] == "refused"
    ticket = get_store().get_ticket(tid)
    assert ticket["status"] == board
    assert ticket["zendesk_status"] == zd_status.lower()  # what Zendesk said is still mirrored
    assert get_store().list_events(tid)[-1]["event_type"] == zendesk_sync.REFUSED_EVENT


def test_every_allowed_move_is_one_the_lifecycle_allows():
    from app import lifecycle
    for (signal, board), (target, _event, _text) in zendesk_sync.MOVES.items():
        assert lifecycle.can_transition(board, target), (signal, board, target)


@pytest.mark.parametrize("zd_status", ["Pending", "On-hold", "New"])
def test_statuses_that_dont_move_the_board_are_only_mirrored(client, tool, zd_status):
    tid = _board_ticket(tool)
    res = _send(client, _payload(tid, status=zd_status, assignee_id="")).json()
    assert res["result"] == "mirrored"
    ticket = get_store().get_ticket(tid)
    assert ticket["status"] == "awaiting_dispatch" and ticket["zendesk_status"] == zendesk_sync._status(zd_status)


def test_reassignment_later_on_is_mirrored_not_refused(client, tool):
    tid = _board_ticket(tool)
    _set_status(tid, "en_route")
    res = _send(client, _payload(tid, assignee_id="7002", assignee_name="Sam Okafor")).json()
    assert res["result"] == "mirrored"
    ticket = get_store().get_ticket(tid)
    assert ticket["status"] == "en_route" and ticket["zendesk_assignee_name"] == "Sam Okafor"


def test_zendesk_never_lowers_an_emergency(client, tool):
    tid = _board_ticket(tool, priority="emergency")
    _send(client, _payload(tid, priority="Low", status="Pending"))
    assert get_store().get_ticket(tid)["priority"] == "emergency"


# --- Repeats -------------------------------------------------------------------------------------------------

def test_the_same_delivery_twice_changes_nothing_the_second_time(client, tool):
    tid = _board_ticket(tool)
    payload = _payload(tid)
    assert _send(client, payload).json()["result"] == "applied"
    assert _send(client, payload).json()["result"] == "duplicate"
    events = [e for e in get_store().list_events(tid) if e["event_type"] == "technician_assigned"]
    assert len(events) == 1


def test_an_older_delivery_arriving_late_is_ignored(client, tool):
    tid = _board_ticket(tool)
    _send(client, _payload(tid, status="Pending", minutes_ago=1))
    assert _send(client, _payload(tid, status="Open", assignee_id="", minutes_ago=4)).json()["result"] == "duplicate"
    assert get_store().get_ticket(tid)["zendesk_status"] == "pending"


def test_a_different_change_in_the_same_second_still_counts(client, tool):
    tid = _board_ticket(tool)
    _send(client, _payload(tid, status="Pending", assignee_id=""))
    res = _send(client, _payload(tid, status="Pending", assignee_id="7001")).json()
    assert res["result"] == "applied"


# --- What Sam hears, and who sees the assignee ----------------------------------------------------------------

def test_sam_never_hears_the_assignee_or_a_time(client, tool):
    tid = _board_ticket(tool)
    _send(client, _payload(tid, assignee_name="Morgan Reyes"))
    said = tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1003"})
    text = json.dumps(said)
    assert "Morgan" not in text and "Reyes" not in text
    assert said["status"] == "Technician assigned"
    assert "don't give or guess any time or a technician's name" in said["next_step"]


def test_sam_doesnt_read_out_a_refused_change(client, tool):
    tid = _board_ticket(tool)
    _send(client, _payload(tid, status="Solved", assignee_id=""))
    said = tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1003"})
    assert "not applied" not in said["tell_the_caller"].lower() and said["status"] == "Waiting for a technician"


def test_public_board_shows_the_zendesk_status_but_not_the_name(client, tool):
    tid = _board_ticket(tool)
    _send(client, _payload(tid, assignee_name="Morgan Reyes"))
    row = next(t for t in client.get("/api/tickets").json() if t["ticket_id"] == tid)
    assert row["zendesk_status"] == "open" and row["zendesk_assigned"] is True
    assert "Morgan" not in json.dumps(client.get("/api/tickets").json())
    assert "Morgan" not in client.get(f"/api/tickets/{tid}").text
    assert "Zendesk: Open, assigned" in client.get("/").text


def test_sidebar_card_shows_the_zendesk_status_and_assignee(client, tool, monkeypatch):
    monkeypatch.setattr(config, "SIDEBAR_SECRET", "sidebar-secret")
    tid = _board_ticket(tool)
    _send(client, _payload(tid, assignee_name="Morgan Reyes"))
    card = client.get("/api/zendesk/tickets/5001", headers={"X-Sidebar-Secret": "sidebar-secret"}).json()
    assert card["nightagent_ticket_id"] == tid
    assert card["board_status_label"] == "Technician assigned"
    assert card["zendesk_status"] == "open" and card["zendesk_assignee_name"] == "Morgan Reyes"


def test_supabase_allows_every_column_and_event_source_the_sync_writes():
    """The in-memory store doesn't enforce the schema, so check the migrations: the events table's source CHECK
    (latest definition wins) must allow 'zendesk', or Supabase would drop the sync's history rows silently."""
    import re
    from pathlib import Path
    sql = "\n".join(p.read_text(encoding="utf-8")
                    for p in sorted(Path(__file__).parent.parent.glob("supabase/migrations/*.sql")))
    checks = re.findall(r"ns_ticket_events_source_check\s+check \(source in \(([^)]*)\)\)", sql)
    assert checks and "'zendesk'" in checks[-1]
    for column in ("zendesk_status", "zendesk_assignee_id", "zendesk_assignee_name", "zendesk_updated_at"):
        assert f"add column if not exists {column}" in sql


# --- Evaluation Lab -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, checks", [("zendesk-duplicate", 6), ("zendesk-skip", 5)])
def test_lab_scenarios_pass_in_a_sandbox(client, name, checks):
    result = client.post(f"/api/lab/inject/{name}").json()
    assert result["passed"] and len(result["checks"]) == checks
    assert get_store().tickets == {} and get_store().events == []  # the live store was never touched


def test_lab_page_lists_the_zendesk_scenarios(client):
    page = client.get("/lab").text
    assert 'data-scenario="zendesk-duplicate"' in page and 'data-scenario="zendesk-skip"' in page
