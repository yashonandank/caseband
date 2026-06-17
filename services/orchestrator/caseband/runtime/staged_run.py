"""staged_run — progressive-disclosure runtime for a RichCase.

The student starts with the SAME opening (company + stage 1 + its exhibits).
As they advance, each new stage reveals new information (the inject). The reveal
*content* is fixed by the author, but its *framing* is personalised to what the
student actually wrote this session (an LLM rephrases the inject as a response to
their reasoning; offline it's shown verbatim).

Nothing here exposes the backbone answer, allocated totals, expected_insight, or
rubric internals — students see only situation, dilemma, task, and unlocked
exhibits (with the analysis left for them to do)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from ..models.rich_case import RichCase
from ..tools import backbone as bb


@dataclass
class StagedRun:
    run_id: str
    case_id: str
    student_id: str
    case: RichCase
    stage_idx: int = 0
    responses: list[dict] = field(default_factory=list)   # [{stage_key, text}]
    status: str = "active"                                  # active -> complete


def _exhibit_view(case: RichCase, key: str) -> dict | None:
    e = case.exhibit(key)
    if e is None:
        return None
    view = {"key": e.key, "title": e.title, "kind": e.kind, "note": e.note,
            "columns": e.columns, "rows": e.rows, "source_url": e.source_url}
    return view


def opening(case: RichCase) -> dict:
    """The same starting view for every student: company + stage 1."""
    s0 = case.stages[0]
    ex = [_exhibit_view(case, k) for k in s0.exhibits]
    out = {
        "title": case.title,
        "company": {"name": case.company.name, "industry": case.company.industry,
                    "size": case.company.size, "protagonist": case.company.protagonist,
                    "backstory": case.company.backstory,
                    "presenting_problem": case.company.presenting_problem},
        "stage": _stage_view(s0),
        "exhibits": [e for e in ex if e],
        "stage_index": 0, "total_stages": len(case.stages),
    }
    # if the backbone is the analysis target of stage 1, hand the student the raw
    # (un-allocated) data table — they must do the allocation themselves.
    if case.backbone and any(c.dimension == "analysis" for c in s0.rubric):
        out["worksheet"] = bb.student_table(case.backbone.__dict__)
    return out


def _stage_view(s) -> dict:
    """Student-safe stage view — no expected_insight, no rubric internals."""
    return {"key": s.key, "title": s.title, "situation": s.situation,
            "dilemma": s.dilemma, "task": s.task}


class StagedPlayer:
    """Drives a StagedRun forward, revealing one stage at a time."""

    def __init__(self, live: bool | None = None):
        self._live = live

    def _is_live(self) -> bool:
        if self._live is not None:
            return self._live
        try:
            from ..llm import require_key
            require_key()
            return True
        except Exception:
            return False

    def advance(self, run: StagedRun, response_text: str) -> dict:
        """Record the student's response to the current stage and reveal the next."""
        if run.status != "active":
            return {"status": run.status, "message": "this run is already complete"}
        cur = run.case.stages[run.stage_idx]
        run.responses.append({"stage_key": cur.key, "text": response_text})

        if run.stage_idx + 1 >= len(run.case.stages):
            run.status = "complete"
            return {"status": "complete", "stage_index": run.stage_idx,
                    "message": "You've reached the end of the case. Submit for feedback."}

        run.stage_idx += 1
        nxt = run.case.stages[run.stage_idx]
        reveal = self._personalise_reveal(nxt.reveal_on_entry, response_text, run.case)
        ex = [_exhibit_view(run.case, k) for k in nxt.exhibits]
        return {"status": "active", "stage_index": run.stage_idx,
                "total_stages": len(run.case.stages),
                "reveal": reveal, "stage": _stage_view(nxt),
                "exhibits": [e for e in ex if e]}

    def _personalise_reveal(self, reveal: str, student_text: str, case: RichCase) -> str:
        """Same inject for everyone, framed as a reaction to what they wrote.
        Offline (or empty): verbatim. The reveal content is never altered, only
        its lead-in — and we never inject the answer."""
        if not reveal or not self._is_live() or not (student_text or "").strip():
            return reveal
        try:
            from ..llm import complete_json
            from .. import config
            raw = complete_json(
                _REVEAL_SYSTEM,
                _REVEAL_USER.format(student=student_text[:1200], reveal=reveal),
                model=config.model_for("facilitator"), max_tokens=400)
            framed = (raw.get("reveal") or "").strip()
            # safety: the inject content must still be present; never drop it.
            return framed if reveal[:40].lower() in framed.lower() or len(framed) > 40 else reveal
        except Exception:
            return reveal


_REVEAL_SYSTEM = (
    "You connect a case's next-stage REVEAL to what the student just argued, in "
    "1-2 sentences, then present the reveal. Acknowledge their reasoning briefly, "
    "then deliver the new information EXACTLY as given (you may rephrase lightly but "
    "must not add facts, numbers, or the answer). Return JSON {reveal}."
)
_REVEAL_USER = "Student wrote:\n{student}\n\nReveal to deliver:\n{reveal}"
