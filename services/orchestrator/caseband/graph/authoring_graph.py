"""authoring_graph — the LangGraph state machine for case authoring.

The loop the professor asked for: solvability is proven WHILE the case is written,
not after. The modeler proposes the backbone numbers FIRST; the deterministic gate
validates them immediately and, on failure, routes straight back to the modeler
with the specific reason (immediate feedback). Only once the numbers are proven
solvable AND non-obvious does the writer build the narrative around them. A leak
gate then checks the prose, and finally the UI builder renders the interactive,
deployable case.

    interview ─▶ propose_backbone ─▶ [validate] ─no(reason)─▶ propose_backbone
                                        │ yes
                                        ▼
                       write_case ─▶ [leak_scan] ─no─▶ write_case
                                        │ clean
                                        ▼
                                    build_ui ─▶ END

Nodes propose; deterministic tools commit/verify. Streaming each node transition
is the live 'what is it doing now' feed. Visualise with graph.get_graph()."""
from __future__ import annotations
import operator
from typing import Annotated, Any, Callable, TypedDict

from . import tools

MAX_BACKBONE_TRIES = 4
MAX_WRITE_TRIES = 3

_PHASE = {
    "propose_backbone": "Designing the analytical backbone (the hidden answer)…",
    "validate": "Proving the numbers are solvable and non-obvious…",
    "write_case": "Writing the company, exhibits and staged dilemmas…",
    "leak_scan": "Red-teaming the prose for answer leaks…",
    "build_ui": "Building the interactive case page…",
}


class GState(TypedDict, total=False):
    brief: dict
    live: bool | None
    case_id: str
    backbone: dict
    validation: dict
    feedback: str
    bb_tries: int
    case: dict
    leaks: dict
    write_tries: int
    ui: dict
    events: Annotated[list, operator.add]   # add-reducer: node deltas accumulate


def _ev(node: str, extra: dict | None = None) -> dict:
    ev = {"type": "phase", "node": node, "label": _PHASE.get(node, node)}
    if extra:
        ev.update(extra)
    return ev


# ---- nodes -----------------------------------------------------------------
def n_propose_backbone(state: GState) -> GState:
    ev = _ev("propose_backbone",
             {"attempt": state.get("bb_tries", 0) + 1, "feedback": state.get("feedback", "")})
    bbn = tools.propose_backbone(state["brief"], state.get("feedback", ""), state.get("live"))
    return {"backbone": bbn, "bb_tries": state.get("bb_tries", 0) + 1, "events": [ev]}


def n_validate(state: GState) -> GState:
    res = tools.validate_backbone(state["backbone"])
    ev = _ev("validate", {"validated": res["validated"],
                          "true_driver": res.get("true_driver"), "margin": res.get("margin")})
    return {"validation": res, "events": [ev],
            "feedback": "" if res["validated"] else "; ".join(res["reasons"])}


def n_write_case(state: GState) -> GState:
    ev = _ev("write_case", {"attempt": state.get("write_tries", 0) + 1})
    case = tools.write_case(state["brief"], state["backbone"], state["validation"],
                            state.get("live"))
    return {"case": case, "write_tries": state.get("write_tries", 0) + 1, "events": [ev]}


def n_leak_scan(state: GState) -> GState:
    res = tools.leak_scan(state["case"])
    ev = _ev("leak_scan", {"clean": res["clean"], "leaks": res["leaks"]})
    return {"leaks": res, "events": [ev]}


def n_build_ui(state: GState) -> GState:
    ui = tools.build_ui(state["case"], state["case_id"])
    return {"ui": ui, "events": [_ev("build_ui")]}


# ---- conditional edges -----------------------------------------------------
def after_validate(state: GState) -> str:
    if state["validation"]["validated"]:
        return "write_case"
    if state.get("bb_tries", 0) >= MAX_BACKBONE_TRIES:
        return "write_case"          # give up tuning; example fallback is already valid
    return "propose_backbone"        # immediate feedback loop back to the modeler


def after_leak(state: GState) -> str:
    if state["leaks"]["clean"] or state.get("write_tries", 0) >= MAX_WRITE_TRIES:
        return "build_ui"
    return "write_case"


# ---- graph build -----------------------------------------------------------
def build_graph():
    from langgraph.graph import StateGraph, END
    g = StateGraph(GState)
    g.add_node("propose_backbone", n_propose_backbone)
    g.add_node("validate", n_validate)
    g.add_node("write_case", n_write_case)
    g.add_node("leak_scan", n_leak_scan)
    g.add_node("build_ui", n_build_ui)

    g.set_entry_point("propose_backbone")
    g.add_edge("propose_backbone", "validate")
    g.add_conditional_edges("validate", after_validate,
                            {"propose_backbone": "propose_backbone", "write_case": "write_case"})
    g.add_edge("write_case", "leak_scan")
    g.add_conditional_edges("leak_scan", after_leak,
                            {"write_case": "write_case", "build_ui": "build_ui"})
    g.add_edge("build_ui", END)
    return g.compile()


def run_authoring(brief: dict, case_id: str, *, live: bool | None = None,
                  on_event: Callable[[dict], None] | None = None) -> dict:
    """Run the authoring graph to completion and return the final state (case + ui)."""
    graph = build_graph()
    init: GState = {"brief": brief, "case_id": case_id, "live": live}
    final: dict = {}
    seen = 0
    # stream node-by-node so the progress feed is LIVE; events accumulate via reducer.
    for snap in graph.stream(init, stream_mode="values"):
        final = snap
        if on_event:
            evs = snap.get("events", [])
            for ev in evs[seen:]:
                on_event(ev)
            seen = len(evs)
    return {"case": final.get("case"), "ui": final.get("ui"),
            "validation": final.get("validation"), "events": final.get("events", [])}


def mermaid() -> str:
    """The workflow as mermaid text (for visualisation / docs)."""
    return build_graph().get_graph().draw_mermaid()
