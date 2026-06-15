"""CasePackage — the canonical blackboard (AGENT_SPECS §1).

Canonical home in production is Supabase case_versions.case_package (JSONB);
the relational tables are reducer-materialized projections. Here it is an
in-memory dataclass for the offline Loop A demo."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CasePackage:
    meta: dict[str, Any] = field(default_factory=lambda: {"status": "intake", "title": None})
    objectives: list[dict[str, Any]] = field(default_factory=list)   # {key,text,tested_by}
    decision_points: list[dict[str, Any]] = field(default_factory=list)  # {dp_key,maps_to_objective,...}
    outcome_model: dict[str, Any] | None = None
    rubric: list[dict[str, Any]] = field(default_factory=list)
    exhibits: list[dict[str, Any]] = field(default_factory=list)
    redteam_findings: list[dict[str, Any]] = field(default_factory=list)
    solvability: dict[str, Any] = field(default_factory=lambda: {"validated": False})

    # ---- Loop exit predicates (AGENT_SPECS §6) -------------------------------
    def all_objectives_tested(self) -> bool:
        """Loop A exit: every objective is exercised by a decision point."""
        return bool(self.objectives) and all(o.get("tested_by") for o in self.objectives)

    def open_blocking_findings(self) -> list[dict[str, Any]]:
        return [f for f in self.redteam_findings
                if f.get("status") == "open" and f.get("severity") in ("blocker", "major")]

    def redteam_clean(self) -> bool:
        """Loop B exit: 0 open blocker/major findings AND solvability validated."""
        return not self.open_blocking_findings() and bool(self.solvability.get("validated"))

    def objective(self, key: str) -> dict[str, Any] | None:
        return next((o for o in self.objectives if o.get("key") == key), None)
