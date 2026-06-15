# Caseband API Contract (frozen 2026-06-14)

The shared interface the parallel build agents target. **Do not change shapes
without updating this file.** Frontend builds to it; backend implements it; the
orchestrator service already serves the `/caseband` half.

Base: Express api-server at `/api`. Auth via `Authorization: Bearer <jwt>` except
`/auth/*` and `/health`. Roles: `professor` | `student`. Errors: `{ "error": string }`
with appropriate HTTP status (400/401/403/404/409/422/502).

## Auth  (backend agent owns — `routes/auth.ts`)
- `POST /api/auth/register` → body `{ name, email, password }` (email must end `@emory.edu`) → `{ token, user }`
- `POST /api/auth/login` → body `{ email, password }` → `{ token, user }`
- `user` = `{ id: string, name: string, email: string, role: "professor"|"student" }`
- JWT signed with `JWT_SECRET`; payload `{ sub: id, role, email }`. Middleware sets `req.user`.

## Courses  (backend agent owns — `routes/courses.ts`)
- `GET  /api/courses` → courses the caller is enrolled in / teaches → `Course[]`
- `POST /api/courses` (professor) → `{ code, name, semester }` → `Course`
- `Course` = `{ id, code, name, semester, professor_id }`
- Tables: `platform_users`, `platform_courses`, `platform_enrollments` (match LP naming).

## Caseband  (ALREADY SERVED via proxy → Python orchestrator; do not rebuild)
All under `/api/caseband`. Add `course_id` scoping in the router later; shapes below are stable.

- `POST /ingest` → `{ text, filename? }` → `{ title, source_type, needs_research, sections, facts[] }`
  - `facts[]` = `{ label, value, unit, raw }`
- `POST /cases/interview` → `{ state?, message? }` → chat-authoring turn: `{ collected, pending, ready, reply, brief? , checkpoints? }`. Call with `{}` to start; pass `state` back each turn. When `ready`, feed `brief` (title, document) into `POST /cases` (live). Duration → checkpoints (~1/15min, 2–6).
- `POST /cases` → `{ title, objectives:[{key,text}], model, document?, live? }` → `CaseSummary & { case_id }`
  - `live:true` uses LLM writers (real OpenAI); omit/false uses deterministic writers + the passed `model`.
  - `model` (formula) = `{ kind:"formula", kpi_key, pass_policy, target:{value,comparator,units}, decision_variables:[{key,bounds:[lo,hi]}], parameters:{...}, spec:{expr} }`
- `POST /cases/:id/redteam` → `CaseSummary & { converged, validated, findings[] }`
- `GET  /cases/:id?view=faculty|student` →
  - faculty: `{ meta, objectives, decision_points, outcome_model, rubric, exhibits, solvability, redteam_findings }`
  - student (redacted): same minus `outcome_model.spec`/`parameters`, `solvability`, `redteam_findings`, rubric weights/levels
- `POST /cases/:id/whatif` → `{ assignment:{var:num} }` → `{ kpi_key, current, levers:{ var:{ current, at_low, at_high, raises_kpi_toward } } }` (live what-if for the student player; no target/answer leaked)
- `POST /runs` → `{ case_id, student_id }` → `{ run_id, case_id, status:"active" }`
- `POST /runs/:id/submit` → `{ assignment:{var:num}, rubric_scores:{crit:0|1|2}, at? }` → `Grade`
  - `Grade` = `{ status:"ai_draft", kpi_key, kpi_value, numeric_pass, rubric_score, rubric_pass, overall_pass, rubric_breakdown[] }`
- `POST /cases/:id/faculty/edit` → `{ op:"set_outcome_target", field:"outcome_model", value:number, apply? }` → `{ diff, approvable, reason, applied }`
- `POST /cases/:id/revise` (play-preview revise loop, flow step 3) → `{ intent?, message?, apply? }` → `{ case_id, intent, diff, approvable, reason, applied, ...CaseSummary }`
  - Pass a structured `intent` (deterministic) OR free-text `message` (parsed by the LLM liaison — needs a live key). Intent ops: `set_outcome_target`, `add_objective` `{value:{key,text}}`, `edit_objective` `{key,value:{text}}`, `remove_objective` `{key}`, `edit_decision_prompt` `{key,value:{prompt}}`, `edit_rubric_prompt` `{key,value:{prompt}}`, `add_rubric_criterion`. Every edit re-runs the full red-team; loop until `approvable`, then publish.
- `POST /cases/:id/access-code` (flow step 4; case must be redteam-clean) → `{ case_id, code }`. Code is stable per case (idempotent).
- `POST /join` (student redeems code + registers, flow step 4→5) → `{ code, name, fields? }` → `{ case_id, run_id, student_id, student_name }`. Code is case/dash-insensitive. Starts a run.
- `POST /runs/:id/coach` (Socratic coach, flow step 5) → `{ message }` → `{ reply, refused }`. Guidance only — never the target, formula, or pass/fail.
- `POST /runs/:id/submit` now returns **feedback, not a grade** (flow step 6): qualitative `{ released:false, objectives:[{criterion_key,objective_key,level,next_step}], summary, kpi_feedback? }`. The numeric grade is computed + stored but withheld.
- `POST /runs/:id/finalize` (professor releases the number) → `{ reviewer_id }` → feedback with `released:true` and a `grade` block `{ overall_pass, rubric_score, numeric_pass, kpi_key, kpi_value }`.
- `GET /runs/:id/grade?view=faculty|student` → faculty: full grade dict; student: feedback (number only once finalized).

`CaseSummary` = `{ case_id?, status, objectives:int, decision_points:int, rubric:int, exhibits:int, all_objectives_tested:bool, redteam_clean:bool }`

## Frontend pages  (frontend agent owns — `artifacts/web`)
Stack: React 19 + Vite + Tailwind 4 + react-router-dom + a simple axios-like `api` client (Bearer from localStorage). Match LP design system: classes `card`, `btn btn-primary/btn-sm`, `badge badge-green/badge-navy`, `tab active`, `strip strip-info`, `spinner`, `fade-up`, `page-header`/`page-label`/`subtitle`, CSS vars `--ink3/--ink4`. Role-branch: `role==='professor' ? <Prof/> : <Student/>`.
- `Login` / `Register` (email @emory.edu).
- `AppShell` with left nav + course context (course.code/name/id in `page-label`).
- `Simulation` page (the Caseband tool):
  - **Professor**: tabs list / author / review. Author = ingest a document → `POST /cases` (live) → show authored objectives/model/decisions/rubric → `POST /redteam` showing the solvability proof (validated badge, findings) → faculty edit (target slider → preview approvable). "Publish" when redteam_clean.
  - **Student**: load `GET /cases/:id?view=student` (redacted), set decision-variable inputs + answer rubric prompts → `POST /runs` then `POST /runs/:id/submit` → show Grade (overall_pass, kpi, rubric breakdown).
