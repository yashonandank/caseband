# Caseband

Caseband turns a source document — a 10-K, a news story, a professor's teaching
note — into a **deployable, provably-solvable interactive teaching case** for
business students. A team of LLM agents authors the case; deterministic code
*proves* it has a reachable winning path before any student sees it; students
play it with a Socratic coach; the professor approves grades before release.

> **Design rule that runs through everything:** the LLM *authors and judges*;
> deterministic code owns *state, math, grades, turn-taking, and the answer key*.
> That split is what lets Caseband guarantee a case is solvable rather than hope it is.

## What the product does (the 6-step flow)

1. **Login** — professor or student (`@emory.edu`), JWT.
2. **Chat authoring** — the professor describes the course, assignment, materials,
   and how long the sim should take (duration → number of checkpoints). An
   interview agent keeps asking until it has enough context, then generates a case.
3. **Play-preview + revise** — the professor plays the generated case in student
   mode, then gives natural-language feedback ("add an objective about pricing",
   "lower the ROI target to 12%"). The liaison applies the edit, **re-runs the
   full red-team validation**, and reports whether it's still approvable. Loop
   until the professor approves.
4. **Access code** — on approval the case gets a short code (e.g. `NWQ-7K2`). The
   professor shares it; a student redeems it, enters their name, and a run starts.
5. **Student play** — the student makes decisions against a *redacted* view (no
   formula, no target, no answer key). A **Socratic coach** gives hints, never
   answers — with a defense-in-depth leak guard.
6. **Feedback now, grade later** — on submit the student immediately sees
   *qualitative* feedback. The numeric grade is computed and stored but withheld
   until the professor finalizes it.

## Architecture

```
 React (Vite) web ──HTTP──> Express api-server ──HTTP──> Python FastAPI orchestrator
 artifacts/web              artifacts/api-server          services/  (the agent "brain")
 :5173 (dev)                :8088  /api/*                 :8099
                            auth, courses, Supabase       authoring/red-team/runtime/grading
```

- **Python orchestrator** (`services/`) — the multi-agent brain. A `CasePackage`
  blackboard + a reducer with a strict ownership matrix; **Loop A** (writers'
  room) drives every objective to "tested"; **Loop B** (red-team) proves
  solvability (a reachable witness + every decision variable moves the KPI);
  runtime proctor/coach/grader. Core is stdlib; the HTTP layer is FastAPI.
- **Express api-server** (`artifacts/api-server`) — the platform surface: auth,
  courses, Supabase persistence. It proxies everything under `/api/caseband/*`
  to the Python orchestrator (see `src/lib/orchestrator.ts`).
- **React web** (`artifacts/web`) — React 19 + Vite + Tailwind 4. Role-branched
  professor/student UI implementing the 6-step flow.

The full HTTP interface is frozen in [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).
Design specs: [`AGENT_SPECS.md`](AGENT_SPECS.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/OUTCOME_MODEL.md`](docs/OUTCOME_MODEL.md).

## Run it locally

Requires Python 3.11+, Node 20+, and pnpm.

```bash
# 1. Python brain (:8099)
pip install -r requirements.txt
python3 -m uvicorn services.api.app:app --port 8099 --app-dir .

# 2. Express api-server (:8088) — proxies to the brain
ORCHESTRATOR_URL=http://127.0.0.1:8099 pnpm --filter @caseband/api-server dev

# 3. React web (dev server)
pnpm --filter @caseband/web dev
```

Or boot both API services together: `bash start.sh`.

## Environment

Put secrets in a **gitignored** `.env` at the repo root (see `.env.example`):

| Var | Used by | Notes |
|-----|---------|-------|
| `OPENAI_API_KEY` | orchestrator | required for live authoring, coach, NL revise |
| `OPENAI_ORG_ID` | orchestrator | optional |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | orchestrator store + api-server | when set, the orchestrator persists to Supabase; otherwise it uses an in-memory store |
| `JWT_SECRET` | api-server | auth token signing |

Models: default `gpt-4o-mini`; flagship agents (solvability validator, grader,
professor liaison) use `gpt-5`. The LLM runner normalizes params across the 4o
and reasoning-model families (`services/orchestrator/caseband/llm.py`).

## Tests

The orchestrator/API suites run **standalone** (no pytest needed):

```bash
for t in tests/test_*.py; do python3 "$t"; done
```

TypeScript: `pnpm -r run typecheck`; web build: `pnpm --filter @caseband/web build`.

## Supabase

Schema + RLS live in `supabase/migrations/0001_init.sql`. The access-code join
flow also expects a `caseband.access_codes` table (`code` PK, `case_id`,
`revoked`). The `SupabaseStore` is written but verify column/enum names against
your project on first connect.
