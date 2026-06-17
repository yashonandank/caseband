"""ledger — the information ledger for a play session.

Tracks what the student has UNCOVERED (via persona interviews) and how
EFFICIENTLY they did it. The anti-stall rule: every interview question or data
pull that surfaces nothing new costs efficiency; questions that unlock a new,
relevant fact are 'progress'. Grading rewards uncovering the facts that matter
and penalises fishing.

Deterministic and pure — the interviewee agent records into it; the grader reads
from it."""
from __future__ import annotations
from dataclasses import dataclass, field

# tuning: each wasted (no-new-info) question costs this much efficiency; the score
# is in [0,1] and feeds a small grade modifier so investigation is rewarded but a
# few dead-end questions aren't fatal.
WASTE_COST = 0.08
FREE_QUESTIONS = 2          # grace: first couple of dead-ends are free (exploration)


@dataclass
class InformationLedger:
    questions_asked: int = 0
    wasted_questions: int = 0                       # asked, surfaced nothing new
    revealed: list[str] = field(default_factory=list)   # knowledge keys uncovered
    revealed_facts: list[dict] = field(default_factory=list)  # {key, fact, persona, ties_to}

    def record_question(self, new_facts: list[dict]) -> dict:
        """Log one interview question. `new_facts` are knowledge items revealed for
        the FIRST time. Returns what changed (for the UI/score feedback)."""
        self.questions_asked += 1
        fresh = [f for f in new_facts if f.get("key") and f["key"] not in self.revealed]
        for f in fresh:
            self.revealed.append(f["key"])
            self.revealed_facts.append(f)
        if not fresh:
            self.wasted_questions += 1
        return {"new_facts": fresh, "progressed": bool(fresh),
                "questions_asked": self.questions_asked,
                "wasted": self.wasted_questions}

    def has(self, knowledge_key: str) -> bool:
        return knowledge_key in self.revealed

    def uncovered_for(self, ties_to: str) -> list[dict]:
        return [f for f in self.revealed_facts if f.get("ties_to") == ties_to]

    def efficiency(self) -> float:
        """1.0 = no wasted questions; decays with dead-ends past the grace window."""
        billable = max(0, self.wasted_questions - FREE_QUESTIONS)
        return round(max(0.0, 1.0 - billable * WASTE_COST), 3)

    def summary(self) -> dict:
        return {"questions_asked": self.questions_asked,
                "wasted_questions": self.wasted_questions,
                "facts_uncovered": len(self.revealed),
                "efficiency": self.efficiency()}
