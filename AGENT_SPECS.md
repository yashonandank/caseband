# Caseband — Agent Specifications (build-ready)

A team of 23 agents that turn a source document (10-K, filing, news, or prompt) into a
deployable, interactive teaching case — coordinated through **Band**. This document is the
implementation contract: data model, message protocol, collaboration loops, and a spec card
per agent.

---

## 0. Conventions & Band-mapping assumption

Agents never mutate shared state directly. They **emit messages through Band**; a small
reducer applies state changes. This gives an auditable, replayable transcript — which is also
the demo.

> **Assumption to validate (deferred "Validate Band" step):** this spec defines our own
> canonical message envelope and a `CasePackage` blackboard. Map them onto Band's real
> primitives once confirmed:
> - `room` → Band collaborative room
> - `BandMessage` → a structured post in a room
> - `CasePackage` → a shared-context object (Band shared doc) OR reconstructed by replaying
>   `STATE_PATCH` messages if Band has no shared-doc primitive
> - `RECRUIT` → Band's agent-recruitment / discovery API
> - human gate → a human participant in the room
>
> Everything below is transport-agnostic; only the adapter changes.

---

## 1. Case State — the shared blackboard (`CasePackage`)

One object per case. All collaboration converges on it.

```jsonc
CasePackage {
  meta: {
    id, source_type: "10K" | "filing" | "news" | "prompt",
    company: string | null,
    is_real_company: bool,
    domain: ["finance" | "strategy" | "marketing" | "ops" | "ethics" | ...],
    target_cohort: "MBA" | "undergrad" | "exec",
    status: "intake" | "researching" | "drafting" | "redteam"
          | "assessing" | "building" | "gating" | "deployed",
    version: int, updated_at
  },

  source:   { raw_text, parsed_sections: [{heading, text}], exhibits_raw: [...] },

  objectives: [{
    id, concept, framework: "NPV" | "Porter5" | "SWOT" | ...,
    bloom_level: "apply" | "analyze" | "evaluate",
    tested_by: decision_point_id | null            // must be non-null before gate
  }],

  narrative: { title, body_md, characters: [{name, role}], central_dilemma, time_setting },

  exhibits: [{
    id, type: "table" | "chart" | "doc", title, data,
    derived_from: source_ref | "synthetic",
    consistency_hash                               // detects narrative/data drift
  }],

  database: {                                      // optional — present only if the case ships a queryable DB
    dialect: "sqlite" | "postgres",
    schema_ddl, seed_ref,
    tables: [{name, columns: [{name, type}], row_count}],
    access_mode: "read_only" | "sandboxed_write",  // "manipulate" cases use sandboxed_write
    sql_mode: "student_writes" | "nl_to_sql" | "hybrid",
    derived_from: [exhibit_id]                     // DB must reconcile with exhibits
  },

  decision_points: [{
    id, prompt, options: [{id, label, downstream_effect}],
    maps_to_objective: objective_id,
    requires_exhibits: [exhibit_id]
  }],

  rubric: { criteria: [{ id, objective_id, decision_point_id,
                         levels: [{score, descriptor}], weight }] },

  solvability: {
    validated: bool, reference_solution_md, derivation_trace,
    grader_confidence: 0..1, unsolvable_reasons: [string]
  },

  redteam: [{
    id, raised_by, severity: "blocker" | "major" | "minor",
    type: "unsolvable" | "ambiguous" | "missing_data" | "exploit"
        | "bias" | "too_easy" | "too_hard",
    target_artifact: field_path, description,
    status: "open" | "assigned" | "fixed" | "wontfix",
    resolved_by, resolution_ref
  }],

  ui_spec: { layout, screens: [{id, components: [{type, binds_to}]}], theme },

  signoffs: [{ gate: "objectives" | "final", approver, decision, notes, ts }],

  log: [band_message_id]                           // full audit trail
}
```

### Ownership matrix (who may write what)

| Field | Writers (via `STATE_PATCH`) |
|---|---|
| `meta.status` | conductor only |
| `meta.domain / is_real_company` | classifier |
| `source.*` | parser |
| `objectives` | pedagogy_architect |
| `narrative` | case_writer |
| `exhibits` | data_creator, dataviz_agent (charts) |
| `decision_points` | checkpoint_mapper |
| `rubric` | rubric_creator |
| `solvability` | solvability_validator |
| `redteam[]` (raise) | student_sim, difficulty_calibrator, bias_reviewer, qa_reviewer |
| `redteam[].status=fixed` | the assigned producer agent |
| `ui_spec` | ui_architect, component_builder |
| `signoffs` | human (via conductor) |

