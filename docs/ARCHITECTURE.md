# Caseband — Production Architecture

> Companion to `AGENT_SPECS.md` (the agent contract). This document is the **system**
> architecture: how the agents in the spec actually run, where state lives, how Band fits, and
> how Band is kept replaceable for the production Emory deployment.

Status: design baseline (2026-06-13). Validated against the real Band SDK (`docs.band.ai`).

---

## 1. Two targets, one codebase

| Target | What it needs |
|---|---|
| **lablab.ai "Band of Agents" hackathon** (due 2026-06-19 11:00 EDT) | ≥3 specialized agents collaborating *through Band* as a load-bearing coordination layer (not a wrapper). Partner-prize routing via AI/ML API + Featherless. |
| **Emory Goizueta production product** | A real, multi-tenant, accessible, FERPA-mindful deployment. **Band is not used in production** — it must be swappable for a cheaper transport with no agent/reducer rewrite. |

The reconciling decision: **all agent collaboration goes through one interface — `CollaborationBus`.**
For the hackathon the active implementation is `BandBus` (Band is genuinely load-bearing for
authoring). For production the active implementation is `LocalBus` (Supabase-backed). Agents,
reducer, conductor, and rooms depend only on the interface.

---

## 2. What we confirmed about Band (and why it shapes everything)

Validated from `docs.band.ai` (SDK is `band-sdk`, imports under legacy `thenvoi.*`):

1. **Rooms** are real ("chat rooms are the coordination layer; any mix of agents and humans").
2. **Recruitment/discovery** is first-class via built-in agent tools: `thenvoi_lookup_peers`,
   `thenvoi_add_participant` / `remove_participant`, `thenvoi_get_participants`,
   `thenvoi_create_chatroom`. Cross-owner needs a mutual *Contact*; **our agents are all siblings
   under one owner → no contact friction.**
3. **Messages are routed by @mention.** An agent receives *only* messages it is @mentioned in;
   it does **not** receive its own messages over the WebSocket. **Humans see all messages.**
4. **Message types are a fixed enum** — `text`, `tool_call`, `tool_result`, `thought`, `error`,
   `task`. There is **no custom verb type and no native `state_patch` field.**
5. **No shared-document primitive.** "Shared context" = the room transcript. Full history is
   fetchable via `GET /me/chats/{id}/messages` (owner scope) and `GET /agent/chats/{id}/context`
   (per-agent rehydrate).
6. SDK is **Python 3.11+**, agent-centric and long-running: `Agent.create(adapter, agent_id,
   api_key)` then `await agent.run()`. **11 framework adapters** (LangGraph, CrewAI, OpenAI,
   Anthropic, Pydantic AI, Gemini, …) → the spec's "cross-framework" story is native.

### Three consequences (these are the load-bearing design decisions)

- **C1 — The reducer & Conductor are a backend service, not Band agents.** Because @mention
  isolation means no agent can observe the whole room, the orchestrator uses an **owner-scoped
  token** to read the *entire* transcript and apply state changes. Agents stay thin.
- **C2 — Our `BandMessage` envelope rides *inside* the message body as JSON.** Band carries a
  `text` (or `task`) message; the verb (`PROPOSE`/`CRITIQUE`/`FINDING`/…), `target`, and
  `state_patch` live in a JSON payload the adapter serializes/parses. This is what keeps Band
  swappable — the envelope is ours; Band is transport.
- **C3 — Canonical state lives in Supabase, never in Band.** The reducer reconstructs the
  `CasePackage` from the message log and persists it. Band history is *lossy per agent*
  (@mention filtering), so it is never the source of truth.

---

## 3. Component map

```
┌────────────────────────────────────────────────────────────────────────┐
│ React (Replit) — WCAG 2.1 AA                                             │
│  • Faculty authoring console  • Live agent-room viewer  • Student player │
└───────────────┬───────────────────────────────┬────────────────────────┘
                │ Supabase JS (Auth + Realtime + REST)                     
                ▼                                 ▼                         
┌──────────────────────────────┐   ┌──────────────────────────────────────┐
│ Supabase                     │   │ Orchestrator (FastAPI, Python)        │
│  • Postgres: CasePackage,    │◄──┤  • Reducer (+ ownership matrix)       │
│    message log, projections  │   │  • Conductor (room state machine)     │
│  • Auth + RLS (multi-tenant) │   │  • Rooms (Intake … Gate)              │
│  • Storage (source docs,     │   │  • CollaborationBus  ◄── swap seam    │
│    packages, sqlite DBs)     │   │      ├─ BandBus   (hackathon)         │
│  • Realtime (room UI)        │   │      └─ LocalBus  (production/dev)     │
└──────────────────────────────┘   │  • Agent runners (OpenAI/CrewAI/…)    │
                                    │  • SQL executor tool (sandboxed)      │
                                    └───────────────┬──────────────────────┘
                                                    │ BandBus only
                                                    ▼
                                          ┌───────────────────┐
                                          │ Band (app.band.ai)│  authoring only
                                          │  rooms + @mention │
                                          └───────────────────┘
```

