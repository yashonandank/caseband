"""case_designer — turns an authoring brief into a full RichCase.

LIVE: a multi-pass LLM design (company + exhibits + backbone numbers + staged
dilemmas + anchored rubric), then the deterministic backbone gate
(tools.backbone.validate) rejects trivial/obvious data and the designer retries
with a 'make the real driver non-obvious' nudge. Deterministic code owns the
verdict; the LLM owns the prose and the proposed numbers.

OFFLINE (no key): a hand-built, gate-passing example case (Brightwood Cabinetry —
AI + activity-based costing to find the real bottleneck) so the whole pipeline is
testable and demos without a key. The fallback is intentionally a *good* case, so
"no key" still shows the target quality."""
from __future__ import annotations
import json
from typing import Any, Callable

from ..models.rich_case import (
    RichCase, Company, Exhibit, Stage, RubricCriterion, Backbone, Persona, Knowledge,
)
from ..tools import backbone as bb
from .. import config

MAX_DESIGN_RETRIES = 3


# ---------------------------------------------------------------------------
# Deterministic, gate-passing example (also the offline fallback + test fixture)
# ---------------------------------------------------------------------------
def example_case() -> RichCase:
    """Brightwood Cabinetry: the owner blames CNC machining; ABC reveals the real
    money is in transactional overhead on full-custom orders. Designed so
    tools.backbone.validate passes (clear winner, non-obvious)."""
    company = Company(
        name="Brightwood Cabinetry",
        industry="Custom millwork / furniture manufacturing",
        size="38 employees, ~$4.2M revenue",
        protagonist="Maria Soto, owner and general manager",
        backstory=(
            "Brightwood builds stock, semi-custom, and full-custom cabinetry for "
            "regional builders and high-end residential clients. Margins have "
            "thinned for three years even as revenue grew, and Maria can't see "
            "where the money goes. A vendor has pitched an $85,000 AI-driven "
            "scheduling-and-quoting system that promises to speed up the CNC line."),
        presenting_problem=(
            "Maria is convinced the bottleneck is the CNC machining station — it's "
            "the most expensive equipment and always looks busy — and is leaning "
            "toward buying the AI tool to optimise it."),
    )
    backbone = Backbone(
        kind="activity_costing",
        overhead_pool=1_200_000.0,
        activities=[
            {"key": "design", "label": "Design & drafting",
             "direct_cost": 120_000, "overhead_driver": 800, "naive_signal": 120_000},
            {"key": "cnc_machining", "label": "CNC machining",
             "direct_cost": 380_000, "overhead_driver": 1_200, "naive_signal": 380_000},
            {"key": "hand_finishing", "label": "Hand finishing",
             "direct_cost": 260_000, "overhead_driver": 1_000, "naive_signal": 260_000},
            {"key": "order_processing", "label": "Order processing & change orders",
             "direct_cost": 90_000, "overhead_driver": 5_000, "naive_signal": 90_000},
            {"key": "rework", "label": "Rework on full-custom",
             "direct_cost": 110_000, "overhead_driver": 2_800, "naive_signal": 110_000},
        ],
        answer_key={
            "true_driver": "order_processing",
            "naive_guess": "cnc_machining",
            "rationale": (
                "CNC has the highest DIRECT cost, but consumes little support "
                "overhead. Order processing & change orders consume ~46% of the "
                "overhead pool (thousands of small transactions and spec changes on "
                "full-custom jobs), making it the largest fully-loaded cost. The AI "
                "scheduling tool targets CNC and barely touches the real driver."),
        },
    )
    exhibits = [
        Exhibit(key="E1", title="Overhead pool & activity resource drivers", kind="table",
                columns=["Activity", "Direct cost ($)", "Overhead driver (volume)"],
                rows=[["Design & drafting", 120_000, 800],
                      ["CNC machining", 380_000, 1_200],
                      ["Hand finishing", 260_000, 1_000],
                      ["Order processing & change orders", 90_000, 5_000],
                      ["Rework on full-custom", 110_000, 2_800]],
                note=("Total annual overhead pool to allocate: $1,200,000. Allocate "
                      "by each activity's share of total resource-driver volume.")),
        Exhibit(key="E2", title="Product lines", kind="table",
                columns=["Line", "Units/yr", "Orders/yr", "Avg change orders/job"],
                rows=[["Stock", 5_200, 900, 0.2],
                      ["Semi-custom", 1_800, 1_500, 1.1],
                      ["Full-custom", 420, 2_600, 4.3]],
                note="Full-custom is <6% of units but generates most orders and changes."),
        Exhibit(key="E3", title="AI vendor quote", kind="quote",
                note=("$85,000 one-time + $1,500/mo. Claims 18% faster CNC throughput "
                      "and automated quoting. Scope: scheduling and CNC tool-pathing. "
                      "Does not touch order intake, spec management, or change orders.")),
    ]
    stages = [
        Stage(key="S1", title="Where does the money actually go?",
              situation=(
                  "Maria hands you the books. She's already told the board the CNC "
                  "line is the problem. Before anyone signs an $85k cheque, she wants "
                  "the numbers."),
              dilemma="Is Maria right that CNC machining is where the cost concentrates?",
              task=("Allocate the $1.2M overhead pool across activities using Exhibit "
                    "E1 and rank activities by fully-loaded cost. State the single "
                    "largest cost driver and defend it."),
              reveal_on_entry="",
              exhibits=["E1", "E2"],
              expected_insight=(
                  "After allocation, order processing & change orders is the largest "
                  "fully-loaded cost (~$594k), above CNC (~$513k). CNC's high direct "
                  "cost is misleading."),
              rubric=[
                  RubricCriterion(key="s1_analysis", text="Correctly performs ABC allocation and identifies the true cost driver",
                                  weight=0.6, dimension="analysis",
                                  levels=["Names CNC or mis-allocates",
                                          "Allocates overhead but stops at partial ranking",
                                          "Correctly ranks and names order processing as the true driver"]),
                  RubricCriterion(key="s1_judgment", text="Explains WHY the naive read (CNC) is wrong",
                                  weight=0.4, dimension="judgment",
                                  levels=["No explanation", "Vague", "Ties it to overhead consumption / transaction volume"]),
              ]),
        Stage(key="S2", title="The tool on the table",
              situation="You bring the ABC numbers to Maria.",
              dilemma="Given the real driver, is the $85k AI scheduling tool worth buying?",
              task=("Evaluate the vendor quote (E3) against your Stage 1 finding. "
                    "Recommend buy / don't buy / re-scope, with the financial logic."),
              reveal_on_entry=(
                  "New information: digging into full-custom, you find the rework and "
                  "change orders trace back to ambiguous, hand-drawn client specs that "
                  "the shop re-interprets mid-build. The AI tool's quoting module reads "
                  "structured orders only — it would not touch the spec ambiguity."),
              exhibits=["E3"],
              expected_insight=(
                  "The tool optimises CNC (~24% of loaded cost) and ignores the real "
                  "driver. A strong answer rejects the tool as scoped, or re-scopes AI "
                  "toward spec digitisation / order automation."),
              rubric=[
                  RubricCriterion(key="s2_judgment", text="Recommendation follows from the ABC finding, not the protagonist's hunch",
                                  weight=0.6, dimension="judgment",
                                  levels=["Buys to fix CNC", "Hedges", "Rejects/re-scopes toward the real driver"]),
                  RubricCriterion(key="s2_analysis", text="Uses the cost magnitudes to size the opportunity",
                                  weight=0.4, dimension="analysis",
                                  levels=["No numbers", "Some", "Quantifies that CNC savings can't justify $85k vs the real driver"]),
              ]),
        Stage(key="S3", title="What would you actually do?",
              situation="Maria: 'Okay — so what do I do Monday?'",
              dilemma="What is the highest-leverage, realistic intervention — and how do you handle the people side?",
              task="Give a prioritised recommendation and address implementation risk.",
              reveal_on_entry=(
                  "New information: your most experienced finisher, Dev, has heard "
                  "'AI' and 'automation' and is quietly interviewing elsewhere. Losing "
                  "Dev would spike rework further."),
              exhibits=[],
              expected_insight=(
                  "Target the transactional overhead (standardise specs, reduce change "
                  "orders, possibly AI for order/spec capture), sequence change to "
                  "retain Dev, and treat CNC AI as optional/later."),
              rubric=[
                  RubricCriterion(key="s3_judgment", text="Prioritises the real driver and sequences realistically",
                                  weight=0.5, dimension="judgment",
                                  levels=["Generic", "Reasonable", "Sharp, sequenced, tied to the data"]),
                  RubricCriterion(key="s3_people", text="Addresses the change-management / retention nuance",
                                  weight=0.5, dimension="judgment",
                                  levels=["Ignores Dev", "Mentions", "Concrete retention + comms plan"]),
              ]),
    ]
    return RichCase(
        title="Brightwood Cabinetry: finding the real bottleneck before buying AI",
        company=company,
        learning_objectives=[
            "Perform activity-based costing to locate the true cost driver",
            "Distinguish a fully-loaded cost driver from a high-visibility direct cost",
            "Judge whether a proposed AI/automation investment addresses the real driver",
            "Weigh implementation and change-management risk in a small business",
        ],
        teaching_note=(
            "Students who anchor on CNC (the protagonist's hunch and the highest "
            "direct cost) miss that transactional overhead on full-custom is the real "
            "driver. The case rewards doing the allocation and resisting the framing."),
        exhibits=exhibits, stages=stages, backbone=backbone,
        personas=[
            Persona(
                key="dev", name="Dev Okafor", role="Lead finisher (22 years)",
                public_bio="Runs the hand-finishing station; Maria's most trusted maker.",
                demeanor="Proud, blunt, a little wary of 'efficiency consultants'.",
                hidden_agenda="Worried automation talk means his job; will quit if pushed.",
                knowledge=[
                    Knowledge(key="dev_specs", reveal="if_asked",
                              topic="rework|spec|specs|quality|mistake|error|custom|drawing",
                              ties_to="order_processing",
                              fact=("Most of our redo work on full-custom comes from the "
                                    "hand-drawn client specs — they're ambiguous, so we "
                                    "guess, build it wrong, and rebuild. It's not the "
                                    "machines, it's the paperwork upstream.")),
                    Knowledge(key="dev_cnc", reveal="free",
                              fact=("The CNC line looks busy, sure, but it rarely sits "
                                    "idle waiting on us. The hold-ups are upstream.")),
                    Knowledge(key="dev_quit", reveal="if_pressed", ties_to="people",
                              fact=("Honestly? If this 'AI' means you don't need me, "
                                    "I've had calls from a shop in Marietta.")),
                ]),
            Persona(
                key="cfo", name="Priya Nair", role="Fractional CFO",
                public_bio="Part-time finance lead; built the current cost reports.",
                demeanor="Confident, numbers-first, slightly defensive of her reports.",
                hidden_agenda="Her reports emphasise direct cost; gently steers toward CNC.",
                knowledge=[
                    Knowledge(key="cfo_direct", reveal="free",
                              fact=("On a direct-cost basis CNC machining is clearly our "
                                    "biggest line — that's where I'd point the investment.")),
                    Knowledge(key="cfo_overhead", reveal="if_asked",
                              topic="overhead|allocation|indirect|support|abc|activity",
                              ties_to="order_processing",
                              fact=("We've never properly allocated the $1.2M overhead by "
                                    "activity — it's spread as a flat rate. If you drove it "
                                    "by transactions, the small-order activities would look "
                                    "very different.")),
                ]),
        ],
        meta={"audience": "MBA", "method": "activity-based costing",
              "source": "fallback-example"},
    )


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------
class CaseDesigner:
    """Builds a RichCase from a brief. live=None -> auto (LLM iff OPENAI_API_KEY)."""

    def __init__(self, live: bool | None = None,
                 on_event: Callable[[dict], None] | None = None):
        self._live = live
        self._emit = on_event or (lambda e: None)

    def _is_live(self) -> bool:
        if self._live is not None:
            return self._live
        try:
            from ..llm import require_key
            require_key()
            return True
        except Exception:
            return False

    def design(self, brief: dict) -> RichCase:
        self._emit({"type": "phase", "phase": "design",
                    "label": "Designing the company and the core dilemma…"})
        if not self._is_live():
            self._emit({"type": "phase", "phase": "design",
                        "label": "Using the built-in example case (no LLM key)."})
            case = example_case()
            case.meta["brief"] = brief
            return case
        return self._design_live(brief)

    def _design_live(self, brief: dict) -> RichCase:
        from ..llm import complete_json
        model = config.model_for("outcome_modeler")
        last_problem = ""
        for attempt in range(1, MAX_DESIGN_RETRIES + 1):
            self._emit({"type": "phase", "phase": "design",
                        "label": f"Drafting the case (attempt {attempt})…"})
            system = _DESIGN_SYSTEM + (
                f"\n\nThe previous attempt was rejected: {last_problem}\n"
                "Fix it — make the TRUE cost driver differ from the obvious "
                "highest-direct-cost activity, with a clear margin." if last_problem else "")
            raw = complete_json(system, _design_user(brief), model=model, max_tokens=4000)
            try:
                case = _case_from_llm(raw, brief)
            except Exception as e:                      # malformed -> retry
                last_problem = f"output was malformed: {e}"
                continue
            self._emit({"type": "phase", "phase": "validate",
                        "label": "Checking the numbers hide a real, non-obvious answer…"})
            result = bb.validate(case.backbone.__dict__ if case.backbone else {})
            if result.validated:
                case.meta["backbone_check"] = {
                    "true_driver": result.true_driver, "naive_guess": result.naive_guess,
                    "margin": result.margin}
                self._emit({"type": "phase", "phase": "validate",
                            "label": "Case has a defensible, hidden answer. ✓"})
                return case
            last_problem = "; ".join(result.reasons) or "backbone trivial/unsolvable"
            self._emit({"type": "phase", "phase": "validate",
                        "label": f"Rejected: {last_problem}. Regenerating…"})
        # Couldn't get a valid live case — fall back to the known-good example.
        self._emit({"type": "phase", "phase": "design",
                    "label": "Falling back to the built-in example case."})
        case = example_case()
        case.meta["brief"] = brief
        case.meta["fell_back"] = True
        return case


