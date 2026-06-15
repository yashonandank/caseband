#!/usr/bin/env python3
"""Loop A, LIVE: the objective_setter is a real OpenAI (gpt-4o-mini) call; the
rest of the writers' room stays deterministic. Proves the same reducer/conductor/
bus pipeline runs with a live LLM authoring agent.

    OPENAI_API_KEY=... python3 scripts/demo_loop_a_live.py
    # or put the key in a gitignored .env at repo root (see .env.example)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus               # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.llm_writers import LLMObjectiveSetter # noqa: E402
from caseband.agents.llm_writers import (                  # noqa: E402
    LLMObjectiveSetter, LLMOutcomeModeler, LLMCheckpointMapper, LLMRubricCreator,
)


def main() -> int:
    bus, store = LocalBus(), StateStore()
    conductor = Conductor(bus, store, room=Room.WRITERS.value)
    # Entire writers' room is now live (gpt-4o-mini). Linkage/weights stay
    # deterministic inside the agents so Loop A's exit predicate is guaranteed.
    agents = [
        Parser(title="Acme Corp 10-K: Marketing ROI", source_type="10K"),
        LLMObjectiveSetter(),
        LLMOutcomeModeler(),
        LLMCheckpointMapper(),
        LLMRubricCreator(),
    ]

    print("=== Loop A LIVE (full writers' room = gpt-4o-mini) ===\n")
    report = conductor.run_loop_a(agents, verbose=True)
    pkg = conductor.pkg

    print("\n=== LLM-authored objectives ===")
    for o in pkg.objectives:
        print(f"  {o['key']}: {o['text']}  (tested_by={o['tested_by']})")

    om = pkg.outcome_model or {}
    tgt = om.get("target", {})
    print("\n=== LLM-authored outcome_model ===")
    print(f"  kind={om.get('kind')} kpi={om.get('kpi_key')} "
          f"target {tgt.get('comparator')} {tgt.get('value')} {tgt.get('units')}")
    print(f"  expr: {om.get('spec', {}).get('expr')}")
    print(f"  decision_variables: {[v.get('key') for v in om.get('decision_variables', [])]}")

    print("\n=== LLM-authored decision points ===")
    for d in pkg.decision_points:
        opts = [o.get('id') for o in d.get('options', [])]
        print(f"  {d['dp_key']} -> {d['maps_to_objective']}: {d.get('prompt')}  options={opts}")

    print("\n=== LLM-authored rubric ===")
    for c in pkg.rubric:
        print(f"  {c['criterion_key']} ({c['objective_key']}) weight={c.get('weight')}")

    print(f"\nconverged={report.converged} rounds={report.rounds} "
          f"applied={report.applied} rejected={len(report.rejected)} "
          f"status={pkg.meta['status']}")
    assert report.converged and pkg.all_objectives_tested()
    print("OK: live Loop A converged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
