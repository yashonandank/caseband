# Caseband — Outcome Model

How a student's interpretation / analysis / recommendation / choice moves a case's
goal **quantitatively and deterministically — never randomly**, across the full
variety of cases a professor might upload.

> Companion to [`ARCHITECTURE.md`](ARCHITECTURE.md). The outcome model is a
> first-class `CasePackage` artifact, projected to `caseband.case_outcome_models`.

---

## 1. The problem

Cases come in two broad shapes, and we must handle *any* uploaded document:

- **Quantitative-goal cases** — "reach 15% ROI", "hit a 4:1 ROAS", "get NPV > 0".
  The student's choices must change a real number, computed the same way every time.
- **Framework / assessment cases** — "assess this AI deployment against NIST AI RMF";
  pass requires **every category** (Govern, Map, Measure, Manage) to clear a threshold.

The risk is an open-ended "handle every case" surface. We close it with a **finite
taxonomy of deterministic engines** plus a **universal fallback**, so no uploaded
case is ever unhandled.

---

## 2. Design principles

1. **Authored as data, executed by code.** The model is a declarative artifact
   (`outcome_model`), not generated code. Mirrors the SQL "real executor" discipline:
   the LLM *authors and explains*; deterministic engines *compute*.
2. **Closed taxonomy → finite code.** A discriminated `kind` field selects exactly one
   engine. Adding a case type means adding an engine, not branching at runtime.
3. **Universal fallback.** `rubric_only` always applies — a case with no usable numeric
   structure still grades deterministically against a rubric. **No case is unhandled.**
4. **Student input is bound, not inferred.** Student choices couple to the number via
   declared `decision_variables`; the LLM may *propose* NL→params but the **student
   confirms before the engine runs**. The number is never a model hallucination.
5. **Principled, not random — proven.** `solvability_validator` runs calibration +
   sensitivity and must show (a) the target/thresholds are reachable and (b) **every
   decision variable actually moves the KPI**. A zero-effect variable raises a FINDING.

---

## 3. The taxonomy

`outcome_model.kind` ∈ a closed set, split across two engines + the fallback:

### Numeric Engine — KPI vs `target`

| kind | what it computes | example |
|---|---|---|
| `formula` | a KPI from a whitelisted-AST expression over decision variables + exhibit constants | ROI = (gain − cost) / cost |
| `allocation` | spend split across channels through **response curves** (diminishing returns) → blended KPI | marketing mix → ROAS |
| `state_machine` | sequential decisions transition a modeled state; terminal state yields the KPI | multi-quarter turnaround → NPV |

The KPI is compared to a `target` `{value, comparator, units}` → pass/fail + margin.

### Rubric-Threshold Engine — per-category scores vs `thresholds`

| kind | what it computes | example |
|---|---|---|
| `framework_threshold` | scores each framework category from the student's evidence; pass = **all** categories ≥ their `min_score` | NIST AI RMF: 4 categories each ≥ 3/5 |

### Fallback

| kind | what it computes |
|---|---|
| `rubric_only` | no numeric coupling; graded purely against `rubric_criteria`. The default for any case the validator can't make numeric. |

**Hackathon scope:** build `formula` + `framework_threshold` (covers ROI/NPV/ROAS +
NIST; `rubric_only` is free since the rubric engine already exists). `allocation` and
`state_machine` are deferred — `outcome_modeler` falls back to `rubric_only` (or a
`formula` approximation) until they ship.

---

## 4. Coupling student input to the number

Two patterns, both deterministic, both confirmed by the student before compute:

- **Structured commitment** — UI sliders/fields bind directly to `decision_variables`
  (`{key, dp_key, type, bounds|options}`). The student sets `marketing_spend = 250000`;
  the engine reads it.
- **Assumption elicitation** — the student *states assumptions* in NL; the LLM maps
  them to params and shows a confirm-before-run diff; on confirm, the engine computes.

In both cases: **engine computes the number; LLM only explains the number.** No engine
ever runs on un-confirmed, LLM-invented inputs.

---

## 5. The "not random" guarantee (solvability_validator)

Before a case can pass its gate, `solvability_validator` (flagship model) runs against
the authored `outcome_model`:

- **Calibration** — there exists at least one decision-variable assignment that reaches
  the `target` / clears all `thresholds`. If not → BLOCK finding (case is unsolvable).
- **Sensitivity** — perturbing each decision variable produces a non-zero KPI delta,
  recorded in `case_outcome_models.sensitivity`. A zero-effect variable means the choice
  is cosmetic → FINDING (the choice must matter). This is the literal "not random"
  proof: every student decision provably moves the goal.
- On success: `calibrated = true`. The grader and the runtime `sim_agent` may now use the
  same `outcome_engine` to score real student submissions.

---

## 6. Pass policy

`outcome_model.pass_policy` default = `all`: a case with both a numeric target and a
rubric requires **both** to pass. Faculty-overridable per case (e.g. "numeric is
advisory, rubric is binding"). `framework_threshold` is itself all-categories-must-pass.

---

## 7. Agents & tools

| agent | role | tool |
|---|---|---|
| `outcome_modeler` (NEW, authoring) | designs the `outcome_model`; picks `kind`; falls back to `rubric_only` when no numeric structure is supportable | `outcome_engine` (dry-run) |
| `checkpoint_mapper` | authors option `effects` (how each decision option perturbs decision variables) | — |
| `rubric_creator` | authors `framework_threshold` category thresholds + rubric levels | — |
| `solvability_validator` (flagship) | calibration + sensitivity; emits BLOCK/FINDING | `outcome_engine` |
| `grader` (flagship), `coach` | score / explain real student submissions deterministically | `outcome_engine` |
| `sim_agent` (NEW, runtime) | conditional on a numeric `outcome_model` — lets students run "what-if" against the engine, exactly mirroring `sql_agent` being conditional on a `database` | `outcome_engine` |

`outcome_engine` is a single **deterministic** tool (sandboxed AST-whitelist formula
interpreter — no arbitrary `eval`) shared across authoring, validation, grading, and
runtime. Same inputs → same number, everywhere.
