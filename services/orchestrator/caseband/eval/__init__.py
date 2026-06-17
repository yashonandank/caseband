"""Eval harness — runs the authoring pipeline over a corpus of briefs and scores
each produced case against deterministic quality checks (solvable, non-obvious,
has personas, staged, leak-free, consistent). This is what makes "did this agent
change make cases better or worse?" measurable instead of vibes."""
from .runner import run_eval  # noqa: F401
