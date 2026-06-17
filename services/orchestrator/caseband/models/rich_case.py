"""rich_case — the schema for a *real* teaching case (not a flat prompt list).

A RichCase is what an HBS-style case looks like: a named company with a
protagonist, numbered data exhibits, a sequence of stages that each reveal new
information and pose a judgement-based dilemma, and — underneath it all — a
deterministic analytical *backbone* with a defensible, non-obvious answer.

The backbone is what keeps Caseband's promise honest: the case isn't just prose,
it has a quantitative spine the engine can prove is solvable AND non-trivial
(the obvious guess is wrong). See tools/backbone.py.

Everything here is plain dataclasses so it serialises to JSON with asdict() and
rehydrates with RichCase.from_dict() for the runtime."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Company:
    name: str
    industry: str
    size: str                      # "38 employees, ~$4.2M revenue"
    protagonist: str               # "Maria Soto, owner / GM"
    backstory: str                 # 1–2 paragraphs of setup
    presenting_problem: str        # the protagonist's STATED belief — usually the trap


@dataclass
class Exhibit:
    key: str                       # "E1"
    title: str
    kind: str = "table"            # "table" | "narrative" | "quote"
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    note: str = ""                 # caption / how to read it
    source_url: str | None = None  # set when grounded by web research


@dataclass
class RubricCriterion:
    key: str
    text: str
    weight: float
    dimension: str = "judgment"    # "analysis" | "judgment"
    levels: list[str] = field(default_factory=list)  # anchored 0/1/2 descriptors


@dataclass
class Stage:
    key: str                       # "S1"
    title: str
    situation: str                 # narrative for this stage
    dilemma: str                   # the judgement question the student must resolve
    task: str                      # what analysis/decision is required here
    reveal_on_entry: str = ""      # the NEW info shown when the student enters (the inject)
    exhibits: list[str] = field(default_factory=list)      # exhibit keys unlocked here
    rubric: list[RubricCriterion] = field(default_factory=list)
    expected_insight: str = ""     # what a strong answer realises (used by grader/coach, hidden from student)


@dataclass
class Backbone:
    """The deterministic analytical spine. Generic 'find the real driver' model:
    each activity has a visible/direct cost and consumes a share of an overhead
    pool via a resource driver. The TRUE top cost is found only after allocation;
    the NAIVE guess (highest visible cost / what the protagonist suspects) is a
    decoy. tools/backbone.py proves the answer exists and is non-obvious."""
    kind: str = "activity_costing"
    overhead_pool: float = 0.0
    # each: {key, label, direct_cost, overhead_driver, naive_signal}
    activities: list[dict] = field(default_factory=list)
    answer_key: dict = field(default_factory=dict)   # {true_driver, naive_guess, rationale}


@dataclass
class RichCase:
    title: str
    company: Company
    learning_objectives: list[str] = field(default_factory=list)
    teaching_note: str = ""
    exhibits: list[Exhibit] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    backbone: Backbone | None = None
    meta: dict = field(default_factory=dict)

    # ---- serialisation ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "RichCase":
        company = Company(**d["company"])
        exhibits = [Exhibit(**e) for e in d.get("exhibits", [])]
        stages = []
        for s in d.get("stages", []):
            s = dict(s)
            s["rubric"] = [RubricCriterion(**c) for c in s.get("rubric", [])]
            stages.append(Stage(**s))
        backbone = Backbone(**d["backbone"]) if d.get("backbone") else None
        return RichCase(title=d["title"], company=company,
                        learning_objectives=d.get("learning_objectives", []),
                        teaching_note=d.get("teaching_note", ""),
                        exhibits=exhibits, stages=stages, backbone=backbone,
                        meta=d.get("meta", {}))

    # ---- convenience --------------------------------------------------------
    def exhibit(self, key: str) -> Exhibit | None:
        return next((e for e in self.exhibits if e.key == key), None)

    def stage(self, key: str) -> Stage | None:
        return next((s for s in self.stages if s.key == key), None)
