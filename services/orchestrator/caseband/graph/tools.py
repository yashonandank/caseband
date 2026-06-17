"""tools — the per-agent tool library the authoring graph nodes call.

Each function is a TOOL an agent invokes. The deterministic tools (validate_*,
leak_scan, build_ui) return verdicts/artifacts the LLM agents cannot override —
that's how the graph stays flexible without losing the solvability guarantee.

Live tools call the LLM (focused, single-purpose calls); offline they derive from
the gate-passing example so the whole graph runs and is testable without a key."""
from __future__ import annotations
import json
from typing import Any

from ..models.rich_case import RichCase, Company, Exhibit, Stage, RubricCriterion, Backbone
from ..tools import backbone as bb
from ..agents.case_designer import example_case
from . import ui_builder


def _live() -> bool:
    try:
        from ..llm import require_key
        require_key()
        return True
    except Exception:
        return False


# ---- MODELER tools ---------------------------------------------------------
def propose_backbone(brief: dict, feedback: str = "", live: bool | None = None) -> dict:
    """Outcome Modeler tool: propose the analytical backbone NUMBERS first, so the
    gate can check them before any prose is written. `feedback` carries the gate's
    last rejection so the modeler can fix the numbers."""
    live = _live() if live is None else live
    if not live:
        bbn = example_case().backbone
        return bbn.__dict__
    from ..llm import complete_json
    from .. import config
    sys = (_MODELER_SYSTEM + (f"\n\nThe previous numbers were rejected: {feedback}\n"
           "Adjust so the highest fully-loaded cost is NOT the highest direct cost, "
           "by >=15%." if feedback else ""))
    raw = complete_json(sys, _modeler_user(brief),
                        model=config.model_for("outcome_modeler"), max_tokens=1500)
    return raw


def validate_backbone(backbone: dict) -> dict:
    """Solvability Validator tool (DETERMINISTIC): proves the answer exists and is
    non-obvious. The verdict is authoritative."""
    res = bb.validate(backbone)
    return {"validated": res.validated, "true_driver": res.true_driver,
            "naive_guess": res.naive_guess, "margin": res.margin,
            "reasons": res.reasons}


# ---- WRITER tools ----------------------------------------------------------
def write_case(brief: dict, backbone: dict, validation: dict,
               live: bool | None = None) -> dict:
    """Case Writer tool: build the company, exhibits and staged dilemmas AROUND the
    already-proven backbone (so the narrative can't drift from the math). Returns a
    full RichCase dict."""
    live = _live() if live is None else live
    if not live:
        case = example_case()
        d = case.to_dict()
        d["backbone"] = backbone               # keep the (validated) backbone
        return d
    from ..llm import complete_json
    from .. import config
    raw = complete_json(_WRITER_SYSTEM, _writer_user(brief, backbone, validation),
                        model=config.model_for("checkpoint_mapper"), max_tokens=4000)
    raw["backbone"] = backbone
    raw.setdefault("meta", {})["source"] = "graph-live"
    return raw


# ---- RED-TEAM tools --------------------------------------------------------
def leak_scan(case_dict: dict) -> dict:
    """Red-Team tool (DETERMINISTIC): the student-facing prose must not name the
    true driver or quote allocated totals. Returns leaks found."""
    answer = ((case_dict.get("backbone") or {}).get("answer_key") or {})
    true_driver = str(answer.get("true_driver", "")).lower()
    true_label = ""
    for a in (case_dict.get("backbone") or {}).get("activities", []):
        if str(a.get("key", "")).lower() == true_driver:
            true_label = str(a.get("label", "")).lower()
    leaks: list[str] = []
    for s in case_dict.get("stages", []):
        visible = " ".join(str(s.get(k, "")) for k in
                           ("situation", "dilemma", "task", "reveal_on_entry")).lower()
        # a stage may legitimately discuss the activity; a leak is naming it AS the answer
        if true_driver and (f"the answer is {true_driver}" in visible or
                            "is the real driver" in visible and true_label and true_label in visible):
            leaks.append(f"{s.get('key')}: names the answer")
        if "expected_insight" in s and s.get("expected_insight") in visible:
            leaks.append(f"{s.get('key')}: expected_insight leaked into student text")
    return {"clean": not leaks, "leaks": leaks}


def difficulty_ok(backbone: dict) -> dict:
    """Red-Team tool (DETERMINISTIC): the obvious guess should be wrong but the case
    shouldn't be a coin-flip — margin in a sensible band."""
    res = bb.validate(backbone)
    band = 0.10 <= res.margin <= 0.60
    return {"ok": bool(res.validated and band), "margin": res.margin}


# ---- UI BUILDER tool -------------------------------------------------------
def build_ui(case_dict: dict, case_id: str) -> dict:
    """UI Builder tool: render the interactive, deployable HTML case page."""
    case = RichCase.from_dict(case_dict)
    return ui_builder.render_to_file(case, case_id)


# ---- prompts ---------------------------------------------------------------
_MODELER_SYSTEM = (
    "You are an outcome modeler. Return ONLY an activity-costing backbone as JSON: "
    "{overhead_pool (number), activities:[{key,label,direct_cost,overhead_driver,"
    "naive_signal}] (>=4), answer_key:{true_driver,naive_guess,rationale}}. Design "
    "the numbers so that after allocating overhead_pool by overhead_driver share, "
    "the highest FULLY-LOADED cost is NOT the highest direct_cost — by >=15%. "
    "naive_signal = direct_cost.")
_WRITER_SYSTEM = (
    "You are a senior case writer. Using the GIVEN, already-validated backbone "
    "numbers (do not change them), write the case as JSON: {title, company"
    "{name,industry,size,protagonist,backstory,presenting_problem}, "
    "learning_objectives[], teaching_note, exhibits[{key,title,kind,columns,rows,"
    "note}], stages[{key,title,situation,dilemma,task,reveal_on_entry,exhibits[],"
    "expected_insight,rubric[{key,text,weight,dimension,levels[]}]}]. The "
    "protagonist's presenting_problem must point at the WRONG (naive) activity. "
    "Stage 1 = do the analysis; later stages reveal new info and pose judgement. "
    "Never state the answer in student-visible text.")


def _modeler_user(brief: dict) -> str:
    return f"Brief:\n{json.dumps(brief.get('context', brief), indent=2)}\nMethod: {brief.get('method')}"


def _writer_user(brief: dict, backbone: dict, validation: dict) -> str:
    return (f"Brief:\n{json.dumps(brief.get('context', brief), indent=2)}\n"
            f"Validated backbone:\n{json.dumps(backbone, indent=2)}\n"
            f"The true driver is {validation.get('true_driver')}; the naive trap is "
            f"{validation.get('naive_guess')}. Build the case so students must discover this.")