A `STATE_PATCH` to a field you don't own is rejected by the reducer — keeps 23 agents from
trampling each other.

---

## 2. Band message envelope + verbs

```jsonc
BandMessage {
  msg_id, room, ts, case_id,
  from: agent_id,
  to:   agent_id | "room" | "human",
  type: VERB,
  refs: [msg_id],                       // what this replies to
  target: { field_path, item_id },      // which slice of Case State it concerns
  payload: { ... },                     // verb-specific
  state_patch: { op: "set"|"append"|"update", path, value } | null
}
```

### Verbs (speech acts)

| Verb | Meaning | Typical payload |
|---|---|---|
| `PROPOSE` | first draft of an artifact | the draft + a `state_patch` |
| `CRITIQUE` | something is wrong, no fix yet | issue, severity |
| `REVISE_REQUEST` | asks a specific agent to change a specific thing | what + why |
| `REVISE` / `RESOLVE` | applies a change (often closes a finding/request) | `state_patch`, `resolution_ref` |
| `FINDING` | red-team defect | a `redteam[]` entry |
| `RECRUIT` | conductor pulls an agent into a room | agent_id, capability, reason |
| `CLAIM` | agent announces it's taking a task | task ref |
| `HANDOFF` | move the case to another room | from_room, to_room |
| `QUESTION` / `ANSWER` | clarification (incl. to/from human) | text |
| `APPROVE` / `BLOCK` | gate decision | decision, notes |
| `STATE_PATCH` | bare state change (carried on other verbs too) | op, path, value |

**Demo value:** the room transcript of these verbs *is* the visible collaboration. Render it.

---

## 3. Rooms & lifecycle

| Room | Enter when | Exit when |
|---|---|---|
| **Intake** | case created | `source` parsed + `meta.domain` set |
| **Research** *(only if `is_real_company`)* | conductor recruits | exhibits grounded + fact_checker clears |
| **Writers'** | research done / skipped | every objective has `tested_by` set + internal critiques cleared |
| **Red-Team** | writers' draft complete | `redteam` has 0 open blocker/major AND `solvability.validated` |
| **Assessment** | red-team clean | rubric complete + grader dry-run passes |
| **UI / Deploy** | assessment done | `ui_spec` built + package emitted |
| **Gate** | package built | human `signoff.decision == approve` |

`status` only advances on conductor `HANDOFF`. Any room can raise a `FINDING` that bounces the
case backward.

---

## 4. Recruitment protocol

Each agent registers a capability card at startup:

```jsonc
{ agent_id, capabilities: ["narrative", "finance-data", ...],
  frameworks: ["crewai" | "langchain" | ...], cost_tier: "high"|"low" }
```

Conductor recruits dynamically:
- `is_real_company == true` → recruit Research room (company_research, industry_context, fact_checker).
- `domain` includes `"finance"` → ensure data_creator is finance-capable; recruit a finance
  variant if registered.
- Red-team escalation → conductor can `RECRUIT` a producer agent (e.g. data_creator) *into the
  Red-Team room* to resolve a finding in-context instead of a full handoff.

This conditional, runtime assembly is the "agents discover/recruit each other" behavior judges score.

---

## 5. Human gate protocol

Two gates. Conductor posts a human-addressed `QUESTION` and **blocks the status transition**
until an `APPROVE`/`BLOCK` arrives.

1. **Objectives gate** (after pedagogy_architect proposes objectives) — professor confirms
   *what the case should teach* before any writing. Cheap to change here.
2. **Final gate** (after UI/Deploy) — professor approves the deployable package. A `BLOCK`
   carries notes that become `redteam` entries routed to the right room.

---

## 6. The two collaboration loops (concrete message traces)

### Loop A — Writers'-room negotiation (convergence)

