"""Intake agents: classify the source + seed meta, and turn extracted figures into
exhibits. `Parser` stamps meta from explicit args (used by tests/offline demos);
`DocParser` runs the real ingestion pipeline (ingestion.extract) over an uploaded
document; `DataCreator` materializes the extracted facts as exhibits."""
from __future__ import annotations
from .base import Agent
from ..models.case_package import CasePackage
from ..models.messages import BandMessage
from ..ingestion.extract import extract, SourceDoc


class Parser(Agent):
    agent_id = "conductor"   # meta is conductor-owned; parser proposes via conductor
    capabilities = ["parse", "classify"]

    def __init__(self, title: str, source_type: str, needs_research: bool = False):
        self.title = title
        self.source_type = source_type
        self.needs_research = needs_research

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.meta.get("title"):
            return []
        return [self._patch(room, "set_meta", {
            "title": self.title, "source_type": self.source_type,
            "needs_research": self.needs_research,
        })]


class DocParser(Agent):
    """Real ingestion: detect + extract an uploaded document, then seed meta."""
    agent_id = "conductor"
    capabilities = ["ingest", "parse", "classify"]

    def __init__(self, text: str, filename: str | None = None):
        self.doc: SourceDoc = extract(text, filename)

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.meta.get("title"):
            return []
        return [self._patch(room, "set_meta", {
            "title": self.doc.title, "source_type": self.doc.source_type,
            "needs_research": self.doc.needs_research,
        })]


class DataCreator(Agent):
    """Materializes extracted figures as exhibits (data_creator owns exhibits)."""
    agent_id = "data_creator"
    capabilities = ["exhibits"]

    def __init__(self, doc: SourceDoc):
        self.doc = doc

    def act(self, pkg: CasePackage, room: str) -> list[BandMessage]:
        if pkg.exhibits or not pkg.meta.get("title"):
            return []
        out: list[BandMessage] = []
        for i, fact in enumerate(self.doc.facts, start=1):
            out.append(self._patch(room, "add_exhibit", {
                "exhibit_key": f"x{i}", "kind": "figure",
                "label": fact["label"], "value": fact["value"],
                "unit": fact["unit"], "source": fact["raw"],
            }))
        return out
