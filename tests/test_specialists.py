"""Specialist assistants Sam hands off to: Jordan (billing) and Riley (sales)."""


def _review(tool, **fields):
    body = {"customer_id": "C-1003", "invoice_id": "INV-1003-0926", "reason": "Monitoring charged twice in September.",
            "caller_name": "Priya Shah", "callback_number": "4245550119", "conversation_id": "conv_bill_1", **fields}
    return tool("billing-review", body)


def test_billing_lookup_flags_the_duplicate_in_code(tool):
    out = tool("billing-lookup", {"customer_id": "C-1003", "conversation_id": "conv_bill_1"})
    sept = out["invoices"][0]
    assert sept["invoice_id"] == "INV-1003-0926" and sept["total"] == "$618.00"
    assert sept["possible_duplicates"] == ["Platinum 24/7 monitoring ($189.00) appears twice"]
    assert out["invoices"][1]["possible_duplicates"] == []
    assert "Never promise a refund" in out["next_step"]


def test_billing_lookup_without_an_account(tool):
    assert tool("billing-lookup", {"customer_id": None})["found"] is False


def test_billing_review_goes_to_morgan_and_promises_nothing(client, tool):
    out = _review(tool)
    assert out["tell_the_caller"].startswith("Morgan Lee from billing will review INV-1003-0926")
    assert "refund" not in out["tell_the_caller"].lower()
    board = client.get("/api/messages").json()
    assert board[0]["department"] == "Billing" and board[0]["message_id"] == out["review_id"]
    rows = {r["label"]: r["value"] for r in client.get(f"/api/messages/{out['review_id']}").json()["report"]["rows"]}
    assert rows["Agents on this call"] == "Sam (front desk) → Jordan (billing assistant)"
    assert rows["Tools Sam used"] == "1: Jordan opened a billing review"


def test_billing_review_updates_instead_of_duplicating(client, tool):
    first = _review(tool)
    again = _review(tool, best_time="tomorrow after 10 AM")
    assert again["review_id"] == first["review_id"]
    assert again["tell_the_caller"].split(".")[0].endswith("call you back tomorrow after 10 AM")
    assert len(client.get("/api/messages").json()) == 1


def test_sales_interest_creates_an_opportunity_and_a_callback(client, tool):
    tool("lookup-customer", {"query": "3105550178", "conversation_id": "conv_sales_1"})
    body = {"customer_id": "C-1002", "interest": "Add six cameras around the lot", "sales_type": "Camera expansion",
            "device_count": "6", "timeline": "next quarter", "caller_name": "James Carter",
            "callback_number": "3105550178", "conversation_id": "conv_sales_1"}
    out = tool("sales-interest", body)
    assert out["opportunity_id"].startswith("OPP-")
    assert out["tell_the_caller"].startswith("Sarah Johnson, your account executive, will call you back")
    again = tool("sales-interest", {**body, "budget": "about $8,000", "best_time": "Friday morning"})
    assert again["opportunity_id"] == out["opportunity_id"]  # same lead, more detail
    board = client.get("/api/messages").json()
    assert len(board) == 1 and board[0]["department"] == "Sales (account executive)"
    rows = {r["label"]: r["value"] for r in client.get(f"/api/messages/{board[0]['message_id']}").json()["report"]["rows"]}
    assert rows["Agents on this call"] == "Sam (front desk) → Riley (sales assistant)"
    assert rows["New opportunity"] == "Add six cameras around the lot"
    assert rows["Callback"].endswith("Friday morning")
    assert rows["What they needed"] == "Add six cameras around the lot"  # no internal ids
    assert rows["Tools Sam used"] == "3: Looked up the account; Riley recorded the upgrade interest; Riley updated the details"
    from app.store import get_store
    opp = get_store().opportunities[out["opportunity_id"]]
    assert opp["estimated_value"] == "Customer-stated budget: about $8,000"  # never estimated by the AI
