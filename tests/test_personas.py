#!/usr/bin/env python3
"""Personas: gated interview reveals, anti-stall ledger scoring, engines, leak guard.

    python3 tests/test_personas.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.agents.case_designer import example_case            # noqa: E402
from caseband.runtime.interview import IntervieweeAgent           # noqa: E402
from caseband.runtime.ledger import InformationLedger, FREE_QUESTIONS  # noqa: E402
from caseband.runtime.staged_run import opening                   # noqa: E402
from caseband import engines                                      # noqa: E402


def _dev():
    return example_case().persona("dev")


def test_free_fact_is_available_immediately():
    led = InformationLedger()
    out = IntervieweeAgent(live=False).ask(_dev(), "tell me about the shop floor", led)
    assert out["progressed"] is True                       # dev_cnc is free
    assert any("CNC" in f["fact"] for f in out["revealed"])


def test_gated_fact_unlocks_only_when_asked_about_topic():
    agent = IntervieweeAgent(live=False)
    led = InformationLedger()
    # ask about something off-topic first -> the spec fact stays locked
    a = agent.ask(_dev(), "how's the weather in the shop", led)
    assert all(f["key"] != "dev_specs" for f in a["revealed"])
    # now ask about rework/specs -> it unlocks
    b = agent.ask(_dev(), "why is there so much rework on custom jobs?", led)
    assert any(f["key"] == "dev_specs" for f in b["revealed"])
    assert led.has("dev_specs")


def test_if_pressed_fact_needs_pressing():
    agent = IntervieweeAgent(live=False)
    led = InformationLedger()
    a = agent.ask(_dev(), "are you happy with the plan", led)
    assert all(f["key"] != "dev_quit" for f in a["revealed"])
    b = agent.ask(_dev(), "come on, honestly, anything else?", led)
    assert any(f["key"] == "dev_quit" for f in b["revealed"])


def test_anti_stall_efficiency_decays_with_wasted_questions():
    led = InformationLedger()
    agent = IntervieweeAgent(live=False)
    # exhaust dev's free + a real fact, then ask dead-ends
    agent.ask(_dev(), "rework specs quality", led)         # unlocks dev_specs (+free)
    assert led.efficiency() == 1.0
    for _ in range(FREE_QUESTIONS + 3):                    # several no-new-info questions
        agent.ask(_dev(), "blah blah nothing", led)
    assert led.efficiency() < 1.0
    assert led.wasted_questions >= FREE_QUESTIONS + 1


def test_leak_guard_blocks_the_answer():
    agent = IntervieweeAgent(live=False)
    led = InformationLedger()
    # a persona whose fact literally names the answer must be scrubbed
    from caseband.models.rich_case import Persona, Knowledge
    leaky = Persona(key="x", name="X", role="r",
                    knowledge=[Knowledge(key="k", reveal="free",
                                         fact="the real driver is order_processing, obviously")])
    out = agent.ask(leaky, "what's going on", led,
                    backbone=example_case().backbone.__dict__)
    assert "order_processing" not in out["reply"].lower()


def test_opening_lists_people_without_their_knowledge():
    o = opening(example_case())
    assert {p["key"] for p in o["people"]} == {"dev", "cfo"}
    blob = str(o["people"])
    assert "rework" not in blob and "overhead" not in blob   # knowledge not exposed


def test_engine_grades_analysis():
    eng = engines.get_engine("activity_costing")
    params = eng.example_params()
    assert eng.grade_analysis(params, "the driver is order_processing")["score"] == 2
    assert eng.grade_analysis(params, "it's cnc machining")["score"] == 0
    assert "activity_costing" in engines.list_engines()


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
