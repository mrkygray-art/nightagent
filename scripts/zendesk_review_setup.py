"""Set up the human-review layer in Zendesk: four ticket fields and the "Needs human review" view.

Run:  .venv/Scripts/python.exe scripts/zendesk_review_setup.py [--dry-run]
Reads ZENDESK_SUBDOMAIN, ZENDESK_CLIENT_ID and ZENDESK_CLIENT_SECRET from the environment (or .env), the same
OAuth client NightAgent uses; nothing is hardcoded. The token asks for ZENDESK_SETUP_SCOPE (default "read write"),
since fields and views have no narrower scope; the client credentials act as the admin who made the OAuth client.

Safe to re-run: every field and view is looked up by title first and only made if missing. Fields are also added
to the default ticket form, so agents see them. --dry-run only reads and prints what it would make. At the end it
prints the env vars NightAgent needs (ZENDESK_FIELD_REVIEW_*).
"""
import argparse
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402  (loads .env)
from app.review import RULES  # noqa: E402
from app.zendesk import subdomain  # noqa: E402

TIMEOUT = 15

# The review reason codes (app/review.py); each option's value is also the tag NightAgent puts on the ticket.
REASON_CODES = list(RULES)
DECISIONS = {"Called back": "review_called_back", "Dispatched": "review_dispatched", "SMS sent": "review_sms_sent",
             "Approved as-is": "review_approved", "Other": "review_other"}

REVIEW_NEEDED = "Review needed"
REVIEW_REASON = "Review reason"
RECOMMENDED = "Recommended options"
REVIEW_DECISION = "Review decision"
VIEW_TITLE = "Needs human review"

FIELDS = [
    # The checkbox's tag matches the tag NightAgent adds, so the two always agree.
    {"title": REVIEW_NEEDED, "type": "checkbox", "tag": "needs_review",
     "description": "Set by NightAgent when a call needs a person to look at it."},
    {"title": REVIEW_REASON, "type": "multiselect",
     "description": "Why NightAgent flagged the call (one or more reason codes).",
     "custom_field_options": [{"name": code, "value": code.lower()} for code in REASON_CODES]},
    {"title": RECOMMENDED, "type": "textarea",
     "description": "NightAgent's suggested next steps; the first one is the recommendation."},
    {"title": REVIEW_DECISION, "type": "tagger",
     "description": "What the reviewer did.",
     "custom_field_options": [{"name": name, "value": value} for name, value in DECISIONS.items()]},
]

ENV_NAMES = {REVIEW_NEEDED: "ZENDESK_FIELD_REVIEW_NEEDED", REVIEW_REASON: "ZENDESK_FIELD_REVIEW_REASON",
             RECOMMENDED: "ZENDESK_FIELD_RECOMMENDED_OPTIONS", REVIEW_DECISION: "ZENDESK_FIELD_REVIEW_DECISION"}


class Zendesk:
    def __init__(self):
        if not all([config.ZENDESK_SUBDOMAIN, config.ZENDESK_CLIENT_ID, config.ZENDESK_CLIENT_SECRET]):
            sys.exit("Set ZENDESK_SUBDOMAIN, ZENDESK_CLIENT_ID and ZENDESK_CLIENT_SECRET first.")
        self.base = f"https://{subdomain()}.zendesk.com"
        res = requests.post(f"{self.base}/oauth/tokens", timeout=TIMEOUT, json={
            "grant_type": "client_credentials", "client_id": config.ZENDESK_CLIENT_ID,
            "client_secret": config.ZENDESK_CLIENT_SECRET,
            "scope": os.getenv("ZENDESK_SETUP_SCOPE", "read write")})
        if res.status_code >= 400:
            sys.exit(f"Zendesk refused the token ({res.status_code}): {res.text[:300]}")
        self.headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        res = requests.request(method, f"{self.base}/api/v2{path}", json=payload, headers=self.headers, timeout=TIMEOUT)
        if res.status_code >= 400:
            sys.exit(f"Zendesk answered {res.status_code} for {method} {path}: {res.text[:500]}")
        return res.json()

    def all(self, path: str, key: str) -> list[dict]:
        """Every page of a list endpoint."""
        out, url = [], f"{self.base}/api/v2{path}"
        while url:
            res = requests.get(url, headers=self.headers, timeout=TIMEOUT)
            if res.status_code >= 400:
                sys.exit(f"Zendesk answered {res.status_code} for GET {path}: {res.text[:500]}")
            body = res.json()
            out += body.get(key) or []
            url = body.get("next_page")
        return out


