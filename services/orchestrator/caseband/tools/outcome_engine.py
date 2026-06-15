"""outcome_engine — the deterministic core that makes a case 'not random'.

A `formula` outcome_model binds student-controlled decision variables to a single
KPI via an arithmetic expression, compared against a target. This module:

  * safely evaluates the expression (whitelisted AST — no eval/exec),
  * `calibrate()` proves the target is REACHABLE (a witness assignment exists),
  * `sensitivity()` proves each decision variable actually MOVES the KPI.

solvability_validator runs calibrate + sensitivity to set solvability.validated;
grader/sim_agent reuse evaluate() at runtime. LLM authors the model; this computes.

outcome_model (kind='formula') shape:
    {"kind": "formula", "kpi_key": "roi",
     "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
     "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
     "parameters": {"gain": 200000},          # fixed scenario constants
     "spec": {"expr": "(gain - marketing_spend) / marketing_spend"}}
"""
from __future__ import annotations
import ast
import itertools
import operator
from typing import Any

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMP = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt,
    "==": lambda a, b: abs(a - b) <= 1e-9, "!=": lambda a, b: abs(a - b) > 1e-9,
}
_EPS = 1e-9


class UnknownSymbol(KeyError):
    """An expression references a name that is neither a decision var nor a parameter."""


# ---- safe expression evaluation -------------------------------------------
def _symbols(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"non-numeric constant {node.value!r}")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise UnknownSymbol(node.id)
        return float(env[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, env))
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def expr_of(model: dict[str, Any]) -> str:
    return (model.get("spec") or {}).get("expr", "")


def free_symbols(model: dict[str, Any]) -> set[str]:
    expr = expr_of(model)
    return _symbols(ast.parse(expr, mode="eval")) if expr.strip() else set()


def declared_symbols(model: dict[str, Any]) -> set[str]:
    keys = {d["key"] for d in model.get("decision_variables", []) if d.get("key")}
    return keys | set(model.get("parameters", {}).keys())


def undefined_symbols(model: dict[str, Any]) -> set[str]:
    """Symbols used in the expr with no decision-var/parameter binding -> not computable."""
    return free_symbols(model) - declared_symbols(model)


def evaluate(model: dict[str, Any], assignment: dict[str, float]) -> float:
    """KPI value for a given decision-variable assignment (parameters merged in)."""
    env = {**model.get("parameters", {}), **assignment}
    return _eval(ast.parse(expr_of(model), mode="eval"), env)


def passes(value: float, target: dict[str, Any]) -> bool:
    cmp = _CMP.get(target.get("comparator", ">="))
    if cmp is None:
        raise ValueError(f"unknown comparator {target.get('comparator')!r}")
    return bool(cmp(value, float(target["value"])))


# ---- calibration + sensitivity --------------------------------------------
def _bounds_of(dv: dict[str, Any]) -> tuple[float, float] | None:
    b = dv.get("bounds")
    if isinstance(b, (list, tuple)) and len(b) == 2:
        return float(b[0]), float(b[1])
    return None


def _grid(lo: float, hi: float, steps: int) -> list[float]:
    if steps < 2 or hi == lo:
        return [lo]
    return [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]


def calibrate(model: dict[str, Any], steps: int = 9, max_combos: int = 50_000) -> dict[str, Any]:
    """Grid-search the decision space for an assignment that hits the target.
    reachable=True with a witness proves the target is achievable (not impossible)."""
    target = model["target"]
    dvs = model.get("decision_variables", [])
    if not dvs:                                   # no levers -> just check constants
        val = evaluate(model, {})
        return {"reachable": passes(val, target), "witness": {}, "kpi": val}

    grids, keys = [], []
    for dv in dvs:
        b = _bounds_of(dv)
        if b is None:
            return {"reachable": False, "witness": None, "kpi": None,
                    "error": f"missing bounds for {dv.get('key')!r}"}
        keys.append(dv["key"])
        grids.append(b)

    while steps > 2 and steps ** len(dvs) > max_combos:
        steps -= 1
    axes = [_grid(lo, hi, steps) for (lo, hi) in grids]

    closest = None
    for combo in itertools.product(*axes):
        assignment = dict(zip(keys, combo))
        val = evaluate(model, assignment)
        if passes(val, target):
            return {"reachable": True, "witness": assignment, "kpi": val, "steps": steps}
        gap = abs(val - float(target["value"]))
        if closest is None or gap < closest[0]:
            closest = (gap, assignment, val)
    return {"reachable": False, "witness": closest[1] if closest else None,
            "kpi": closest[2] if closest else None, "steps": steps}


def sensitivity(model: dict[str, Any], steps: int = 9) -> dict[str, dict[str, Any]]:
    """For each decision var: sweep it across its bounds (others held at midpoint)
    and record whether the KPI actually changes. A var that never moves the KPI is
    dead weight (the case would be partly 'random' wrt that lever)."""
    dvs = model.get("decision_variables", [])
    mids = {}
    for dv in dvs:
        b = _bounds_of(dv)
        mids[dv["key"]] = (b[0] + b[1]) / 2 if b else 0.0

    out: dict[str, dict[str, Any]] = {}
    for dv in dvs:
        key, b = dv["key"], _bounds_of(dv)
        if b is None:
            out[key] = {"moves": False, "delta": 0.0, "error": "missing bounds"}
            continue
        base = {k: v for k, v in mids.items() if k != key}
        vals = [evaluate(model, {**base, key: x}) for x in _grid(b[0], b[1], steps)]
        delta = max(vals) - min(vals)
        out[key] = {"moves": delta > _EPS, "delta": delta}
    return out
