"""BandMessage envelope (AGENT_SPECS §2). Rides as JSON inside a Band message
body; verbs are Caseband-level, independent of Band's fixed message-type enum."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import itertools

_seq = itertools.count(1)


class Verb(str, Enum):
    PROPOSE = "PROPOSE"
    CRITIQUE = "CRITIQUE"
    REVISE_REQUEST = "REVISE_REQUEST"
    REVISE = "REVISE"
    RESOLVE = "RESOLVE"
    FINDING = "FINDING"
    RECRUIT = "RECRUIT"
    CLAIM = "CLAIM"
    HANDOFF = "HANDOFF"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    APPROVE = "APPROVE"
    BLOCK = "BLOCK"
    STATE_PATCH = "STATE_PATCH"


@dataclass
class BandMessage:
    verb: Verb
    sender: str
    room: str
    to: list[str] = field(default_factory=list)   # @mention routing; [] = broadcast
    payload: dict[str, Any] = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)  # ids of messages this responds to
    id: str = ""
    seq: int = 0

    def __post_init__(self) -> None:
        if not self.seq:
            self.seq = next(_seq)
        if not self.id:
            self.id = f"m{self.seq}"
        if isinstance(self.verb, str):
            self.verb = Verb(self.verb)

    def addressed_to(self, agent_id: str) -> bool:
        return not self.to or agent_id in self.to

    def to_body(self) -> dict[str, Any]:
        """Serialize for transport inside a Band message body."""
        return {
            "__caseband__": 1,
            "id": self.id, "seq": self.seq, "verb": self.verb.value,
            "sender": self.sender, "room": self.room, "to": self.to,
            "payload": self.payload, "refs": self.refs,
        }
