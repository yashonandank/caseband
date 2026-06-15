-- Caseband — initial schema (Supabase / Postgres)
-- Companion to docs/ARCHITECTURE.md §11 and AGENT_SPECS.md §1.
--
-- Design:
--   * case_versions.case_package (JSONB) is the CANONICAL CasePackage (source of truth).
--   * objectives/exhibits/decision_points/rubric_criteria/redteam_findings are PROJECTIONS
--     materialized by the orchestrator's reducer in the same transaction as the JSONB write.
--   * The orchestrator connects with the SERVICE ROLE (bypasses RLS) and is the only writer of
--     case_versions + projections. RLS below protects the client-facing (anon/authenticated)
--     surface for faculty/student multi-tenancy.
--
-- Apply with:  supabase db push   (or psql -f)

create schema if not exists caseband;

create extension if not exists "pgcrypto";   -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$ begin
  create type caseband.member_role   as enum ('faculty', 'student', 'admin');
  create type caseband.source_type   as enum ('10K', 'filing', 'news', 'prompt');
  create type caseband.case_status    as enum ('intake','researching','drafting','redteam',
                                               'assessing','building','gating','deployed');
  create type caseband.msg_via        as enum ('band', 'local');
  create type caseband.finding_sev    as enum ('blocker', 'major', 'minor');
  create type caseband.finding_type   as enum ('unsolvable','ambiguous','missing_data','exploit',
                                               'bias','too_easy','too_hard');
  create type caseband.finding_status as enum ('open','assigned','fixed','wontfix');
  create type caseband.gate_kind      as enum ('objectives','final');
  create type caseband.gate_decision  as enum ('approve','block');
  create type caseband.db_dialect     as enum ('sqlite','postgres');
  create type caseband.db_access_mode as enum ('read_only','sandboxed_write');
  create type caseband.sql_mode       as enum ('student_writes','nl_to_sql','hybrid');
  create type caseband.run_status     as enum ('in_progress','submitted','graded');
  create type caseband.sandbox_status as enum ('active','reset','closed');
  -- AI grading is advisory-with-faculty-review: ai_draft -> reviewed -> finalized.
  create type caseband.grade_status   as enum ('ai_draft','reviewed','finalized');
  -- Outcome-model engine taxonomy (closed set; rubric_only is the universal fallback).
  create type caseband.outcome_kind   as enum ('formula','allocation','state_machine',
                                               'framework_threshold','rubric_only');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Tenancy & auth
-- ---------------------------------------------------------------------------
create table if not exists caseband.organizations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

-- Mirrors Supabase auth.users (id = auth.uid()).
create table if not exists caseband.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  full_name   text,
  email       text,
  created_at  timestamptz not null default now()
);

create table if not exists caseband.memberships (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references caseband.profiles(id) on delete cascade,
  org_id      uuid not null references caseband.organizations(id) on delete cascade,
  role        caseband.member_role not null,
  created_at  timestamptz not null default now(),
  unique (user_id, org_id, role)
);
create index if not exists idx_memberships_user on caseband.memberships(user_id);
create index if not exists idx_memberships_org  on caseband.memberships(org_id);

-- RLS helper: is the current user a member of org (optionally with a specific role)?
create or replace function caseband.is_member(p_org uuid, p_role caseband.member_role default null)
returns boolean
language sql stable security definer set search_path = caseband, public as $$
  select exists (
    select 1 from caseband.memberships m
    where m.user_id = auth.uid()
      and m.org_id = p_org
      and (p_role is null or m.role = p_role)
  );
$$;

