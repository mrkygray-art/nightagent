"""The front desk: Sam takes a message for a department or a person."""


def _message(tool, **fields):
    body = {"department": "account_executive", "reason": "Wants a quote to add cameras at the warehouse.",
            "caller_name": "Priya Shah", "callback_number": "(424) 555-0119", "customer_id": "C-1003",
            "person_requested": "Sarah", "conversation_id": "conv_desk_1", **fields}
    return tool("take-message", body)


def test_message_goes_to_the_right_person_and_says_so(tool):
    out = _message(tool)
    assert out["saved"] and out["message_id"].startswith("TASK-")
    assert out["tell_the_caller"] == ("Sarah Johnson, your account executive, will get your message "
                                      "and call you back on the next business day.")


def test_each_department_has_a_natural_sentence(tool):
    said = {d: _message(tool, department=d, conversation_id=f"conv_{d}")["tell_the_caller"]
            for d in ("billing", "support", "service_manager", "service")}
    assert said["billing"].startswith("Morgan Lee from billing will")
    assert said["support"].startswith("Our support desk will")
    assert said["service_manager"].startswith("Alex Moreno, our service manager, will")
    assert said["service"].startswith("Our service desk will")


def test_unknown_department_falls_back_to_the_service_desk(tool):
    assert _message(tool, department="marketing")["tell_the_caller"].startswith("Our service desk")


def test_best_time_is_repeated_back(tool):
    out = _message(tool, best_time="tomorrow after 10 AM")
    assert out["tell_the_caller"].endswith("call you back tomorrow after 10 AM.")


def test_message_shows_on_the_board_with_its_report(client, tool):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_desk_1"})
    mid = _message(tool)["message_id"]
    board = client.get("/api/messages").json()
    assert [m["message_id"] for m in board] == [mid]
    assert board[0]["callback_number"] == "(•••) •••-0119"  # never the full number
    assert board[0]["department"] == "Sales (account executive)"
    detail = client.get(f"/api/messages/{mid}").json()
    rows = {r["label"]: r["value"] for r in detail["report"]["rows"]}
    assert rows["Asked for"] == "Sarah"
    assert rows["Tools Sam used"] == "2: Looked up the account; Took a message"
    assert rows["Service ticket"] == "None: not a service problem"
    assert rows["Handed to"] == "Sarah Johnson, Account Executive (fictional)"
    assert rows["Callback"] == "(•••) •••-0119, next business day"


def test_message_on_a_service_call_joins_the_ticket(client, tool):
    made = tool("create-ticket", {"customer_id": "C-1003", "caller_name": "Priya Shah",
                                  "callback_number": "4245550119", "issue_summary": "Camera offline",
                                  "category": "system_offline", "conversation_id": "conv_both"})
    _message(tool, ticket_id=made["ticket_id"], conversation_id="conv_both")
    assert client.get("/api/messages").json() == []  # it lives on the ticket, not as its own card
    rows = {r["label"]: r["value"] for r in client.get(f"/api/tickets/{made['ticket_id']}").json()["report"]["rows"]}
    assert "Sarah Johnson" in rows["Handed to"]
    assert rows["Tools Sam used"].startswith("2: Created the ticket; Took a message")


def test_voice_for_a_message_needs_the_calls_own_id(client, tool):
    mid = _message(tool)["message_id"]
    bad = client.post("/api/demo/voice", json={"ticket_id": mid, "conversation_id": "conv_other_1", "voice": "Eric"})
    assert bad.status_code == 403
    ok = client.post("/api/demo/voice", json={"ticket_id": mid, "conversation_id": "conv_desk_1", "voice": "Lauren"})
    assert ok.status_code == 200
    rows = {r["label"]: r["value"] for r in client.get(f"/api/messages/{mid}").json()["report"]["rows"]}
    assert rows["Agent"].endswith("(voice: Lauren)") and rows["Call"] == "Voice call"


def test_unknown_message_is_404(client):
    assert client.get("/api/messages/TASK-0000").status_code == 404


def test_second_message_to_the_same_person_updates_the_first(client, tool):
    first = _message(tool)
    again = _message(tool, best_time="tomorrow after 10 AM")
    assert again["message_id"] == first["message_id"]
    assert again["tell_the_caller"].endswith("call you back tomorrow after 10 AM.")
    board = client.get("/api/messages").json()
    assert len(board) == 1 and board[0]["best_time"] == "tomorrow after 10 AM"
    rows = {r["label"]: r["value"] for r in client.get(f"/api/messages/{first['message_id']}").json()["report"]["rows"]}
    assert rows["Tools Sam used"] == "2: Took a message; Updated the message"
    other = _message(tool, department="billing", reason="Invoice question")
    assert other["message_id"] != first["message_id"]  # a different person gets their own message


def test_complaint_about_something_broken_ends_up_on_a_repair_ticket(client, tool):
    first = _message(tool, department="service_manager", reason="Technician left a mess and the gate still sticks",
                     conversation_id="conv_complaint_1")
    assert "call create_ticket" in first["next_step"]  # the server reminds Sam about the repair
    made = tool("create-ticket", {"customer_id": "C-1002", "caller_name": "James Carter", "callback_number": "3105550178",
                                  "issue_summary": "Gate still sticks after the repair", "category": "cannot_secure_site",
                                  "conversation_id": "conv_complaint_1"})
    again = _message(tool, department="service_manager", reason="Technician left a mess and the gate still sticks",
                     ticket_id=made["ticket_id"], conversation_id="conv_complaint_1")
    assert again["message_id"] == first["message_id"]
    assert "call create_ticket" not in again["next_step"]
    assert client.get("/api/messages").json() == []  # now it lives on the ticket
    rows = {r["label"]: r["value"] for r in client.get(f"/api/tickets/{made['ticket_id']}").json()["report"]["rows"]}
    assert "Alex Moreno" in rows["Handed to"]
