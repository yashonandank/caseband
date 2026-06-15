"""Runtime student-facing agents (AGENT_SPECS §9). Each is woken by exactly one
proctor trigger and only ever sees the REDACTED student_view — never the formula,
parameters, calibrated answer, or rubric weights (see redact.py). They are live
LLM agents (gpt-4o-mini); the proctor owns turn-taking and never routes them
through Band. They return text for the student; they do NOT patch any blackboard.

  stuck      -> Coach        (Socratic nudge, never the answer)
  checkpoint -> Facilitator  (advance discussion / cold-call)
  idle       -> Facilitator
  ask:<role> -> Stakeholder  (in-character; isolated to its own knowledge)
"""
from __future__ import annotations
import json
from typing import Any

from .. import config
from ..llm import complete_json
from .redact import student_view
from .case_run import CaseRun


class _RuntimeAgent:
    agent_id = "runtime_agent"
    _system = "You are a helpful classroom agent."

    def _context(self, run: CaseRun) -> str:
        # Only the redacted view crosses into the prompt — the answer can't leak.
        return json.dumps(student_view(run.package), ensure_ascii=False)

    def _reply(self, run: CaseRun, user: str) -> str:
        data = complete_json(self._system, user,
                             model=config.model_for(self.agent_id), max_tokens=350)
        return data.get("reply", "")


class Coach(_RuntimeAgent):
    """Woken on `stuck`. Nudges the student's thinking; must NOT give the answer."""
    agent_id = "coach"
    _system = (
        "You are a Socratic case coach. The student is stuck. Ask ONE guiding "
        "question or offer ONE framing hint that moves them forward. NEVER reveal "
        "the target value, the formula, or a specific number to choose. Respond as "
        'JSON: {"reply": "..."}.'
    )

    def nudge(self, run: CaseRun, student_msg: str) -> str:
        return self._reply(run, f"Case (redacted): {self._context(run)}\n"
                                f"Student said: {student_msg}")


class Facilitator(_RuntimeAgent):
    """Woken on `checkpoint`/`idle`. Advances the discussion or cold-calls."""
    agent_id = "facilitator"
    _system = (
        "You are a business-school discussion facilitator. Move the case forward "
        "with a crisp prompt tied to the current objective, or cold-call the student "
        "to commit to a decision. Do not grade and do not reveal answers. Respond as "
        'JSON: {"reply": "..."}.'
    )

    def nudge(self, run: CaseRun, event: str = "checkpoint") -> str:
        return self._reply(run, f"Case (redacted): {self._context(run)}\nEvent: {event}")


class Stakeholder(_RuntimeAgent):
    """Woken on an addressed `ask`. Role-plays one stakeholder, in character, with
    only that role's knowledge (isolation mirrors @mention — honest role-play)."""
    def __init__(self, role: str, persona: str = "") -> None:
        self.agent_id = role
        self.persona = persona

    @property
    def _system(self) -> str:  # type: ignore[override]
        return (
            f"You are {self.agent_id}, a stakeholder in this business case. "
            f"{self.persona} Stay in character and answer ONLY from what this role "
            "would plausibly know. Do not reveal grading criteria, the target, or the "
            'underlying formula. Respond as JSON: {"reply": "..."}.'
        )

    def answer(self, run: CaseRun, question: str) -> str:
        return self._reply(run, f"Case (redacted): {self._context(run)}\n"
                                f"Question to {self.agent_id}: {question}")
