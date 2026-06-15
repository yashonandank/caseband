"""FastAPI app: HTTP surface for the case lifecycle. Run:

    uvicorn services.api.app:app --reload   # from repo root

Endpoints mirror the pipeline: ingest -> author -> redteam -> get -> run/submit
-> faculty edit. Student reads are redacted; faculty reads are full."""
from __future__ import annotations
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .service import CaseService, ServiceError

app = FastAPI(title="Caseband API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])
svc = CaseService()

_WEB = os.path.join(os.path.dirname(__file__), "..", "..", "web", "index.html")


@app.get("/")
def home() -> Any:
    if os.path.isfile(_WEB):
        return FileResponse(_WEB)
    return JSONResponse({"service": "caseband", "ui": "not built"})


# ---- request models ---------------------------------------------------------
class IngestReq(BaseModel):
    text: str
    filename: str | None = None


class Objective(BaseModel):
    key: str
    text: str


class AuthorReq(BaseModel):
    title: str = "Untitled case"
    objectives: list[Objective] = Field(default_factory=list)
    model: dict[str, Any] = Field(default_factory=dict)
    document: str | None = None
    live: bool = False


class RunReq(BaseModel):
    case_id: str
    student_id: str


class SubmitReq(BaseModel):
    assignment: dict[str, float] = Field(default_factory=dict)
    rubric_scores: dict[str, int] = Field(default_factory=dict)
    at: str | None = None


class FacultyEditReq(BaseModel):
    op: str
    field: str
    value: Any
    apply: bool = False


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ServiceError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


# ---- routes -----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestReq) -> dict[str, Any]:
    return _guard(svc.ingest, req.text, req.filename)


class InterviewReq(BaseModel):
    state: dict[str, Any] | None = None
    message: str = ""


@app.post("/cases/interview")
def interview(req: InterviewReq) -> dict[str, Any]:
    return _guard(svc.interview, req.state, req.message)


@app.post("/cases")
def author(req: AuthorReq) -> dict[str, Any]:
    return _guard(svc.author, title=req.title,
                  objectives=[o.model_dump() for o in req.objectives],
                  model=req.model, document=req.document, live=req.live)


@app.post("/cases/{case_id}/redteam")
def redteam(case_id: str) -> dict[str, Any]:
    return _guard(svc.redteam, case_id)


@app.get("/cases/{case_id}")
def get_case(case_id: str, view: str = "faculty") -> dict[str, Any]:
    return _guard(svc.get_case, case_id, view)


@app.post("/runs")
def start_run(req: RunReq) -> dict[str, Any]:
    return _guard(svc.start_run, req.case_id, req.student_id)


@app.post("/runs/{run_id}/submit")
def submit(run_id: str, req: SubmitReq) -> dict[str, Any]:
    return _guard(svc.submit, run_id, req.assignment, req.rubric_scores, req.at)


class WhatIfReq(BaseModel):
    assignment: dict[str, float] = Field(default_factory=dict)


@app.post("/cases/{case_id}/whatif")
def whatif(case_id: str, req: WhatIfReq) -> dict[str, Any]:
    return _guard(svc.whatif, case_id, req.assignment)


@app.post("/cases/{case_id}/faculty/edit")
def faculty_edit(case_id: str, req: FacultyEditReq) -> dict[str, Any]:
    intent = {"op": req.op, "field": req.field, "value": req.value}
    return _guard(svc.faculty_edit, case_id, intent, req.apply)


class ReviseReq(BaseModel):
    intent: dict[str, Any] | None = None
    message: str | None = None
    apply: bool = True


@app.post("/cases/{case_id}/revise")
def revise(case_id: str, req: ReviseReq) -> dict[str, Any]:
    return _guard(svc.revise, case_id, req.intent, req.message, req.apply)


@app.post("/cases/{case_id}/access-code")
def access_code_route(case_id: str) -> dict[str, Any]:
    return _guard(svc.issue_access_code, case_id)


class JoinReq(BaseModel):
    code: str
    name: str
    fields: dict[str, Any] | None = None


@app.post("/join")
def join(req: JoinReq) -> dict[str, Any]:
    return _guard(svc.join, req.code, req.name, req.fields)


class CoachReq(BaseModel):
    message: str


@app.post("/runs/{run_id}/coach")
def coach(run_id: str, req: CoachReq) -> dict[str, Any]:
    return _guard(svc.coach_turn, run_id, req.message)


class FinalizeReq(BaseModel):
    reviewer_id: str


@app.post("/runs/{run_id}/finalize")
def finalize_grade(run_id: str, req: FinalizeReq) -> dict[str, Any]:
    return _guard(svc.finalize_grade, run_id, req.reviewer_id)


@app.get("/runs/{run_id}/grade")
def get_grade(run_id: str, view: str = "student") -> dict[str, Any]:
    return _guard(svc.get_grade, run_id, view)