-- ---------------------------------------------------------------------------
-- Case + audit
-- ---------------------------------------------------------------------------
create table if not exists caseband.cases (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references caseband.organizations(id) on delete cascade,
  owner_id         uuid references caseband.profiles(id) on delete set null,   -- faculty
  title            text,
  source_type      caseband.source_type,
  status           caseband.case_status not null default 'intake',
  current_version  integer not null default 0,
  is_real_company  boolean,
  company          text,
  domain           text[] not null default '{}',
  target_cohort    text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index if not exists idx_cases_org    on caseband.cases(org_id);
create index if not exists idx_cases_status on caseband.cases(status);

-- Append-only snapshots of the full CasePackage. Canonical state + replay/audit.
create table if not exists caseband.case_versions (
  id            uuid primary key default gen_random_uuid(),
  case_id       uuid not null references caseband.cases(id) on delete cascade,
  version       integer not null,
  case_package  jsonb not null,
  created_by    text,                       -- agent_id or 'reducer'
  created_at    timestamptz not null default now(),
  unique (case_id, version)
);
create index if not exists idx_case_versions_case on caseband.case_versions(case_id, version desc);

create table if not exists caseband.source_documents (
  id            uuid primary key default gen_random_uuid(),
  case_id       uuid not null references caseband.cases(id) on delete cascade,
  storage_path  text not null,              -- Supabase Storage object path
  filename      text,
  content_type  text,
  uploaded_by   uuid references caseband.profiles(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists idx_source_docs_case on caseband.source_documents(case_id);

-- The agent message log = the audit trail (AGENT_SPECS §2). One row per BandMessage envelope.
-- via='band' for authoring under BandBus; via='local' for LocalBus + ALL runtime messages.
create table if not exists caseband.messages (
  id               uuid primary key default gen_random_uuid(),
  case_id          uuid not null references caseband.cases(id) on delete cascade,
  case_run_id      uuid,                    -- non-null only for runtime (Act Two); FK added after case_runs
  room             text not null,
  via              caseband.msg_via not null default 'local',
  band_msg_id      text,                    -- external id when via='band'
  ts               timestamptz not null default now(),
  from_agent       text not null,
  to_target        text,                    -- 'room' | '@AgentName' | 'human'
  type             text not null,           -- VERB: PROPOSE/CRITIQUE/FINDING/...
  refs             text[] not null default '{}',
  target           jsonb,                   -- {field_path, item_id}
  payload          jsonb,
  state_patch      jsonb,                   -- {op, path, value} | null
  applied          boolean not null default false,
  rejected_reason  text
);
create index if not exists idx_messages_case_ts on caseband.messages(case_id, ts);
create index if not exists idx_messages_run      on caseband.messages(case_run_id);
create index if not exists idx_messages_room     on caseband.messages(case_id, room, ts);

create table if not exists caseband.signoffs (
  id           uuid primary key default gen_random_uuid(),
  case_id      uuid not null references caseband.cases(id) on delete cascade,
  gate         caseband.gate_kind not null,
  approver_id  uuid references caseband.profiles(id) on delete set null,
  decision     caseband.gate_decision not null,
  notes        text,
  created_at   timestamptz not null default now()
);
create index if not exists idx_signoffs_case on caseband.signoffs(case_id);

-- ---------------------------------------------------------------------------
-- Projections (materialized by the reducer; never written directly by agents)
-- ---------------------------------------------------------------------------
create table if not exists caseband.objectives (
  id             uuid primary key default gen_random_uuid(),
  case_id        uuid not null references caseband.cases(id) on delete cascade,
  objective_key  text not null,             -- 'o1', 'o2' (id within CasePackage)
  concept        text,
  framework      text,                      -- NPV | Porter5 | SWOT | ...
  bloom_level    text,                      -- apply | analyze | evaluate
  tested_by      text,                      -- decision_point_key | null
  unique (case_id, objective_key)
);
create index if not exists idx_objectives_case on caseband.objectives(case_id);

create table if not exists caseband.exhibits (
  id                uuid primary key default gen_random_uuid(),
  case_id           uuid not null references caseband.cases(id) on delete cascade,
  exhibit_key       text not null,          -- 'ex1'
  type              text,                   -- table | chart | doc
  title             text,
  data              jsonb,
  derived_from      text,                   -- source_ref | 'synthetic'
  consistency_hash  text,
  unique (case_id, exhibit_key)
);
create index if not exists idx_exhibits_case on caseband.exhibits(case_id);

create table if not exists caseband.decision_points (
  id                 uuid primary key default gen_random_uuid(),
  case_id            uuid not null references caseband.cases(id) on delete cascade,
  dp_key             text not null,         -- 'dp1'
  prompt             text,
  options            jsonb,                 -- [{id,label,downstream_effect}]
  maps_to_objective  text,                  -- objective_key
  requires_exhibits  text[] not null default '{}',
  unique (case_id, dp_key)
);
create index if not exists idx_decision_points_case on caseband.decision_points(case_id);

create table if not exists caseband.rubric_criteria (
  id                 uuid primary key default gen_random_uuid(),
  case_id            uuid not null references caseband.cases(id) on delete cascade,
  criterion_key      text not null,
  objective_key      text,
  dp_key             text,
  levels             jsonb,                 -- [{score, descriptor}]
  weight             numeric,
  unique (case_id, criterion_key)
);
create index if not exists idx_rubric_case on caseband.rubric_criteria(case_id);

-- Projection of CasePackage.outcome_model (discriminated by `kind`). One per case.
-- Numeric kinds (formula/allocation/state_machine) target a KPI vs `target`;
-- framework_threshold targets per-category scores vs `thresholds`; rubric_only carries neither.
create table if not exists caseband.case_outcome_models (
  id                 uuid primary key default gen_random_uuid(),
  case_id            uuid not null references caseband.cases(id) on delete cascade,
  kind               caseband.outcome_kind not null default 'rubric_only',
  kpi_key            text,                  -- numeric kinds: name of the computed KPI (e.g. 'roi')
  target             jsonb,                 -- numeric kinds: {value, comparator, units}
  thresholds         jsonb,                 -- framework_threshold: [{category, min_score}]
  decision_variables jsonb,                 -- [{key, dp_key, type, bounds|options}] bound to student input
  spec               jsonb,                 -- engine-specific authored body (formula AST, curves, transitions)
  pass_policy        text not null default 'all', -- 'all' = numeric AND rubric must pass (faculty-overridable)
  calibrated         boolean not null default false,  -- solvability_validator proved reachable + sensitive
  sensitivity        jsonb,                 -- [{variable_key, kpi_delta}] proof each var moves the KPI
  unique (case_id)
);
create index if not exists idx_outcome_models_case on caseband.case_outcome_models(case_id);

create table if not exists caseband.redteam_findings (
  id               uuid primary key default gen_random_uuid(),
  case_id          uuid not null references caseband.cases(id) on delete cascade,
  finding_key      text not null,           -- 'f1'
  raised_by        text,
  severity         caseband.finding_sev,
  type             caseband.finding_type,
  target_artifact  text,                    -- field_path
  description      text,
  status           caseband.finding_status not null default 'open',
  resolved_by      text,
  resolution_ref   text,
  created_at       timestamptz not null default now(),
  unique (case_id, finding_key)
);
create index if not exists idx_findings_case   on caseband.redteam_findings(case_id);
create index if not exists idx_findings_status on caseband.redteam_findings(case_id, status, severity);

-- ---------------------------------------------------------------------------
-- Authoring infra — capability cards for discovery/recruitment (AGENT_SPECS §4)
-- ---------------------------------------------------------------------------
create table if not exists caseband.agent_registry (
  id               uuid primary key default gen_random_uuid(),
  agent_key        text not null unique,    -- 'data_creator'
  capabilities     text[] not null default '{}',
  frameworks       text[] not null default '{}',
  cost_tier        text,                    -- high | low
  model            text,
  bus              caseband.msg_via not null default 'local',  -- runs as band agent or in-process
  band_agent_uuid  text,
  active           boolean not null default true,
  created_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Runtime + grading (Act Two — never via Band)
-- ---------------------------------------------------------------------------
-- Canonical case DB definition produced by db_provisioner (CasePackage.database).
create table if not exists caseband.case_databases (
  id            uuid primary key default gen_random_uuid(),
  case_id       uuid not null references caseband.cases(id) on delete cascade,
  dialect       caseband.db_dialect not null default 'sqlite',
  schema_ddl    text,
  seed_path     text,                       -- Storage path to canonical seed/.sqlite
  access_mode   caseband.db_access_mode not null default 'read_only',
  sql_mode      caseband.sql_mode not null default 'student_writes',
  tables        jsonb,                      -- [{name, columns:[{name,type}], row_count}]
  derived_from  text[] not null default '{}',  -- exhibit_keys
  created_at    timestamptz not null default now(),
  unique (case_id)
);

-- A student's play session of a deployed case.
create table if not exists caseband.case_runs (
  id            uuid primary key default gen_random_uuid(),
  case_id       uuid not null references caseband.cases(id) on delete cascade,
  case_version  integer not null,           -- pin the version the student played
  student_id    uuid not null references caseband.profiles(id) on delete cascade,
  status        caseband.run_status not null default 'in_progress',
  started_at    timestamptz not null default now(),
  submitted_at  timestamptz
);
create index if not exists idx_runs_case    on caseband.case_runs(case_id);
create index if not exists idx_runs_student on caseband.case_runs(student_id);

-- now that case_runs exists, point messages.case_run_id at it
do $$ begin
  alter table caseband.messages
    add constraint fk_messages_run foreign key (case_run_id)
    references caseband.case_runs(id) on delete cascade;
exception when duplicate_object then null; end $$;

-- Per-student sandbox DB copy.
create table if not exists caseband.sandboxes (
  id             uuid primary key default gen_random_uuid(),
  case_id        uuid not null references caseband.cases(id) on delete cascade,
  case_run_id    uuid not null references caseband.case_runs(id) on delete cascade,
  student_id     uuid not null references caseband.profiles(id) on delete cascade,
  dialect        caseband.db_dialect not null default 'sqlite',
  storage_path   text,                      -- Storage path to the student's .sqlite copy
  connection_ref text,                      -- or schema name for isolated-postgres mode
  access_mode    caseband.db_access_mode not null default 'read_only',
  status         caseband.sandbox_status not null default 'active',
  reset_count    integer not null default 0,
  created_at     timestamptz not null default now()
);
create index if not exists idx_sandboxes_run on caseband.sandboxes(case_run_id);

-- sql_agent query history = grading evidence.
create table if not exists caseband.query_logs (
  id            uuid primary key default gen_random_uuid(),
  sandbox_id    uuid not null references caseband.sandboxes(id) on delete cascade,
  case_run_id   uuid not null references caseband.case_runs(id) on delete cascade,
  student_id    uuid not null references caseband.profiles(id) on delete cascade,
  sql           text not null,
  row_count     integer,
  truncated     boolean not null default false,
  success       boolean not null default true,
  error         text,
  executed_at   timestamptz not null default now()
);
create index if not exists idx_query_logs_run on caseband.query_logs(case_run_id, executed_at);

create table if not exists caseband.submissions (
  id            uuid primary key default gen_random_uuid(),
  case_run_id   uuid not null references caseband.case_runs(id) on delete cascade,
  case_id       uuid not null references caseband.cases(id) on delete cascade,
  student_id    uuid not null references caseband.profiles(id) on delete cascade,
  answers       jsonb not null,             -- {dp_key: {option_id?, rationale}}
  submitted_at  timestamptz not null default now()
);
create index if not exists idx_submissions_run on caseband.submissions(case_run_id);

create table if not exists caseband.grades (
  id             uuid primary key default gen_random_uuid(),
  submission_id  uuid not null references caseband.submissions(id) on delete cascade,
  case_run_id    uuid not null references caseband.case_runs(id) on delete cascade,
  total          numeric,
  per_criterion  jsonb,                     -- [{criterion_key, score, justification, evidence_span}]
  graded_by      text,                      -- 'grader'
  -- Grading lifecycle: AI releases feedback immediately at ai_draft; faculty review/edit -> finalize.
  status         caseband.grade_status not null default 'ai_draft',
  edited_by      uuid references caseband.profiles(id),  -- faculty who reviewed/overrode
  edited_at      timestamptz,
  override_note  text,                      -- faculty rationale when overriding the AI score
  created_at     timestamptz not null default now()
);
create index if not exists idx_grades_submission on caseband.grades(submission_id);

create table if not exists caseband.feedback (
  id             uuid primary key default gen_random_uuid(),
  submission_id  uuid not null references caseband.submissions(id) on delete cascade,
  summary        text,
  strengths      jsonb,
  gaps           jsonb,                      -- [{criterion_key, suggestion}]
  created_at     timestamptz not null default now()
);
create index if not exists idx_feedback_submission on caseband.feedback(submission_id);

-- ---------------------------------------------------------------------------
-- updated_at trigger for cases
-- ---------------------------------------------------------------------------
create or replace function caseband.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists trg_cases_touch on caseband.cases;
create trigger trg_cases_touch before update on caseband.cases
  for each row execute function caseband.touch_updated_at();

-- ===========================================================================
-- Row Level Security
-- ===========================================================================
-- Strategy: orchestrator uses the service role (RLS bypassed). Policies below
-- govern the client (authenticated) surface: faculty manage their org's cases;
-- students see deployed cases and own only their runtime rows.

alter table caseband.organizations    enable row level security;
alter table caseband.profiles         enable row level security;
alter table caseband.memberships      enable row level security;
alter table caseband.cases            enable row level security;
alter table caseband.case_versions    enable row level security;
alter table caseband.source_documents enable row level security;
alter table caseband.messages         enable row level security;
alter table caseband.signoffs         enable row level security;
alter table caseband.objectives       enable row level security;
alter table caseband.exhibits         enable row level security;
alter table caseband.decision_points  enable row level security;
alter table caseband.rubric_criteria  enable row level security;
alter table caseband.redteam_findings enable row level security;
alter table caseband.case_databases   enable row level security;
alter table caseband.case_runs        enable row level security;
alter table caseband.sandboxes        enable row level security;
alter table caseband.query_logs       enable row level security;
alter table caseband.submissions      enable row level security;
alter table caseband.grades           enable row level security;
alter table caseband.feedback         enable row level security;

-- profiles: a user sees/edits their own profile row.
create policy profiles_self on caseband.profiles
  for all using (id = auth.uid()) with check (id = auth.uid());

-- memberships: a user sees their own memberships.
create policy memberships_self on caseband.memberships
  for select using (user_id = auth.uid());

-- organizations: visible to its members.
create policy orgs_member_read on caseband.organizations
  for select using (caseband.is_member(id));

-- cases: faculty/admin read+write own org; students read only deployed cases in their org.
create policy cases_faculty_all on caseband.cases
  for all using (caseband.is_member(org_id, 'faculty') or caseband.is_member(org_id, 'admin'))
  with check (caseband.is_member(org_id, 'faculty') or caseband.is_member(org_id, 'admin'));
create policy cases_student_read on caseband.cases
  for select using (status = 'deployed' and caseband.is_member(org_id, 'student'));

-- Faculty-only read of authoring artifacts (audit trail, versions, projections, findings).
-- Helper expressed inline via the parent case's org.
create policy case_versions_faculty on caseband.case_versions
  for select using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));
create policy source_docs_faculty on caseband.source_documents
  for all using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))))
  with check (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));