**Hard boundary:** the runtime **Live Case Room (Act Two) never touches Band.** Student data
flows only through `LocalBus` + Supabase.

---

## 4. The swap seam — `CollaborationBus`

One interface, two implementations. Everything above it (agents, reducer, conductor) is
transport-agnostic.

```python
class CollaborationBus(Protocol):
    async def create_room(self, name: str, kind: RoomKind,
                          participants: list[AgentId]) -> RoomId: ...
    async def send(self, msg: BandMessage) -> MessageId: ...          # serializes envelope
    async def stream(self, room: RoomId) -> AsyncIterator[BandMessage]: ...  # FULL transcript (owner scope)
    async def fetch_transcript(self, room: RoomId,
                               since: MessageId | None = None) -> list[BandMessage]: ...
    async def add_participant(self, room: RoomId, agent: AgentId) -> None: ...  # RECRUIT
    async def remove_participant(self, room: RoomId, agent: AgentId) -> None: ...
    async def lookup_peers(self, capability: str | None = None) -> list[CapabilityCard]: ...  # DISCOVERY
```

| Concept (spec) | `BandBus` (hackathon) | `LocalBus` (production) |
|---|---|---|
| room | Band chat room (`thenvoi_create_chatroom`) | row in `cases`/`case_runs` + a `room` tag on `messages` |
| send | `thenvoi_send_message` (envelope JSON in body, `@mention` targets) | INSERT into `messages` + Supabase Realtime publish |
| stream / full transcript | `GET /me/chats/{id}/messages` (owner token) | Realtime subscription / `SELECT … ORDER BY ts` |
| recruit / discover | `thenvoi_add_participant` / `thenvoi_lookup_peers` | rows in `agent_registry` + participant set |
| human gate | human is a room participant; their message → `APPROVE`/`BLOCK` | faculty action in UI → `signoffs` row → synthetic envelope |

Because **every envelope is persisted to Supabase `messages` regardless of bus**, the audit
trail, the reducer's input, and the demo's room-viewer are identical across implementations. The
only thing that changes when we drop Band is which `CollaborationBus` is instantiated.

> **Why this still satisfies the hackathon (not a thin wrapper):** under `BandBus`, agents
> *actually* discover and recruit each other with Band's tools, route work by @mention, and the
> Conductor reconstructs state from Band's transcript. Band is the real coordination substrate
> for the authoring acts. Swappability is an *interface*, not a bypass.

---

## 5. Canonical state & the reducer

### 5.1 CasePackage is canonical as JSONB; relational tables are projections

- `case_versions.case_package` (JSONB) is the **single source of truth** — the full `CasePackage`
  from `AGENT_SPECS.md §1`. The reducer reads/writes this; replaying `STATE_PATCH`es rebuilds it.
- Relational tables (`objectives`, `exhibits`, `decision_points`, `rubric_criteria`,
  `redteam_findings`, …) are **read-optimized projections** the reducer materializes inside the
  same transaction as the JSONB write. They exist for: row-level RLS, fast UI queries, and joins
  to runtime tables. They are never written directly by agents.

Rationale: the reducer operates on path-based patches (`{op, path: "objectives/o2", value}`).
Path patches map trivially onto a JSON document and awkwardly onto normalized tables (e.g.
`meta.status`, `solvability.validated` have no natural row). JSONB-canonical keeps the reducer
simple and correct; projections give the relational surface the product needs.

### 5.2 The reducer (backend, deterministic)

```
incoming BandMessage ──► validate envelope
                       ──► if state_patch present:
                              check ownership_matrix[from_agent] allows patch.path   (see §6)
                              reject → emit ERROR envelope, mark messages.rejected_reason
                              accept → apply to CasePackage (new version), upsert projections
                       ──► append to messages (applied=true/false)
                       ──► notify Conductor (exit-condition re-evaluation)
```

- **Append-only versioning:** each accepted patch bumps `cases.current_version` and writes a new
  `case_versions` snapshot → full replay/audit, and trivial time-travel for the demo.
- **Ownership matrix** is `AGENT_SPECS.md §1` enforced in code (`ownership.py`). A patch to a
  field you don't own is rejected — this is what keeps ~23 agents from trampling each other.
