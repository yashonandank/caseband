"""Writers'-room mocks (deterministic). They emit STATE_PATCHes that drive Loop A
to its exit predicate: every objective.tested_by != null.

  objective_setter  -> adds learning objectives
  outcome_modeler   -> authors the outcome_model (formula KPI)  [NEW agent]
  checkpoint_mapper -> adds a decision point per objective AND links it (set_tested_by)
  rubric_creator    -> adds a rubric criterion per objective

Each agent is idempotent: it only acts on work not yet present, so the conductor
can poll them round-robin until convergence."""
from __future__ import annotations
from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage


class ObjectiveSetter(Agent):
    agent_id = "objective_setter"
    capabilities = ["objectives"]

    def __init__(self, objectives: list[dict]):
        self._spec = objectives

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.objectives or not pkg.meta.get("title"):
            return []
        return [self._patch(room, "add_objective", o) for o in self._spec]


class OutcomeModeler(Agent):
    agent_id = "outcome_modeler"
    capabilities = ["outcome_model"]

    def __init__(self, model: dict):
        self._model = model

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.outcome_model is not None or not pkg.objectives:
            return []
        return [self._patch(room, "set_outcome_model", self._model)]


class CheckpointMapper(Agent):
    agent_id = "checkpoint_mapper"
    capabilities = ["decision_points"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.outcome_model is None:
            return []  # decisions must bind to a defined model
        out: list[BandMessage] = []
        existing = {d["maps_to_objective"] for d in pkg.decision_points}
        for i, obj in enumerate(pkg.objectives, start=1):
            if obj["key"] in existing:
                continue
            dp_key = f"dp{i}"
            out.append(self._patch(room, "add_decision_point", {
                "dp_key": dp_key,
                "maps_to_objective": obj["key"],
                "prompt": f"Decision exercising: {obj['text']}",
                "options": [{"id": "a", "label": "Option A"},
                            {"id": "b", "label": "Option B"}],
            }))
            out.append(self._patch(room, "set_tested_by", {
                "objective_key": obj["key"], "dp_key": dp_key,
            }))
        return out


class RubricCreator(Agent):
    agent_id = "rubric_creator"
    capabilities = ["rubric"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if not pkg.decision_points:
            return []
        out: list[BandMessage] = []
        have = {c["objective_key"] for c in pkg.rubric}
        for obj in pkg.objectives:
            if obj["key"] in have:
                continue
            out.append(self._patch(room, "add_rubric_criterion", {
                "criterion_key": f"c_{obj['key']}",
                "objective_key": obj["key"],
                "levels": [{"score": 0, "descriptor": "absent"},
                           {"score": 1, "descriptor": "adequate"},
                           {"score": 2, "descriptor": "strong"}],
                "weight": round(1.0 / max(len(pkg.objectives), 1), 3),
            }))
        return out
