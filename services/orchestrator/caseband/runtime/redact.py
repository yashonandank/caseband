"""Answer-leak redaction (AGENT_SPECS §9). A runtime agent that talks to the
student (coach, facilitator, stakeholder) — and the student UI itself — may only
see a redacted view of the deployed CasePackage. The 'answer' must never leak:

  * outcome_model.spec.expr   — the formula (compute the exact optimum)
  * outcome_model.parameters  — the fixed constants behind the formula
  * solvability.calibration   — the witness is literally a passing answer
  * solvability.sensitivity   — reveals which lever matters most
  * rubric levels/weights      — exactly what graders reward (gameable)
  * redteam_findings           — internal authoring notes

The student DOES see: the brief, objectives, decision points + options, the KPI
name and the levers (with bounds) they control, and the stated target goal. This
is a pure function: same package -> same view; it never mutates the input."""
from __future__ import annotations
from typing import Any

from ..models.case_package import CasePackage

# Fields that, if exposed, hand the student the answer or a shortcut to it.
_SECRET_OUTCOME_KEYS = ("spec", "parameters")


def student_view(pkg: CasePackage) -> dict[str, Any]:
    """The redacted, student-safe projection of a deployed case."""
    view: dict[str, Any] = {
        "meta": {"title": pkg.meta.get("title"), "status": pkg.meta.get("status")},
        "objectives": [{"key": o["key"], "text": o["text"]} for o in pkg.objectives],
        "decision_points": [
            {"dp_key": d["dp_key"], "prompt": d.get("prompt"),
             "options": [{"id": op.get("id"), "label": op.get("label")}
                         for op in d.get("options", [])]}
            for d in pkg.decision_points
        ],
        # rubric: criteria/objectives are visible so students know what's assessed,
        # but NOT the weights or level descriptors (gameable).
        "rubric": [{"criterion_key": c.get("criterion_key"),
                    "objective_key": c.get("objective_key")} for c in pkg.rubric],
    }
    if pkg.outcome_model:
        m = pkg.outcome_model
        view["outcome_model"] = {
            "kind": m.get("kind"),
            "kpi_key": m.get("kpi_key"),
            "target": m.get("target"),                 # the GOAL is fair to state
            "decision_variables": [
                {"key": dv.get("key"), "bounds": dv.get("bounds"), "type": dv.get("type")}
                for dv in m.get("decision_variables", [])
            ],
        }
    return view


def leaks(view: dict[str, Any]) -> list[str]:
    """Return any answer-revealing keys present in a view (empty == safe). Used by
    the redaction test as a hard invariant."""
    found: list[str] = []
    om = view.get("outcome_model", {})
    for k in _SECRET_OUTCOME_KEYS:
        if k in om:
            found.append(f"outcome_model.{k}")
    if "solvability" in view:
        found.append("solvability")
    if "redteam_findings" in view:
        found.append("redteam_findings")
    for c in view.get("rubric", []):
        if "weight" in c or "levels" in c:
            found.append("rubric.weight/levels")
            break
    return found
