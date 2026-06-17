"""Pluggable analytical engines — the deterministic quantitative spine of a case.

Each engine proves a case is solvable AND non-obvious, hands the student a
worksheet (without the answer), computes the live calculator behind it, and grades
the analysis deterministically. The LLM proposes magnitudes; the engine owns the
verdict and the math. See base.AnalyticalEngine."""
from .base import get_engine, list_engines, EngineVerdict  # noqa: F401
