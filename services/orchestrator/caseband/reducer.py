"""Deterministic reducer. Applies STATE_PATCH messages to the CasePackage,
enforcing the ownership matrix. Pure: returns a new package, never mutates the
input. Same patches in the same order -> same package (replayable from the log)."""
from __future__ import annotations
import copy
from dataclasses import dataclass

from .models.case_package import CasePackage
from .models.messages import BandMessage, Verb
from .ownership import owner_of_op


@dataclass
class ReducerResult:
    applied: bool
    package: CasePackage
    reason: str = ""


def apply(pkg: CasePackage, msg: BandMessage) -> ReducerResult:
    if msg.verb is not Verb.STATE_PATCH:
        return ReducerResult(False, pkg, f"not a STATE_PATCH ({msg.verb.value})")

    op = msg.payload.get("op")
    owner = owner_of_op(op)
    if owner is None:
        return ReducerResult(False, pkg, f"unknown op {op!r}")
    if msg.sender != owner:
        return ReducerResult(False, pkg,
                             f"ownership: {msg.sender!r} cannot {op} (owner={owner!r})")

    p = copy.deepcopy(pkg)
    data = msg.payload.get("data", {})

    if op == "set_meta":
        p.meta.update(data)
    elif op == "add_objective":
        p.objectives.append({"tested_by": None, **data})
    elif op == "add_decision_point":
        p.decision_points.append(dict(data))
    elif op == "set_tested_by":
        obj = p.objective(data["objective_key"])
        if obj is None:
            return ReducerResult(False, pkg, f"no objective {data['objective_key']!r}")
        obj["tested_by"] = data["dp_key"]
    elif op == "set_outcome_model":
        p.outcome_model = dict(data)
    elif op == "add_rubric_criterion":
        p.rubric.append(dict(data))
    elif op == "add_exhibit":
        p.exhibits.append(dict(data))
    elif op == "add_finding":
        p.redteam_findings.append({"status": "open", **data})
    elif op == "resolve_finding":
        f = next((x for x in p.redteam_findings if x.get("finding_key") == data["finding_key"]), None)
        if f is None:
            return ReducerResult(False, pkg, f"no finding {data['finding_key']!r}")
        f["status"] = data.get("status", "fixed")
    elif op == "set_solvability":
        p.solvability.update(data)
    else:  # pragma: no cover - guarded by owner_of_op
        return ReducerResult(False, pkg, f"unhandled op {op!r}")

    return ReducerResult(True, p, "")
