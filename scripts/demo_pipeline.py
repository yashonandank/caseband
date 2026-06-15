#!/usr/bin/env python3
"""Full Caseband backend, end-to-end and OFFLINE (no Band, no API keys):

  ingest (10-K) -> writers (Loop A) -> red-team (Loop B, solvability proof)
  -> deploy -> student submit -> grade -> professor edit + re-validation

Uses the deterministic writers' mocks so it runs with zero keys; swap in the
agents.llm_writers classes for the live authoring path.

    python3 scripts/demo_pipeline.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.ingestion.extract import extract             # noqa: E402
from caseband.agents.intake import DocParser, DataCreator  # noqa: E402
from caseband.agents.writers_room import (                 # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402
from caseband.runtime.case_run import CaseRun, Proctor     # noqa: E402
from caseband.runtime.redact import student_view, leaks    # noqa: E402
from caseband.agents.professor_liaison import ProfessorLiaison  # noqa: E402

TENK = """ACME CORP FORM 10-K
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Annual Report Pursuant to Section 13

Item 7. Management's Discussion and Analysis
Total revenue was $4,200 million for fiscal 2025.
Net income of $560 million was reported.
Marketing spend of $300 million drove a gross profit of $1,800 million.
"""

# A formula model grounded in the filing: ROI on marketing spend.
MODEL = {
    "kind": "formula", "kpi_key": "roi", "pass_policy": "all",
    "target": {"value": 0.15, "comparator": ">=", "units": "ratio"},
    "decision_variables": [{"key": "marketing_spend", "bounds": [50_000_000, 500_000_000]}],
    "parameters": {"gain": 1_800_000_000},
    "spec": {"expr": "(gain - marketing_spend) / marketing_spend"},
}


def main() -> int:
    # 1) INGEST -------------------------------------------------------------
    doc = extract(TENK)
    print(f"[ingest] type={doc.source_type} title={doc.title!r} "
          f"needs_research={doc.needs_research} facts={len(doc.facts)}")

    # 2) WRITERS (Loop A) ---------------------------------------------------
    c = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
    a = c.run_loop_a([
        DocParser(TENK), DataCreator(doc),
        ObjectiveSetter([{"key": "o1", "text": "Diagnose the marketing ROI"},
                         {"key": "o2", "text": "Recommend a spend level"}]),
        OutcomeModeler(MODEL), CheckpointMapper(), RubricCreator(),
    ])
    print(f"[writers] converged={a.converged} objectives={len(c.pkg.objectives)} "
          f"exhibits={len(c.pkg.exhibits)} status={c.pkg.meta['status']}")

    # 3) RED-TEAM (Loop B) --------------------------------------------------
    c.room = Room.REDTEAM.value
    b = c.run_loop_b([SolvabilityValidator(), StructuralCritic()])
    cal = c.pkg.solvability["calibration"]
    print(f"[red-team] converged={b.converged} validated={c.pkg.solvability['validated']} "
          f"reachable={cal['reachable']} findings={len(c.pkg.redteam_findings)} "
          f"status={c.pkg.meta['status']}")
    assert c.pkg.redteam_clean(), "only a clean case may deploy"

    # 4) DEPLOY + redaction check ------------------------------------------
    assert leaks(student_view(c.pkg)) == [], "student view must not leak the answer"
    print("[deploy] redaction OK — formula/parameters/witness hidden from students")

    # 5) RUNTIME: student submits, gets graded -----------------------------
    run = CaseRun(run_id="r1", case_id="acme", student_id="stu_1", package=c.pkg)
    proctor = Proctor()
    grade = proctor.submit(run, {"marketing_spend": 100_000_000}, {"c_o1": 2, "c_o2": 2})
    print(f"[runtime] submit -> grade status={grade['status']} kpi={grade['kpi_value']:.2f} "
          f"overall_pass={grade['overall_pass']} run_status={run.status}")

    # 6) FACULTY: professor edits the target; the case re-validates ---------
    liaison = ProfessorLiaison()
    ok = liaison.apply_and_revalidate(c.pkg, {"op": "set_outcome_target",
                                              "field": "outcome_model", "value": 0.10})
    bad = liaison.apply_and_revalidate(c.pkg, {"op": "set_outcome_target",
                                               "field": "outcome_model", "value": 999})
    print(f"[faculty] lower target -> approvable={ok.approvable}; "
          f"impossible target -> approvable={bad.approvable} ({bad.reason})")

    assert a.converged and b.converged
    assert grade["overall_pass"] and grade["status"] == "ai_draft"
    assert ok.approvable and not bad.approvable
    print("\nOK: ingest -> author -> prove -> deploy -> grade -> faculty-gate all green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