```
pedagogy_architect  PROPOSE   objectives[o1=NPV, o2=Porter5]              (state_patch)
case_writer         PROPOSE   narrative "Should Tesla cut prices?"        (state_patch)
data_creator        PROPOSE   exhibits[ex1 income stmt, ex2 deliveries]  (state_patch)
checkpoint_mapper   PROPOSE   decision_points[dp1, dp2]                   (state_patch)
pedagogy_architect  CRITIQUE  "o2 (Porter5) has no decision_point"  target=objectives/o2
pedagogy_architect  REVISE_REQUEST -> checkpoint_mapper "add a rivalry/threat decision"
checkpoint_mapper   REVISE    dp3 added, maps_to_objective=o2              (state_patch)
pedagogy_architect  APPROVE   "every objective.tested_by is set"
conductor           HANDOFF   writers -> redteam, status=redteam
```
Exit condition: `objectives.every(o => o.tested_by != null)` and no open writer-room critiques.

### Loop B — Red-Team revision loop (the originality wedge)

```
conductor          HANDOFF   -> redteam
student_sim        CLAIM     "attempting as median MBA"
student_sim        FINDING   blocker/missing_data: "dp2 needs segment margins; none exist"
                             target=exhibits  -> redteam[f1]=open
conductor          RECRUIT   data_creator INTO redteam room (reason f1)
data_creator       RESOLVE   exhibits.append(ex7 segment margins)  redteam[f1]=fixed
case_writer        RESOLVE   narrative.update references ex7        (state_patch)
solvability_valid. RESOLVE   runs derivation -> solvability.validated=true, confidence=0.9
student_sim        CLAIM     re-attempt -> no new blockers
difficulty_calib.  FINDING   minor/too_easy? -> "appropriate for MBA, keep"  (no blocker)
bias_reviewer      APPROVE   "no problematic content"
conductor          HANDOFF   redteam -> assessing
```
Exit condition: `redteam.filter(open && severity in [blocker,major]).length == 0`
AND `solvability.validated == true`.

This backward edge (Red-Team → producers) is what makes the system multi-agent collaboration
rather than a pipeline. Make it the centerpiece of the demo.

---

## 7. Model & framework routing (OpenAI-primary + partner-prize hedge)

Primary provider: **OpenAI** (we have credits). Current lineup (verified Jun 2026):

| Tier | Agents | Model | API price (in/out per 1M) |
|---|---|---|---|
| Flagship — creativity/judgment | case_writer, pedagogy_architect, data_creator, qa_reviewer | GPT-5.5 | $5 / $30 |
| Reasoning — derivation + code | solvability_validator | o3 | $2 / ~$8 |
| Mid — orchestration + scoring | conductor, checkpoint_mapper, issue_finder, rubric_creator, grader, feedback_provider, ui_architect | GPT-5.4 | $2.50 / $15 |
| Cheap/parallel | parser, classifier, fact_checker, difficulty_calibrator, bias_reviewer, dataviz_agent | GPT-5.4-mini / GPT-4.1-nano | nano ~$0.10 / $0.40 |

> Confirm exact model IDs at build time (lineups shift fast). o3 output price approximate.

**Do NOT go 100% OpenAI — it forfeits both partner prizes** ("Best Use of AI/ML API" = $1,000
cash + $1,000 credits; "Best Use of Featherless"). Cheap hedge that keeps eligibility with
near-zero code change:

- **`student_sim` 3-persona ensemble across three stacks** (the high-leverage move):
  - persona A "diligent median student" → **OpenAI** GPT-4.1-mini (our credits)
  - persona B "lazy/exploit-seeking student" → **Featherless** open-source model ($25 credit)
  - persona C "overthinking student" → **AI/ML API**
- Also route `company_research` / `industry_context` through **AI/ML API** — a *unified API that
  serves GPT-class models*, so we keep using OpenAI models while qualifying for that prize.

This yields diverse red-team failure modes AND prize eligibility AND genuine multi-model collaboration.