def ensure_fields(zd: Zendesk, dry_run: bool) -> dict[str, int | None]:
    existing = {f["title"]: f for f in zd.all("/ticket_fields.json", "ticket_fields")}
    ids = {}
    for field in FIELDS:
        found = existing.get(field["title"])
        if found:
            if found["type"] != field["type"]:
                print(f"  ! field {field['title']!r} exists as type {found['type']}, expected {field['type']}; fix it by hand")
            print(f"  skipped field {field['title']!r} (exists, id {found['id']})")
            ids[field["title"]] = found["id"]
        elif dry_run:
            print(f"  would create field {field['title']!r} ({field['type']})")
            ids[field["title"]] = None
        else:
            made = zd.call("POST", "/ticket_fields.json", {"ticket_field": field})["ticket_field"]
            print(f"  created field {field['title']!r} (id {made['id']})")
            ids[field["title"]] = made["id"]
    return ids


def ensure_on_default_form(zd: Zendesk, ids: dict[str, int | None], dry_run: bool) -> None:
    forms = zd.all("/ticket_forms.json", "ticket_forms")
    form = next((f for f in forms if f.get("default")), None)
    if not form:
        print("  no default ticket form found; add the fields to your form by hand")
        return
    missing = [i for i in ids.values() if i and i not in form["ticket_field_ids"]]
    if not missing:
        print(f"  skipped form {form['name']!r} (already has the fields)")
    elif dry_run:
        print(f"  would add {len(missing)} field(s) to form {form['name']!r}")
    else:
        zd.call("PUT", f"/ticket_forms/{form['id']}.json",
                {"ticket_form": {"ticket_field_ids": form["ticket_field_ids"] + missing}})
        print(f"  added {len(missing)} field(s) to form {form['name']!r}")


def view_payload(ids: dict[str, int | None]) -> dict:
    return {"view": {
        "title": VIEW_TITLE,
        "all": [{"field": "status", "operator": "less_than", "value": "solved"},
                {"field": f"custom_fields_{ids[REVIEW_NEEDED]}", "operator": "is", "value": True}],
        # Grouped by priority (urgent first), oldest first inside each group
        "output": {"columns": ["subject", "requester", "priority", ids[REVIEW_REASON], "created"],
                   "group_by": "priority", "group_order": "desc", "sort_by": "created", "sort_order": "asc"},
    }}


def ensure_view(zd: Zendesk, ids: dict[str, int | None], dry_run: bool) -> None:
    found = next((v for v in zd.all("/views.json", "views") if v["title"] == VIEW_TITLE), None)
    if found:
        print(f"  skipped view {VIEW_TITLE!r} (exists, id {found['id']})")
    elif dry_run or not all(ids.values()):
        print(f"  would create view {VIEW_TITLE!r}")
    else:
        made = zd.call("POST", "/views.json", view_payload(ids))["view"]
        print(f"  created view {VIEW_TITLE!r} (id {made['id']})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="only read and print what would be made")
    args = parser.parse_args()
    zd = Zendesk()
    print(f"Zendesk {zd.base}{' (dry run)' if args.dry_run else ''}")
    print("Ticket fields:")
    ids = ensure_fields(zd, args.dry_run)
    print("Ticket form:")
    ensure_on_default_form(zd, ids, args.dry_run)
    print("View:")
    ensure_view(zd, ids, args.dry_run)
    print("\nSet these in Vercel (Production) so NightAgent fills the fields:")
    for title, env in ENV_NAMES.items():
        print(f"  {env}={ids.get(title) or '<made on a real run>'}")


if __name__ == "__main__":
    main()
