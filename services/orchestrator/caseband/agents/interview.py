"""intake_interviewer — the conversational authoring front door (user flow step 2).

The professor builds a case by CHATTING (Replit/Claude-style): the agent keeps
asking clarifying questions until it has enough context, then signals ready. It
MUST learn how long the sim should take — duration determines the checkpoint count.

Stateless step (the frontend holds the transcript and passes state back each turn),
so it's trivially testable and persistence-agnostic. Deterministic slot-filling
drives readiness; an LLM can phrase the questions more naturally later, but the
'do we have enough?' decision stays here, not in the model."""
from __future__ import annotations
import re
from typing import Any

# Ordered slots the agent must fill before it can draft a case.
REQUIRED_SLOTS: list[tuple[str, str]] = [
    ("course", "Which course is this for, and what topic should the case cover?"),
    ("assignment", "What should students walk away able to do — the core decision or "
                   "analysis the case puts them through?"),
    ("materials", "Share anything to ground the case: paste source text (a 10-K excerpt, "
                  "a memo), drop links, or describe the scenario and key numbers."),
    ("duration", "About how long should this take a student (in minutes)? That sets how "
                 "many checkpoints I build into the case."),
]
_GREETING = ("Let's build your case. I'll ask a few questions until I have enough to "
             "draft something you can play through. ")


def checkpoints_for(minutes: int) -> int:
    """~1 checkpoint per 15 minutes of student time, clamped to a sane 2–6."""
    return max(2, min(6, round(minutes / 15)))


def parse_minutes(text: str, default: int = 45) -> int:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else default


class InterviewAgent:
    agent_id = "intake_interviewer"

    def start(self) -> dict[str, Any]:
        slot, question = REQUIRED_SLOTS[0]
        return {"collected": {}, "pending": slot, "ready": False,
                "reply": _GREETING + question}

    def step(self, state: dict[str, Any], message: str) -> dict[str, Any]:
        collected = dict(state.get("collected", {}))
        pending = state.get("pending")
        if pending and message and message.strip():
            collected[pending] = message.strip()

        for slot, question in REQUIRED_SLOTS:
            if slot not in collected:
                return {"collected": collected, "pending": slot, "ready": False,
                        "reply": question}

        # Enough context — produce the authoring brief + checkpoint plan.
        minutes = parse_minutes(collected["duration"])
        checkpoints = checkpoints_for(minutes)
        brief = {
            "title": collected["course"].split(".")[0][:80].strip() or "Untitled case",
            "document": collected["materials"],
            "context": {"course": collected["course"], "assignment": collected["assignment"]},
            "duration_minutes": minutes,
            "checkpoints": checkpoints,
        }
        return {"collected": collected, "pending": None, "ready": True,
                "checkpoints": checkpoints, "duration_minutes": minutes, "brief": brief,
                "reply": (f"Got it — that's enough to draft the case. For a ~{minutes}-minute "
                          f"sim I'll build {checkpoints} checkpoints. Generating your case now…")}
