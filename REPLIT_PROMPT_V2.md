# Replit prompt — backend upgrade (CrewAI, live progress, real research, conversational authoring)

Paste the block below into the Replit AI Agent for the
`Agentic-Case-Simulation` project.

---

You're working on **Caseband** (this repo). Read `replit.md`, then
`services/orchestrator/caseband/` (the Python "brain") and
`services/api/{app.py,service.py,store.py}` before changing anything.

**Non-negotiable design rule — do not violate it while adding CrewAI:** the LLM
*authors and judges*; deterministic Python owns *state, math, grades,
turn-taking, and the answer key*. The whole product promise is that a case is
**provably solvable**. The reducer (`reducer.py` + `ownership.py`), the outcome
engine (`tools/outcome_engine.py`), the red-team validator (`agents/red_team.py`
`SolvabilityValidator`), and the grader (`tools/grader.py`) are the deterministic
guarantee. CrewAI may orchestrate the *creative* agents and the *conversation*,
but every structural change must still flow through the reducer and every case
must still pass the deterministic red-team gate. **Never let an LLM agent write
the outcome model's target/formula directly into the package without the outcome
engine validating it.**

Focus this pass on **backend capability and correctness**. UX is later — for the
frontend, only do the minimum to surface new backend data.

## 0. First, fix these regressions/cleanups (quick)

1. **Restore the test suite.** The `tests/` directory was dropped. It is the only
   thing proving solvability/grading still work. Recreate `tests/` with standalone
   runners (each file: `python3 tests/<file>.py`) covering at minimum: outcome
   engine (calibrate/sensitivity), reducer ownership, red-team solvability,
   grader lifecycle, runtime submit, access-code join, coach leak-guard, feedback
   gating, and the API (`fastapi.testclient`). If the originals aren't in git
   history, write fresh ones. Wire `pnpm run test:py` to run them. Treat green
   tests as the definition of done for every item below.
2. **Dedupe `requirements.txt`** (fastapi/openai/pydantic/supabase/uvicorn are
   listed twice). Add `crewai` and `crewai-tools` (pin versions).
3. **Make model routing env-driven.** `caseband/config.py` hardcodes
   `FLAGSHIP_MODEL = "gpt-5"`. Read `CASEBAND_DEFAULT_MODEL` and
   `CASEBAND_FLAGSHIP_MODEL` from env with safe fallbacks (`gpt-4o-mini` /
   `gpt-4o`). `replit.md` says the pipeline uses GPT-4o — make that real and
   configurable so a missing gpt-5 entitlement can't break authoring.
4. **Add a timeout to the LLM runner.** `caseband/llm.py` `complete_json` has
   `max_retries=0` and no timeout — a hung call blocks the whole author job. Pass
   `timeout=` to the OpenAI client (e.g. 30s) and surface a clean error.

## 1. Adopt CrewAI for the authoring + research crew (keep the deterministic gate)

Introduce CrewAI as the orchestration layer for the **creative** agents only,
behind the existing `live=True` path. Do **not** rip out the conductor/reducer.

- Add `services/orchestrator/caseband/crew/` with a `build_authoring_crew(...)`.
  Define CrewAI Agents: **Researcher**, **Objective Setter**, **Outcome Modeler**,
  **Checkpoint Mapper**, **Rubric Creator**, and a **Red-Team Critic**. Give each a
  role/goal/backstory aligned to the existing agents in `caseband/agents/`.
- Expose the deterministic functions as **CrewAI tools** the agents must call:
  - `calibrate_outcome_model` / `sensitivity_check` → wrap
    `tools/outcome_engine.calibrate` and `.sensitivity`. The Outcome Modeler MUST
    use these to confirm the target is reachable and every decision variable moves
    the KPI before proposing the model.
  - `web_research` → real web search/scrape (see item 3).
- The Crew produces *proposals* (objectives, decision points, an outcome-model
  spec, a rubric). Convert each proposal into the existing reducer ops
  (`add_objective`, `set_outcome_model`/`add_decision_point`, `add_rubric_criterion`,
  …) and apply them through `reducer.apply` so ownership + validation still hold.
  Then run the existing deterministic `SolvabilityValidator` + `StructuralCritic`
  red-team loop as the **gate**. If it fails, feed findings back to the crew and
  re-run (bounded by `config.MAX_LOOP_*`).
- Keep the current non-CrewAI deterministic writers as a fallback when
  `OPENAI_API_KEY` is absent, so tests run offline.

Acceptance: with a key, `live=True` authoring runs through CrewAI and the produced
case passes the deterministic red-team (`validated: true`). Without a key, the
deterministic path still works and tests pass.

## 2. Live progress feed — "what is the conductor doing right now"

The plumbing already exists: `POST /cases/jobs` + `GET /cases/jobs/{id}/events`
(SSE) in `app.py`, fed by `service.start_author_job` → `on_event` → a queue.
Today it only emits `{type:"agent", agent:<ClassName>, status:"running|done"}`.
Upgrade it to broadcast **human-readable, phase-level** activity:

