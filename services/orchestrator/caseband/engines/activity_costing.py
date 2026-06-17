"""activity_costing engine — find the real cost driver. Wraps tools.backbone so the
existing deterministic gate is reused behind the engine interface."""
from __future__ import annotations

from ..tools import backbone as bb
from .base import EngineVerdict, register

key = "activity_costing"


def validate(params: dict) -> EngineVerdict:
    r = bb.validate(params)
    return EngineVerdict(validated=r.validated, answer=r.true_driver,
                         naive_guess=r.naive_guess, margin=r.margin, reasons=r.reasons)


def worksheet(params: dict) -> dict:
    return bb.student_table(params)


def _terms(params: dict, key: str) -> list[str]:
    """The key plus its human label, normalised so 'cnc_machining' matches
    'cnc machining'."""
    label = next((a.get("label", "") for a in params.get("activities", [])
                  if a.get("key") == key), "")
    raw = [key, key.replace("_", " "), label]
    return [t.lower() for t in raw if t]


def grade_analysis(params: dict, answer: str) -> dict:
    """Score whether the student named the true cost driver (0/1/2)."""
    r = bb.validate(params)
    a = (answer or "").strip().lower()
    if r.true_driver and any(t in a for t in _terms(params, r.true_driver)):
        return {"score": 2, "correct": r.true_driver, "note": "named the true cost driver"}
    if r.naive_guess and any(t in a for t in _terms(params, r.naive_guess)):
        return {"score": 0, "correct": r.true_driver,
                "note": "anchored on the naive (high direct-cost) guess"}
    return {"score": 1, "correct": r.true_driver,
            "note": "partial / did not clearly identify the driver"}


def example_params() -> dict:
    from ..agents.case_designer import example_case
    return example_case().backbone.__dict__


register(key, __import__(__name__, fromlist=["_"]))