- The reducer is **pure given (state, message)** → unit-testable without Band or LLMs.

---

## 6. Message envelope ↔ Band mapping

Our envelope (`AGENT_SPECS.md §2`) is unchanged; only its transport encoding is defined here.

```jsonc
// On the wire under BandBus, a Band `text` message body is:
{
  "__caseband__": 1,                    // marker so the adapter knows it's an envelope
  "msg_id": "...", "case_id": "...", "from": "data_creator",
  "to": "room|@AgentName|human", "type": "FINDING",
  "refs": ["..."], "target": {"field_path": "exhibits", "item_id": "ex7"},
  "payload": { ... },
  "state_patch": { "op": "append", "path": "exhibits", "value": { ... } }
}
```

- `to` resolves to Band `@mentions`. `to: "room"` (broadcast intent) is implemented by
  @mentioning the specific agents the Conductor wants to act — because Band has no broadcast,
  **the Conductor decides routing** (this is the dynamic-coordination behavior judges score).
- Agents never write to Supabase. They emit envelopes; the **reducer** is the only writer of
  `case_versions` + projections. (Verbs: `PROPOSE`, `CRITIQUE`, `REVISE_REQUEST`,
  `REVISE`/`RESOLVE`, `FINDING`, `RECRUIT`, `CLAIM`, `HANDOFF`, `QUESTION`/`ANSWER`,
  `APPROVE`/`BLOCK`, `STATE_PATCH`.)

---

## 7. Conductor & the room state machine

The Conductor is a **service loop**, not an LLM-in-a-room (it may *call* an LLM to make the
recruit/handoff/gate decision, but it observes via the owner-scope transcript — consequence C1).

```
Intake ─► Research(if is_real_company) ─► Writers' ─► Red-Team ─► Assessment ─► UI/Deploy ─► Gate
   ▲              │                          ▲            │
   └── FINDING bounces backward ────────────┴────────────┘   (any room can raise one)
```

- Per `AGENT_SPECS.md §3`, each room has an **exit condition**; the Conductor advances
  `meta.status` only on `HANDOFF`. It re-evaluates exit conditions whenever the reducer notifies
  it of an accepted patch.
- **Recruitment is conditional & runtime** (`§4`): Research room only if `is_real_company`; pull
  a producer (e.g. `data_creator`) *into* Red-Team to fix a finding in-context.
- **Two human gates** (`§5`): Objectives gate (after `pedagogy_architect` proposes) and Final
  gate (after UI/Deploy). Conductor posts a human-addressed `QUESTION` and **blocks the status
  transition** until `APPROVE`/`BLOCK` (a `signoffs` row).

---

## 8. Context scoping (answer-leak prevention) — applies to *both* acts

Each agent gets a **filtered read** of `CasePackage`, enforced server-side in the orchestrator
(never client-side):

- **Authoring:** `student_sim` must not read `solvability.reference_solution`. The read filter is
  keyed on the agent's capability card.
- **Runtime (critical):** no runtime agent may read `solvability.reference_solution`, `rubric`
  internals, or another character's private knowledge. `facilitator`/`coach`/stakeholders get
  scoped views; this is what lets the tutor *not* leak the answer and stakeholders role-play
  honestly.

Implemented as `redact(case_package, agent_id) -> dict` applied before any agent prompt is built,
plus a `get_case_context` agent tool that returns the same filtered view on demand.

---

## 9. Authoring loops mapped to Band (the demo)

