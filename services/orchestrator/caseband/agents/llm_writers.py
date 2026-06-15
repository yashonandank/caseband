"""Live (LLM-backed) writers'-room agents. Same contract as the deterministic
mocks: .act() returns STATE_PATCH messages; the reducer enforces ownership. The
LLM authors content only — it never writes the CasePackage directly."""
from __future__ import annotations

from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage
from .. import config
from ..llm import complete_json

_OBJ_SYSTEM = (
    "You are an expert business-school case designer. Given a case title and "
    "source type, propose 3 concise, measurable learning objectives. Respond as "
    'JSON: {\"objectives\": [{\"key\": \"obj1\", \"text\": \"...\"}, ...]} with keys '
    "obj1..obj3. Each text is one sentence, action-oriented."
)


class LLMObjectiveSetter(Agent):
    """Real OpenAI call (gpt-4o-mini) to author objectives from the case meta."""
    agent_id = "objective_setter"
    capabilities = ["objectives"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.objectives or not pkg.meta.get("title"):
            return []
        user = (f"Title: {pkg.meta['title']}\n"
                f"Source type: {pkg.meta.get('source_type', 'unknown')}")
        data = complete_json(_OBJ_SYSTEM, user, model=config.model_for(self.agent_id),
                             max_tokens=400)
        out = []
        for o in data.get("objectives", [])[:3]:
            if o.get("key") and o.get("text"):
                out.append(self._patch(room, "add_objective",
                                       {"key": o["key"], "text": o["text"]}))
        return out


_OUTCOME_SYSTEM = (
    "You are a quantitative case designer. Given the case title and learning "
    "objectives, author a deterministic numeric outcome model of kind 'formula' "
    "for a single KPI the student must hit. Respond as JSON: "
    '{"kpi_key": "roi", "target": {"value": 0.15, "comparator": ">=", "units": '
    '"ratio"}, "decision_variables": [{"key": "marketing_spend", "dp_key": "dp2", '
    '"type": "number", "bounds": [50000, 500000]}], "parameters": {"gain": 200000}, '
    '"spec": {"expr": "(gain - marketing_spend) / marketing_spend"}}. CRITICAL: every '
    "symbol in expr must be EITHER a decision_variable key OR a parameters key — "
    "list every fixed constant (e.g. gain, revenue, baseline) in parameters with a "
    "concrete number. Use only + - * / ** and parentheses (no function calls). Pick "
    "bounds and parameters so the target is actually reachable within the bounds."
)


class LLMOutcomeModeler(Agent):
    """Authors the outcome_model (formula kind). LLM proposes; reducer owns the field."""
    agent_id = "outcome_modeler"
    capabilities = ["outcome_model"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.outcome_model is not None or not pkg.objectives:
            return []
        user = (f"Title: {pkg.meta.get('title')}\nObjectives:\n"
                + "\n".join(f"- {o['key']}: {o['text']}" for o in pkg.objectives))
        data = complete_json(_OUTCOME_SYSTEM, user,
                             model=config.model_for(self.agent_id), max_tokens=400)
        model = {
            "kind": "formula",
            "kpi_key": data.get("kpi_key", "kpi"),
            "target": data.get("target", {"value": 0, "comparator": ">=", "units": ""}),
            "decision_variables": data.get("decision_variables", []),
            "parameters": data.get("parameters", {}),
            "spec": data.get("spec", {}),
            "pass_policy": "all",
        }
        return [self._patch(room, "set_outcome_model", model)]


_CHECKPOINT_SYSTEM = (
    "You design decision points for a business case. For EACH learning objective, "
    "author one decision point that exercises it. Respond as JSON: "
    '{"decision_points": [{"dp_key": "dp1", "maps_to_objective": "obj1", "prompt": '
    '"...", "options": [{"id": "a", "label": "..."}, {"id": "b", "label": "..."}]}]}. '
    "Use dp_key dp1..dpN aligned to the objectives in order."
)


class LLMCheckpointMapper(Agent):
    """Authors decision points via LLM; the objective<-dp linkage (set_tested_by)
    is emitted DETERMINISTICALLY from each dp's maps_to_objective, so Loop A's exit
    predicate is guaranteed regardless of LLM phrasing."""
    agent_id = "checkpoint_mapper"
    capabilities = ["decision_points"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.outcome_model is None:
            return []
        existing = {d["maps_to_objective"] for d in pkg.decision_points}
        todo = [o for o in pkg.objectives if o["key"] not in existing]
        if not todo:
            return []
        user = (f"Title: {pkg.meta.get('title')}\nObjectives:\n"
                + "\n".join(f"- {o['key']}: {o['text']}" for o in todo))
        data = complete_json(_CHECKPOINT_SYSTEM, user,
                             model=config.model_for(self.agent_id), max_tokens=700)
        authored = {d.get("maps_to_objective"): d for d in data.get("decision_points", [])}
        out: list[BandMessage] = []
        for i, obj in enumerate(todo, start=len(existing) + 1):
            dp = authored.get(obj["key"], {})
            dp_key = dp.get("dp_key") or f"dp{i}"
            out.append(self._patch(room, "add_decision_point", {
                "dp_key": dp_key,
                "maps_to_objective": obj["key"],
                "prompt": dp.get("prompt", f"Decision exercising: {obj['text']}"),
                "options": dp.get("options", []),
            }))
            # deterministic linkage -> guarantees exit predicate
            out.append(self._patch(room, "set_tested_by",
                                   {"objective_key": obj["key"], "dp_key": dp_key}))
        return out


_RUBRIC_SYSTEM = (
    "You write grading rubrics. For EACH objective, author one rubric criterion with "
    "a 0/1/2 level scale. Respond as JSON: {\"criteria\": [{\"criterion_key\": "
    '"c_obj1", "objective_key": "obj1", "levels": [{"score": 0, "descriptor": "..."}, '
    '{"score": 1, "descriptor": "..."}, {"score": 2, "descriptor": "..."}]}]}.'
)


class LLMRubricCreator(Agent):
    """Authors rubric criteria via LLM; weights normalized deterministically."""
    agent_id = "rubric_creator"
    capabilities = ["rubric"]

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if not pkg.decision_points:
            return []
        have = {c["objective_key"] for c in pkg.rubric}
        todo = [o for o in pkg.objectives if o["key"] not in have]
        if not todo:
            return []
        user = "Objectives:\n" + "\n".join(f"- {o['key']}: {o['text']}" for o in todo)
        data = complete_json(_RUBRIC_SYSTEM, user,
                             model=config.model_for(self.agent_id), max_tokens=700)
        authored = {c.get("objective_key"): c for c in data.get("criteria", [])}
        weight = round(1.0 / max(len(pkg.objectives), 1), 3)
        default_levels = [{"score": 0, "descriptor": "absent"},
                          {"score": 1, "descriptor": "adequate"},
                          {"score": 2, "descriptor": "strong"}]
        out: list[BandMessage] = []
        for obj in todo:
            c = authored.get(obj["key"], {})
            out.append(self._patch(room, "add_rubric_criterion", {
                "criterion_key": c.get("criterion_key", f"c_{obj['key']}"),
                "objective_key": obj["key"],
                "levels": c.get("levels", default_levels),
                "weight": weight,
            }))
        return out
