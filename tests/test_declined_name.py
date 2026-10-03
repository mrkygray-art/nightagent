"""A caller who won't give a name still gets help (QA-15). Sam sends "not given"; nothing is made up."""
from app.store import get_store

NO_NAME = {"caller_name": "not given", "callback_number": "818-555-0100", "issue_summary": "All cameras are down",
           "category": "system_offline", "suggested_priority": "urgent"}


def test_a_declined_name_is_stored_as_empty_not_as_words(tool):
    out = tool("create-ticket", {**NO_NAME, "conversation_id": "conv_noname_1"})
    ticket = get_store().get_ticket(out["ticket_id"])
    assert ticket["caller_name"] is None
    assert ticket["callback_number"] == "8185550100"


def test_a_repeat_call_without_a_name_reads_naturally(client, tool):
    first = tool("create-ticket", {**NO_NAME, "conversation_id": "conv_noname_2"})
    tool("create-ticket", {**NO_NAME, "conversation_id": "conv_noname_3"})
    events = client.get(f"/api/tickets/{first['ticket_id']}").json()["events"]
    again = next(e for e in events if e["event_type"] == "caller_called_again")
    assert again["description"].startswith("The caller called again")


def test_a_message_without_a_name_has_no_made_up_contact(tool):
    tool("take-message", {"department": "support", "reason": "How do I add a user?", "caller_name": "not given",
                          "callback_number": "8185550100", "conversation_id": "conv_noname_4"})
    task = next(iter(get_store().tasks.values()))
    assert task["contact_name"] is None


def test_lookup_without_a_match_says_a_name_is_optional(tool):
    out = tool("lookup-customer", {"query": "8185550100", "conversation_id": "conv_noname_5"})
    assert out["found"] is False
    assert "don't ask again" in out["next_step"] and "not given" in out["next_step"]
