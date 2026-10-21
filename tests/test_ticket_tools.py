"""check_ticket_status and add_ticket_note: a caller asks about, or adds to, a ticket they already have."""
import pytest

from app import config, zendesk
from app.service import public_event
from app.store import get_store


def _ticket(tool, customer_id="C-1003", callback="4245550119", conv="conv_first"):
    return tool("create-ticket", {"customer_id": customer_id, "caller_name": "Priya Shah", "callback_number": callback,
                                  "issue_summary": "Main entrance won't unlock", "category": "entry_blocked",
                                  "suggested_priority": "emergency", "conversation_id": conv})["ticket_id"]


def _digits(ticket_id):
    return ticket_id.split("-")[1]


@pytest.mark.parametrize("spoken", ["{id}", "N S {d}", "ns {d}", "{d}", "N S " + "{spaced}"])
def test_status_for_the_callers_own_ticket(tool, spoken):
    tid = _ticket(tool)
    d = _digits(tid)
    out = tool("ticket-status", {"ticket_id": spoken.format(id=tid, d=d, spaced=" ".join(d)), "customer_id": "C-1003"})
    assert out["found"] is True and out["ticket_id"] == tid
    assert out["status"] == "Waiting for a technician" and out["open"] is True
    assert "waiting for a technician" in out["tell_the_caller"] and "next_step" in out


def test_another_accounts_ticket_looks_like_no_ticket(tool):
    tid = _ticket(tool)
    other = tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1001"})
    missing = tool("ticket-status", {"ticket_id": "NS-0000", "customer_id": "C-1001"})
    assert other == missing and other["found"] is False


def test_the_ticket_number_alone_is_never_enough(tool):
    tid = _ticket(tool)
    assert tool("ticket-status", {"ticket_id": tid})["found"] is False
    assert tool("ticket-status", {"ticket_id": tid, "callback_number": "424-555-0119"})["found"] is False


def test_ticket_without_an_account_needs_the_same_callback_number(tool):
    tid = _ticket(tool, customer_id=None, callback="3105550199")
    assert tool("ticket-status", {"ticket_id": tid, "callback_number": "(310) 555-0199"})["found"] is True
    assert tool("ticket-status", {"ticket_id": tid, "callback_number": "3105550100"})["found"] is False
    assert tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1003"})["found"] is False


def test_status_without_a_number_lists_the_accounts_tickets(tool):
    assert tool("ticket-status", {"customer_id": "C-1003"})["found"] is False  # no tickets yet
    first = _ticket(tool)
    one = tool("ticket-status", {"customer_id": "C-1003"})
    assert one["found"] is True and one["ticket_id"] == first
    tool("create-ticket", {"customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "4245550119",
                           "issue_summary": "Camera 4 is offline", "category": "system_offline", "conversation_id": "conv_2"})
    two = tool("ticket-status", {"customer_id": "C-1003"})
    assert len(two["tickets"]) == 2 and "ticket_id" not in two
    assert tool("ticket-status", {})["found"] is False  # no account and no number: ask for the number


def test_note_goes_on_the_history_but_not_on_public_pages(tool):
    tid = _ticket(tool)
    out = tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "The side door code changed to the new one",
                               "conversation_id": "conv_second"})
    assert out["saved"] is True and out["ticket_id"] == tid
    event = get_store().list_events(tid)[-1]
    assert event["event_type"] == "caller_added_note" and event["metadata"]["note"] == "The side door code changed to the new one"
    shown = public_event(event)
    assert "door code" not in str(shown) and shown["label"] == "Caller added a note"
    assert any(t["tool"] == "add_ticket_note" and t["ticket_id"] == tid for t in get_store().recent_tool_calls())


def test_note_on_someone_elses_ticket_is_refused(tool):
    tid = _ticket(tool)
    before = len(get_store().list_events(tid))
    out = tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1001", "note": "Cancel the technician"})
    assert out["saved"] is False and len(get_store().list_events(tid)) == before


