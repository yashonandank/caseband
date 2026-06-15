"""Append-only version store + message persistence. Mirrors Supabase
case_versions (canonical JSONB) + messages (audit log). In-memory here so the
demo runs with no DB. Append-only enables 'resume from last good version'."""
from __future__ import annotations
import copy
from dataclasses import dataclass, field

from .models.case_package import CasePackage
from .models.messages import BandMessage


@dataclass
class StateStore:
    versions: list[CasePackage] = field(default_factory=list)
    messages: list[BandMessage] = field(default_factory=list)

    def commit(self, pkg: CasePackage) -> int:
        self.versions.append(copy.deepcopy(pkg))
        return len(self.versions) - 1

    def record(self, msg: BandMessage) -> None:
        self.messages.append(msg)

    @property
    def head(self) -> CasePackage:
        return self.versions[-1]

    def last_good(self) -> CasePackage:
        return self.versions[-1]
