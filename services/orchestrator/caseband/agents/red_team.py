"""Red-Team room agents (Loop B). This is the originality wedge: a case is only
shipped once it is PROVABLY solvable and free of structural defects.

  solvability_validator -> runs calibration + sensitivity on the outcome_model and
                           sets `solvability` (the 'not random' guarantee). Pure
                           math (no LLM): the deterministic outcome_engine decides.
  red_team_lead         -> structural critic. Re-scans the package each round,
                           raises a FINDING per invariant violation, and RESOLVES
                           a finding once its violation is gone (raiser + verifier).

Loop B exit (CasePackage.redteam_clean): 0 open blocker/major findings AND
solvability.validated. Both owners are single per the ownership matrix."""
from __future__ import annotations

from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage
from ..tools import outcome_engine as engine


class SolvabilityValidator(Agent):
    """Proves the outcome_model is reachable AND that every decision variable moves
    the KPI. Writes the proof (calibration + sensitivity) into `solvability`."""
    agent_id = "solvability_validator"
    capabilities = ["solvability"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        model = pkg.outcome_model
        if model is None or pkg.solvability.get("validated"):
            return []  # nothing to validate yet, or already proven (idempotent)

        kind = model.get("kind")
        if kind == "rubric_only":
            # No numeric target to reach — solvable by construction (rubric grades it).
            return [self._patch(room, "set_solvability",
                                {"validated": True, "method": "rubric_only", "issues": []})]

        undef = engine.undefined_symbols(model)
        if undef:
            return [self._patch(room, "set_solvability", {
                "validated": False, "kpi_key": model.get("kpi_key"),
                "issues": [{"kind": "undefined_symbols", "symbols": sorted(undef)}],
            })]

        cal = engine.calibrate(model)
        sens = engine.sensitivity(model)
        zero_effect = sorted(k for k, v in sens.items() if not v.get("moves"))

        issues: list[dict] = []
        if not cal.get("reachable"):
            issues.append({"kind": "target_unreachable", "closest_kpi": cal.get("kpi")})
        if zero_effect:
            issues.append({"kind": "zero_effect_variables", "variables": zero_effect})

        return [self._patch(room, "set_solvability", {
            "validated": not issues,
            "kpi_key": model.get("kpi_key"),
            "calibration": cal,
            "sensitivity": sens,
            "issues": issues,
        })]


class StructuralCritic(Agent):
    """Deterministic red-team critic. Raises a finding per invariant violation and
    resolves it once fixed — so Loop B converges exactly when the case is clean."""
    agent_id = "red_team_lead"
    capabilities = ["redteam_findings"]
    # Only resolve findings THIS critic raises, so other critics (e.g. QACritic)
    # can share the redteam_findings list without each clearing the other's.
    _OWNS = ("dp_options:", "rubric_missing:", "rubric_weights_sum")

    def _violations(self, pkg: CasePackage) -> dict[str, dict]:
        """finding_key -> finding for every CURRENT structural defect."""
        v: dict[str, dict] = {}
        for d in pkg.decision_points:
            if len(d.get("options", [])) < 2:
                k = f"dp_options:{d['dp_key']}"
                v[k] = {"finding_key": k, "severity": "major", "target": "decision_points",
                        "title": f"Decision point {d['dp_key']} offers fewer than 2 options"}
        rubric_objs = {c.get("objective_key") for c in pkg.rubric}
        for o in pkg.objectives:
            if o["key"] not in rubric_objs:
                k = f"rubric_missing:{o['key']}"
                v[k] = {"finding_key": k, "severity": "major", "target": "rubric",
                        "title": f"Objective {o['key']} has no rubric criterion"}
        if pkg.rubric:
            total = sum(c.get("weight", 0) for c in pkg.rubric)
            if abs(total - 1.0) > 0.05:
                k = "rubric_weights_sum"
                v[k] = {"finding_key": k, "severity": "major", "target": "rubric",
                        "title": f"Rubric weights sum to {round(total, 3)}, not 1.0"}
        return v

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        viol = self._violations(pkg)
        open_now = {f["finding_key"] for f in pkg.redteam_findings
                    if f.get("status") == "open"}
        out: list[BandMessage] = []
        for key, finding in viol.items():
            if key not in open_now:                       # raise new violations
                out.append(self._patch(room, "add_finding", finding))
        for f in pkg.redteam_findings:                    # resolve cleared ones
            key = f["finding_key"]
            if (f.get("status") == "open" and key not in viol
                    and key.startswith(self._OWNS)):
                out.append(self._patch(room, "resolve_finding",
                                       {"finding_key": key, "status": "fixed"}))
        return out
