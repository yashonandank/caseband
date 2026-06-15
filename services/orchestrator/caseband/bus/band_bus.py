"""BandBus skeleton — the hackathon impl. Maps the CollaborationBus interface
onto the real Band SDK (package `band-sdk`, imports `thenvoi.*`). Not wired here;
the offline Loop A demo runs entirely on LocalBus. Methods document the mapping."""
from __future__ import annotations
from typing import Iterable

from ..models.messages import BandMessage


class BandBus:
    via = "band"

    def __init__(self, api_key: str, owner_token: str) -> None:
        # owner_token: a Band owner-scoped token lets the backend read the FULL
        # transcript (GET /me/chats/{id}/messages) despite @mention isolation.
        self._api_key = api_key
        self._owner_token = owner_token
        raise NotImplementedError(
            "BandBus requires Band creds; use LocalBus until provisioned. "
            "create_room -> thenvoi_create_chatroom; add/remove -> thenvoi_add/"
            "remove_participant; lookup_peers -> thenvoi_lookup_peers; send -> post "
            "message with BandMessage.to_body() in the body; fetch_transcript -> "
            "GET /me/chats/{id}/messages with the owner token."
        )

    def create_room(self, room: str, participants: list[str]) -> str: ...
    def send(self, msg: BandMessage) -> None: ...
    def stream(self, agent_id: str) -> Iterable[BandMessage]: ...
    def fetch_transcript(self, room: str) -> list[BandMessage]: ...
    def add_participant(self, room: str, agent_id: str) -> None: ...
    def remove_participant(self, room: str, agent_id: str) -> None: ...
    def lookup_peers(self, capability: str) -> list[str]: ...
