#!/usr/bin/env python3
"""intake_interviewer invariants: asks until enough context, duration->checkpoints.
No API needed.

    python3 tests/test_interview.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.agents.interview import InterviewAgent, checkpoints_for, parse_minutes  # noqa: E402


def test_checkpoints_scale_and_clamp():
    assert checkpoints_for(15) == 2          # clamp floor
    assert checkpoints_for(30) == 2
    assert checkpoints_for(60) == 4
    assert checkpoints_for(90) == 6
    assert checkpoints_for(180) == 6         # clamp ceiling


def test_parse_minutes():
    assert parse_minutes("about 45 minutes") == 45
    assert parse_minutes("no number here") == 45    # default


def test_interview_asks_until_ready():
    a = InterviewAgent()
    s = a.start()
    assert s["pending"] == "course" and not s["ready"]
    s = a.step(s, "ISOM 599 — marketing ROI")
    assert s["pending"] == "assignment" and not s["ready"]
    s = a.step(s, "Decide a marketing budget that clears a 15% ROI")
    assert s["pending"] == "materials" and not s["ready"]
    s = a.step(s, "Gross profit was $1.8B; last spend was $300M")
    assert s["pending"] == "duration" and not s["ready"]
    s = a.step(s, "around 60 minutes")
    assert s["ready"] is True
    assert s["checkpoints"] == 4
    assert s["brief"]["duration_minutes"] == 60
    assert s["brief"]["document"].startswith("Gross profit")
    assert s["brief"]["context"]["assignment"].startswith("Decide")


def test_empty_message_does_not_advance():
    a = InterviewAgent()
    s = a.start()
    s2 = a.step(s, "   ")
    assert s2["pending"] == "course" and not s2["ready"]   # still waiting on course


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
