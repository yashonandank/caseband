"""interview_agent — the AGENTIC authoring conversation (replaces the slot-filler).

The old InterviewAgent marched through a fixed list of questions. This one is a
real conversation: when the professor names a rich idea, it digs deeper on that
thread, proposes angles, and asks about the things a good case needs — the
analytical method (the backbone), what's analysis vs judgement, the company/data
source, difficulty, AND how they want it graded — before it produces a brief and
a short build plan.

LIVE (OPENAI_API_KEY): the LLM drives the next move each turn. Deterministic code
still owns the readiness FLOOR (it won't let the model declare 'ready' until the
must-have dimensions are actually covered).

OFFLINE: a richer scripted interviewer (still covers method + grading) so the
pipeline is testable and demoable without a key.

Stateless: the caller round-trips `state` each turn (frontend holds the transcript)."""
from __future__ import annotations
import json
from typing import Any

# Dimensions a case brief must cover before we can design a good case.
REQUIRED = [
    ("goal", "What should students walk away able to do — and is the heart of this "
             "case the *analysis* (getting the numbers right), the *judgement* (what "
             "to decide), or both equally?"),
    ("method", "What analytical method or framework anchors it? (e.g. activity-based "
               "costing to find a bottleneck, NPV, breakeven, segmentation…) This "
               "becomes the case's solvable backbone."),
    ("context", "Tell me about the setting — real company or fictional, the industry, "
                "and the decision on the table. The more specific, the better the case."),
    ("data", "Where should the data come from — should I research a real company, or "
             "invent realistic numbers seeded with industry benchmarks?"),
    ("grading", "How do you want it graded? What separates an A answer from a C — and "
                "any rubric criteria you care about?"),
    ("duration", "About how long should this take a student (minutes)? That sets how "
                 "many stages/checkpoints I build."),
]
_GREETING = ("Let's design your case. I'll dig into the idea with you, then build "
             "a full case — company, data exhibits, and staged dilemmas. ")


def checkpoints_for(minutes: int) -> int:
    return max(2, min(6, round(minutes / 15)))


def _parse_minutes(text: str, default: int = 60) -> int:
    import re
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else default


class AgenticInterviewer:
    agent_id = "intake_interviewer"

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

    # ---- public API ---------------------------------------------------------
    def start(self) -> dict[str, Any]:
        if self._is_live():
            return self._live_turn([], "")
        slot, q = REQUIRED[0]
        return {"collected": {}, "pending": slot, "ready": False,
                "reply": _GREETING + q, "state": {"collected": {}, "pending": slot}}

    def step(self, state: dict[str, Any], message: str) -> dict[str, Any]:
        if self._is_live():
            history = state.get("history", [])
            return self._live_turn(history, message, state)
        return self._scripted_turn(state, message)

    # ---- deterministic floor (also the offline path) ------------------------
    def _scripted_turn(self, state: dict, message: str) -> dict:
        collected = dict(state.get("collected", {}))
        pending = state.get("pending")
        if pending and message and message.strip():
            collected[pending] = message.strip()
        for slot, q in REQUIRED:
            if slot not in collected:
                return {"collected": collected, "pending": slot, "ready": False,
                        "reply": q, "state": {"collected": collected, "pending": slot}}
        return self._finalize(collected)

    def _finalize(self, collected: dict) -> dict:
        minutes = _parse_minutes(collected.get("duration", ""))
        checkpoints = checkpoints_for(minutes)
        brief = {
            "title": (collected.get("context", "").split(".")[0][:80].strip()
                      or collected.get("method", "Untitled case")),
            "context": {"goal": collected.get("goal"), "setting": collected.get("context"),
                        "topic": collected.get("method")},
            "method": collected.get("method"),
            "data_source": collected.get("data"),
            "grading": collected.get("grading"),
            "audience": collected.get("audience", "MBA"),
            "duration_minutes": minutes,
            "checkpoints": checkpoints,
        }
        plan = [
            "Design the company and protagonist (with a plausible wrong hunch)",
            f"Build the {collected.get('method', 'analytical')} backbone with a hidden answer",
            "Draft data exhibits", f"Write {checkpoints} staged dilemmas with reveals",
            "Validate the case is solvable and non-obvious",
        ]
        return {"collected": collected, "pending": None, "ready": True,
                "checkpoints": checkpoints, "duration_minutes": minutes,
                "brief": brief, "plan": plan,
                "reply": (f"Great — I have enough. Here's my plan:\n- " + "\n- ".join(plan) +
                          f"\n\nFor a ~{minutes}-minute case I'll build {checkpoints} "
                          "stages. Generating now…"),
                "state": {"collected": collected, "pending": None}}

    # ---- agentic LLM path ---------------------------------------------------
    def _live_turn(self, history: list[dict], message: str, state: dict | None = None) -> dict:
        from ..llm import complete_json
        from .. import config
        history = list(history)
        if message:
            history.append({"role": "professor", "text": message})
        convo = "\n".join(f"{m['role']}: {m['text']}" for m in history) or "(conversation start)"
        raw = complete_json(_AGENT_SYSTEM, _AGENT_USER.format(convo=convo),
                            model=config.model_for("intake_interviewer"), max_tokens=1200)

        covered = raw.get("covered", {}) or {}
        missing = [k for k, _ in REQUIRED if not covered.get(k)]
        reply = raw.get("reply") or "Tell me more about the case you have in mind."
        # FLOOR: the model may only finalise when the must-haves are actually covered.
        ready = bool(raw.get("ready")) and not missing
        history.append({"role": "agent", "text": reply})
        new_state = {"history": history, "covered": covered}

        out = {"collected": covered, "pending": (missing[0] if missing else None),
               "ready": ready, "reply": reply, "state": new_state}
        if ready:
            brief = raw.get("brief") or {}
            minutes = _parse_minutes(str(brief.get("duration_minutes", "")), 60)
            brief["duration_minutes"] = minutes
            brief["checkpoints"] = checkpoints_for(minutes)
            brief.setdefault("audience", "MBA")
            out["brief"] = brief
            out["plan"] = raw.get("plan", [])
            out["checkpoints"] = brief["checkpoints"]
            out["duration_minutes"] = minutes
        return out


_AGENT_SYSTEM = (
    "You are an expert business-school case designer running an authoring "
    "interview with a professor. Be genuinely conversational: when the professor "
    "names an idea, DIG DEEPER on that specific thread and propose concrete angles "
    "(don't just march through a checklist). Across the conversation you must learn "
    "these dimensions before building: goal (analysis vs judgement vs both), method "
    "(the analytical backbone, e.g. activity-based costing), context (company "
    "real/fictional, industry, the decision), data (research a real company vs "
    "invent benchmark-seeded numbers), grading (what an A vs C answer looks like, "
    "rubric criteria), duration (minutes -> stages). Ask ONE focused question per "
    "turn. Only set ready=true once every dimension is genuinely covered; then also "
    "return a build `plan` (3-6 short steps) and a `brief`.\n"
    "Return JSON: {reply, ready (bool), covered{goal,method,context,data,grading,"
    "duration} (each a short string of what you learned, omit/empty if unknown), "
    "plan[] (only when ready), brief{title,context{goal,setting,topic},method,"
    "data_source,grading,audience,duration_minutes} (only when ready)}."
)
_AGENT_USER = "Conversation so far:\n{convo}\n\nProduce your next turn as JSON."
