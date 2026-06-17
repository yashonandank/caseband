"""checks — deterministic quality predicates a generated case must pass.

Each returns (ok: bool, detail: str). Add checks here as the bar rises; the runner
runs them all and a case 'passes' only if every required check is ok."""
from __future__ import annotations

from ..models.rich_case import RichCase
from ..tools import backbone as bb
from ..graph import tools as gtools


def solvable(case: RichCase):
    if not case.backbone:
        return False, "no analytical backbone"
    r = bb.validate(case.backbone.__dict__)
    return r.validated, ("solvable + non-obvious" if r.validated
                         else "; ".join(r.reasons))


def difficulty_band(case: RichCase):
    if not case.backbone:
        return False, "no backbone"
    d = gtools.difficulty_ok(case.backbone.__dict__)
    return d["ok"], f"margin={d['margin']}"


def staged(case: RichCase):
    return len(case.stages) >= 2, f"{len(case.stages)} stages"


def has_personas(case: RichCase):
    return len(case.personas) >= 1, f"{len(case.personas)} personas"


def leak_free(case: RichCase):
    res = gtools.leak_scan(case.to_dict())
    return res["clean"], ("clean" if res["clean"] else "; ".join(res["leaks"]))


def objectives_present(case: RichCase):
    return len(case.learning_objectives) >= 2, f"{len(case.learning_objectives)} objectives"


# required checks (all must pass) and their order
REQUIRED = [solvable, difficulty_band, staged, has_personas, leak_free, objectives_present]
