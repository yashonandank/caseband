"""professor_liaison (AGENT_SPECS §10) — the faculty HITL console.

The professor talks to their case in natural language; the liaison is a
TRANSLATOR/ROUTER only. It owns no blackboard field: it converts intent into a
REVISE_REQUEST addressed to the field's owner (or a FINDING to red-team), shows a
confirm-before-apply diff, and — critically — every applied edit RE-ENTERS
validation (solvability + structural critic) before the case may be approved. The
liaison cannot let the professor approve a case their own edit just broke.

NL parsing (text -> intent) is the LLM half (LLMProfessorLiaison); everything that
touches the blackboard is deterministic and attributed to the owning agent, so the
ownership matrix still holds.

intent shape (closed set):
    {"op": "set_outcome_target", "field": "outcome_model", "value": 0.10}
    {"op": "add_objective",  "value": {"key": "o3", "text": "..."}}
    {"op": "edit_objective", "key": "o1", "value": {"text": "..."}}
    {"op": "remove_objective", "key": "o2"}
    {"op": "edit_decision_prompt", "key": "dp1", "value": {"prompt": "..."}}
    {"op": "edit_rubric_prompt",   "key": "c_o1", "value": {"prompt": "..."}}
    {"op": "add_rubric_criterion", "value": {"criterion_key","objective_key",...}}

Every op carries the field-root it touches so ownership routing stays explicit:

    OP_FIELD_ROOT[op] -> field-root -> FIELD_OWNER[field-root] -> owning agent

The reducer (ownership-enforcing, replayable) only exposes append/replace ops, so
edits and removals that the reducer cannot express are performed here as a single
deterministic, owner-attributed, purity-preserving (deepcopy) field rewrite. The
LLM never mutates state — it only PARSES the request and AUTHORS the new text.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Any

from .. import config
from ..llm import complete_json
from ..models.case_package import CasePackage
from ..models.messages import BandMessage, Verb
from ..ownership import FIELD_OWNER
from ..reducer import apply
from .red_team import SolvabilityValidator, StructuralCritic


# op -> the CasePackage field-root it edits (drives ownership routing for every op,
# including the edit/remove ops the reducer has no native verb for).
OP_FIELD_ROOT = {
    "set_outcome_target": "outcome_model",
    "add_objective": "objectives",
    "edit_objective": "objectives",
    "remove_objective": "objectives",
    "edit_decision_prompt": "decision_points",
    "edit_rubric_prompt": "rubric",
    "add_rubric_criterion": "rubric",
}


@dataclass
class LiaisonResult:
    applied: bool
    package: CasePackage
    approvable: bool          # may the professor APPROVE after this edit?
    reason: str
    validation: dict[str, Any]


class ProfessorLiaison:
    """Routes professor intent into owner-attributed edits + mandatory re-validation."""
    agent_id = "professor_liaison"

    def _field_root(self, intent: dict[str, Any]) -> str:
        # An explicit `field` (legacy set_outcome_target) wins; otherwise derive it
        # from the op so every op is owner-routable.
        root = intent.get("field") or OP_FIELD_ROOT.get(intent.get("op"))
        if root is None:
            raise ValueError(f"unsupported intent op {intent.get('op')!r}")
        return root

    def _owner_of(self, intent: dict[str, Any]) -> str:
        owner = FIELD_OWNER.get(self._field_root(intent))
        if owner is None:
            raise ValueError(f"no owner for field {self._field_root(intent)!r}")
        return owner

    def propose(self, intent: dict[str, Any], room: str) -> BandMessage:
        """A REVISE_REQUEST to the field owner — NEVER a direct STATE_PATCH."""
        return BandMessage(verb=Verb.REVISE_REQUEST, sender=self.agent_id, room=room,
                           to=[self._owner_of(intent)], payload={"intent": intent})

    # ---- preview (confirm-before-apply) --------------------------------------
    def preview_diff(self, pkg: CasePackage, intent: dict[str, Any]) -> dict[str, Any]:
        """Confirm-before-apply: what exactly changes (before/after) for every op."""
        op = intent["op"]
        if op == "set_outcome_target":
            return {"field": "outcome_model.target.value",
                    "before": (pkg.outcome_model or {}).get("target", {}).get("value"),
                    "after": intent["value"]}
        if op == "add_objective":
            return {"field": f"objectives[{intent['value']['key']}]",
                    "before": None, "after": dict(intent["value"])}
        if op == "edit_objective":
            obj = pkg.objective(intent["key"])
            return {"field": f"objectives[{intent['key']}].text",
                    "before": (obj or {}).get("text"),
                    "after": intent["value"]["text"]}
        if op == "remove_objective":
            obj = pkg.objective(intent["key"])
            return {"field": f"objectives[{intent['key']}]",
                    "before": copy.deepcopy(obj), "after": None}
        if op == "edit_decision_prompt":
            dp = self._decision(pkg, intent["key"])
            return {"field": f"decision_points[{intent['key']}].prompt",
                    "before": (dp or {}).get("prompt"),
                    "after": intent["value"]["prompt"]}
        if op == "edit_rubric_prompt":
            c = self._criterion(pkg, intent["key"])
            return {"field": f"rubric[{intent['key']}].prompt",
                    "before": (c or {}).get("prompt"),
                    "after": intent["value"]["prompt"]}
        if op == "add_rubric_criterion":
            return {"field": f"rubric[{intent['value']['criterion_key']}]",
                    "before": None, "after": dict(intent["value"])}
        raise ValueError(f"unsupported intent op {op!r}")

    # ---- helpers --------------------------------------------------------------
    @staticmethod
    def _decision(pkg: CasePackage, dp_key: str) -> dict[str, Any] | None:
        return next((d for d in pkg.decision_points if d.get("dp_key") == dp_key), None)

    @staticmethod
    def _criterion(pkg: CasePackage, criterion_key: str) -> dict[str, Any] | None:
        return next((c for c in pkg.rubric if c.get("criterion_key") == criterion_key), None)

    # ---- the owner edit (deterministic; LLM authored only the text) ----------
    def _apply_owner_edit(self, pkg: CasePackage, intent: dict[str, Any],
                          room: str):
        """Return a ReducerResult-like (applied, package, reason). Reducer-native ops
        go through `apply` (ownership-checked, replayable); edit/remove ops the reducer
        has no verb for are performed as one deterministic, owner-attributed field
        rewrite on a deepcopy (purity preserved, ownership still explicit)."""
        op = intent["op"]
        owner = self._owner_of(intent)

        # Ops the reducer can express natively -> go through it (ownership-enforced).
        if op == "set_outcome_target":
            model = copy.deepcopy(pkg.outcome_model)
            model["target"] = {**model["target"], "value": intent["value"]}
            return apply(pkg, BandMessage(verb=Verb.STATE_PATCH, sender=owner, room=room,
                         payload={"op": "set_outcome_model", "data": model}))
        if op == "add_objective":
            return apply(pkg, BandMessage(verb=Verb.STATE_PATCH, sender=owner, room=room,
                         payload={"op": "add_objective", "data": dict(intent["value"])}))
        if op == "add_rubric_criterion":
            return apply(pkg, BandMessage(verb=Verb.STATE_PATCH, sender=owner, room=room,
                         payload={"op": "add_rubric_criterion", "data": dict(intent["value"])}))

        # Edit/remove ops: deterministic rewrite (reducer has no native verb).
        p = copy.deepcopy(pkg)
        if op == "edit_objective":
            obj = p.objective(intent["key"])
            if obj is None:
                return _Fail(pkg, f"no objective {intent['key']!r}")
            obj["text"] = intent["value"]["text"]
        elif op == "remove_objective":
            if p.objective(intent["key"]) is None:
                return _Fail(pkg, f"no objective {intent['key']!r}")
            p.objectives = [o for o in p.objectives if o.get("key") != intent["key"]]
        elif op == "edit_decision_prompt":
            dp = self._decision(p, intent["key"])
            if dp is None:
                return _Fail(pkg, f"no decision point {intent['key']!r}")
            dp["prompt"] = intent["value"]["prompt"]
        elif op == "edit_rubric_prompt":
            c = self._criterion(p, intent["key"])
            if c is None:
                return _Fail(pkg, f"no rubric criterion {intent['key']!r}")
            c["prompt"] = intent["value"]["prompt"]
        else:
            return _Fail(pkg, f"unsupported intent op {op!r}")
        return _Ok(p)

    def apply_and_revalidate(self, pkg: CasePackage, intent: dict[str, Any],
                             room: str = "redteam") -> LiaisonResult:
        """Apply the owner's edit, then RE-ENTER validation. The case is approvable
        only if it is still provably solvable and structurally clean afterward."""
        res = self._apply_owner_edit(pkg, intent, room)
        if not res.applied:
            return LiaisonResult(False, pkg, False, f"edit rejected: {res.reason}", {})

        p = copy.deepcopy(res.package)
        p.solvability = {"validated": False}          # force a fresh proof
        # Re-run the FULL red-team loop to convergence: new structural violations
        # (e.g. an objective with no rubric/decision coverage) raise findings, and
        # cleared ones resolve, so approvable reflects the final, settled verdict.
        for _ in range(self._MAX_ROUNDS):
            emitted = False
            for agent in (SolvabilityValidator(), StructuralCritic()):
                for msg in agent.act(p, room):
                    r = apply(p, msg)
                    if r.applied:
                        p = r.package
                        emitted = True
            if not emitted:
                break

        approvable = p.redteam_clean()
        reason = "" if approvable else self._block_reason(p)
        return LiaisonResult(True, p, approvable, reason,
                             {"solvability": p.solvability,
                              "open_findings": p.open_blocking_findings()})

    _MAX_ROUNDS = 8

    @staticmethod
    def _block_reason(p: CasePackage) -> str:
        bits = []
        if not p.solvability.get("validated"):
            issues = p.solvability.get("issues") or []
            kinds = ", ".join(sorted({i.get("kind", "?") for i in issues})) or "unproven"
            bits.append(f"solvability failed ({kinds})")
        findings = p.open_blocking_findings()
        if findings:
            bits.append("open findings: " + ", ".join(f["finding_key"] for f in findings))
        detail = "; ".join(bits) if bits else "case not clean"
        return f"edit failed re-validation; approval blocked — {detail}"


# Tiny ReducerResult-shaped holders for the non-reducer edit path, so
# apply_and_revalidate can treat every edit uniformly.
@dataclass
class _Ok:
    package: CasePackage
    applied: bool = True
    reason: str = ""


@dataclass
class _Fail:
    package: CasePackage
    reason: str = ""
    applied: bool = False


_INTENT_SYSTEM = (
    "You translate a professor's natural-language request about a teaching case into "
    "a single structured intent. Supported ops:\n"
    "- set_outcome_target: change the KPI target value -> "
    '{"op":"set_outcome_target","field":"outcome_model","value":0.1}\n'
    "- add_objective: add a learning objective -> "
    '{"op":"add_objective","value":{"key":"o3","text":"..."}}\n'
    "- edit_objective: reword an objective -> "
    '{"op":"edit_objective","key":"o1","value":{"text":"..."}}\n'
    "- remove_objective: delete an objective -> "
    '{"op":"remove_objective","key":"o2"}\n'
    "- edit_decision_prompt: reword a decision point prompt -> "
    '{"op":"edit_decision_prompt","key":"dp1","value":{"prompt":"..."}}\n'
    "- edit_rubric_prompt: reword a rubric criterion prompt -> "
    '{"op":"edit_rubric_prompt","key":"c_o1","value":{"prompt":"..."}}\n'
    "- add_rubric_criterion: add a rubric criterion -> "
    '{"op":"add_rubric_criterion","value":{"criterion_key":"...","objective_key":"...","weight":0.5}}\n'
    "Respond with a single JSON object for the one op that best matches the request."
)


class LLMProfessorLiaison(ProfessorLiaison):
    """Adds the NL->intent parsing half (LLM); routing + re-validation inherited."""

    def parse_intent(self, text: str) -> dict[str, Any]:
        intent = complete_json(_INTENT_SYSTEM, f"Professor said: {text}",
                               model=config.model_for(self.agent_id), max_tokens=200)
        return self._normalize_intent(intent)

    @staticmethod
    def _normalize_intent(intent: dict[str, Any]) -> dict[str, Any]:
        """The op implies the target field — don't trust the LLM to name it. Coerce
        the canonical field and value types deterministically."""
        op = intent.get("op")
        if op == "set_outcome_target":
            intent["field"] = "outcome_model"
            try:
                intent["value"] = float(intent.get("value"))
            except (TypeError, ValueError):
                pass
        return intent
