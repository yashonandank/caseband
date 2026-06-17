# Caseband — implementation roadmap (rich agentic system)

Status legend: ✅ built · 🔨 partial · 📋 planned.

This is the full build map for turning Caseband into a ~30-node agentic system on
LangGraph where each agent owns unique tools, cases are nuanced multi-stage
artifacts (data + personas + staged reveals), and the "provably solvable"
guarantee holds throughout.

---

## 0. Invariants (hold these for every new piece)

1. **LLM proposes; deterministic code commits & verifies.** Every state change
   goes through a reducer; every "is it good?" verdict (solvable, non-obvious,
   consistent, leak-free, in difficulty band) is deterministic code, never an LLM
   opinion. This is the moat.
2. **Every LLM agent has an offline deterministic fallback** so the whole system
   runs and is testable with no API key (the demo path).
3. **Nothing student-facing leaks the answer** — not exhibits, worksheets,
   personas, coach, or UI. A deterministic leak auditor enforces it.
4. **Every node streams a human-readable phase event** (the live "what's it doing"
   feed) — authoring and runtime.
5. **Tools are typed, registered, and reusable across agents** (a tool registry,
   not ad-hoc functions).

---

## 1. Current state ✅

- Rich case schema (`models/rich_case.py`): company, exhibits, stages, backbone.
- Deterministic backbone gate (`tools/backbone.py`): solvable + **non-obvious**.
- Case designer (`agents/case_designer.py`): LLM + gate + retry + example fallback.
- Agentic interviewer (`agents/interview_agent.py`): deepening, asks method+grading.
- Staged-reveal runtime (`runtime/staged_run.py`).
- LangGraph authoring graph (`graph/authoring_graph.py`): interleaved
  propose→validate→feedback→write→leak→build-UI.
- Agent tool library (`graph/tools.py`) + **UI-builder agent** (`graph/ui_builder.py`):
  interactive HTML (exhibits, live worksheet, staged player), served `/case-ui/{id}`.
- Legacy spine still present & green: reducer, ownership, outcome_engine, grader,
  coach_session, feedback, access_code, redact, professor_liaison. 125 tests green.

---

## 2. Target architecture

```
                ┌──────────────── AUTHORING GRAPH (LangGraph) ───────────────┐
 professor chat │ interview → research → dataset → model(engine) → validate  │
   (agentic)    │   → write narrative → personas → exhibits → rubric         │
                │   → adversarial-student gate → difficulty/leak/consistency │
                │   → UI build (multi-artifact) → publish                    │
                └────────────────────────────────────────────────────────────┘
                                  │ RichCase (frozen, proven)
                                  ▼
                ┌──────────────── RUNTIME GRAPH (LangGraph) ─────────────────┐
   student      │ proctor(turn-token) → [coach | facilitator | interviewee   │
                │  personas | sim/what-if] → stage advance/reveal → submit   │
                │  → grade(analysis det. + judgment LLM) → feedback-now      │
                └────────────────────────────────────────────────────────────┘

   DETERMINISTIC SPINE (authority, never an LLM): reducer · analytical engines ·
   consistency auditor · leak auditor · difficulty calibrator · grader math ·
   information ledger · redaction · access codes
   INFRA: tool registry · streaming bus · model router · persistence (Supabase) ·
   tracing · generation cache
```

Two graphs (authoring vs runtime) keep concerns clean and let us reason about
cost (authoring = heavy/one-time; runtime = lean/per-student).

---

## 3. Domain model evolution 📋

### 3a. Pluggable analytical engines (`engines/`)
Generalize `backbone.py` (today ABC-only) into an `AnalyticalEngine` protocol so a
case can be ABC, NPV, breakeven, capacity, segmentation, pricing, variance…:

```
class AnalyticalEngine(Protocol):
    key: str
    def propose_params(brief, benchmarks) -> dict        # LLM-assisted
    def validate(params) -> EngineVerdict                 # DETERMINISTIC: solvable, non_obvious, margin, answer
    def student_worksheet(params) -> WorksheetSpec        # what the student fills in (no answer)
    def compute(params, student_inputs) -> dict           # the live calculator behind the worksheet
    def grade_analysis(params, student_answer) -> Score   # DETERMINISTIC analysis score
```
Starter engines: `activity_costing` ✅ (refactor existing), `npv_irr`,
`breakeven_contribution`, `capacity_bottleneck` (theory of constraints),
`segmentation_clv`, `pricing_elasticity`, `variance_analysis`. Each ships its own
deterministic validator + worksheet renderer + analysis grader. The UI builder
renders the right interactive widget per engine.

### 3b. Persona model (your interviewee idea) 📋
Add `personas: list[Persona]` to RichCase, authored by the writer:
```
Persona{ key, name, role, public_bio, demeanor,
         knowledge:[{ fact, reveal: "free"|"if_asked:<topic>"|"if_pressed"|"never",
                      ties_to_objective? }],
         hidden_agenda }
```
Runtime **Interviewee agent** answers in character, gating each fact by its reveal
rule, and writes to an **information ledger** (what the student uncovered). Never
reveals the engine answer or `never` facts. The ledger feeds the grader (reward
good investigation) and the coach ("have you asked the plant manager about
rework?"). This is progressive disclosure pulled by the student, not just pushed.

### 3c. Dataset model (your dataset-creator idea) 📋
A **Dataset Creator agent** generates internally-consistent data (financials, ops
tables, time series) that (a) feed the engine's params, (b) become exhibits, and
(c) tie out across exhibits. A deterministic **consistency auditor** checks
invariants (totals reconcile, drivers match volumes, ratios within benchmark
ranges) and rejects contradictions. Controlled "noise"/decoys are added so the
answer isn't obvious — but the auditor proves the real answer still wins.

### 3d. Information ledger + run state 📋
Runtime state object tracking: current stage, revealed facts (from personas &
reveals), worksheet submissions, transcript, coach-help budget, grade. Backs
grading, feedback, and resumability.

---

## 4. Full agent roster (the real "32")

LLM = reasoning agent; DET = deterministic node/tool (not an LLM). Each LLM agent
owns tools and has an offline fallback.

### Authoring room
| # | Agent | Kind | Owns / tools |
|---|-------|------|--------------|
| 1 | Intake Interviewer ✅ | LLM | propose_angle, set_brief_dimension, summarize_plan |
| 2 | Research Scout 📋 | LLM | web_search, scrape_page, fetch_benchmarks, verify_fact(2-src), cite_source |
| 3 | **Dataset Creator** 📋 | LLM | synth_financials, synth_timeseries, anchor_to_benchmark, inject_decoy, build_exhibit_table |
| 4 | Consistency Auditor 📋 | DET | reconcile_totals, check_ratios, cross_exhibit_ties |
| 5 | Outcome Modeler 📋 | LLM | choose_engine, propose_params (per engine) |
| 6 | Solvability Validator ✅ | DET | engine.validate (solvable + non-obvious + margin) |
| 7 | Difficulty Calibrator 📋 | DET+LLM | sample_pass_region, tune_to_band(20–55%) |
| 8 | Case Writer 🔨 | LLM | create_company, define_protagonist, set_presenting_problem(trap), draft_stage, decide_checkpoints, write_reveal |
| 9 | **Persona Author** 📋 | LLM | author_persona, set_knowledge_reveals, define_hidden_agenda |
| 10 | Exhibit Designer 📋 | LLM | select_exhibits, decide_what_to_hide, caption |
| 11 | Decoy/Trap Author 📋 | LLM | plant_plausible_distractor (validated wrong by engine) |
| 12 | Rubric Designer 🔨 | LLM | draft_criterion, anchor_levels, map_to_objective, tag_dimension |
| 13 | Pedagogy/Bloom Auditor 📋 | LLM | score_cognitive_level, reject_recall_objectives |
| 14 | Adversarial Student 📋 | LLM | attempt_solve(student_view), attempt_game → gate |
| 15 | Leak/Redaction Auditor 🔨 | DET | scan_student_surfaces_for_answer |
| 16 | Numeracy Auditor 📋 | DET | recompute_all_numbers, flag_impossible |
| 17 | Case Doctor 📋 | LLM | holistic critique → punch-list back to writers |
| 18 | UI Builder ✅ | DET | render exhibits/worksheet/staged player (+ per-engine widgets, charts) |
| 19 | Professor Liaison ✅ | LLM | parse_intent, preview_diff, apply+revalidate |

### Runtime room
| # | Agent | Kind | Owns / tools |
|---|-------|------|--------------|
| 20 | Proctor ✅ | DET | turn-token, trigger routing |
| 21 | Coach ✅ | LLM | socratic_hint, graduated_hint, detect_misconception, leak_guard(DET) |
| 22 | Facilitator 📋 | LLM | checkpoint_nudge, cold_call, pace_check |
| 23 | **Interviewee personas** 📋 | LLM | answer_in_persona, gate_reveal, log_to_ledger, leak_guard(DET) |
| 24 | Sim / What-if ✅ | DET | engine.compute, lever_effects (no target leak) |
| 25 | Grader — analysis ✅ | DET | engine.grade_analysis |
| 26 | Grader — judgment 📋 | LLM | judge_rubric(anchored), multi-rater agreement |
| 27 | Feedback Composer 📋 | LLM | tie feedback to student's decisions + ledger; "what a strong answer saw" |
| 28 | Tutorial/Onboarding 📋 | LLM | explain the tools to the student on entry |

### Cross-cutting
| # | Agent | Kind | Owns / tools |
|---|-------|------|--------------|
| 29 | Reading-level/Localizer 📋 | LLM | adjust length/difficulty/translate |
| 30 | Citation agent 📋 | DET+LLM | ensure researched facts carry sources |
| 31 | Pacing/Time agent 📋 | DET | duration → stage budget, enforce |
| 32 | Eval Harness driver 📋 | DET | run corpus, score regressions |

---

## 5. New/expanded tool library 📋

Registry `graph/registry.py`: each tool = `{name, kind: llm|det, schema_in, schema_out, fn}`.
New tools beyond what's built: `web_search`, `scrape_page`, `fetch_benchmarks`,
`verify_fact`, `synth_financials`, `synth_timeseries`, `inject_decoy`,
`reconcile_totals`, `cross_exhibit_ties`, `choose_engine`, `sample_pass_region`,
`tune_difficulty`, `author_persona`, `set_knowledge_reveals`, `attempt_solve`,
`attempt_game`, `score_cognitive_level`, `judge_rubric`, `compose_feedback`,
`answer_in_persona`, `gate_reveal`, `render_chart`, `render_timeline`,
`render_model_sandbox`.

---

## 6. Authoring graph (expanded) 📋

```
interview ─▶ research ─▶ dataset_create ─▶ consistency_audit ─(fail)▶ dataset_create
  ▶ choose_engine ─▶ propose_params ─▶ validate ─(fail+reason)▶ propose_params
  ▶ difficulty_calibrate ─(out of band)▶ propose_params
  ▶ write_narrative ─▶ author_personas ─▶ design_exhibits ─▶ design_rubric
  ▶ leak_audit ─(leak)▶ write_narrative
  ▶ adversarial_student ─(trivial/gameable)▶ propose_params | write_narrative
  ▶ case_doctor ─(punch-list)▶ relevant node
  ▶ build_ui ─▶ END
```
Keeps the interleaved "validate while writing" principle; adds the consistency,
difficulty, adversarial, and doctor gates as conditional edges. Every gate is
deterministic or a structured-verdict LLM with a deterministic threshold.

---

## 7. Runtime graph 📋
Proctor holds the turn token; conditional routing to coach / facilitator /
interviewee persona / sim. Student advances stages (push reveals) and interviews
personas (pull reveals → ledger). Submit → analysis grade (DET) + judgment
(LLM) → feedback-now; numeric grade gated to professor finalize. All on student
view only; persona + coach run the deterministic leak guard.

---

## 8. Grading & feedback 📋
- **Analysis** graded deterministically by the engine (right driver / right NPV…).
- **Judgment** graded by an LLM judge with **anchored rubric levels** and
  **multi-rater agreement** (flag low-agreement for professor review).
- Feedback ties to the student's *actual* inputs + what they *uncovered* via
  interviews (the ledger), plus a post-finalize "what a strong answer considered"
  built from the engine witness + rubric.

---

## 9. Quality & eval harness 📋 (the meta-layer)
- **Adversarial-student gate** (authoring): a sim student must be able to solve it
  from the student view AND must fail to game it. Both required to publish.
- **Regression corpus** (`eval/cases/*.json`): briefs with expected properties
  (engine, solvable, difficulty band, objective coverage, no leaks, persona
  consistency). A driver runs the authoring graph over them and scores deltas, so
  "did this change make cases worse?" is measurable. Without this, agent quality
  is unmeasurable.

---

## 10. Frontend 📋
- **Authoring chat** (agentic, Replit-style): streams the plan/tasks + live phase
  feed (SSE from the graph), shows the generated case, preview/revise loop.
- **Play**: renders the UI-builder page + an **interview panel** (chat with
  personas) + worksheet submission + staged reveals.
- **Professor**: preview-as-student, revise, grade review/release.

---

## 11. API additions 📋
`/cases/graph` ✅, `/case-ui/{id}` ✅; add `/cases/{id}/personas`,
`/rich-runs/{id}/interview` (persona Q&A), `/rich-runs/{id}/worksheet`,
`/rich-runs/{id}/grade`, `/rich-runs/{id}/finalize`, SSE `/cases/graph/stream`,
`/eval/run`.

---

## 12. Infra 📋
- **Tool registry** + typed schemas; **streaming bus** standardized event shape.
- **Model router**: per-node tier (cheap phrasing vs flagship judgment), env-driven.
- **Persistence (Supabase)**: `rich_cases`, `personas`, `datasets`, `rich_runs`,
  `ledgers`, `grades`, `eval_runs`. RichCase JSONB + relational indexes.
- **Generation cache**: hash(brief+engine) → case, so re-runs are cheap.
- **Tracing**: per-node timing/cost/token logs (LangSmith-compatible or local).

---

## 13. Build phases (sequencing)

- **P1 — Engines + grading close-out** (offline-testable): refactor backbone into
  `engines/activity_costing`, add `npv_irr` + `breakeven`; per-stage grader
  (analysis det. + judgment LLM); feedback-now/grade-later wired to rich runs.
- **P2 — Personas + interviewee runtime**: persona model, Persona Author node,
  Interviewee runtime agent, information ledger, interview API + leak guard.
- **P3 — Dataset Creator + consistency/numeracy auditors + decoy author**:
  real, tie-out datasets with planted-but-beaten decoys.
- **P4 — Quality gates**: adversarial student, difficulty calibrator, Bloom
  auditor, case doctor; wire into the authoring graph.
- **P5 — Research grounding**: web_search/scrape/benchmarks behind env keys.
- **P6 — Eval harness + tracing + cache + model router** (make it measurable/cheap).
- **P7 — Persistence to Supabase** for all new entities.
- **P8 — Frontend**: authoring chat + live feed, play (UI page + interview panel),
  professor review.

Each phase ends green-tested with offline fallbacks; live LLM optional per phase.

---

## 14. Open decisions (need your call before P1)
1. **Engine breadth first or persona depth first?** (P1 engines vs P2 personas) —
   personas are the most novel demo feature; engines make cases varied.
2. **How many engines for v1?** (ABC + 2, or just polish ABC deeply?)
3. **Personas: how many per case, and is interviewing required or optional** to
   solve? (Affects grading — do we reward investigation?)
4. **Dataset realism**: synthetic-calibrated only, or web-grounded benchmarks now?
5. **Eval harness now or later?** (Strongly recommend early — it guards every
   later change.)
6. **Frontend**: build in this repo, or keep handing Replit prompts?