create policy messages_faculty on caseband.messages
  for select using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));
create policy signoffs_faculty on caseband.signoffs
  for all using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))))
  with check (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));

-- Projections: faculty read full; students read only for deployed cases (case player needs them).
do $$
declare t text;
begin
  foreach t in array array['objectives','exhibits','decision_points','rubric_criteria','redteam_findings','case_databases']
  loop
    execute format($f$
      create policy %1$s_faculty on caseband.%1$s for select using (exists (
        select 1 from caseband.cases c where c.id = case_id
          and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));
    $f$, t);
  end loop;
  -- students may read player-facing projections for deployed cases (NOT rubric/findings)
  foreach t in array array['objectives','exhibits','decision_points','case_databases']
  loop
    execute format($f$
      create policy %1$s_student on caseband.%1$s for select using (exists (
        select 1 from caseband.cases c where c.id = case_id
          and c.status = 'deployed' and caseband.is_member(c.org_id,'student')));
    $f$, t);
  end loop;
end $$;

-- Runtime rows: a student owns their own; faculty of the case's org may read.
create policy runs_student_own on caseband.case_runs
  for all using (student_id = auth.uid()) with check (student_id = auth.uid());
create policy runs_faculty_read on caseband.case_runs
  for select using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));

create policy sandboxes_student_own on caseband.sandboxes
  for all using (student_id = auth.uid()) with check (student_id = auth.uid());
