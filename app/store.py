"""Data access. Two interchangeable backends:

- MemoryStore: seeded demo data, no setup needed. Great for local dev and tests.
  Data resets whenever the process restarts.
- SupabaseStore: Postgres via Supabase. Used automatically when SUPABASE_URL is set.

Both expose the same methods, so the rest of the app doesn't care which one it gets.
"""
import re
import secrets
from datetime import datetime, timezone
from functools import lru_cache

from app import config

SEED_CUSTOMERS = [
    {
        "customer_id": "C-1001",
        "business_name": "Sunset Dental Group",
        "contact_name": "Maria Lopez",
        "phone_digits": "3105550142",
        "site_address": "4100 Demo Ave, Suite 200, Torrance, CA",
        "systems": "Bosch intrusion panel, 12 Hanwha cameras, 4-door Acre access control",
        "service_plan": "Gold - 24/7 monitoring and after-hours service",
        "after_hours_coverage": True,
    },
    {
        "customer_id": "C-1002",
        "business_name": "Westside Self Storage",
        "contact_name": "James Carter",
        "phone_digits": "3105550178",
        "site_address": "880 Example Blvd, Hawthorne, CA",
        "systems": "DMP intrusion panel, 8 Verkada cameras, gate keypad",
        "service_plan": "Standard - business-hours service only",
        "after_hours_coverage": False,
    },
    {
        "customer_id": "C-1003",
        "business_name": "Harbor Logistics Warehouse",
        "contact_name": "Priya Shah",
        "phone_digits": "4245550119",
        "site_address": "2200 Sample Way, Carson, CA",
        "systems": "Mercury-based access control (24 doors), 40 Axis cameras, Milestone VMS",
        "service_plan": "Platinum - 24/7 monitoring and priority dispatch",
        "after_hours_coverage": True,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def phone_digits(text: str) -> str:
    """Keep digits only and drop a leading US country code."""
    digits = re.sub(r"\D", "", text or "")
    return digits[-10:] if len(digits) >= 10 else digits


def new_ticket_id() -> str:
    return f"NS-{secrets.randbelow(9000) + 1000}"


def _clean_name_query(text: str) -> str:
    # Letters, digits and spaces only, so the text is safe inside a filter expression.
    return re.sub(r"[^A-Za-z0-9 ]", "", text or "").strip()


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self.customers = [dict(c) for c in SEED_CUSTOMERS]
        self.tickets: dict[str, dict] = {}
        self.calls: dict[str, dict] = {}
        self.events: list[dict] = []
        self._event_seq = 0

    def find_customers(self, query: str) -> list[dict]:
        digits = phone_digits(query)
        if len(digits) == 10:
            return [c for c in self.customers if c["phone_digits"] == digits]
        q = _clean_name_query(query).lower()
        if not q:
            return []
        return [
            c for c in self.customers
            if q in c["business_name"].lower() or q in (c["contact_name"] or "").lower()
        ]

    def get_customer(self, customer_id: str) -> dict | None:
        return next((c for c in self.customers if c["customer_id"] == customer_id), None)

    def create_ticket(self, ticket: dict) -> dict:
        ticket = {"status": "awaiting_dispatch", "demo": False, **ticket,
                  "ticket_id": new_ticket_id(), "created_at": now_iso()}
        self.tickets[ticket["ticket_id"]] = ticket
        return ticket

    def get_ticket(self, ticket_id: str) -> dict | None:
        return self.tickets.get(ticket_id)

    def update_ticket(self, ticket_id: str, fields: dict) -> None:
        if ticket_id in self.tickets:
            self.tickets[ticket_id].update(fields)

    def upsert_call(self, call: dict) -> None:
        self.calls[call["conversation_id"]] = {**call, "received_at": now_iso()}

    def add_event(self, event: dict) -> dict:
        self._event_seq += 1
        row = {"simulated": False, "source": "call", "occurred_at": now_iso(), **event,
               "id": self._event_seq, "created_at": now_iso()}
        self.events.append(row)
        return row

    def list_events(self, ticket_id: str) -> list[dict]:
        rows = [e for e in self.events if e["ticket_id"] == ticket_id]
        return sorted(rows, key=lambda e: (e["occurred_at"], e["id"]))

    def delete_events(self, ticket_id: str, source: str) -> None:
        self.events = [e for e in self.events if not (e["ticket_id"] == ticket_id and e["source"] == source)]

    def count_demo_tickets_since(self, since_iso: str) -> int:
        return sum(1 for t in self.tickets.values() if t.get("scenario") and t["created_at"] >= since_iso)

    def recent_tickets(self, limit: int = 25) -> list[dict]:
        rows = sorted(self.tickets.values(), key=lambda t: t["created_at"], reverse=True)
        return rows[:limit]

    def calls_by_ids(self, conversation_ids: list[str]) -> dict[str, dict]:
        return {cid: self.calls[cid] for cid in conversation_ids if cid in self.calls}


class SupabaseStore:
    name = "supabase"

    def __init__(self, url: str, key: str, prefix: str = "") -> None:
        from supabase import create_client  # imported here so tests don't need it

        self.db = create_client(url, key)
        self.customers_table = f"{prefix}customers"
        self.tickets_table = f"{prefix}tickets"
        self.calls_table = f"{prefix}calls"
        self.events_table = f"{prefix}ticket_events"

    def find_customers(self, query: str) -> list[dict]:
        digits = phone_digits(query)
        table = self.db.table(self.customers_table).select("*")
        if len(digits) == 10:
            return table.eq("phone_digits", digits).limit(3).execute().data
        q = _clean_name_query(query)
        if not q:
            return []
        return (
            table.or_(f"business_name.ilike.%{q}%,contact_name.ilike.%{q}%")
            .limit(3)
            .execute()
            .data
        )

    def get_customer(self, customer_id: str) -> dict | None:
        rows = self.db.table(self.customers_table).select("*").eq("customer_id", customer_id).execute().data
        return rows[0] if rows else None

    def create_ticket(self, ticket: dict) -> dict:
        row = {"status": "awaiting_dispatch", **ticket, "ticket_id": new_ticket_id()}
        return self.db.table(self.tickets_table).insert(row).execute().data[0]

    def get_ticket(self, ticket_id: str) -> dict | None:
        rows = self.db.table(self.tickets_table).select("*").eq("ticket_id", ticket_id).execute().data
        return rows[0] if rows else None

    def update_ticket(self, ticket_id: str, fields: dict) -> None:
        self.db.table(self.tickets_table).update(fields).eq("ticket_id", ticket_id).execute()

    def upsert_call(self, call: dict) -> None:
        # Upsert on conversation_id so webhook retries never create duplicates.
        self.db.table(self.calls_table).upsert(call, on_conflict="conversation_id").execute()

    def add_event(self, event: dict) -> dict:
        return self.db.table(self.events_table).insert(event).execute().data[0]

    def list_events(self, ticket_id: str) -> list[dict]:
        return (
            self.db.table(self.events_table).select("*").eq("ticket_id", ticket_id)
            .order("occurred_at").order("id").execute().data
        )

    def delete_events(self, ticket_id: str, source: str) -> None:
        self.db.table(self.events_table).delete().eq("ticket_id", ticket_id).eq("source", source).execute()

    def count_demo_tickets_since(self, since_iso: str) -> int:
        res = (
            self.db.table(self.tickets_table).select("ticket_id", count="exact")
            .not_.is_("scenario", "null").gte("created_at", since_iso).limit(1).execute()
        )
        return res.count or 0

    def recent_tickets(self, limit: int = 25) -> list[dict]:
        return (
            self.db.table(self.tickets_table).select("*")
            .order("created_at", desc=True).limit(limit).execute().data
        )

    def calls_by_ids(self, conversation_ids: list[str]) -> dict[str, dict]:
        if not conversation_ids:
            return {}
        rows = (
            self.db.table(self.calls_table).select("*")
            .in_("conversation_id", conversation_ids).execute().data
        )
        return {r["conversation_id"]: r for r in rows}


@lru_cache
def get_store() -> MemoryStore | SupabaseStore:
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
        return SupabaseStore(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.TABLE_PREFIX)
    return MemoryStore()