- Emit events shaped like
  `{type:"phase", phase:"research", label:"Scraping the web for company context…", detail:"...", pct: 0-100}`.
  Map each stage to a friendly label: ingest → "Reading your source material", research
  → "Researching real-world context on the web", objectives → "Defining learning
  objectives", outcome_model → "Building the decision model and checking it's
  solvable", checkpoints → "Writing checkpoint questions", rubric → "Designing the
  grading rubric", redteam → "Proving the case is solvable", done → "Case ready".
- If you adopt CrewAI (item 1), drive these from CrewAI's `step_callback` /
  `task_callback` so the feed reflects real agent steps (including tool calls like
  web search). Otherwise enrich the existing `on_agent` callback in
  `conductor.run_loop_a/b`.
- **Extend the job to cover the whole pipeline**, not just Loop A: run
  research → writers → **red-team** inside the same job and stream phases for all of
  it, ending with a single `done` event carrying the case summary. (Right now
  redteam is a separate synchronous call.)
- Frontend (minimal): in `artifacts/web`, subscribe to the SSE stream during
  generation and show the latest `label` in the existing spinner, with a small
  rolling log of completed phases. No redesign — just surface `label`/`pct`.

Acceptance: starting a live generation shows a changing status line
("Researching…", "Writing checkpoint questions…", "Proving the case is solvable…")
backed by real backend phases, ending in "Case ready".

## 3. Real web research (replace the stub)

`agents/research.py` `ResearchScout` only materializes *injected* findings — no
actual research happens, so the research room is effectively dead even though
`extract()` sets `needs_research`.

- Add a real research tool using a search/scrape provider — prefer **Tavily**
  (`TAVILY_API_KEY`) or **Serper** (`SERPER_API_KEY`); CrewAI ships
  `SerperDevTool` / `ScrapeWebsiteTool` you can reuse. Gate it behind the env key;
  with no key, fall back to the injected/no-op behavior so tests stay offline.
- When `needs_research` is true, the Researcher agent should search for the
  company/topic/industry context, extract a few grounded facts (label, value,
  unit, **source URL**), and add them as exhibits via the existing `add_exhibit`
  reducer op (data_creator owns exhibits). Always store the source URL.
- Stream research activity into the progress feed (item 2): "Searching for {query}…",
  "Reading {domain}…", "Found: {fact}".

Acceptance: authoring a case from a thin prompt (e.g. "a pricing case about
Netflix") pulls real, sourced facts into exhibits, visible in the progress feed.

## 4. Conversational, deepening case creation (replace linear slot-filling)

`agents/interview.py` is a rigid slot-filler (course → assignment → materials →
duration). Make it genuinely conversational: when the professor names a rich
topic or goal, the agent should **probe deeper on that thread** before moving on,
the way Claude/Replit chat does.

- Replace the linear `step()` with an **LLM-driven interviewer** that keeps
  structured state: `brief_so_far` (what's known), `open_threads` (things worth
  digging into), and `missing` (hard requirements still unfilled). Each turn the
  LLM decides: ask a deeper follow-up on the current thread, surface a suggestion,
  or advance — and updates the structured state. Keep the stateless contract
  (`interview(state, message)` round-trips `state`) so the frontend is unchanged.
- Keep a **deterministic readiness floor**: do not signal `ready:true` until the
  hard requirements are satisfied (a teachable decision/goal, some grounding
  material or an explicit "research it for me", and a duration → checkpoints via
  the existing `checkpoints_for`). The LLM enriches; deterministic code still
  decides "enough".
- The agent should be able to *propose* directions ("This sounds like a
  market-entry decision — want me to make the core tension pricing vs. share?")
  and, when the professor says "research it", trigger the web-research path (item
  3) instead of demanding pasted material.
- Provide a deterministic offline fallback (current slot-filler) so tests pass
  with no key.

Acceptance: a professor can type a one-line idea and have a multi-turn,
branching conversation that drills into the topic, suggests angles, and only
finalizes the brief once the real requirements are met — verifiable with a live
key, with the offline floor still covered by a test.

## 5. Other backend improvements (do if time permits, smallest first)

- **Persist access codes and jobs** (currently in-memory in `store.py`/`app.py`)
  in Supabase so they survive restarts and work across workers. Add a
  `caseband.access_codes` table (`code` PK, `case_id`, `revoked`).
- **Job lifecycle**: cap concurrent jobs, clean up finished queues, add a cancel
  endpoint, and a max wall-clock per job.
- **Stream red-team** findings the same way as authoring.
- **Structured logging** (one line per agent step + tool call) for debugging the
  multi-agent pipeline.
- **Verify `SupabaseStore`** end-to-end against the real schema and fix any
  column/enum mismatches (it was written but never run against a live DB).

## Constraints

- Keep the HTTP contract stable where the frontend already depends on it; add new
  fields rather than breaking shapes.
- Every item ends with **green tests** (item 0). If you add a capability, add a
  test for it (offline-deterministic path at minimum).
- Make all new external dependencies (CrewAI provider, Tavily/Serper) **env-gated
  with offline fallbacks** so the app and tests run without keys.
- Work within the existing structure; don't introduce a second orchestration
  architecture alongside the reducer — CrewAI sits *in front of* it, not instead
  of it.
