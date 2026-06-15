"""qa_critic — authoring QA critic (AGENT_SPECS §5). A red-team-room critic that
catches QUALITY defects distinct from StructuralCritic's invariants: weak objectives,
thin decision prompts, rubric criteria with no levels, dangling exhibit references.
Emits findings as red_team_lead (shares the redteam_findings list) but namespaces its
keys with 'qa_' and only resolves its own — so it composes with StructuralCritic."""
from __future__ import annotations

from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage

# A measurable objective should name an analytical action (Bloom verb).
_ACTION_VERBS = (
    "analyze", "evaluate", "assess", "compare", "recommend", "diagnose",
    "calculate", "design", "determine", "justify", "prioritize", "forecast",
    "estimate", "interpret", "optimize", "model",
)
_PREFIX = "qa_"


class QACritic(Agent):
    agent_id = "red_team_lead"
    capabilities = ["redteam_findings"]

    def _violations(self, pkg: CasePackage) -> dict[str, dict]:
        v: dict[str, dict] = {}
        for o in pkg.objectives:
            if not any(verb in (o.get("text") or "").lower() for verb in _ACTION_VERBS):
                k = f"{_PREFIX}obj_verb:{o['key']}"
                v[k] = {"finding_key": k, "severity": "minor", "type": "ambiguous",
                        "target": "objectives",
                        "title": f"Objective {o['key']} lacks a measurable action verb"}
        for d in pkg.decision_points:
            if len((d.get("prompt") or "").split()) < 5:
                k = f"{_PREFIX}dp_prompt:{d['dp_key']}"
                v[k] = {"finding_key": k, "severity": "minor", "type": "ambiguous",
                        "target": "decision_points",
                        "title": f"Decision point {d['dp_key']} prompt is too thin"}
        for c in pkg.rubric:
            if not c.get("levels"):
                k = f"{_PREFIX}rubric_levels:{c['criterion_key']}"
                v[k] = {"finding_key": k, "severity": "major", "type": "missing_data",
                        "target": "rubric",
                        "title": f"Rubric criterion {c['criterion_key']} has no levels"}
        exhibit_keys = {e.get("exhibit_key") for e in pkg.exhibits}
        for d in pkg.decision_points:
            for ex in d.get("requires_exhibits", []) or []:
                if ex not in exhibit_keys:
                    k = f"{_PREFIX}missing_exhibit:{d['dp_key']}:{ex}"
                    v[k] = {"finding_key": k, "severity": "major", "type": "missing_data",
                            "target": "exhibits",
                            "title": f"Decision {d['dp_key']} needs missing exhibit {ex}"}
        return v

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        viol = self._violations(pkg)
        open_now = {f["finding_key"] for f in pkg.redteam_findings
                    if f.get("status") == "open"}
        out: list[BandMessage] = []
        for key, finding in viol.items():
            if key not in open_now:
                out.append(self._patch(room, "add_finding", finding))
        for f in pkg.redteam_findings:                    # resolve only OUR cleared findings
            key = f["finding_key"]
            if (f.get("status") == "open" and key.startswith(_PREFIX) and key not in viol):
                out.append(self._patch(room, "resolve_finding",
                                       {"finding_key": key, "status": "fixed"}))
        return out
