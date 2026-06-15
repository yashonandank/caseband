"""Agent base. A real agent wraps an LLM runner (OpenAI Agents SDK / CrewAI /
LangChain) behind .act(); these scaffold agents are deterministic mocks so Loop A
converges offline. An agent only ever emits messages — the reducer owns state."""
from __future__ import annotations
from ..models.case_package import CasePackage
from ..models.messages import BandMessage


class Agent:
    agent_id: str = "agent"
    capabilities: list[str] = []

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        """Return zero or more messages given the current package. Pure wrt state."""
        return []

    def _patch(self, room: str, op: str, data: dict) -> BandMessage:
        from ..models.messages import Verb
        return BandMessage(verb=Verb.STATE_PATCH, sender=self.agent_id, room=room,
                           payload={"op": op, "data": data})
