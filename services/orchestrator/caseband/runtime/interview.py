"""interview — the Interviewee (persona NPC) agent.

The student questions a character authored by the writer. The agent answers IN
CHARACTER and reveals each piece of knowledge only when its reveal rule is met:
  free            -> always available
  if_asked:<kw>   -> only when the question mentions the topic keyword(s)
  if_pressed      -> only on a follow-up / when the student pushes
  never           -> never divulged (e.g. the case answer)
Newly revealed facts are recorded in the InformationLedger (which drives the
anti-stall score). A deterministic leak guard ensures the answer is never spoken.

LIVE: an LLM phrases the in-character reply (constrained to the unlocked facts).
OFFLINE: deterministic keyword gating + templated reply, so it's testable."""
from __future__ import annotations
from typing import Any

from ..models.rich_case import Persona, Knowledge
from .ledger import InformationLedger


_PRESS_WORDS = ("why", "really", "sure", "more", "explain", "elaborate", "come on",
                "anything else", "what else", "press", "honestly")


def _unlocked(persona: Persona, question: str, *, pressed: bool) -> list[Knowledge]:
    q = (question or "").lower()
    out: list[Knowledge] = []
    for k in persona.knowledge:
        rule = (k.reveal or "free").lower()
        if rule == "never":
            continue
        if rule == "free":
            out.append(k)
        elif rule.startswith("if_asked"):
            topic = (k.topic or rule.split(":", 1)[-1]).lower().strip()
            if topic and any(t in q for t in topic.split("|")):
                out.append(k)
        elif rule == "if_pressed":
            if pressed:
                out.append(k)
    return out


def _answer_key_terms(case_backbone: dict | None) -> list[str]:
    if not case_backbone:
        return []
    ans = (case_backbone.get("answer_key") or {})
    terms = [str(ans.get("true_driver", "")).lower()]
    return [t for t in terms if t]


class IntervieweeAgent:
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

    def ask(self, persona: Persona, question: str, ledger: InformationLedger,
            *, backbone: dict | None = None) -> dict[str, Any]:
        """One interview turn. Returns the in-character reply, the facts newly
        unlocked this turn, and the ledger delta (for scoring/UI)."""
        pressed = any(w in (question or "").lower() for w in _PRESS_WORDS)
        unlocked = _unlocked(persona, question, pressed=pressed)
        new_facts = [{"key": k.key or k.fact[:24], "fact": k.fact,
                      "persona": persona.key, "ties_to": k.ties_to} for k in unlocked]
        delta = ledger.record_question(new_facts)

        if delta["progressed"]:
            reply = self._voice(persona, [k.fact for k in unlocked], question)
        else:
            reply = self._deflect(persona, question)

        reply = self._leak_guard(reply, backbone)
        return {"persona": persona.key, "reply": reply,
                "revealed": delta["new_facts"], "progressed": delta["progressed"],
                "ledger": ledger.summary()}

    # ---- voicing ------------------------------------------------------------
    def _voice(self, persona: Persona, facts: list[str], question: str) -> str:
        if not self._is_live():
            joined = " ".join(facts)
            return f"[{persona.name}, {persona.role}] {joined}"
        try:
            from ..llm import complete_json
            from .. import config
            raw = complete_json(_VOICE_SYSTEM, _voice_user(persona, facts, question),
                               model=config.model_for("facilitator"), max_tokens=350)
            return (raw.get("reply") or " ".join(facts)).strip()
        except Exception:
            return f"[{persona.name}] " + " ".join(facts)

    def _deflect(self, persona: Persona, question: str) -> str:
        if not self._is_live():
            return (f"[{persona.name}, {persona.role}] I'm not sure that's where I'd "
                    "look — was there something specific you wanted to ask about?")
        try:
            from ..llm import complete_json
            from .. import config
            raw = complete_json(_DEFLECT_SYSTEM, f"{persona.name} ({persona.role}). "
                               f"Demeanor: {persona.demeanor}. Question: {question}",
                               model=config.model_for("facilitator"), max_tokens=200)
            return (raw.get("reply") or "I don't have anything useful on that.").strip()
        except Exception:
            return f"[{persona.name}] I don't really have anything on that."

    def _leak_guard(self, reply: str, backbone: dict | None) -> str:
        for term in _answer_key_terms(backbone):
            if term and term in reply.lower():
                return ("[the character changes the subject] I'd rather you draw your "
                        "own conclusion from the numbers than have me hand it to you.")
        return reply


_VOICE_SYSTEM = (
    "You voice a case character answering a student's interview question. Speak in "
    "first person, in character, briefly. Convey ONLY the given facts (do not invent "
    "new facts or state the case's analytical answer). Return JSON {reply}.")
_DEFLECT_SYSTEM = (
    "You voice a case character. The student asked about something you don't have "
    "useful information on. Stay in character and deflect briefly without inventing "
    "facts. Return JSON {reply}.")


def _voice_user(persona: Persona, facts: list[str], question: str) -> str:
    import json
    return (f"Character: {persona.name}, {persona.role}. Demeanor: {persona.demeanor}. "
            f"Hidden agenda (color your tone, don't state it): {persona.hidden_agenda}.\n"
            f"Student asked: {question}\nFacts you may share now: {json.dumps(facts)}")
