"""Evaluation Lab fixes log: every entry points at real tests, and "now" is live."""
from app import fix_log, qa_lab


def test_every_entry_is_complete_and_points_at_real_tests():
    ids = [f["id"] for f in fix_log.FIXES]
    assert len(ids) == len(set(ids))
    for f in fix_log.FIXES:
        assert f["cause"] in fix_log.CAUSES
        assert all(q in fix_log.QA for q in f["tests"]), f["id"]
        assert f["tests"] or f.get("scenario"), f"{f['id']} has no way to retest"
        for key in ("title", "found", "why", "fix", "where", "before"):
            assert f[key], (f["id"], key)


def test_now_is_read_from_the_latest_runs_newest_first():
    qa18 = fix_log.QA["QA-18"]
    lab = {"tests": [{"test_id": qa18, "passed": 2, "failed": 1}]}
    out = fix_log.fixes(lab)
    assert out[0]["id"] == fix_log.FIXES[-1]["id"] == "FIX-13"
    assert out[0]["now"] == {"passed": 2, "finished": 3, "holding": False}
    alert = next(f for f in out if f["id"] == "FIX-09")
    assert alert["now"]["finished"] == 0 and alert["scenario"]


def test_qa_names_map_to_test_ids():
    assert set(fix_log.QA.values()) == set(qa_lab.TESTS)


def test_api_lab_includes_the_fixes(client):
    body = client.get("/api/lab").json()
    assert [f["id"] for f in body["fixes"]][:2] == ["FIX-13", "FIX-12"]