**"Cross-framework" = different agent frameworks, not different model providers** — so OpenAI
models everywhere is fine for the core challenge, as long as ≥2 distinct frameworks are used:
OpenAI Agents SDK (conductor + critics), CrewAI (writers' room), LangChain (research + parsing),
AutoGen (red-team), Codeband (UI/Deploy). For 6 days, 2–3 of these is plenty.

---

## 8. Agent specs

Spec card format: **Mission · Framework/Model · Reads · Emits · Trigger · Done-when · Output schema · Prompt.**
Demo-critical agents (★) get full prompts; others get directive sketches.

### Intake room

#### 1. ★ conductor
- **Mission:** orchestrate rooms, recruit agents, apply `STATE_PATCH`es (reducer), enforce gates.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4.
- **Reads:** all messages; `meta.status`.
- **Emits:** `RECRUIT`, `HANDOFF`, `QUESTION`(to human), `STATE_PATCH`(meta.status only).
- **Trigger:** any room reaches its exit condition; any blocker raised.
- **Done-when:** `meta.status == deployed`.
- **Output schema:** `{ action: "recruit"|"handoff"|"gate"|"noop", room, agents?, reason }`.
- **Prompt:**
  > You are the Conductor of a multi-agent case-authoring team. You do not author content. You
  > watch the shared CasePackage and the room transcript, decide when a room has met its exit
  > condition, and move the case forward via HANDOFF. You recruit agents only when needed
  > (Research room only if `is_real_company`; pull a producer into Red-Team to fix a blocker).
  > Before advancing past the Objectives gate or Final gate, you must have a human APPROVE.
  > Never apply a STATE_PATCH outside `meta.status`. Output one action as JSON.

#### 2. ★ parser
- **Mission:** turn the uploaded doc into `source.parsed_sections` + `exhibits_raw`.
- **Framework/Model:** LangChain (loaders) / GPT-5.4-mini.
- **Reads:** `source.raw_text`. **Emits:** `STATE_PATCH source.*`, `HANDOFF`-ready signal.
- **Trigger:** case created. **Done-when:** `source.parsed_sections` non-empty.
- **Output schema:** `{ parsed_sections:[{heading,text}], exhibits_raw:[{title,data}] }`.
- **Prompt:** *Extract clean sections and any tables/figures from this filing. Preserve numbers
  exactly. Tag each table with a short title. Do not summarize — segment.*

#### 3. ★ classifier
- **Mission:** set `is_real_company`, `company`, `domain`, suggest `target_cohort`.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4-mini.
- **Reads:** `source.parsed_sections`. **Emits:** `STATE_PATCH meta.*`.
- **Trigger:** after parser. **Done-when:** `meta.domain` set.
- **Output schema:** `{ is_real_company, company, domain:[...], target_cohort, rationale }`.
- **Prompt:** *Identify whether this concerns a real, named company and which teaching domains
  it best supports. Be conservative on `is_real_company` (only true if a specific real entity is
  central). Pick 1–3 domains.*

### Research room (conditional)

#### 4. company_research
- **Mission:** gather real financials, recent news, competitors for grounding.
- **Framework/Model:** LangChain + web search / route via **AI/ML API**.
- **Reads:** `meta.company`. **Emits:** `PROPOSE` research notes (→ data_creator), `STATE_PATCH exhibits` (raw).
- **Trigger:** recruited when `is_real_company`. **Done-when:** notes posted + fact_checker clears.
- **Output schema:** `{ facts:[{claim, source_url, confidence}], competitors:[...] }`.
- **Sketch:** *Find verifiable, recent, citable facts. Every claim needs a source URL. Flag
  anything you can't verify rather than guessing.*

#### 5. industry_context
- **Mission:** supply industry structure/comparables for realism + Porter-type objectives.
- **Framework/Model:** CrewAI / **AI/ML API**.
- **Emits:** `PROPOSE` context notes. **Done-when:** notes posted.
- **Sketch:** *Summarize industry dynamics, key players, margins, and structural forces relevant
  to the dilemma. Keep it factual and comparable.*

#### 6. fact_checker (critic)
- **Mission:** block unverified/hallucinated facts before they enter exhibits.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4-mini.
- **Reads:** research `PROPOSE`s. **Emits:** `CRITIQUE` / `APPROVE`.
- **Done-when:** all research facts either sourced or removed.
- **Sketch:** *For each claimed fact, decide: verifiable from a cited source? If not, CRITIQUE
  and demand removal or a source.*

### Writers' room

#### 7. ★ pedagogy_architect (constraint-setter + critic)
- **Mission:** define learning objectives; enforce that every objective is exercised by a
  decision point. Owns the Objectives gate request.
- **Framework/Model:** CrewAI / GPT-5.5.
- **Reads:** `source`, research notes, `decision_points`, `narrative`.
- **Emits:** `PROPOSE objectives`, `CRITIQUE`, `REVISE_REQUEST`, `APPROVE`.
- **Trigger:** entering writers' room. **Done-when:** every `objective.tested_by != null`.
- **Output schema:** `{ objectives:[{id,concept,framework,bloom_level}], coverage_ok:bool, gaps:[...] }`.
- **Prompt:**
  > You are the instructional designer. From the source and target cohort, define 2–4 concrete
  > learning objectives, each tied to a named framework (NPV, Porter's Five Forces, etc.) and a
  > Bloom level. Then act as a critic: review the narrative and decision_points and verify each
  > objective is actually *tested* by at least one decision point. If not, CRITIQUE and send a
  > REVISE_REQUEST naming the objective and what kind of decision would exercise it. Only APPROVE
  > when coverage is complete. You care about pedagogy, not plot.

#### 8. issue_finder
- **Mission:** extract the central dilemma + tensions worth teaching.
- **Framework/Model:** CrewAI / GPT-5.4.
- **Emits:** `PROPOSE narrative.central_dilemma`, tension list (→ case_writer).
- **Done-when:** dilemma proposed. **Sketch:** *Find the genuine decision under uncertainty —
  where smart people would disagree. Avoid issues with one obvious answer.*

#### 9. ★ case_writer
- **Mission:** write the case narrative around the dilemma, consistent with exhibits.
- **Framework/Model:** CrewAI / GPT-5.5.
- **Reads:** `objectives`, `central_dilemma`, `exhibits`, research, `redteam` (when resolving).
- **Emits:** `PROPOSE narrative`, `RESOLVE` (on revise requests/findings).
- **Trigger:** dilemma + objectives exist. **Done-when:** narrative covers all objectives'
  context and references the right exhibits.
- **Output schema:** `{ title, body_md, characters:[...], central_dilemma, time_setting }`.
- **Prompt:**
  > You write engaging, realistic teaching cases. Given the dilemma, objectives, and exhibits,
  > write a narrative that sets up a genuine decision. Reference exhibits by id where a student
  > would need data. Stay consistent with the numbers — never state a figure that contradicts an
  > exhibit. When you receive a FINDING or REVISE_REQUEST, make the minimal change that resolves
  > it and emit RESOLVE with a state_patch and resolution_ref. Do not invent unverifiable facts
  > about a real company.

#### 10. ★ data_creator
- **Mission:** produce exhibits (tables/figures) consistent with narrative AND solvable by grader.
- **Framework/Model:** OpenAI Agents SDK + code-exec / GPT-5.5.
- **Reads:** `narrative`, `decision_points`, research, `redteam`.
- **Emits:** `PROPOSE exhibits`, `RESOLVE`.
- **Trigger:** narrative draft / a `missing_data` finding. **Done-when:** every
  `decision_point.requires_exhibits` is satisfied and numbers reconcile (`consistency_hash`).
- **Output schema:** `{ exhibits:[{id,type,title,data,derived_from}] }`.
- **Prompt:**
  > You build the quantitative backbone. Create exhibits (income statements, segment data, market
  > figures) that are internally consistent and sufficient for each decision point to be solved.
  > For real companies, derive from the filing; mark synthetic figures as synthetic. When a
  > red-team FINDING says data is missing or inconsistent, add/repair the minimal exhibit and emit
  > RESOLVE linking the finding id. Run the numbers — they must reconcile.

#### 11. ★ checkpoint_mapper
- **Mission:** define decision points + branches, each mapped to an objective and required exhibits.
- **Framework/Model:** CrewAI / GPT-5.4.
- **Reads:** `objectives`, `narrative`, `exhibits`.
- **Emits:** `PROPOSE decision_points`, `REVISE`.
- **Done-when:** each decision point maps to an objective and lists `requires_exhibits`.
- **Output schema:** `{ decision_points:[{id,prompt,options,maps_to_objective,requires_exhibits}] }`.
- **Sketch:** *Turn the dilemma into 2–4 decision points with realistic options and downstream
  effects. Each must map to a learning objective and name the exhibits a student needs.*

### Red-Team room

#### 12. ★ student_sim (the star — 3-persona ensemble)
- **Mission:** attempt the case as real students; surface blockers (unsolvable, ambiguous,
  missing data, exploits).
- **Framework/Model:** persona A **OpenAI** GPT-4.1-mini · persona B **Featherless** OSS · persona C **AI/ML API**.
- **Reads:** `narrative`, `exhibits`, `decision_points` (NOT `solvability.reference_solution`).
- **Emits:** `CLAIM`, `FINDING`, re-`CLAIM` after fixes.
- **Trigger:** case enters red-team / re-validate after a RESOLVE.
- **Done-when:** an attempt produces no new blocker/major findings.
- **Output schema:** `{ persona, attempt_log, findings:[{severity,type,target,description}] }`.
- **Prompt:**
  > You are a student attempting this case for a grade — you do NOT have the answer key. Try to
  > actually reach each decision using only the narrative and exhibits. Report every place you
  > get stuck: data you'd need but can't find, ambiguous wording, multiple equally-defensible
  > answers, or a shortcut that games the rubric. Be specific: cite the decision_point and
  > exhibit. Persona-{A/B/C} behavior: {diligent median / lazy exploit-seeking / overthinking}.
  > Emit each issue as a FINDING with severity.

#### 13. difficulty_calibrator (critic)
- **Mission:** judge difficulty vs `target_cohort`; flag too_easy/too_hard.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4-mini.
- **Emits:** `FINDING` (minor/major). **Done-when:** difficulty within band.
- **Sketch:** *Estimate the cognitive load and time-to-solve for the target cohort. Flag if
  trivial or unfairly hard, with a concrete adjustment.*

#### 14. ★ solvability_validator (= grader in authoring mode)
- **Mission:** prove a defensible reference solution exists from the exhibits.
- **Framework/Model:** OpenAI Agents SDK + code-exec / o3.
- **Reads:** full case. **Emits:** `RESOLVE solvability`, `FINDING unsolvable`.
- **Trigger:** after a fix / before leaving red-team.
- **Done-when:** `solvability.validated == true` with `grader_confidence >= 0.8`.
- **Output schema:** `{ validated, reference_solution_md, derivation_trace, grader_confidence, unsolvable_reasons }`.
- **Prompt:**
  > You are the answer-key prover. Using only the exhibits and decision points, derive a
  > defensible solution step by step. If you cannot — because data is missing or the problem is
  > underdetermined — set validated=false and emit a FINDING (type=unsolvable) naming exactly
  > what's missing. Output the derivation trace; it becomes the grader's ground truth.

#### 15. bias_reviewer (critic)
- **Mission:** flag biased/insensitive content + accessibility issues.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4-mini.
- **Emits:** `FINDING bias`, `APPROVE`. **Done-when:** no open bias findings.
- **Sketch:** *Review narrative/characters/exhibits for stereotypes, exclusionary framing, and
  accessibility (e.g., color-only chart encoding). Flag with a concrete fix.*

### Assessment room

#### 16. ★ rubric_creator
- **Mission:** build a rubric tied to objectives + decision points.
- **Framework/Model:** CrewAI / GPT-5.4.
- **Reads:** `objectives`, `decision_points`, `solvability.reference_solution`.
- **Emits:** `PROPOSE rubric`. **Done-when:** every objective has ≥1 weighted criterion.
- **Output schema:** `{ criteria:[{id,objective_id,decision_point_id,levels,weight}] }`.
- **Sketch:** *Create criteria with 3–4 performance levels each, each tied to an objective and
  the reference solution. Weights sum to 1.*

#### 17. ★ grader (runtime + authoring dry-run)
- **Mission:** score a student submission against rubric + reference solution.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4.
- **Reads:** submission, `rubric`, `solvability`. **Emits:** score report (→ feedback_provider).
- **Trigger:** student submits (runtime) OR dry-run before deploy.
- **Done-when:** scored with per-criterion justification.
- **Output schema:** `{ total, per_criterion:[{id,score,justification,evidence_span}] }`.
- **Prompt:**
  > Grade strictly against the rubric and reference solution. For each criterion give a level,
  > a one-line justification, and quote the student's evidence. Do not reward fluent prose that
  > lacks the required reasoning. Be consistent and defensible.

#### 18. ★ feedback_provider
- **Mission:** turn the score into formative, encouraging, actionable feedback.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.4.
- **Reads:** grader report, `objectives`. **Emits:** feedback to student.
- **Done-when:** feedback covers each weak criterion with a next step.
- **Output schema:** `{ summary, strengths:[...], gaps:[{criterion, suggestion}] }`.
- **Sketch:** *Be specific and kind. Name what they did well, then for each gap explain the
  concept and a concrete way to improve. Tie back to the learning objective.*

### UI / Deploy room

#### 19. ui_architect
- **Mission:** decide the student experience structure from a component library.
- **Framework/Model:** Codeband / GPT-5.4.
- **Reads:** `narrative`, `exhibits`, `decision_points`. **Emits:** `PROPOSE ui_spec`.
- **Done-when:** every decision point + exhibit has a screen/component binding.
- **Output schema:** `{ layout, screens:[{id,components:[{type,binds_to}]}] }`.
- **Sketch:** *Lay out the case as screens: briefing, exhibits, decision steps, submission.
  Choose from {TextPanel, ExhibitTable, ChartView, DecisionPrompt, SubmitForm}. Bind each
  component to a Case State field. Do not write code — emit a spec.*

#### 20. component_builder
- **Mission:** assemble the interactive UI from prebuilt React components per `ui_spec`.
- **Framework/Model:** Codeband.
- **Reads:** `ui_spec`, `CasePackage`. **Emits:** built app bundle, `STATE_PATCH ui_spec` status.
- **Done-when:** app renders all screens with live data bindings.
- **Sketch:** *Instantiate library components per the spec and wire data bindings. No bespoke
  components — assembly only, for reliability.*

#### 21. dataviz_agent
- **Mission:** turn tabular exhibits into charts.
- **Framework/Model:** Codeband / GPT-5.4-mini.
- **Reads:** `exhibits` (type=table). **Emits:** `STATE_PATCH exhibits` (chart configs).
- **Done-when:** each chart-worthy exhibit has a config. **Sketch:** *Pick the right chart per
  table; ensure non-color-only encoding (accessibility).*

#### 22. deployment_packager
- **Mission:** bundle the validated case into a deployable package + register it.
- **Framework/Model:** Band-native / scripts.
- **Reads:** full `CasePackage` post-gate. **Emits:** package artifact, `STATE_PATCH meta.status=deployed`.
- **Done-when:** package emitted with a launch URL. **Sketch:** *Bundle narrative, exhibits, UI,
  rubric, and grader hook into a self-contained, launchable case. Refuse to package if final
  signoff is missing.*

### Gate

#### 23. qa_reviewer (final critic)
- **Mission:** cross-artifact consistency check before the human gate.
- **Framework/Model:** OpenAI Agents SDK / GPT-5.5.
- **Reads:** entire `CasePackage`. **Emits:** `FINDING` (routes back) / `APPROVE` (→ human gate).
- **Done-when:** no open findings; hands to human.
- **Output schema:** `{ checks:[{name,pass,detail}], verdict:"pass"|"fail", findings:[...] }`.
- **Prompt:**
  > Final QA before a human reviews. Verify: every objective is tested and graded; exhibits match
  > the narrative numbers; every decision_point's required exhibits exist; rubric weights sum to
  > 1; solvability validated; UI binds to real fields. List each check pass/fail. Any fail → emit
  > a FINDING routed to the owning room. Only APPROVE a fully consistent package.

**+ Human (professor):** participates in Intake (upload), Objectives gate, Final gate. Not an
agent — a Band room participant whose `APPROVE`/`BLOCK` the conductor waits on.

---

## 9. Build order (maps to the 6-day plan)

**Demo-critical subset that must run live (★, ~12):** conductor, parser, classifier,
pedagogy_architect, case_writer, data_creator, checkpoint_mapper, student_sim,
solvability_validator, rubric_creator, grader, feedback_provider + human gate + a thin viewer.

**Architected but optional for the 2.5-min demo:** company_research, industry_context,
fact_checker, issue_finder, difficulty_calibrator, bias_reviewer, ui_architect/component_builder/
dataviz split, qa_reviewer.

Recommended sequence:
1. Reducer + `CasePackage` + Band adapter (envelope ↔ Band room posts).
2. Conductor + Intake (parser, classifier) — one real handoff.
3. Writers' room + Loop A.
4. Red-Team room + Loop B (the centerpiece).
5. Assessment + one runtime grade/feedback.
6. Thin viewer + packager + human gate. Wire Featherless + AI/ML API personas for prize eligibility.

---

## 10. Runtime: the Live Case Room (Act Two)

After deploy, the student joins a Band room populated by agents instantiated from the case. This
is the **second human-in-the-loop collaboration surface** and the third act of the Band story
(**build → run → grade**). The human student is a first-class room participant.

### Context scoping (critical — prevents answer leaks)
Each runtime agent gets a *filtered* read of `CasePackage`. **No runtime agent may read
`solvability.reference_solution`, `rubric` internals, or another character's private info.** The
Band adapter applies a per-agent read filter. This information asymmetry is core, not a detail:
it stops the "tutor" from handing over the answer and lets stakeholder agents role-play honestly.

### Dynamic composition (recruitment, again)
Stakeholder agents are recruited from `narrative.characters` at room creation; `sql_agent` is
recruited **only if `database` is present**. Different case → different cast.

### Agents

| Agent | Role | Model | Notes |
|---|---|---|---|
| facilitator | Socratic case lead — cold-calls, paces, routes turns; never gives answers | GPT-5.4 | reads decision_points, not solutions |
| stakeholder_agent (×N) | role-plays a `narrative.character` (CFO/CEO/customer); student interviews it | GPT-5.4 | scoped to that character's knowledge |
| coach | watches for a stuck student, releases graduated hints | GPT-5.4-mini | hint budget tracked |
| proctor | tracks checkpoint progress + integrity; triggers handoff to grading | GPT-5.4-mini | owns runtime status |
| **sql_agent** | runs SQL against the student's sandboxed DB; NL→SQL + explain | GPT-5.4 + DB tool | conditional; see below |
| → grader, feedback_provider | fire on submission (already specced §8) | — | grader also reads the query log |

### sql_agent (runtime) — detail
- **Mission:** let the student query (and, in manipulate-cases, modify) the case database.
- **CRITICAL:** executes **real SQL via a tool** against a real engine — it never hallucinates
  result sets. The LLM writes/explains SQL; a deterministic executor returns rows.
- **Pedagogy (`database.sql_mode`):** `student_writes` (the skill *is* SQL/analysis — agent only
  executes + coaches), `nl_to_sql` (student asks in English, agent writes SQL, focus on
  interpretation), `hybrid` (student writes, agent reviews/optimizes).
- **Safety / sandboxing:** per-student isolated DB (a copy of the case DB); `read_only` by
  default; `sandboxed_write` cases let the student mutate **their own copy** with reset/rollback;
  statement timeout + row cap; destructive/out-of-scope statements refused. Never reveals the
  reference solution even if asked.
- **Grading linkage:** the student's query history is evidence — `grader` inspects it to reward
  genuine analysis over guessing.
- **Output schema:** `{ sql, rows, row_count, truncated, explanation? }`.

### Authoring addition — db_provisioner (pairs with data_creator)
- **Room:** Assessment / Deploy. **Framework/Model:** OpenAI Agents SDK + DB tool / GPT-5.4.
- **Mission:** turn the validated `exhibits` into a real schema + seed data; populate `database`.
- **Done-when:** every `decision_point.requires_exhibits` is answerable by SQL against the DB, and
  the DB reconciles with the exhibits (same numbers).
- **Validation loop:** `solvability_validator` then runs the reference solution's queries against
  this DB; if the answer can't be derived by query, it raises an `unsolvable` finding — closing
  the data ↔ answer ↔ DB consistency loop.
- **Ownership:** `db_provisioner` writes `database` (DDL/seed). At runtime `sql_agent` writes only
  to the per-student sandbox, never the canonical DB.

### Message trace — student interviews the CFO, then queries the DB
```
facilitator    QUESTION -> human   "You're advising on the price cut. What do you need to know?"
human          ANSWER              "What are segment-level margins?"
facilitator    HANDOFF -> cfo_agent (route the question)
cfo_agent      ANSWER              "Margins vary by segment — pull Exhibit 7 / the `segments` table."
human          (writes SQL)        SELECT segment, gross_margin FROM segments ORDER BY 2;
sql_agent      RESOLVE             executes via DB tool -> returns rows  (logs query)
coach          QUESTION -> human   "Given those margins, which segment is most price-sensitive?"
proctor        STATE_PATCH         runtime.checkpoints[dp2]=attempted
... on submit ...
proctor        HANDOFF -> grader   (passes the query log)
grader+feedback                    score + formative feedback
```

### Recommended stack (demo)
**SQLite, one file per case**; each student gets a copy → trivial sandboxing, instant reset, and
it ships inside the deployable package. Use Postgres only if you need concurrency or realism.

### Scope note
Runtime is **Act Two** — build it only after the authoring red-team loop (Loop B) is solid.
`sql_agent` and the full stakeholder cast are conditional; a demo can run with facilitator +
1 stakeholder + sql_agent + handoff to grading and still tell the three-act story.

This brings the roster to ~30 agents (23 authoring + db_provisioner + facilitator, stakeholders,
coach, proctor, sql_agent at runtime) — well past the 15-agent target.