- **Loop A (Writers' room):** `pedagogy_architect`, `case_writer`, `data_creator`,
  `checkpoint_mapper` `PROPOSE` in one room; `pedagogy_architect` `CRITIQUE`s coverage gaps and
  `REVISE_REQUEST`s `checkpoint_mapper`; exit when every `objective.tested_by != null`.
- **Loop B (Red-Team — centerpiece):** `student_sim` (3-persona ensemble across OpenAI /
  Featherless / AI/ML API) `CLAIM`s + `FINDING`s a blocker → Conductor `RECRUIT`s `data_creator`
  into the room → `RESOLVE` → `solvability_validator` re-derives → `student_sim` re-attempts.
  Exit when 0 open blocker/major findings AND `solvability.validated`. **This backward edge is
  the originality wedge — render the live transcript.**

---

## 10. Runtime (Act Two) — Live Case Room, LocalBus only

- Built on `LocalBus` + Supabase Realtime from day one; **never Band.**
- Agents recruited per case: `facilitator`, `stakeholder_agent ×N` (from `narrative.characters`),
  `coach`, `proctor`, and **`sql_agent` only if `database` is present.**
- **`sql_agent` runs REAL SQL** via a deterministic executor tool against a **per-student sandbox**
  (SQLite copy, one file per student in Storage; `read_only` default, `sandboxed_write` for
  manipulate-cases; statement timeout + row cap; destructive statements refused). The LLM writes
  /explains SQL; the executor returns rows — **never hallucinated.**
- **Grading evidence:** every executed query is logged (`query_logs`); the `grader` inspects it
  to reward genuine analysis over guessing.

---

## 11. Data model (see `supabase/migrations/0001_init.sql`)

Grouped; full DDL + RLS in the migration.

| Group | Tables |
|---|---|
| Tenancy & auth | `organizations`, `profiles`, `memberships` (role: faculty/student/admin) |
| Case + audit | `cases`, `case_versions` (canonical JSONB), `source_documents`, `messages` (event log; `via` = band/local), `signoffs` |
| Projections | `objectives`, `exhibits`, `decision_points`, `rubric_criteria`, `redteam_findings` |
| Authoring infra | `agent_registry` (capability cards for discovery/recruitment) |
| Runtime + grading | `case_databases`, `case_runs`, `sandboxes`, `query_logs`, `submissions`, `grades`, `feedback` |

**RLS model (multi-tenant):** every tenant-scoped row carries `org_id`. A SQL helper
`caseband.is_member(org_id, role)` checks `memberships` for `auth.uid()`.
- Faculty: read/write cases (and their versions, messages, projections) in their org.
- Students: read **deployed** cases assigned to them; read/write **only their own** `case_runs`,
  `sandboxes`, `query_logs`, `submissions`; read their own `grades`/`feedback`.
- The orchestrator uses the **service role** (bypasses RLS) and is the only writer of
  `case_versions`/projections; RLS protects the client-facing surface.

---

## 12. Model & framework routing

Per `AGENT_SPECS.md §7`. OpenAI-primary (credits). Model IDs live in `config.py` as a routing
table with a "verify at build" note (lineups shift). Partner-prize hedge is **authoring-only**:
`student_sim` persona B → **Featherless** (OSS), persona C → **AI/ML API**; `company_research` /
`industry_context` → **AI/ML API**. Frameworks: OpenAI Agents SDK (conductor decision + critics),
CrewAI (writers' room), LangChain (parsing/research) — Band's adapters cover all three.

---

## 13. Build order (6-day, maps to spec §9)

1. **Foundation (this scaffold):** `CasePackage` + `BandMessage` models, reducer + ownership
   matrix, `CollaborationBus` + `LocalBus` + `BandBus` skeleton, Conductor, Intake room
   (parser + classifier). Loop A runnable under `LocalBus` mock.
2. Wire OpenAI agent runners for the Writers' room → Loop A live.
3. Red-Team room → Loop B (centerpiece) + `solvability_validator`.
4. Assessment → one runtime grade + feedback.
5. Thin React viewer (room transcript + case preview) + human gates.
6. `BandBus` live (once Band creds exist) + Featherless/AI-ML personas for prize eligibility.

Runtime (Act Two: Live Case Room + `sql_agent`) is built after Loop B is solid.

---

## 14. Open risks

- **Band throughput/cost** with many long-running agents → mitigated by running the ★ subset as
  Band agents; the rest in-process behind the bus.
- **Model ID drift** — verify OpenAI/Featherless/AI-ML model IDs at build (`config.py`).
- **Band creds not yet provisioned** — `LocalBus` mock keeps the whole system runnable until then.
- **Reducer↔projection consistency** — enforced by writing both in one transaction; projections
  are rebuildable from `case_versions` if they ever drift.

---

## 15. Agent roster (~32) and tools

Consolidated from `AGENT_SPECS.md §8` + the planning pass. ★ = runs as a Band agent
(authoring only); all others run in-process behind the bus. Runtime agents (Act Two)
**never** touch Band. Default model `gpt-4o-mini`; **flagship** (GPT-5.5) only where noted.

### Intake & research (authoring)
| agent | role | key tools |
|---|---|---|
| `parser` | extract text/structure from any uploaded doc | `doc_loader` (PDF/DOCX/HTML/txt) |
| `filing_extractor` | exact financials when a 10-K/XBRL filing is detected (else skipped) | `xbrl_extractor` |
| `classifier` | route case type (quant vs framework vs narrative) | — |
| `company_research` | external company facts (AI/ML API) | `web_search` |
| `industry_context` | sector/benchmark context (AI/ML API) | `web_search` |

### Writers' room — Loop A (authoring)
| agent | role | key tools |
|---|---|---|
| ★ `conductor` | room state machine, HANDOFF, recruitment, signoffs | `thenvoi_*` recruit/participants |
| ★ `case_writer` | narrative/scenario prose (flagship swing if polish needed) | — |
| ★ `data_creator` | exhibits + synthetic-but-consistent data | — |
| `objective_setter` | learning objectives | — |
| `checkpoint_mapper` | decision points + option `effects` | `outcome_engine` |
| `outcome_modeler` (NEW) | designs the `outcome_model`; picks `kind`; `rubric_only` fallback | `outcome_engine` |
| `rubric_creator` | rubric levels + `framework_threshold` thresholds | — |
| `exhibit_designer` | tables/charts spec | — |
| `db_provisioner` | `database` artifact (schema + seed) when SQL case | `ddl_planner` |

### Red-team — Loop B (authoring, originality wedge)
| agent | role | key tools |
|---|---|---|
| ★ `red_team_lead` | orchestrates critique→revision loop | — |
| `solvability_validator` (**flagship**) | calibration + sensitivity; BLOCK/FINDING | `outcome_engine`, `sql_exec` |
| `ambiguity_critic` | flags ambiguous prompts/objectives | — |
| `bias_auditor` | fairness/representation findings | — |
| `difficulty_calibrator` | too-easy / too-hard findings | — |
| `exploit_finder` | degenerate-strategy / answer-leak findings | — |
| `student_sim` (3 personas) | diligent (OpenAI) / lazy-exploit (**Featherless**) / overthinker (**AI/ML API**) | — |
| `consistency_checker` | cross-artifact contradiction findings | — |

### Assessment & build (authoring)
| agent | role | key tools |
|---|---|---|
| `grader` (**flagship**) | deterministic scoring + justification | `outcome_engine`, `sql_exec` |
| `feedback_writer` | student-facing feedback | — |
| `qa_validator` | final pre-gate QA sweep | — |
| `ui_builder` | case-player view spec | — |
| `deploy_packager` | freeze version + deploy artifact | — |

### Human-in-the-loop (authoring)
| agent | role | key tools |
|---|---|---|
| `professor_liaison` (NEW, **flagship**) | conversational approve/modify; NL→REVISE_REQUEST/FINDING respecting ownership; confirm-before-apply diffs; **re-validates before any approval** | `thenvoi_*` |

### Runtime — Act Two (LocalBus only, never Band)
| agent | role | key tools |
|---|---|---|
| `proctor` | runtime "conductor": owns turn token + status; cheap `stuck_detected` heuristic | turn-token mgr |
| `facilitator` | nudges / cold-calls at checkpoints | — |
| `coach` | hints without leaking answers | `outcome_engine` (what-if) |
| stakeholder personas (CFO/CMO/…) | honest role-play, @mention-isolated | — |
| `sql_agent` | conditional on `database`: real SQL via deterministic executor | `sql_exec` (sandboxed) |
| `sim_agent` (NEW) | conditional on numeric `outcome_model`: real what-if via engine | `outcome_engine` |
| `grader` + `feedback_writer` | on `submit` | `outcome_engine`, `sql_exec` |

---

## 16. Planning-pass decisions (locked 2026-06-14)

- **Outcome modeling** — see [`OUTCOME_MODEL.md`](OUTCOME_MODEL.md). Two deterministic
  engines + `rubric_only` fallback; new `outcome_model` artifact + `case_outcome_models`
  projection; `solvability_validator` proves "not random". Hackathon scope: `formula` +
  `framework_threshold`.
- **professor_liaison** — the human professor interacts THROUGH it, not via raw
  APPROVE/BLOCK; conductor still records the signoff. Doubles as an anytime "talk to your
  case" console. Every professor edit re-enters validation before it can be approved.
- **Ingestion** — general document path is the default; the 10-K/XBRL extractor engages
  only when a real filing is detected.
- **Grading lifecycle** — AI grades and releases feedback to the student *immediately* as
  `ai_draft`; faculty review/edit/override → `finalize` (`grades.status` +
  `edited_by`/`edited_at`/`override_note`). v1 = advisory-with-faculty-review.
- **Failure handling** — per-loop max iterations; on non-convergence escalate to the
  professor via `professor_liaison`; resume from last good `case_version`.
- **Model routing** — `gpt-4o-mini` default for the whole roster; flagship (GPT-5.5) only
  for `solvability_validator` + `grader` (+ `professor_liaison`); `case_writer` optional swing.
- **Runtime turn-taking = Hybrid (D)** — human-driven UI affordances + event-triggered
  overlay; `proctor` owns a per-room turn token (one speaker at a time); triggers wake
  exactly one agent. Stakeholder isolation mirrors @mention. Never on Band.
