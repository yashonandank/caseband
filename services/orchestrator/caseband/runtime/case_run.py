"""Runtime CaseRun + Proctor (AGENT_SPECS §9, Hybrid turn-taking).

A CaseRun is one student's play-through of a DEPLOYED case (a frozen CasePackage).
The proctor is the runtime conductor: it owns a per-run turn token (one speaker at
a time, no talk-over) and routes triggers to exactly one agent. On `submit` it
grades deterministically (tools.grader) and releases the AI grade to the student
immediately as `ai_draft` — the professor reviews/finalizes later (lifecycle lives
in tools.grader).

This is RUNTIME on student data: messages carry case_run_id and via='local'; the
proctor NEVER routes through Band."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from ..models.case_package import CasePackage
from ..models.messages import BandMessage, Verb
from ..tools import grader


class TurnError(RuntimeError):
    """Someone tried to speak while another agent holds the turn token."""


class RunError(RuntimeError):
    """An action that is illegal for the run's current status."""


@dataclass
class CaseRun:
    run_id: str
    case_id: str
    student_id: str
    package: CasePackage                       # the deployed (frozen) case
    status: str = "active"                     # active -> submitted -> graded
    transcript: list[BandMessage] = field(default_factory=list)
    grade: dict[str, Any] | None = None


class Proctor:
    """Runtime conductor. Holds the turn token and drives the submit->grade path."""
    agent_id = "proctor"

    def __init__(self) -> None:
        self._holder: str | None = None

    # ---- turn token: one speaker at a time -----------------------------------
    def grant(self, agent_id: str) -> None:
        if self._holder is not None and self._holder != agent_id:
            raise TurnError(f"turn held by {self._holder!r}; {agent_id!r} must wait")
        self._holder = agent_id

    def release(self, agent_id: str) -> None:
        if self._holder == agent_id:
            self._holder = None

    @property
    def holder(self) -> str | None:
        return self._holder

    # ---- trigger routing: a trigger wakes EXACTLY one agent --------------------
    def wake_for(self, trigger: str, addressed_to: str | None = None) -> str:
        """Map a runtime trigger to the single agent that should respond (Hybrid D).
        Stakeholder isolation: an addressed question wakes only that stakeholder."""
        if trigger == "ask":
            if not addressed_to:
                raise RunError("an 'ask' trigger must name the addressed stakeholder")
            return addressed_to
        routing = {
            "stuck": "coach",            # cheap stuck heuristic -> coach
            "checkpoint": "facilitator",  # checkpoint reached -> facilitator nudge
            "idle": "facilitator",        # idle timeout -> facilitator cold-call
            "submit": "grader",           # submit -> grader (see .submit)
        }
        if trigger not in routing:
            raise RunError(f"unknown trigger {trigger!r}")
        return routing[trigger]

    def _emit(self, run: CaseRun, sender: str, verb: Verb, payload: dict[str, Any]) -> BandMessage:
        # via='local', case_run_id set -> runtime transcript, never Band.
        msg = BandMessage(verb=verb, sender=sender, room=f"run:{run.run_id}",
                          payload={"case_run_id": run.run_id, "via": "local", **payload})
        run.transcript.append(msg)
        return msg

    # ---- submit trigger: grade + immediate feedback --------------------------
    def submit(self, run: CaseRun, assignment: dict[str, float],
               rubric_scores: dict[str, int], at: str | None = None) -> dict[str, Any]:
        """Student submits. Proctor takes the turn, grades deterministically, releases
        the ai_draft grade + feedback immediately, and closes the run."""
        if run.status != "active":
            raise RunError(f"cannot submit a run in status {run.status!r}")
        self.grant(self.agent_id)
        try:
            self._emit(run, run.student_id, Verb.HANDOFF,
                       {"event": "submit", "assignment": assignment,
                        "rubric_scores": rubric_scores})
            run.status = "submitted"
            grade = grader.grade_submission(
                run.package.outcome_model, run.package.rubric,
                {"assignment": assignment, "rubric_scores": rubric_scores}, edited_at=at)
            run.grade = grade
            run.status = "graded"
            # released to the student now (ai_draft); professor finalizes later.
            self._emit(run, self.agent_id, Verb.ANSWER, {
                "event": "feedback", "status": grade["status"],
                "overall_pass": grade["overall_pass"], "kpi_value": grade["kpi_value"],
                "rubric_score": grade["rubric_score"],
            })
            return grade
        finally:
            self.release(self.agent_id)
