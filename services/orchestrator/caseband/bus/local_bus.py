"""In-memory CollaborationBus. Models Band's two visibility rules:
  - agents see only messages they are @mentioned in (or broadcasts);
  - the backend (conductor/reducer) reads the FULL transcript via fetch_transcript.
In production this is backed by Supabase `messages`; here it is a list."""
from __future__ import annotations
from typing import Iterable

from ..models.messages import BandMessage


class LocalBus:
    via = "local"

    def __init__(self) -> None:
        self._log: list[BandMessage] = []
        self._rooms: dict[str, list[str]] = {}
        self._registry: dict[str, list[str]] = {}  # capability -> agent_ids

    def register_capabilities(self, agent_id: str, capabilities: list[str]) -> None:
        for cap in capabilities:
            self._registry.setdefault(cap, []).append(agent_id)

    def create_room(self, room: str, participants: list[str]) -> str:
        self._rooms[room] = list(participants)
        return room

    def send(self, msg: BandMessage) -> None:
        self._log.append(msg)

    def stream(self, agent_id: str) -> Iterable[BandMessage]:
        return [m for m in self._log if m.addressed_to(agent_id) and m.sender != agent_id]

    def fetch_transcript(self, room: str) -> list[BandMessage]:
        return [m for m in self._log if m.room == room]

    def add_participant(self, room: str, agent_id: str) -> None:
        self._rooms.setdefault(room, []).append(agent_id)

    def remove_participant(self, room: str, agent_id: str) -> None:
        if agent_id in self._rooms.get(room, []):
            self._rooms[room].remove(agent_id)

    def lookup_peers(self, capability: str) -> list[str]:
        return list(self._registry.get(capability, []))
