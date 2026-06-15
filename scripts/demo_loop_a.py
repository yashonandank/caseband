#!/usr/bin/env python3
"""Proves Loop A converges OFFLINE — no Band creds, no API keys, stdlib only.

    python3 scripts/demo_loop_a.py

Wires LocalBus + Conductor + intake/writers'-room mock agents on a sample
quantitative case (10-K-style ROI target), runs the writers' loop to its exit
predicate (every objective tested_by != null), and prints the trace + the
materialized CasePackage projections."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus              # noqa: E402
from caseband.conductor import Conductor                  # noqa: E402
from caseband.state_store import StateStore               # noqa: E402
from caseband.rooms import Room                           # noqa: E402
from caseband.agents.intake import Parser                 # noqa: E402
from caseband.agents.writers_room import (                # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)

SAMPLE_OBJECTIVES = [
    {"key": "obj1", "text": "Interpret the cost structure from the 10-K exhibits"},
    {"key": "obj2", "text": "Recommend a marketing spend that hits the ROI target"},
    {"key": "obj3", "text": "Justify the recommendation against downside risk"},
]

SAMPLE_OUTCOME_MODEL = {
    "kind": "formula",
    "kpi_key": "roi",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [
        {"key": "marketing_spend", "dp_key": "dp2", "type": "number",
         "bounds": [50000, 500000]},
    ],
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
    "pass_policy": "all",
}


def main() -> int:
    bus = LocalBus()
    store = StateStore()
    conductor = Conductor(bus, store, room=Room.WRITERS.value)

    agents = [
        Parser(title="Acme Corp 10-K: Marketing ROI", source_type="10K"),
        ObjectiveSetter(SAMPLE_OBJECTIVES),
        OutcomeModeler(SAMPLE_OUTCOME_MODEL),
        CheckpointMapper(),
        RubricCreator(),
    ]

    print("=== Loop A (writers' room) — offline, LocalBus ===\n")
    report = conductor.run_loop_a(agents, verbose=True)
    pkg = conductor.pkg

    print("\n=== Result ===")
    print(f"converged        : {report.converged}")
    print(f"rounds           : {report.rounds}")
    print(f"patches applied  : {report.applied}")
    print(f"patches rejected : {len(report.rejected)}")
    print(f"versions committed: {report.versions}")
    print(f"status advanced  : {pkg.meta['status']}  (handoff -> redteam on convergence)")

    print("\n=== CasePackage projections ===")
    print(f"title        : {pkg.meta['title']}")
    print(f"outcome_model: kind={pkg.outcome_model['kind']} kpi={pkg.outcome_model['kpi_key']} "
          f"target {pkg.outcome_model['target']['comparator']} {pkg.outcome_model['target']['value']}")
    for o in pkg.objectives:
        print(f"  objective {o['key']}: tested_by={o['tested_by']!r}  ({o['text']})")
    print(f"decision_points: {[d['dp_key'] for d in pkg.decision_points]}")
    print(f"rubric criteria: {[c['criterion_key'] for c in pkg.rubric]}")

    print("\n=== Transcript (audit log) ===")
    for m in store.messages:
        op = m.payload.get('op', '')
        print(f"  {m.id:>4} {m.verb.value:<12} {m.sender:<16} {op}")

    assert report.converged, "Loop A did not converge"
    assert pkg.all_objectives_tested(), "exit predicate not satisfied"
    print("\nOK: Loop A converged and every objective is tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
