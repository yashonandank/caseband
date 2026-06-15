"""FastAPI layer over the caseband orchestrator. Wraps the tested in-memory
pipeline (ingest -> author -> red-team -> deploy -> run -> grade -> faculty) as
HTTP. The in-memory CaseService store is the swap seam for Supabase persistence."""
