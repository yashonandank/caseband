"""Live (LLM-backed) grader judge — the runtime assessment half.

Same split as the writers' room: the LLM only *judges* a student's open-ended
answers into per-criterion levels (0/1/2); the deterministic tools.grader then
computes the KPI, applies the rubric weights + pass policy, and produces the
grade. So two students with identical answers get identical grades.

This is RUNTIME, on student data: it is NOT an Agent that emits STATE_PATCHes to
the authoring blackboard, and it NEVER routes through Band (see Band boundary).
It is a plain local callable returning a grade dict (an `ai_draft` row)."""
from __future__ import annotations
from typing import Any

from .. import config
from ..llm import complete_json
from ..tools import grader

_JUDGE_SYSTEM = (
    "You are a fair, consistent grading assistant. For EACH rubric criterion, read "
    "the student's answer and assign the integer level it reaches: 0 (absent), "
    "1 (adequate), or 2 (strong). Judge only against the criterion; do not invent "
    "criteria. Respond as JSON: {\"scores\": {\"c_o1\": 2, \"c_o2\": 1}} with one "
    "entry per criterion_key provided."
)


class LLMGraderJudge:
    """Judges free-text answers into rubric levels, then grades deterministically."""
    agent_id = "grader"

    def _criteria_brief(self, rubric: list[dict[str, Any]]) -> str:
        lines = []
        for c in rubric:
            levels = "; ".join(f"{lv['score']}={lv['descriptor']}"
                               for lv in c.get("levels", []))
            lines.append(f"- {c['criterion_key']} (objective {c.get('objective_key')}): "
                         f"{levels or 'levels: 0=absent;1=adequate;2=strong'}")
        return "\n".join(lines)

    def judge_scores(self, rubric: list[dict[str, Any]],
                     answers: dict[str, str]) -> dict[str, int]:
        """LLM: criterion_key -> level (0/1/2). Falls back to 0 for any missing key."""
        user = ("Rubric criteria:\n" + self._criteria_brief(rubric)
                + "\n\nStudent answers (by criterion_key):\n"
                + "\n".join(f"- {k}: {v}" for k, v in answers.items()))
        data = complete_json(_JUDGE_SYSTEM, user,
                             model=config.model_for(self.agent_id), max_tokens=400)
        raw = data.get("scores", {})
        return {c["criterion_key"]: int(raw.get(c["criterion_key"], 0)) for c in rubric}

    def grade(self, outcome_model: dict[str, Any] | None,
              rubric: list[dict[str, Any]],
              assignment: dict[str, float],
              answers: dict[str, str],
              edited_at: str | None = None) -> dict[str, Any]:
        """Full runtime grade: LLM judges text, grader computes the rest."""
        scores = self.judge_scores(rubric, answers)
        submission = {"assignment": assignment, "rubric_scores": scores}
        return grader.grade_submission(outcome_model, rubric, submission, edited_at=edited_at)
