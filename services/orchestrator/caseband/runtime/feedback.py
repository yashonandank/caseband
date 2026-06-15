"""feedback — split "feedback now" from "grade later" (gap e).

When a student completes a case, they should immediately receive QUALITATIVE,
formative feedback (what they did well, what to reconsider, whether they met each
objective qualitatively) — but NOT the numeric grade. The numeric grade is already
computed by tools.grader (an `ai_draft`), but it is withheld until the professor
walks it through the lifecycle and FINALIZES it. Only a finalized grade releases
the numbers to the student.

This mirrors redact.py's spirit: deterministic code owns what a student may see;
same grade -> same student view; the function never mutates its input. An LLM may
optionally *phrase* the prose (see _phrase_*), but the release gate and the
met/partially-met/revisit derivation are 100% deterministic so the offline test
path is exact.

  is_released(grade)        -> bool   (True iff status == "finalized")
  student_feedback(grade)   -> dict   (ALWAYS safe to show a student)

Release gate
------------
Pre-finalize the returned dict contains ONLY qualitative levels + next-step
prompts and a single qualitative line on the KPI goal. It contains NO numeric
grade fields: not rubric_score, not overall_pass, not numeric_pass, and not
kpi_value.

KPI value decision
------------------
We WITHHOLD kpi_value (the student's achieved KPI) until finalize, and pre-finalize
expose only a qualitative "met / not yet met the KPI goal" line WITHOUT any number
or threshold. Rationale: the case's target threshold is deliberately hidden from
students (see redact.py — level descriptors/weights are secret; the achieved value
is the answer made concrete). If a student saw their achieved kpi_value together
with a pass/fail signal, repeated resubmissions would let them binary-search the
hidden target and back out the exact optimum, defeating the solvability design.
The qualitative met/not-met line carries the formative signal without leaking the
number. After finalize the professor has locked the grade, so the numbers (overall,
rubric_score, kpi_value/target) are released together.
"""
from __future__ import annotations
from typing import Any

# rubric levels are 0/1/2 (see grader._MAX_LEVEL). Map a raw level to a
# qualitative, non-numeric formative label. This is the per-criterion signal the
# student sees immediately — derived from the level, never from the weight/number.
_LEVEL_LABELS = {
    0: "revisit",          # absent / not yet demonstrated
    1: "partially met",    # adequate but with room to grow
    2: "met",              # strong
}

_NEXT_STEP = {
    "revisit": "Revisit this objective — your response did not yet demonstrate it. "
               "Look back at the relevant decision points and try a fuller approach.",
    "partially met": "You're on the way here. Strengthen this by adding more depth or "
                     "evidence to fully meet the objective.",
    "met": "Well done — you clearly met this objective. Keep this up.",
}


def is_released(grade: dict[str, Any]) -> bool:
    """True iff the professor has finalized the grade (numbers may be shown)."""
    return grade.get("status") == "finalized"


def _criterion_feedback(b: dict[str, Any]) -> dict[str, Any]:
    """One per-criterion qualitative entry derived from its level (no numbers)."""
    level = int(b.get("score", 0))
    label = _LEVEL_LABELS.get(level, "revisit")
    return {
        "criterion_key": b.get("criterion_key"),
        "objective_key": b.get("objective_key"),
        "level": label,                       # "met" / "partially met" / "revisit"
        "next_step": _NEXT_STEP[label],
    }


def _kpi_qualitative(grade: dict[str, Any]) -> str | None:
    """A qualitative line on the KPI goal — NO value, NO threshold. None if the
    case has no numeric half (rubric_only / no outcome_model)."""
    numeric_pass = grade.get("numeric_pass")
    if numeric_pass is None:
        return None
    kpi_key = grade.get("kpi_key") or "the target metric"
    if numeric_pass:
        return f"You met the goal for {kpi_key}."
    return (f"You have not yet met the goal for {kpi_key}. "
            f"Reconsider which levers move it and try again.")


def student_feedback(grade: dict[str, Any]) -> dict[str, Any]:
    """Student-safe formative view of a grade. ALWAYS safe to show.

    Pre-finalize (status ai_draft/reviewed): qualitative only — per-criterion
    levels, next-step prompts, a qualitative KPI line, and released=False. NO
    numeric grade fields and no target leak.

    Finalized: the same qualitative body PLUS a `grade` block with the released
    numbers (overall_pass, rubric_score, kpi_key/kpi_value, numeric_pass).
    """
    breakdown = grade.get("rubric_breakdown", []) or []
    criteria = [_criterion_feedback(b) for b in breakdown]

    view: dict[str, Any] = {
        "released": is_released(grade),
        "objectives": criteria,                 # per-criterion qualitative levels
        "summary": _summary(criteria),
    }
    kpi_line = _kpi_qualitative(grade)
    if kpi_line is not None:
        view["kpi_feedback"] = kpi_line

    if is_released(grade):
        # Professor has finalized: release the numbers alongside the prose.
        view["grade"] = {
            "overall_pass": grade.get("overall_pass"),
            "rubric_score": grade.get("rubric_score"),
            "numeric_pass": grade.get("numeric_pass"),
            "kpi_key": grade.get("kpi_key"),
            "kpi_value": grade.get("kpi_value"),
        }
    return view


def _summary(criteria: list[dict[str, Any]]) -> str:
    """A short, encouraging, qualitative overview — no scores."""
    if not criteria:
        return "Submission received. Detailed feedback will follow."
    met = sum(1 for c in criteria if c["level"] == "met")
    partial = sum(1 for c in criteria if c["level"] == "partially met")
    revisit = sum(1 for c in criteria if c["level"] == "revisit")
    parts = []
    if met:
        parts.append(f"{met} objective(s) clearly met")
    if partial:
        parts.append(f"{partial} partially met")
    if revisit:
        parts.append(f"{revisit} to revisit")
    body = ", ".join(parts)
    if revisit == 0 and partial == 0:
        return f"Strong work — {body}. See the notes below."
    return f"Good progress — {body}. See the per-objective notes for next steps."
