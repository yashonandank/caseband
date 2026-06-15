"""Persistence seam. CaseService talks to a Store, never to a DB directly.

  InMemoryStore  — default; deepcopy-isolated dicts. Keeps the API testable with
                   no external services.
  SupabaseStore  — production. The canonical CasePackage is persisted as an
                   append-only JSONB snapshot in caseband.case_versions (mirrors
                   the schema's source-of-truth design); the orchestrator writes
                   with the SERVICE ROLE (RLS bypassed). Import-safe: the supabase
                   client is only imported when this store is constructed.

Both round-trip a CasePackage; selection is env-driven in build_store()."""
from __future__ import annotations
import copy
import os
import sys
from dataclasses import asdict
from typing import Any, Protocol

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))
from caseband.models.case_package import CasePackage     # noqa: E402
from caseband.runtime.case_run import CaseRun            # noqa: E402


def pkg_to_dict(pkg: CasePackage) -> dict[str, Any]:
    return asdict(pkg)


def pkg_from_dict(d: dict[str, Any]) -> CasePackage:
    fields = ("meta", "objectives", "decision_points", "outcome_model",
              "rubric", "exhibits", "redteam_findings", "solvability")
    return CasePackage(**{k: copy.deepcopy(d[k]) for k in fields if k in d})


class Store(Protocol):
    def save_case(self, case_id: str, pkg: CasePackage, by: str = "reducer") -> None: ...
    def load_case(self, case_id: str) -> CasePackage | None: ...
    def save_run(self, run: CaseRun) -> None: ...
    def load_run(self, run_id: str) -> CaseRun | None: ...
    # access codes (join flow): key is the normalized code (see runtime.access_code)
    def save_code(self, norm_code: str, case_id: str) -> None: ...
    def lookup_code(self, norm_code: str) -> str | None: ...
    def revoke_code(self, norm_code: str) -> bool: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._cases: dict[str, CasePackage] = {}
        self._runs: dict[str, CaseRun] = {}
        self._codes: dict[str, str] = {}        # normalized code -> case_id

    def save_case(self, case_id: str, pkg: CasePackage, by: str = "reducer") -> None:
        self._cases[case_id] = copy.deepcopy(pkg)

    def load_case(self, case_id: str) -> CasePackage | None:
        p = self._cases.get(case_id)
        return copy.deepcopy(p) if p is not None else None

    def save_run(self, run: CaseRun) -> None:
        self._runs[run.run_id] = copy.deepcopy(run)

    def load_run(self, run_id: str) -> CaseRun | None:
        r = self._runs.get(run_id)
        return copy.deepcopy(r) if r is not None else None

    def save_code(self, norm_code: str, case_id: str) -> None:
        self._codes[norm_code] = case_id

    def lookup_code(self, norm_code: str) -> str | None:
        return self._codes.get(norm_code)

    def revoke_code(self, norm_code: str) -> bool:
        return self._codes.pop(norm_code, None) is not None


class SupabaseStore:
    """Canonical CasePackage <-> caseband.case_versions (append-only JSONB).
    NOTE: requires SUPABASE_URL + SUPABASE_SERVICE_KEY; verified once creds exist."""
    schema = "caseband"

    def __init__(self, url: str | None = None, service_key: str | None = None,
                 org_id: str | None = None) -> None:
        from supabase import create_client  # import-safe: only when used
        self._url = url or os.environ["SUPABASE_URL"]
        self._key = service_key or os.environ["SUPABASE_SERVICE_KEY"]
        self._org = org_id or os.environ.get("CASEBAND_ORG_ID")
        self.sb = create_client(self._url, self._key)
        self._runs_pkg: dict[str, CasePackage] = {}  # run->package cache (frozen at start)

    def _t(self, name: str):
        return self.sb.schema(self.schema).table(name)

    def save_case(self, case_id: str, pkg: CasePackage, by: str = "reducer") -> None:
        status = pkg.meta.get("status", "intake")
        title = pkg.meta.get("title")
        source_type = pkg.meta.get("source_type")
        # upsert the case row (service role) and bump the version counter
        existing = self._t("cases").select("current_version").eq("id", case_id).execute()
        if existing.data:
            version = (existing.data[0]["current_version"] or 0) + 1
            self._t("cases").update({"status": status, "title": title,
                                     "current_version": version}).eq("id", case_id).execute()
        else:
            version = 1
            row = {"id": case_id, "status": status, "title": title,
                   "current_version": version}
            if self._org:
                row["org_id"] = self._org
            if source_type in ("10K", "filing", "news", "prompt"):
                row["source_type"] = source_type
            self._t("cases").insert(row).execute()
        self._t("case_versions").insert({
            "case_id": case_id, "version": version,
            "case_package": pkg_to_dict(pkg), "created_by": by}).execute()

    def load_case(self, case_id: str) -> CasePackage | None:
        res = (self._t("case_versions").select("case_package")
               .eq("case_id", case_id).order("version", desc=True).limit(1).execute())
        if not res.data:
            return None
        return pkg_from_dict(res.data[0]["case_package"])

    def save_run(self, run: CaseRun) -> None:
        status_map = {"active": "in_progress", "submitted": "submitted", "graded": "graded"}
        self._runs_pkg[run.run_id] = run.package
        row = {"id": run.run_id, "case_id": run.case_id, "student_id": run.student_id,
               "case_version": 0, "status": status_map.get(run.status, "in_progress")}
        self._t("case_runs").upsert(row).execute()
        if run.grade is not None:
            sub = self._t("submissions").insert({
                "case_run_id": run.run_id, "case_id": run.case_id,
                "student_id": run.student_id, "answers": {}}).execute()
            submission_id = sub.data[0]["id"]
            g = run.grade
            self._t("grades").insert({
                "submission_id": submission_id, "case_run_id": run.run_id,
                "total": g.get("rubric_score"), "per_criterion": g.get("rubric_breakdown"),
                "graded_by": "grader", "status": g.get("status", "ai_draft")}).execute()

    def load_run(self, run_id: str) -> CaseRun | None:
        res = self._t("case_runs").select("*").eq("id", run_id).limit(1).execute()
        if not res.data:
            return None
        row = res.data[0]
        pkg = self._runs_pkg.get(run_id) or self.load_case(row["case_id"])
        rev = {"in_progress": "active", "submitted": "submitted", "graded": "graded"}
        return CaseRun(run_id=run_id, case_id=row["case_id"], student_id=row["student_id"],
                       package=pkg, status=rev.get(row["status"], "active"))

    def save_code(self, norm_code: str, case_id: str) -> None:
        # NOTE: requires a caseband.access_codes table (code PK, case_id, revoked);
        # unverified until creds exist, consistent with the rest of this store.
        self._t("access_codes").upsert(
            {"code": norm_code, "case_id": case_id, "revoked": False}).execute()

    def lookup_code(self, norm_code: str) -> str | None:
        res = (self._t("access_codes").select("case_id,revoked")
               .eq("code", norm_code).limit(1).execute())
        if not res.data or res.data[0].get("revoked"):
            return None
        return res.data[0]["case_id"]

    def revoke_code(self, norm_code: str) -> bool:
        self._t("access_codes").update({"revoked": True}).eq("code", norm_code).execute()
        return True


def build_store() -> Store:
    """Pick the store from env: Supabase when creds are present, else in-memory."""
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        return SupabaseStore()
    return InMemoryStore()
