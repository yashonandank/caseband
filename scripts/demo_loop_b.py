#!/usr/bin/env python3
"""Loop A -> Loop B, fully OFFLINE (no Band, no API keys). Drives the writers' room
to a converged package, then runs the Red-Team room: solvability_validator proves
the outcome_model is reachable + sensitive, the structural critic finds it clean,
and the conductor hands off to Assessment.

    python3 scripts/demo_loop_b.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.agents.intake import Parser                  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402

MODEL = {
    "kind": "formula", "kpi_key": "roi",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50000, 500000]}],
    "parameters": {"gain": 200000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def main() -> int:
    c = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)

    print("=== Loop A (writers' room) ===")
    a = c.run_loop_a([
        Parser(title="Acme Corp 10-K: Marketing ROI", source_type="10K"),
        ObjectiveSetter([{"key": "o1", "text": "Diagnose the ROI shortfall"},
                         {"key": "o2", "text": "Recommend a spend level"}]),
        OutcomeModeler(MODEL),
        CheckpointMapper(),
        RubricCreator(),
    ], verbose=True)
    print(f"  Loop A: converged={a.converged} status={c.pkg.meta['status']}\n")

    print("=== Loop B (red-team room) ===")
    c.room = Room.REDTEAM.value
    b = c.run_loop_b([SolvabilityValidator(), StructuralCritic()], verbose=True)

    s = c.pkg.solvability
    cal = s.get("calibration", {})
    print("\n=== solvability proof ===")
    print(f"  validated={s['validated']}  issues={s.get('issues')}")
    print(f"  reachable={cal.get('reachable')} via witness={cal.get('witness')} "
          f"(kpi={cal.get('kpi')})")
    print("  sensitivity:", {k: v["moves"] for k, v in s.get("sensitivity", {}).items()})

    print("\n=== red-team findings ===")
    if c.pkg.redteam_findings:
        for f in c.pkg.redteam_findings:
            print(f"  [{f['status']}] {f.get('severity')}: {f.get('title')}")
    else:
        print("  (none — structurally clean)")

    print(f"\nconverged={b.converged} rounds={b.rounds} applied={b.applied} "
          f"rejected={len(b.rejected)} status={c.pkg.meta['status']}")
    assert b.converged and c.pkg.redteam_clean()
    assert c.pkg.meta["status"] == Room.ASSESSMENT.value
    print("OK: Loop A -> Loop B converged; case is provably solvable and clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
