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
             "posts": [], "puts": [], "next_id": 100}

    def post(url, json=None, timeout=None):  # the token
        return FakeResponse(200, {"access_token": "tok"})

    def get(url, headers=None, timeout=None):
        key = url.rsplit("/", 1)[1].removesuffix(".json")
        return FakeResponse(200, {key: state[key], "next_page": None})

    def request(method, url, json=None, headers=None, timeout=None):
        path = url.split("/api/v2", 1)[1]
        if method == "PUT":
            key = path.split("/")[1]
            item_id = int(path.split("/")[2].removesuffix(".json"))
            next(i for i in state[key] if i["id"] == item_id).update(next(iter(json.values())))
            state["puts"].append(key)
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
    monkeypatch.delenv("ZENDESK_REVIEW_GROUP", raising=False)
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
    assert {"field": f"custom_fields_{fields['Review needed']['id']}", "operator": "is", "value": "true"} in view["all"]
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


def test_trigger_emails_the_review_group(fake, monkeypatch, capsys):
    run(monkeypatch, "--group", "reviewers")  # names match without case
    fields = {f["title"]: f["id"] for f in fake["ticket_fields"]}
    trigger = fake["triggers"][0]
    conditions = trigger["conditions"]["all"]
    assert {"field": "current_tags", "operator": "includes", "value": "needs_review"} in conditions
    assert {"field": "current_tags", "operator": "not_includes",
            "value": "review_called_back review_dispatched review_sms_sent review_approved review_other"} in conditions
    assert [c["value"] for c in trigger["conditions"]["any"]] == ["Create", "Change"]
    group, subject, body = trigger["actions"][0]["value"]
    assert trigger["actions"][0]["field"] == "notification_group" and group == "77"
    assert subject == "[Review] {{ticket.title}}"
    assert f"{{{{ticket.ticket_field_option_title_{fields['Review reason']}}}}}" in body
    assert f"{{{{ticket.ticket_field_{fields['Recommended options']}}}}}" in body
    assert trigger["actions"][1] == {"field": "current_tags", "value": "review_alerted"}
    assert "created trigger" in capsys.readouterr().out


def test_trigger_is_skipped_without_a_group_or_with_an_unknown_one(fake, monkeypatch, capsys):
    run(monkeypatch)
    run(monkeypatch, "--group", "Nobody")
    out = capsys.readouterr().out
    assert fake["triggers"] == [] and "no review group" in out and "no Zendesk group" in out


def test_trigger_rerun_skips_and_a_new_group_updates_it(fake, monkeypatch, capsys):
    run(monkeypatch, "--group", "77")
    fake["groups"].append({"id": 88, "name": "Night leads"})
    run(monkeypatch, "--group", "77")
    assert len(fake["triggers"]) == 1 and fake["puts"].count("triggers") == 0
    run(monkeypatch, "--group", "Night leads")
    assert len(fake["triggers"]) == 1 and fake["triggers"][0]["actions"][0]["value"][0] == "88"
    assert "updated trigger" in capsys.readouterr().out
