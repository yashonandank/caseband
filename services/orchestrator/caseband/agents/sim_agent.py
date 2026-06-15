"""sim_agent — RUNTIME numeric what-if (AGENT_SPECS §9). Conditional on a numeric
outcome_model (mirrors sql_agent being conditional on a database). It lets a student
see how moving a decision variable moves the KPI, WITHOUT ever revealing the target
or whether they pass — that stays with the grader. Deterministic: reuses
tools.outcome_engine. Plain callable (runtime), never a blackboard writer, never Band."""
from __future__ import annotations
from typing import Any

from ..tools import outcome_engine as engine


class SimAgent:
    agent_id = "sim_agent"

    def _full_env(self, model: dict[str, Any], assignment: dict[str, float]) -> dict[str, float]:
        """Assignment with any unset decision variable defaulted to its midpoint."""
        env = dict(assignment)
        for dv in model.get("decision_variables", []):
            k = dv.get("key")
            if k not in env:
                b = dv.get("bounds")
                env[k] = (float(b[0]) + float(b[1])) / 2 if isinstance(b, (list, tuple)) and len(b) == 2 else 0.0
        return env

    def kpi(self, model: dict[str, Any], assignment: dict[str, float]) -> float:
        """Current KPI for the student's choices (numeric models only)."""
        if model.get("kind") != "formula":
            raise ValueError("sim_agent only runs on numeric (formula) outcome models")
        return engine.evaluate(model, self._full_env(model, assignment))

    def what_if(self, model: dict[str, Any], assignment: dict[str, float]) -> dict[str, Any]:
        """Per decision variable: the KPI at its low/high bound (others held at the
        current assignment) and which direction raises the KPI. No target leaked."""
        env = self._full_env(model, assignment)
        current = engine.evaluate(model, env)
        levers: dict[str, Any] = {}
        for dv in model.get("decision_variables", []):
            k, b = dv.get("key"), dv.get("bounds")
            if not (isinstance(b, (list, tuple)) and len(b) == 2):
                continue
            at_low = engine.evaluate(model, {**env, k: float(b[0])})
            at_high = engine.evaluate(model, {**env, k: float(b[1])})
            direction = "up" if at_high > at_low else ("down" if at_high < at_low else "flat")
            levers[k] = {"current": current, "at_low": at_low, "at_high": at_high,
                         "raises_kpi_toward": "high" if direction == "up"
                         else ("low" if direction == "down" else "flat")}
        return {"kpi_key": model.get("kpi_key"), "current": current, "levers": levers}
