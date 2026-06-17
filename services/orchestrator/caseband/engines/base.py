"""AnalyticalEngine registry. An engine is a module exposing:
  validate(params) -> EngineVerdict          # deterministic: solvable + non-obvious
  worksheet(params) -> dict                  # student-facing inputs, no answer
  grade_analysis(params, answer) -> dict     # deterministic analysis score
  example_params() -> dict
Engines generalise the case spine beyond activity-costing."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class EngineVerdict:
    validated: bool
    answer: str | None
    naive_guess: str | None
    margin: float
    reasons: list[str] = field(default_factory=list)


_ENGINES: dict = {}


def register(key: str, module) -> None:
    _ENGINES[key] = module


def get_engine(key: str):
    from . import activity_costing  # noqa: F401  (ensure built-ins are registered)
    try:
        from . import breakeven      # noqa: F401
    except Exception:
        pass
    if key not in _ENGINES:
        raise KeyError(f"unknown analytical engine {key!r}; have {sorted(_ENGINES)}")
    return _ENGINES[key]


def list_engines() -> list[str]:
    from . import activity_costing  # noqa: F401
    try:
        from . import breakeven      # noqa: F401
    except Exception:
        pass
    return sorted(_ENGINES)
