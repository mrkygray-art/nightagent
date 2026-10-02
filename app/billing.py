"""Demo invoices for the billing assistant. All made up, like the rest of the demo accounts.

Spotting a duplicate charge is done here, in code, so the assistant reports what the records show
instead of guessing. The assistant can explain an invoice and open a review, but never promises a
refund or credit: a person in billing decides that.
"""

INVOICES = {
    "C-1001": [  # Sunset Dental Group
        {"invoice_id": "INV-1001-0926", "month": "September 2026", "status": "Paid",
         "lines": [("24/7 alarm monitoring", 129.00), ("Video cloud storage, 12 cameras", 84.00)]},
        {"invoice_id": "INV-1001-0826", "month": "August 2026", "status": "Paid",
         "lines": [("24/7 alarm monitoring", 129.00), ("Video cloud storage, 12 cameras", 84.00)]},
    ],
    "C-1002": [  # Westside Self Storage
        {"invoice_id": "INV-1002-0926", "month": "September 2026", "status": "Due Oct 15",
         "lines": [("Business-hours service plan", 95.00), ("Gate keypad repair (Sept 12 visit)", 165.00)]},
        {"invoice_id": "INV-1002-0826", "month": "August 2026", "status": "Paid",
         "lines": [("Business-hours service plan", 95.00)]},
    ],
    "C-1003": [  # Harbor Logistics Warehouse: September has the monitoring charge twice
        {"invoice_id": "INV-1003-0926", "month": "September 2026", "status": "Paid",
         "lines": [("Platinum 24/7 monitoring", 189.00), ("Platinum 24/7 monitoring", 189.00),
                   ("Access control license, 24 doors", 240.00)]},
        {"invoice_id": "INV-1003-0826", "month": "August 2026", "status": "Paid",
         "lines": [("Platinum 24/7 monitoring", 189.00), ("Access control license, 24 doors", 240.00)]},
    ],
}


def _duplicates(lines: list[tuple[str, float]]) -> list[dict]:
    seen, dupes = {}, []
    for desc, amount in lines:
        key = (desc, amount)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dupes.append({"item": desc, "amount": amount})
    return dupes


def invoices_for(customer_id: str | None) -> dict:
    rows = INVOICES.get(customer_id or "")
    if not rows:
        return {"found": False, "message": "No invoices on file for this caller. Offer to have billing call them."}
    out = []
    for inv in rows:
        total = round(sum(a for _, a in inv["lines"]), 2)
        out.append({
            "invoice_id": inv["invoice_id"],
            "month": inv["month"],
            "status": inv["status"],
            "total": f"${total:,.2f}",
            "lines": [f"{d}: ${a:,.2f}" for d, a in inv["lines"]],
            "possible_duplicates": [f"{d['item']} (${d['amount']:,.2f}) appears twice" for d in _duplicates(inv["lines"])],
        })
    return {"found": True, "invoices": out, "note": "Demo invoices with made-up amounts."}


def find_invoice(customer_id: str | None, invoice_id: str | None) -> dict | None:
    return next((i for i in INVOICES.get(customer_id or "", []) if i["invoice_id"] == (invoice_id or "").strip().upper()), None)
