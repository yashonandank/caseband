"""CoachSession — the runtime turn-wrapper around the Socratic Coach (AGENT_SPECS §9).

During a student's play-through the student can ask the coach for help. The coach
gives Socratic guidance (a guiding question, a reframing, what to consider) but
NEVER the answer, the target value, or the formula. This module is the
session/turn wrapper around the existing `runtime_agents.Coach`:

  * The LLM AUTHORS the guidance; deterministic code owns turn-taking, the
    direct-answer refusal, and the answer-leak guard (defense in depth).
  * Mirrors runtime_agents' live-vs-mock split: with a key the real Coach runs;
    offline (no key) a deterministic Socratic nudge is produced so tests pass.
  * The coach only ever sees the REDACTED student_view (never the full package).
  * Every coach reply is run through a leak guard — redact.leaks() over a
    view-shaped wrapper PLUS a token scan for the target value / formula tokens.
    If anything leaks it is SCRUBBED and replaced with a safe Socratic fallback.
  * Each exchange is appended to the run transcript so coaching is on the record.

Public surface:
    CoachSession(coach=None).respond(student_view, transcript, message)
        -> {"reply": str, "refused": bool}
    The same exchange is appended to `transcript` (student QUESTION + coach ANSWER).
"""
from __future__ import annotations
import json
from typing import Any

from ..models.messages import BandMessage, Verb
from .redact import leaks
from .runtime_agents import Coach

# A direct "just give me the answer" ask — refuse and redirect, never the value.
_ANSWER_ASKS = (
    "what is the answer", "what's the answer", "whats the answer", "the answer is",
    "just tell me the answer", "just give me the answer", "tell me the answer",
    "give me the answer", "what is the target", "what's the target", "whats the target",
    "what is the right number", "what's the right number", "what number should",
    "what value should", "which option is correct", "which option is right",
    "what is the formula", "what's the formula", "whats the formula", "the formula",
    "tell me the formula", "what's the right answer", "what is the right answer",
    "did i pass", "did i win", "am i passing", "is this correct", "is that correct",
    "what should i pick", "what should i choose", "solve it for me",
)

_REFUSAL = (
    "I won't hand you the answer — that's the part you're meant to reason to. "
    "But let's get you there: what does the goal actually ask you to maximize or hit, "
    "and which of the levers you control moves that metric? Start by naming the one "
    "lever you think matters most and why."
)

_FALLBACK = (
    "Let's step back rather than jump to a number. Re-read the goal and the levers "
    "you control: which lever do you expect to move the KPI, and in which direction? "
    "Try reasoning through one change at a time and see what it implies."
)


def _wants_answer(message: str) -> bool:
    m = " ".join(message.lower().split())
    return any(p in m for p in _ANSWER_ASKS)


def _number_tokens(value: Any) -> list[str]:
    """Distinctive string forms of a numeric target value, for the leak scan."""
    out: list[str] = []
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        f = float(value)
        forms = {repr(value), str(value)}
        if f == int(f):
            forms.add(str(int(f)))
        # also a couple of rounded forms a model might paraphrase to
        for nd in (2, 4):
            forms.add(f"{f:.{nd}f}")
        for s in forms:
            s = s.rstrip("0").rstrip(".") if "." in s else s
            if s and any(c.isdigit() for c in s):
                out.append(s)
    return out


def _formula_tokens(spec: Any) -> list[str]:
    """Identifier/expression tokens from the formula spec, for the leak scan."""
    out: list[str] = []
    if isinstance(spec, dict):
        expr = spec.get("expr")
        if isinstance(expr, str) and expr.strip():
            out.append(expr.strip())
    elif isinstance(spec, str) and spec.strip():
        out.append(spec.strip())
    return out


