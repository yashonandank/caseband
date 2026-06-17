"""backbone — deterministic analysis + quality gate for a RichCase's spine.

This is the math that makes a case honest. Given an activity-costing backbone
(an overhead pool + activities with a visible/direct cost and a resource-driver
volume), it allocates overhead, computes each activity's TRUE total cost, and
proves three things a good case needs:

  1. has_answer   — there's a clear winner (the real cost driver), not a tie.
  2. non_obvious  — the winner is NOT what a novice would guess from the visible
                    numbers (or what the protagonist suspects). i.e. the data is
                    not obvious; ABC actually changes the conclusion.
  3. consistent   — costs are positive and the pool is real.

A case whose backbone fails these is pedagogically dead (trivial or unsolvable),
so the generator must regenerate. LLM authors the story; this owns the verdict."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

MIN_MARGIN = 0.10          # winner must beat #2 by >=10% of the winner's cost


class BackboneError(ValueError):
    """Malformed backbone (missing fields, non-positive numbers)."""


@dataclass
class BackboneResult:
    validated: bool
    true_driver: str | None
    naive_guess: str | None
    margin: float                       # (top - second) / top, 0..1
    costs: dict[str, dict]              # per-activity breakdown
    reasons: list[str]


def _num(x: Any, name: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise BackboneError(f"{name} is not a number: {x!r}")
    return v


def allocate(backbone: dict) -> dict[str, dict]:
    """Allocate the overhead pool across activities by resource-driver share and
    return {key: {label, direct, overhead, total, naive_signal}}."""
    pool = _num(backbone.get("overhead_pool"), "overhead_pool")
    acts = backbone.get("activities") or []
    if len(acts) < 3:
        raise BackboneError("a backbone needs at least 3 activities")
    total_driver = sum(_num(a.get("overhead_driver"), f"{a.get('key')}.overhead_driver")
                       for a in acts)
    if total_driver <= 0:
        raise BackboneError("total overhead-driver volume must be > 0")
    out: dict[str, dict] = {}
    for a in acts:
        key = a.get("key") or a.get("label")
        if not key:
            raise BackboneError("every activity needs a key")
        direct = _num(a.get("direct_cost"), f"{key}.direct_cost")
        drv = _num(a.get("overhead_driver"), f"{key}.overhead_driver")
        naive = _num(a.get("naive_signal", direct), f"{key}.naive_signal")
        if direct < 0 or drv < 0:
            raise BackboneError(f"{key}: costs/drivers must be non-negative")
        overhead = pool * (drv / total_driver)
        out[key] = {"label": a.get("label", key), "direct": round(direct, 2),
                    "overhead": round(overhead, 2), "total": round(direct + overhead, 2),
                    "naive_signal": naive}
    return out


def validate(backbone: dict) -> BackboneResult:
    """Run the gate. Pure + deterministic — same backbone, same verdict."""
    reasons: list[str] = []
    costs = allocate(backbone)

    ranked = sorted(costs.items(), key=lambda kv: kv[1]["total"], reverse=True)
    top_key, top = ranked[0]
    second = ranked[1][1]["total"] if len(ranked) > 1 else 0.0
    margin = (top["total"] - second) / top["total"] if top["total"] else 0.0

    naive_key = max(costs.items(), key=lambda kv: kv[1]["naive_signal"])[0]
    declared = (backbone.get("answer_key") or {}).get("true_driver")
    declared_naive = (backbone.get("answer_key") or {}).get("naive_guess")

    has_answer = margin >= MIN_MARGIN
    if not has_answer:
        reasons.append(f"no clear cost driver: top beats #2 by only {margin:.0%} "
                       f"(need {MIN_MARGIN:.0%})")
    non_obvious = top_key != naive_key
    if not non_obvious:
        reasons.append(f"trivial: the real driver ({top_key}) is also the obvious "
                       f"highest-visible-cost guess")
    # the authored answer key must match what the math actually says
    if declared and declared != top_key:
        reasons.append(f"answer_key.true_driver={declared!r} but the math says "
                       f"{top_key!r}")
    if declared_naive and declared_naive != naive_key:
        reasons.append(f"answer_key.naive_guess={declared_naive!r} but the obvious "
                       f"guess is {naive_key!r}")

    validated = has_answer and non_obvious and not (
        declared and declared != top_key) and not (
        declared_naive and declared_naive != naive_key)
    return BackboneResult(validated=validated, true_driver=top_key,
                          naive_guess=naive_key, margin=round(margin, 4),
                          costs=costs, reasons=reasons)


def student_table(backbone: dict) -> dict:
    """The numbers a STUDENT sees — direct costs + driver volumes only, NOT the
    allocated totals or the answer. The student must do the allocation themselves."""
    acts = backbone.get("activities") or []
    return {
        "overhead_pool": backbone.get("overhead_pool"),
        "activities": [{"key": a.get("key"), "label": a.get("label"),
                        "direct_cost": a.get("direct_cost"),
                        "overhead_driver": a.get("overhead_driver")} for a in acts],
        "instructions": ("Allocate the overhead pool across activities by each "
                         "activity's share of the total resource driver, then rank "
                         "activities by fully-loaded cost."),
    }
