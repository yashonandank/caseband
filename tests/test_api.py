#!/usr/bin/env python3
"""API integration test: drive the whole lifecycle over HTTP with TestClient.
No external services, no API keys.

    python3 tests/test_api.py
    pytest tests/test_api.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient            # noqa: E402
from services.api.app import app                     # noqa: E402

client = TestClient(app)

MODEL = {
    "kind": "formula", "kpi_key": "roi", "pass_policy": "all",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}
OBJECTIVES = [{"key": "o1", "text": "Diagnose ROI"}, {"key": "o2", "text": "Recommend spend"}]


def _author():
    r = client.post("/cases", json={"title": "Acme ROI", "objectives": OBJECTIVES,
                                     "model": MODEL})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_detects_10k():
    r = client.post("/ingest", json={"text": "FORM 10-K\nTotal revenue was $4,200 million."})
    assert r.status_code == 200
    assert r.json()["source_type"] == "10K"


def test_author_then_redteam():
    cid = _author()
    body = client.post(f"/cases/{cid}/redteam").json()
    assert body["converged"] and body["validated"] is True
    assert body["redteam_clean"] is True


def test_student_view_is_redacted():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    view = client.get(f"/cases/{cid}", params={"view": "student"}).json()
    assert "spec" not in view.get("outcome_model", {})       # formula hidden
    assert "solvability" not in view
    full = client.get(f"/cases/{cid}").json()
    assert full["outcome_model"]["spec"]["expr"]             # faculty sees all


def test_run_submit_returns_feedback_not_grade():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    run_id = client.post("/runs", json={"case_id": cid, "student_id": "stu_1"}).json()["run_id"]
    fb = client.post(f"/runs/{run_id}/submit",
                     json={"assignment": {"marketing_spend": 60000},
                           "rubric_scores": {"c_o1": 2, "c_o2": 2}}).json()
    assert fb["released"] is False                  # student sees feedback, not a number
    assert "overall_pass" not in fb and "rubric_score" not in fb
    assert fb["objectives"]                          # qualitative per-criterion feedback


def test_finalize_releases_the_number():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    run_id = client.post("/runs", json={"case_id": cid, "student_id": "stu_2"}).json()["run_id"]
    client.post(f"/runs/{run_id}/submit",
                json={"assignment": {"marketing_spend": 60000},
                      "rubric_scores": {"c_o1": 2, "c_o2": 2}})
    released = client.post(f"/runs/{run_id}/finalize", json={"reviewer_id": "prof_1"}).json()
    assert released["released"] is True and released["grade"]["overall_pass"] is True


def test_revise_loop_revalidates():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    ok = client.post(f"/cases/{cid}/revise",
                     json={"intent": {"op": "set_outcome_target",
                                      "field": "outcome_model", "value": 0.10}}).json()
    assert ok["approvable"] and ok["applied"]
    bad = client.post(f"/cases/{cid}/revise",
                      json={"intent": {"op": "set_outcome_target",
                                       "field": "outcome_model", "value": 999},
                            "apply": True}).json()
    assert bad["approvable"] is False and bad["applied"] is False


def test_access_code_join_then_play():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    code = client.post(f"/cases/{cid}/access-code").json()["code"]
    assert code and client.post(f"/cases/{cid}/access-code").json()["code"] == code  # stable
    joined = client.post("/join", json={"code": code.lower(), "name": "Dana Lee"}).json()
    assert joined["case_id"] == cid and joined["run_id"]
    fb = client.post(f"/runs/{joined['run_id']}/submit",
                     json={"assignment": {"marketing_spend": 60000},
                           "rubric_scores": {"c_o1": 2, "c_o2": 2}}).json()
    assert fb["released"] is False


def test_join_rejects_bad_code():
    assert client.post("/join", json={"code": "NOPE-123", "name": "X"}).status_code == 404


def test_coach_gives_socratic_help_no_leak():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    run_id = client.post("/runs", json={"case_id": cid, "student_id": "stu_3"}).json()["run_id"]
    out = client.post(f"/runs/{run_id}/coach",
                      json={"message": "I'm stuck on the marketing spend decision"}).json()
    assert out["reply"] and out["refused"] is False
    assert "0.15" not in out["reply"]               # never leaks the target


def test_faculty_edit_revalidates():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    ok = client.post(f"/cases/{cid}/faculty/edit",
                     json={"op": "set_outcome_target", "field": "outcome_model",
                           "value": 0.10, "apply": True}).json()
    assert ok["approvable"] and ok["applied"]
    bad = client.post(f"/cases/{cid}/faculty/edit",
                      json={"op": "set_outcome_target", "field": "outcome_model",
                            "value": 999}).json()
    assert bad["approvable"] is False


def test_interview_chat_until_ready():
    s = client.post("/cases/interview", json={}).json()      # start
    assert s["pending"] == "course" and not s["ready"]
    for msg in ["ISOM 599 marketing ROI", "Decide a budget hitting 15% ROI",
                "Gross profit $1.8B, last spend $300M"]:
        s = client.post("/cases/interview", json={"state": s, "message": msg}).json()
        assert not s["ready"]
    s = client.post("/cases/interview", json={"state": s, "message": "60 minutes"}).json()
    assert s["ready"] is True and s["checkpoints"] == 4
    assert s["brief"]["document"].startswith("Gross profit")


def test_whatif_returns_levers_no_target():
    cid = _author()
    client.post(f"/cases/{cid}/redteam")
    body = client.post(f"/cases/{cid}/whatif",
                       json={"assignment": {"marketing_spend": 100000}}).json()
    assert body["kpi_key"] == "roi"
    assert "marketing_spend" in body["levers"]
    assert "target" not in str(body)              # no answer leak


def test_unknown_case_404():
    assert client.post("/cases/nope/redteam").status_code == 404


def test_home_serves_ui():
    r = client.get("/")
    assert r.status_code == 200
    assert "Caseband" in r.text and "Ingest" in r.text


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
