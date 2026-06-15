"""research — Research-room agent. When meta.needs_research is true (news/generic
sources that aren't self-contained like a 10-K), it adds external context as
exhibits (data_creator owns exhibits). Deterministic-testable: findings can be
injected; an LLM scout can be wired later behind a flag like the llm_writers."""
from __future__ import annotations

from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage


class ResearchScout(Agent):
    """Materializes researched context as exhibits, only when research is needed."""
    agent_id = "data_creator"
    capabilities = ["exhibits", "research"]

    def __init__(self, findings: list[dict] | None = None):
        # findings: [{label, value?, unit?, source}] — injected (or from an LLM later)
        self._findings = findings or []

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if not pkg.meta.get("needs_research") or not pkg.meta.get("title"):
            return []
        existing = {e.get("exhibit_key") for e in pkg.exhibits}
        out: list[BandMessage] = []
        for i, f in enumerate(self._findings, start=1):
            key = f"r{i}"
            if key in existing:
                continue
            out.append(self._patch(room, "add_exhibit", {
                "exhibit_key": key, "kind": "research",
                "label": f.get("label", f"finding {i}"),
                "value": f.get("value"), "unit": f.get("unit", "text"),
                "source": f.get("source", "research"),
            }))
        return out