create policy query_logs_student_own on caseband.query_logs
  for all using (student_id = auth.uid()) with check (student_id = auth.uid());
create policy query_logs_faculty_read on caseband.query_logs
  for select using (exists (select 1 from caseband.case_runs r join caseband.cases c on c.id = r.case_id
    where r.id = case_run_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));

create policy submissions_student_own on caseband.submissions
  for all using (student_id = auth.uid()) with check (student_id = auth.uid());
create policy submissions_faculty_read on caseband.submissions
  for select using (exists (select 1 from caseband.cases c
    where c.id = case_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));

-- Grades/feedback: student reads their own (via submission); faculty read all in org.
create policy grades_student_read on caseband.grades
  for select using (exists (select 1 from caseband.submissions s
    where s.id = submission_id and s.student_id = auth.uid()));
create policy grades_faculty_read on caseband.grades
  for select using (exists (select 1 from caseband.submissions s join caseband.cases c on c.id = s.case_id
    where s.id = submission_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));
create policy feedback_student_read on caseband.feedback
  for select using (exists (select 1 from caseband.submissions s
    where s.id = submission_id and s.student_id = auth.uid()));
create policy feedback_faculty_read on caseband.feedback
  for select using (exists (select 1 from caseband.submissions s join caseband.cases c on c.id = s.case_id
    where s.id = submission_id and (caseband.is_member(c.org_id,'faculty') or caseband.is_member(c.org_id,'admin'))));

-- agent_registry: readable by any authenticated member; managed by service role only.
create policy agent_registry_read on caseband.agent_registry for select using (auth.uid() is not null);