_DESIGN_SYSTEM = (
    "You are a senior business-school case writer. Produce a rich, realistic, "
    "5+ exhibit teaching case as a SINGLE JSON object. The case MUST have:\n"
    "- a named (fictional unless told otherwise) company with a protagonist whose "
    "STATED belief is a plausible TRAP;\n"
    "- an 'activity_costing' backbone: an overhead_pool and >=4 activities, each "
    "with direct_cost, overhead_driver (resource-driver volume), and naive_signal "
    "(=direct_cost). DESIGN THE NUMBERS so that after allocating the pool by "
    "overhead_driver share, the activity with the highest FULLY-LOADED cost is NOT "
    "the one with the highest direct_cost — the obvious guess must be wrong, by a "
    ">=15% margin. Put the real answer in answer_key.true_driver and the decoy in "
    "answer_key.naive_guess.\n"
    "- 2–4 stages. Stage 1 = do the analysis (find the real driver). Later stages "
    "REVEAL new information in reveal_on_entry that adds nuance and pose judgement "
    "dilemmas (is the proposed solution worth it? what would you do?). Each stage "
    "has an anchored rubric (levels for scores 0/1/2) tagged dimension "
    "'analysis' or 'judgment'.\n"
    "Return JSON with keys: title, company{name,industry,size,protagonist,"
    "backstory,presenting_problem}, learning_objectives[], teaching_note, "
    "exhibits[{key,title,kind,columns,rows,note}], backbone{overhead_pool,"
    "activities[{key,label,direct_cost,overhead_driver,naive_signal}],answer_key"
    "{true_driver,naive_guess,rationale}}, stages[{key,title,situation,dilemma,"
    "task,reveal_on_entry,exhibits[],expected_insight,rubric[{key,text,weight,"
    "dimension,levels[]}]}]."
)


def _design_user(brief: dict) -> str:
    ctx = brief.get("context", brief)
    return (f"Build the case from this brief:\n{json.dumps(ctx, indent=2)}\n\n"
            f"Topic/method: {brief.get('method') or ctx.get('topic') or 'as described'}. "
            f"Audience: {brief.get('audience', 'MBA')}. Make it detailed and nuanced.")


def _case_from_llm(raw: dict, brief: dict) -> RichCase:
    raw.setdefault("meta", {})
    raw["meta"]["brief"] = brief
    raw["meta"].setdefault("source", "llm")
    return RichCase.from_dict(raw)
