"""Conductor — backend orchestration service. It is NOT a Band-native primitive:
it reads the full transcript via the bus, runs the deterministic reducer, commits
versions, and advances meta.status on HANDOFF. Drives Loop A to convergence."""
from __future__ import annotations
from dataclasses import dataclass

from . import config
from .agents.base import Agent
from .models.case_package import CasePackage
from .models.messages import BandMessage, Verb
from .reducer import apply
from .rooms import Room
from .state_store import StateStore


@dataclass
class LoopReport:
    converged: bool
    rounds: int
    applied: int
    rejected: list[str]
    versions: int


class Conductor:
    def __init__(self, bus, store: StateStore, room: str = Room.WRITERS.value):
        self.bus = bus
        self.store = store
        self.room = room
        self.pkg = CasePackage()
        self.store.commit(self.pkg)

    def _emit(self, msg: BandMessage) -> None:
        self.bus.send(msg)
        self.store.record(msg)

    def run_loop_a(self, agents: list[Agent], verbose: bool = False) -> LoopReport:
        """Poll agents round-robin; apply their patches via the reducer; stop when
        every objective is tested (Loop A exit) or we hit the iteration guard."""
        applied = rejected = 0
        rejections: list[str] = []
        rounds = 0
        for rounds in range(1, config.MAX_LOOP_A_ROUNDS + 1):
            progressed = False
            for agent in agents:
                for msg in agent.act(self.pkg, self.room):
                    self._emit(msg)
                    res = apply(self.pkg, msg)
                    if res.applied:
                        self.pkg = res.package
                        self.store.commit(self.pkg)
                        applied += 1
                        progressed = True
                        if verbose:
                            print(f"  [{rounds}] {msg.sender:>16} {msg.payload['op']} -> applied")
                    else:
                        rejected += 1
                        rejections.append(res.reason)
                        if verbose:
                            print(f"  [{rounds}] {msg.sender:>16} {msg.payload.get('op')} -> REJECT: {res.reason}")
            if self.pkg.all_objectives_tested():
                self._emit(BandMessage(verb=Verb.HANDOFF, sender="conductor",
                                       room=self.room, payload={"to_room": Room.REDTEAM.value}))
                self.pkg.meta["status"] = Room.REDTEAM.value
                self.store.commit(self.pkg)
                return LoopReport(True, rounds, applied, rejections, len(self.store.versions))
            if not progressed:
                break
        return LoopReport(False, rounds, applied, rejections, len(self.store.versions))

    def run_loop_b(self, agents: list[Agent], verbose: bool = False) -> LoopReport:
        """Red-Team loop. Poll the validator + critics round-robin until the case is
        provably clean (CasePackage.redteam_clean) or the iteration guard trips.
        Exit hands off to the Assessment room."""
        applied = 0
        rejections: list[str] = []
        rounds = 0
        for rounds in range(1, config.MAX_LOOP_B_ROUNDS + 1):
            progressed = False
            for agent in agents:
                for msg in agent.act(self.pkg, self.room):
                    self._emit(msg)
                    res = apply(self.pkg, msg)
                    if res.applied:
                        self.pkg = res.package
                        self.store.commit(self.pkg)
                        applied += 1
                        progressed = True
                        if verbose:
                            print(f"  [{rounds}] {msg.sender:>20} {msg.payload['op']} -> applied")
                    else:
                        rejections.append(res.reason)
                        if verbose:
                            print(f"  [{rounds}] {msg.sender:>20} {msg.payload.get('op')} -> REJECT: {res.reason}")
            if self.pkg.redteam_clean():
                self._emit(BandMessage(verb=Verb.HANDOFF, sender="conductor",
                                       room=self.room, payload={"to_room": Room.ASSESSMENT.value}))
                self.pkg.meta["status"] = Room.ASSESSMENT.value
                self.store.commit(self.pkg)
                return LoopReport(True, rounds, applied, rejections, len(self.store.versions))
            if not progressed:
                break
        return LoopReport(False, rounds, applied, rejections, len(self.store.versions))