def test_empty_note_is_not_saved(tool):
    tid = _ticket(tool)
    assert tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "n/a"})["saved"] is False


def test_status_skips_the_callers_own_notes(tool):
    tid = _ticket(tool)
    tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "I'll be on site at 7"})
    out = tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1003"})
    assert "note" not in out["tell_the_caller"].lower()


class FakeResponse:
    def __init__(self, status):
        self.status_code = status

    def json(self):
        return {"access_token": "tok-1"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def zd(monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_SUBDOMAIN", "acme")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(zendesk, "_token", {"value": "", "expires_at": 0.0})
    state = {"puts": [], "fail": None}
    monkeypatch.setattr(zendesk.requests, "post", lambda url, **kw: FakeResponse(200))

    def put(url, json=None, headers=None, timeout=None):
        state["puts"].append({"url": url, "json": json})
        return FakeResponse(state["fail"] or 200)
    monkeypatch.setattr(zendesk.requests, "put", put)
    return state


def test_note_goes_to_the_zendesk_ticket_as_a_private_comment(tool, zd):
    tid = _ticket(tool)
    get_store().update_ticket(tid, {"zendesk_ticket_id": 9002})
    tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "Gate code changed"})
    (sent,) = zd["puts"]
    assert sent["url"] == "https://acme.zendesk.com/api/v2/tickets/9002.json"
    assert sent["json"]["ticket"]["comment"] == {"body": "Caller added on a NightAgent call: Gate code changed", "public": False}
    assert sent["json"]["ticket"]["additional_tags"] == ["nightagent_update"]


def test_zendesk_failure_still_saves_the_note(tool, zd):
    tid = _ticket(tool)
    get_store().update_ticket(tid, {"zendesk_ticket_id": 9002})
    zd["fail"] = 500
    out = tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "Gate code changed"})
    assert out["saved"] is True and get_store().list_events(tid)[-1]["event_type"] == "caller_added_note"


def test_ticket_not_in_zendesk_yet_skips_zendesk(tool, zd):
    tid = _ticket(tool)  # Zendesk tickets are made after the call ends
    assert tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": "Gate code changed"})["saved"] is True
    assert zd["puts"] == []


def test_ticket_tools_need_the_tool_secret(client):
    assert client.post("/tools/ticket-status", json={"ticket_id": "NS-1000"}).status_code == 401
    assert client.post("/tools/ticket-note", json={"ticket_id": "NS-1000", "note": "x"}).status_code == 401


@pytest.mark.parametrize("note", ["No additional information provided.", "Nothing new to add", "Caller had nothing to add.",
                                  "No update", "None provided"])
def test_a_note_that_adds_nothing_is_not_saved(tool, note):
    """Seen on a test call: Sam logged "No additional information provided." on the ticket."""
    tid = _ticket(tool)
    before = len(get_store().list_events(tid))
    out = tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": note})
    assert out["saved"] is False and "nothing new" in out["message"]
    assert len(get_store().list_events(tid)) == before


@pytest.mark.parametrize("note", ["No one will be on site until 7, use the new side gate", "No power to the gate since 6pm",
                                  "Nothing works on the keypad now"])
def test_real_notes_that_start_with_no_are_saved(tool, note):
    tid = _ticket(tool)
    assert tool("ticket-note", {"ticket_id": tid, "customer_id": "C-1003", "note": note})["saved"] is True


def test_status_tells_sam_not_to_promise_contact_or_times(tool):
    """Seen on a test call: Sam said the technician "will be in touch", which nothing on the ticket said."""
    tid = _ticket(tool)
    out = tool("ticket-status", {"ticket_id": tid, "customer_id": "C-1003"})
    assert "be in touch" in out["next_step"] and "don't give or guess any time" in out["next_step"]
    assert not any(w in out["tell_the_caller"].lower() for w in ("will call", "in touch", "will arrive"))
