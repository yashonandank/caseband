"""grader — deterministic scoring + grade lifecycle (AGENT_SPECS §8).

Grading splits the way the rest of Caseband does: the LLM may *judge* open-ended
rubric answers into per-criterion scores, but combining those scores, evaluating
the numeric KPI, and applying the pass policy is DETERMINISTIC here. Same
submission -> same grade. Reuses outcome_engine for the numeric half.

A grade is a plain dict mirroring the Supabase `grades` row, including the
lifecycle the schema models: ai_draft -> reviewed -> finalized. The AI grade is
released to the student immediately as `ai_draft`; the professor reviews/overrides
(-> reviewed) and then finalizes (-> finalized). Every professor edit is audited
(edited_by / edited_at / override_note).

submission = {
    "assignment":    {"marketing_spend": 60000},   # decision-variable values
    "rubric_scores": {"c_o1": 2, "c_o2": 1},        # per-criterion level reached
}
"""
from __future__ import annotations
from typing import Any

from . import outcome_engine as engine

# Lifecycle state machine. Student sees ai_draft immediately; professor advances it.
_TRANSITIONS = {"ai_draft": {"reviewed"}, "reviewed": {"finalized"}, "finalized": set()}
_MAX_LEVEL = 2          # rubric levels are 0/1/2 (see rubric_creator)
_DEFAULT_RUBRIC_PASS = 0.6


class GradeError(ValueError):
    """Illegal lifecycle transition or malformed submission."""


def _rubric_score(rubric: list[dict[str, Any]], scores: dict[str, int]) -> tuple[float, list[dict]]:
    """Weighted rubric score in [0,1] plus a per-criterion breakdown."""
    total, breakdown = 0.0, []
    for c in rubric:
        key = c.get("criterion_key")
        weight = float(c.get("weight", 0))
        raw = int(scores.get(key, 0))
        fraction = max(0.0, min(raw / _MAX_LEVEL, 1.0))
        total += weight * fraction
        breakdown.append({"criterion_key": key, "objective_key": c.get("objective_key"),
                          "score": raw, "weight": weight})
    return round(total, 4), breakdown


def grade_submission(outcome_model: dict[str, Any] | None,
                     rubric: list[dict[str, Any]],
                     submission: dict[str, Any],
                     rubric_pass: float = _DEFAULT_RUBRIC_PASS,
                     edited_at: str | None = None) -> dict[str, Any]:
    """Produce an `ai_draft` grade. Deterministic: KPI via outcome_engine, rubric
    via weighted levels, overall via the model's pass_policy."""
    assignment = submission.get("assignment", {})
    scores = submission.get("rubric_scores", {})

    kpi_value: float | None = None
    numeric_pass: bool | None = None
    model = outcome_model or {}
    if model.get("kind") == "formula" and engine.expr_of(model):
        if engine.undefined_symbols(model):
            raise GradeError(f"outcome_model has undefined symbols: "
                             f"{sorted(engine.undefined_symbols(model))}")
        kpi_value = engine.evaluate(model, assignment)
        numeric_pass = engine.passes(kpi_value, model["target"])

    rubric_score, breakdown = _rubric_score(rubric, scores)
    rubric_pass_bool = rubric_score >= rubric_pass

    policy = model.get("pass_policy", "all")
    if policy == "numeric_only":
        overall = bool(numeric_pass)
    elif policy == "rubric_only" or numeric_pass is None:
        overall = rubric_pass_bool
    else:  # "all" — both halves must pass
        overall = bool(numeric_pass) and rubric_pass_bool

    return {
        "status": "ai_draft",
        "kpi_key": model.get("kpi_key"),
        "kpi_value": kpi_value,
        "numeric_pass": numeric_pass,
        "rubric_score": rubric_score,
        "rubric_pass": rubric_pass_bool,
        "rubric_breakdown": breakdown,
        "pass_policy": policy,
        "overall_pass": overall,
        "edited_by": None,
        "edited_at": edited_at,
        "override_note": None,
    }


def _transition(grade: dict[str, Any], target: str) -> None:
    cur = grade.get("status")
    if target not in _TRANSITIONS.get(cur, set()):
        raise GradeError(f"illegal grade transition {cur!r} -> {target!r}")
    grade["status"] = target


def review(grade: dict[str, Any], reviewer_id: str, *,
           score_overrides: dict[str, int] | None = None,
           rubric: list[dict[str, Any]] | None = None,
           override_note: str | None = None, at: str | None = None) -> dict[str, Any]:
    """Professor review (ai_draft -> reviewed). Optional per-criterion overrides
    recompute the rubric score; every edit is audited. Returns a new grade dict."""
    g = dict(grade)
    _transition(g, "reviewed")
    if score_overrides and rubric is not None:
        new_scores = {b["criterion_key"]: b["score"] for b in g["rubric_breakdown"]}
        new_scores.update(score_overrides)
        g["rubric_score"], g["rubric_breakdown"] = _rubric_score(rubric, new_scores)
        g["rubric_pass"] = g["rubric_score"] >= _DEFAULT_RUBRIC_PASS
        policy = g.get("pass_policy", "all")
        if policy == "numeric_only":
            g["overall_pass"] = bool(g["numeric_pass"])
        elif policy == "rubric_only" or g["numeric_pass"] is None:
            g["overall_pass"] = g["rubric_pass"]
        else:
            g["overall_pass"] = bool(g["numeric_pass"]) and g["rubric_pass"]
    g["edited_by"] = reviewer_id
    g["edited_at"] = at
    g["override_note"] = override_note
    return g


def finalize(grade: dict[str, Any], reviewer_id: str, at: str | None = None) -> dict[str, Any]:
    """Lock the grade (reviewed -> finalized)."""
    g = dict(grade)
    _transition(g, "finalized")
    g["edited_by"] = reviewer_id
    g["edited_at"] = at
    return g