class CoachSession:
    """One coaching turn against a redacted student view + the run transcript.

    Deterministic code owns turn-taking, the refusal, and the leak guard; the
    underlying `Coach` (live LLM, or our offline nudge) authors the guidance.
    """

    sender_id = "coach"

    def __init__(self, coach: Coach | None = None, live: bool | None = None) -> None:
        """`live` selects authoring path: True = always call the LLM, False = always
        use the deterministic offline nudge, None (default) = auto (LLM iff a key is
        present, else offline). Tests pass live=False for a key-independent path."""
        self._coach = coach or Coach()
        self._live = live

    # ---- public turn API ------------------------------------------------------
    def respond(self, student_view: dict[str, Any],
                transcript: list[BandMessage] | None,
                message: str) -> dict[str, Any]:
        """Produce Socratic guidance for `message` from the redacted student_view.

        Returns {"reply": str, "refused": bool}. Appends the student question and
        the coach answer to `transcript` (if given) as local BandMessages."""
        message = (message or "").strip()
        refused = False

        if _wants_answer(message):
            reply, refused = _REFUSAL, True
        else:
            reply = self._author(student_view, message)
            # Defense in depth: scan the model's OWN output for leaks and scrub.
            if self._leaks(student_view, reply):
                reply = _FALLBACK
            if not reply.strip():
                reply = _FALLBACK

        self._record(transcript, message, reply, refused)
        return {"reply": reply, "refused": refused}

    # ---- authoring: live LLM vs deterministic offline path --------------------
    def _author(self, student_view: dict[str, Any], message: str) -> str:
        """Ask the Coach for a nudge. Live path uses the real Coach's system prompt
        via the LLM, fed ONLY the already-redacted view; offline (no key / any LLM
        error) falls back to a deterministic Socratic nudge so the default test path
        needs no API. Mirrors runtime_agents._reply (complete_json) without
        re-running student_view on an already-redacted dict."""
        if self._live is False:
            return self._offline_nudge(student_view, message)
        try:
            from ..llm import require_key, complete_json
            require_key()
            from .. import config
            view = json.dumps(student_view, ensure_ascii=False)
            data = complete_json(
                self._coach._system,  # type: ignore[attr-defined]
                f"Case (redacted): {view}\nStudent said: {message}",
                model=config.model_for(self._coach.agent_id), max_tokens=350,
            )
            return data.get("reply", "")
        except Exception:
            return self._offline_nudge(student_view, message)

    @staticmethod
    def _offline_nudge(student_view: dict[str, Any], message: str) -> str:
        """A deterministic Socratic nudge built ONLY from the redacted view: name
        the KPI and the levers, ask a direction question. No target, no formula."""
        om = student_view.get("outcome_model") or {}
        kpi = om.get("kpi_key") or "the key metric"
        levers = [dv.get("key") for dv in om.get("decision_variables", []) if dv.get("key")]
        lever_phrase = (", ".join(levers[:-1]) + f" and {levers[-1]}") if len(levers) > 1 \
            else (levers[0] if levers else "the choices you control")
        return (
            f"Good place to pause and think it through. The goal is framed around "
            f"{kpi}. You control {lever_phrase}. Pick one of those levers and ask "
            f"yourself: if I move it up, does {kpi} go up or down — and why? Reason "
            f"through one lever at a time before committing to a decision."
        )

    # ---- leak guard -----------------------------------------------------------
    def _leaks(self, student_view: dict[str, Any], reply: str) -> bool:
        """True if the coach output leaks anything it must never reveal.

        Two layers:
          1. redact.leaks() over a view-shaped wrapper — catches any structured
             secret key a model might echo back (spec/parameters/solvability/...).
          2. A token scan for the target value and formula tokens. These are NOT
             in student_view, so this is pure defense in depth against a Coach
             that somehow saw more than it should.
        """
        if leaks(student_view):
            return True

        low = reply.lower()
        # Pass/fail / solvability words must never appear in coaching.
        for word in ("you pass", "you fail", "you will pass", "you will fail",
                     "correct answer is", "the answer is", "the target is",
                     "the formula is"):
            if word in low:
                return True

        secret = _leak_tokens(student_view)
        for tok in secret:
            t = tok.lower()
            if not t:
                continue
            # numbers: substring is fine and stricter; words: still substring.
            if t in low:
                return True

        # Structural formula-leak heuristic (defense in depth): the real formula
        # spec is NOT in student_view, so we can't token-match it. Instead, flag a
        # coach that quotes an arithmetic expression over a lever it controls —
        # e.g. "(gain - marketing_spend) / marketing_spend". Direction words
        # ("raising X tends to raise the KPI") are fine; an actual expression isn't.
        if self._looks_like_formula(student_view, reply):
            return True
        return False

    @staticmethod
    def _looks_like_formula(student_view: dict[str, Any], reply: str) -> bool:
        om = student_view.get("outcome_model") or {}
        levers = [str(dv.get("key")) for dv in om.get("decision_variables", [])
                  if dv.get("key")]
        for k in levers:
            i = reply.find(k)
            while i != -1:
                # chars immediately flanking the lever (ignoring spaces/parens)
                before = reply[:i].rstrip(" (")[-1:]
                after = reply[i + len(k):].lstrip(" )")[:1]
                if before in "/*+-=" or after in "/*+-=":
                    return True
                i = reply.find(k, i + len(k))
        return False

    # ---- transcript -----------------------------------------------------------
    def _record(self, transcript: list[BandMessage] | None, message: str,
                reply: str, refused: bool) -> None:
        if transcript is None:
            return
        transcript.append(BandMessage(
            verb=Verb.QUESTION, sender="student", room="run",
            payload={"via": "local", "event": "coach_ask", "text": message},
        ))
        transcript.append(BandMessage(
            verb=Verb.ANSWER, sender=self.sender_id, room="run",
            payload={"via": "local", "event": "coach_reply",
                     "text": reply, "refused": refused},
        ))


# Module-level so tests can exercise the guard tokens directly if needed.
def _leak_tokens(student_view: dict[str, Any]) -> list[str]:
    """Tokens the coach output must not contain: target value forms + formula
    tokens. These come from the (secret) outcome model, NOT student_view — but if
    a caller passes a richer object we still extract and forbid them."""
    toks: list[str] = []
    om = student_view.get("outcome_model") or {}
    toks += _number_tokens(om.get("target"))
    toks += _formula_tokens(om.get("spec"))
    if "parameters" in om and isinstance(om["parameters"], dict):
        for v in om["parameters"].values():
            toks += _number_tokens(v)
    return [t for t in toks if t]
