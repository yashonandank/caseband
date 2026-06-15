"""Room state machine (AGENT_SPECS §3). meta.status advances only on a conductor
HANDOFF. Research is conditional; backward FINDING edges (redteam->writers) are
how Loop B revises."""
from __future__ import annotations
from enum import Enum


class Room(str, Enum):
    INTAKE = "intake"
    RESEARCH = "researching"
    WRITERS = "drafting"
    REDTEAM = "redteam"
    ASSESSMENT = "assessing"
    UI_DEPLOY = "building"
    GATE = "gating"
    DEPLOYED = "deployed"


# Forward handoff order. Research is skipped unless the case needs external facts.
FORWARD = [
    Room.INTAKE, Room.RESEARCH, Room.WRITERS, Room.REDTEAM,
    Room.ASSESSMENT, Room.UI_DEPLOY, Room.GATE, Room.DEPLOYED,
]


def next_room(current: Room, needs_research: bool = False) -> Room:
    i = FORWARD.index(current)
    nxt = FORWARD[i + 1]
    if nxt is Room.RESEARCH and not needs_research:
        return FORWARD[i + 2]
    return nxt
