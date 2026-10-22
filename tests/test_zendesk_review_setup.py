"""scripts/zendesk_review_setup.py against a small fake Zendesk: makes what's missing, and a second run makes nothing."""
import importlib.util
from pathlib import Path

import pytest

from app import config

SPEC = importlib.util.spec_from_file_location(
    "zendesk_review_setup", Path(__file__).resolve().parent.parent / "scripts" / "zendesk_review_setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_SUBDOMAIN", "acme")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "client-secret")
    state = {"ticket_fields": [], "views": [], "triggers": [], "groups": [{"id": 77, "name": "Reviewers"}],
             "ticket_forms": [{"id": 5, "name": "Default Ticket Form", "default": True, "ticket_field_ids": [1, 2]}],
             "posts": [], "next_id": 100}

    def post(url, json=None, timeout=None):  # the token
        return FakeResponse(200, {"access_token": "tok"})

    def get(url, headers=None, timeout=None):
        key = url.rsplit("/", 1)[1].removesuffix(".json")
        return FakeResponse(200, {key: state[key], "next_page": None})

    def request(method, url, json=None, headers=None, timeout=None):
        path = url.split("/api/v2", 1)[1]
        if method == "PUT":
            state["ticket_forms"][0].update(json["ticket_form"])
            return FakeResponse(200, json)
        key = path.removeprefix("/").removesuffix(".json")
        item = dict(next(iter(json.values())), id=state["next_id"])
        state["next_id"] += 1
        state[key].append(item)
        state["posts"].append((key, item))
        return FakeResponse(201, {key[:-1]: item})

    monkeypatch.setattr(setup.requests, "post", post)
    monkeypatch.setattr(setup.requests, "get", get)
    monkeypatch.setattr(setup.requests, "request", request)
    return state


def run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["zendesk_review_setup.py", *argv])
    setup.main()


def test_first_run_makes_the_fields_and_view(fake, monkeypatch, capsys):
    run(monkeypatch)
    fields = {f["title"]: f for f in fake["ticket_fields"]}
    assert set(fields) == {"Review needed", "Review reason", "Recommended options", "Review decision"}
    assert fields["Review needed"]["tag"] == "needs_review"
    assert [o["value"] for o in fields["Review reason"]["custom_field_options"]][:2] == ["emergency_unclear", "no_account_match"]
    assert [o["name"] for o in fields["Review decision"]["custom_field_options"]] == \
        ["Called back", "Dispatched", "SMS sent", "Approved as-is", "Other"]
    view = fake["views"][0]
    assert view["title"] == "Needs human review"
    assert {"field": f"custom_fields_{fields['Review needed']['id']}", "operator": "is", "value": True} in view["all"]
    assert view["output"]["columns"] == ["subject", "requester", "priority", fields["Review reason"]["id"], "created"]
    assert set(fake["ticket_forms"][0]["ticket_field_ids"]) >= {f["id"] for f in fields.values()}
    assert "ZENDESK_FIELD_REVIEW_NEEDED=" in capsys.readouterr().out


def test_second_run_makes_nothing(fake, monkeypatch, capsys):
    run(monkeypatch)
    made = len(fake["posts"])
    capsys.readouterr()
    run(monkeypatch)
    assert len(fake["posts"]) == made
    out = capsys.readouterr().out
    assert "created" not in out and out.count("skipped") >= 5


def test_dry_run_makes_nothing(fake, monkeypatch, capsys):
    run(monkeypatch, "--dry-run")
    assert fake["posts"] == [] and "would create view" in capsys.readouterr().out
