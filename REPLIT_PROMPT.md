# Replit setup prompt

Paste the block below into the Replit AI Agent after importing
`github.com/yashonandank/caseband`.

---

I've imported an existing, working monorepo called **Caseband**. Do **not** rebuild
it — wire it up to run on Replit and connect Supabase. Read `README.md` and
`docs/API_CONTRACT.md` first.

**What Caseband is:** a multi-agent system that turns a source document (a 10-K,
a news story, a professor's teaching note) into a *provably-solvable* interactive
business-school teaching case. LLM agents author the case; deterministic Python
*proves* there's a reachable winning path before any student sees it; students
play with a Socratic coach; the professor approves grades before release. Core
principle: the LLM authors/judges, deterministic code owns state, math, grades,
turn-taking, and the answer key.

**The product flow (already implemented end to end):**
1. Login (professor/student, JWT).
2. Professor authors via a chat interface (asks until it has enough context;
   duration → number of checkpoints).
3. Professor plays the generated case in student mode, gives natural-language
   feedback, the system revises + re-validates solvability, loop until approved.
4. On approval the case gets an access code; a student redeems it + enters a name.
5. Student plays a redacted view; a Socratic coach gives hints, never answers.
6. Student sees qualitative feedback immediately; the numeric grade is withheld
   until the professor finalizes it.

**Architecture (three services):**
- `services/` — Python **FastAPI orchestrator** (the agent brain). Run:
  `python3 -m uvicorn services.api.app:app --host 0.0.0.0 --port 8099 --app-dir .`
- `artifacts/api-server/` — **Express** platform/auth server. Proxies everything
  under `/api/caseband/*` to the Python orchestrator via `ORCHESTRATOR_URL`.
  Run: `pnpm --filter @caseband/api-server start` (set `ORCHESTRATOR_URL=http://127.0.0.1:8099`).
- `artifacts/web/` — **React 19 + Vite + Tailwind** UI. Dev:
  `pnpm --filter @caseband/web dev`. Prod: `pnpm --filter @caseband/web build`
  then serve `dist/`. It calls the Express server's `/api`.

`bash start.sh` already boots the two API services together; `.replit` and
`replit.nix` are included.

**What I need you to do:**
1. Install deps: `pip install -r requirements.txt` and `pnpm install`.
2. Set these Replit Secrets (do not hardcode):
   - `OPENAI_API_KEY` — required for live authoring, the coach, and NL revise.
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — when present the orchestrator
     persists to Supabase; without them it uses an in-memory store.
   - `JWT_SECRET` — for the Express auth server.
3. Provision Supabase: run `supabase/migrations/0001_init.sql`. Then add a
   `caseband.access_codes` table for the join flow: columns `code` (text, primary
   key, the normalized code), `case_id` (uuid/text), `revoked` (bool, default
   false). The `SupabaseStore` in `services/api/store.py` is written but
   unverified — reconcile any column/enum name mismatches against the actual
   schema and fix them in that file only.
4. Expose the web app publicly and point it at the Express server. Make sure the
   Express server can reach the Python orchestrator on localhost.
5. Verify: run the standalone tests (`for t in tests/test_*.py; do python3 "$t"; done`),
   then smoke-test the live flow — author a case, run red-team (expect
   `validated: true`), issue an access code, join, ask the coach (should give a
   hint, never the answer), submit (should return feedback with `released:false`),
   finalize (should release the number).

Keep changes minimal and within the existing structure. The HTTP contract in
`docs/API_CONTRACT.md` is frozen — match it.
