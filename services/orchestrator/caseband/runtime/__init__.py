"""Runtime (Act Two): a deployed case being played by a student. Persists to
local messages/case_runs/grades (+ Supabase Realtime in prod) and NEVER routes
through Band — student data stays local (see caseband Band boundary)."""
