"""CaseService — orchestrator operations over a pluggable store. The default store
is in-memory (dicts); a Supabase-backed store swaps in behind the same methods for
production. All authoring here uses the deterministic writers' mocks so the API is
testable with no keys; pass live=True later to use the LLM writers."""
from __future__ import annotations
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))

from caseband.bus.local_bus import LocalBus              # noqa: E402
from caseband.conductor import Conductor                 # noqa: E402
from caseband.state_store import StateStore              # noqa: E402
from caseband.rooms import Room                          # noqa: E402
from caseband.models.case_package import CasePackage     # noqa: E402
from caseband.ingestion.extract import extract           # noqa: E402
from caseband.agents.intake import Parser, DocParser, DataCreator      # noqa: E402
from caseband.agents.writers_room import (               # noqa: E402
    ObjectiveSetter, OutcomeModeler, CheckpointMapper, RubricCreator,
)
from caseband.agents.red_team import SolvabilityValidator, StructuralCritic  # noqa: E402
from caseband.runtime.case_run import CaseRun, Proctor   # noqa: E402
from caseband.runtime.redact import student_view         # noqa: E402
from caseband.runtime import access_code                 # noqa: E402
from caseband.runtime.coach_session import CoachSession  # noqa: E402
from caseband.runtime.feedback import student_feedback, is_released  # noqa: E402
from caseband.agents.professor_liaison import ProfessorLiaison, LLMProfessorLiaison  # noqa: E402
from caseband.agents.sim_agent import SimAgent                          # noqa: E402
from caseband.agents.interview import InterviewAgent                     # noqa: E402
from caseband.agents.interview_agent import AgenticInterviewer           # noqa: E402
from caseband.agents.case_designer import CaseDesigner                   # noqa: E402
from caseband.models.rich_case import RichCase                           # noqa: E402
from caseband.runtime.staged_run import StagedRun, StagedPlayer, opening as rich_opening  # noqa: E402
from caseband.graph import ui_builder as graph_ui         # noqa: E402
from caseband.tools import grader                         # noqa: E402
from caseband.tools import backbone as backbone_tool      # noqa: E402

_JOINABLE = {Room.ASSESSMENT.value, Room.DEPLOYED.value}


class ServiceError(Exception):
    """Bad request against the case lifecycle (maps to HTTP 400/404/409)."""
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class CaseService:
    def __init__(self, store=None) -> None:
        from .store import build_store
        self.store = store or build_store()
        # RichCase pipeline (in-process for the local demo; survives within a run).
        self._rich: dict[str, dict] = {}          # case_id -> RichCase.to_dict()
        self._staged: dict[str, StagedRun] = {}   # run_id -> StagedRun

    def _conductor_for(self, pkg: CasePackage, room: str) -> Conductor:
        c = Conductor(LocalBus(), StateStore(), room=room)
        c.pkg = pkg                       # seed with the loaded canonical package
        return c

    def _load(self, case_id: str) -> CasePackage:
        pkg = self.store.load_case(case_id)
        if pkg is None:
            raise ServiceError(f"no case {case_id!r}", 404)
        return pkg

    def _run(self, run_id: str) -> CaseRun:
        run = self.store.load_run(run_id)
        if run is None:
            raise ServiceError(f"no run {run_id!r}", 404)
        return run

    # ======================================================================
    # Rich case pipeline: agentic interview -> detailed case -> staged play
    # ======================================================================
    def interview_rich(self, state: dict | None, message: str = "") -> dict:
        """One turn of the AGENTIC authoring conversation. Round-trip `state`.
        When `ready`, feed `brief` into design_rich()."""
        agent = AgenticInterviewer()
        return agent.start() if state is None else agent.step(state, message)

    def design_rich(self, brief: dict, live: bool | None = None) -> dict:
        """Generate a full RichCase from a brief and store it."""
        case = CaseDesigner(live=live).design(brief or {})
        case_id = str(uuid.uuid4())
        self._rich[case_id] = case.to_dict()
        return {"case_id": case_id, **self._rich_summary(case)}

    def author_graph(self, brief: dict, live: bool | None = None) -> dict:
        """Run the LangGraph authoring pipeline: propose backbone -> validate (loop on
        fail) -> write case -> leak-scan -> build interactive UI. Returns the case
        summary, the live phase events, and the deployable UI url."""
        from caseband.graph.authoring_graph import run_authoring
        case_id = str(uuid.uuid4())
        out = run_authoring(brief or {}, case_id, live=live)
        if not out.get("case"):
            raise ServiceError("authoring graph produced no case", 422)
        self._rich[case_id] = out["case"]
        case = RichCase.from_dict(out["case"])
        return {"case_id": case_id, "ui_url": f"/case-ui/{case_id}",
                "validation": out.get("validation"), "events": out.get("events", []),
                **self._rich_summary(case)}

    def get_case_ui(self, case_id: str) -> str:
        """Render the interactive HTML case page (deployable student view)."""
        return graph_ui.render(self._load_rich(case_id))

    def _load_rich(self, case_id: str) -> RichCase:
        d = self._rich.get(case_id)
        if d is None:
            raise ServiceError(f"no rich case {case_id!r}", 404)
        return RichCase.from_dict(d)

    def get_rich_case(self, case_id: str, view: str = "faculty") -> dict:
        case = self._load_rich(case_id)
        if view == "student":
            return rich_opening(case)            # opening view, answer hidden
        d = case.to_dict()
        if case.backbone:                        # faculty also sees the proof
            d["backbone_check"] = backbone_tool.validate(case.backbone.__dict__).__dict__
        return d

    def start_rich_run(self, case_id: str, student_id: str) -> dict:
        case = self._load_rich(case_id)
        run_id = str(uuid.uuid4())
        self._staged[run_id] = StagedRun(run_id=run_id, case_id=case_id,
                                         student_id=student_id, case=case)
        return {"run_id": run_id, "case_id": case_id, "status": "active",
                "opening": rich_opening(case)}

    def advance_rich_run(self, run_id: str, text: str) -> dict:
        run = self._staged.get(run_id)
        if run is None:
            raise ServiceError(f"no rich run {run_id!r}", 404)
        return StagedPlayer().advance(run, text or "")

    @staticmethod
    def _rich_summary(case: RichCase) -> dict:
        return {"title": case.title, "company": case.company.name,
                "stages": len(case.stages), "exhibits": len(case.exhibits),
                "objectives": len(case.learning_objectives),
                "solvable": bool(case.backbone and
                                 backbone_tool.validate(case.backbone.__dict__).validated),
                "source": case.meta.get("source")}

    # ---- ingestion ----------------------------------------------------------
    def ingest(self, text: str, filename: str | None = None) -> dict[str, Any]:
        doc = extract(text, filename)
        return {"title": doc.title, "source_type": doc.source_type,
                "needs_research": doc.needs_research,
                "sections": len(doc.sections), "facts": doc.facts}

    # ---- conversational authoring (user flow step 2) ------------------------
    def interview(self, state: dict | None, message: str = "") -> dict:
        """One turn of the chat authoring interview. Stateless: the caller passes
        `state` back each turn. When `ready`, the returned `brief` feeds author()."""
        agent = InterviewAgent()
        if not state:
            return agent.start()
        return agent.step(state, message)

    # ---- authoring (Loop A) -------------------------------------------------
    def author(self, *, title: str, objectives: list[dict], model: dict,
               document: str | None = None, live: bool = False) -> dict[str, Any]:
        case_id = str(uuid.uuid4())
        conductor = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
        agents: list = []
        if document:
            doc = extract(document)
            agents += [DocParser(document), DataCreator(doc)]
        else:
            agents.append(Parser(title=title, source_type="manual"))
        if live:
            # Live writers' room: the LLM authors objectives/model/decisions/rubric.
            from caseband.agents.llm_writers import (
                LLMObjectiveSetter, LLMOutcomeModeler, LLMCheckpointMapper, LLMRubricCreator,
            )
            agents += [LLMObjectiveSetter(), LLMOutcomeModeler(),
                       LLMCheckpointMapper(), LLMRubricCreator()]
        else:
            agents += [ObjectiveSetter(objectives), OutcomeModeler(model),
                       CheckpointMapper(), RubricCreator()]
        report = conductor.run_loop_a(agents)
        if not report.converged:
            raise ServiceError("authoring did not converge", 422)
        self.store.save_case(case_id, conductor.pkg, by="conductor")
        return {"case_id": case_id, **self._summary(conductor.pkg)}

    # ---- red-team (Loop B) --------------------------------------------------
    def redteam(self, case_id: str) -> dict[str, Any]:
        conductor = self._conductor_for(self._load(case_id), Room.REDTEAM.value)
        report = conductor.run_loop_b([SolvabilityValidator(), StructuralCritic()])
        pkg = conductor.pkg
        self.store.save_case(case_id, pkg, by="conductor")
        return {"case_id": case_id, "converged": report.converged,
                "validated": pkg.solvability.get("validated"),
                "findings": pkg.redteam_findings, **self._summary(pkg)}

    # ---- read ---------------------------------------------------------------
    def get_case(self, case_id: str, view: str = "faculty") -> dict[str, Any]:
        pkg = self._load(case_id)
        if view == "student":
            return student_view(pkg)
        return {"meta": pkg.meta, "objectives": pkg.objectives,
                "decision_points": pkg.decision_points, "outcome_model": pkg.outcome_model,
                "rubric": pkg.rubric, "exhibits": pkg.exhibits,
                "solvability": pkg.solvability, "redteam_findings": pkg.redteam_findings}

    # ---- runtime ------------------------------------------------------------
    def start_run(self, case_id: str, student_id: str) -> dict[str, Any]:
        pkg = self._load(case_id)
        if pkg.meta.get("status") not in (Room.ASSESSMENT.value, Room.DEPLOYED.value):
            raise ServiceError("case is not deployed/assessable yet", 409)
        run_id = str(uuid.uuid4())
        self.store.save_run(
            CaseRun(run_id=run_id, case_id=case_id, student_id=student_id, package=pkg))
        return {"run_id": run_id, "case_id": case_id, "status": "active"}

    def submit(self, run_id: str, assignment: dict, rubric_scores: dict,
               at: str | None = None) -> dict[str, Any]:
        """Student submits. The numeric grade is computed + stored on the run, but
        the student only gets qualitative FEEDBACK back — the number stays gated
        behind professor finalize (flow step 6)."""
        run = self._run(run_id)
        grade = Proctor().submit(run, assignment, rubric_scores, at=at)
        self.store.save_run(run)                 # persist graded state (ai_draft)
        return student_feedback(grade)

    # ---- Socratic coach (flow step 5) ---------------------------------------
    def coach_turn(self, run_id: str, message: str) -> dict[str, Any]:
        """One coaching turn: Socratic guidance from the redacted view, never the
        answer. Records the exchange on the run transcript."""
        run = self._run(run_id)
        out = CoachSession().respond(student_view(run.package), run.transcript, message)
        self.store.save_run(run)                 # persist the coaching exchange
        return out

    # ---- grade lifecycle: professor releases the number (flow step 6) --------
    def finalize_grade(self, run_id: str, reviewer_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        if run.grade is None:
            raise ServiceError("run has no grade to finalize", 409)
        try:
            g = grader.review(run.grade, reviewer_id)
            g = grader.finalize(g, reviewer_id)
        except grader.GradeError as e:
            raise ServiceError(str(e), 409)
        run.grade = g
        self.store.save_run(run)
        return student_feedback(g)               # now includes the released number

    def get_grade(self, run_id: str, view: str = "student") -> dict[str, Any]:
        run = self._run(run_id)
        if run.grade is None:
            raise ServiceError("run has no grade yet", 404)
        if view == "faculty":
            return run.grade                     # full grade for the professor
        return student_feedback(run.grade)       # released number only when finalized

    def whatif(self, case_id: str, assignment: dict) -> dict[str, Any]:
        """Live KPI + per-lever what-if for the student player (no answer leaked)."""
        pkg = self._load(case_id)
        if not pkg.outcome_model or pkg.outcome_model.get("kind") != "formula":
            raise ServiceError("case has no numeric outcome model", 409)
        return SimAgent().what_if(pkg.outcome_model, assignment)

    # ---- faculty HITL -------------------------------------------------------
    def faculty_edit(self, case_id: str, intent: dict, apply: bool = False) -> dict[str, Any]:
        pkg = self._load(case_id)
        liaison = ProfessorLiaison()
        diff = liaison.preview_diff(pkg, intent)
        res = liaison.apply_and_revalidate(pkg, intent)
        if apply and res.approvable:
            self.store.save_case(case_id, res.package, by="professor_liaison")
        return {"case_id": case_id, "diff": diff, "approvable": res.approvable,
                "reason": res.reason, "applied": bool(apply and res.approvable)}

    # ---- play-preview + revise loop (flow step 3) ---------------------------
    def revise(self, case_id: str, intent: dict | None = None,
               message: str | None = None, apply: bool = True) -> dict[str, Any]:
        """One turn of the professor revise loop. Accepts a structured `intent`
        (deterministic, no key) OR free-text `message` (parsed by the LLM liaison).
        Applies the edit, re-runs the full red-team validation, and reports whether
        the result is approvable. Loop until approvable, then publish."""
        pkg = self._load(case_id)
        liaison = ProfessorLiaison()
        if intent is None:
            if not message:
                raise ServiceError("revise needs an intent or a message", 400)
            try:
                intent = LLMProfessorLiaison().parse_intent(message)
            except Exception as e:                       # no key / parse failure
                raise ServiceError(f"could not parse revision: {e}", 422)
        diff = liaison.preview_diff(pkg, intent)
        res = liaison.apply_and_revalidate(pkg, intent)
        applied = bool(apply and res.approvable)
        if applied:
            self.store.save_case(case_id, res.package, by="professor_liaison")
        return {"case_id": case_id, "intent": intent, "diff": diff,
                "approvable": res.approvable, "reason": res.reason,
                "applied": applied, **self._summary(res.package)}

    # ---- access code (flow step 4) ------------------------------------------
    def issue_access_code(self, case_id: str) -> dict[str, Any]:
        """Mint (or re-mint) the join code for an approved case. Codes are stable
        per case_id, so calling twice returns the same code."""
        pkg = self._load(case_id)
        if not pkg.redteam_clean():
            raise ServiceError("prove the case solvable before publishing a code", 409)
        code = access_code.generate_code(case_id)
        self.store.save_code(access_code.normalize_code(code), case_id)
        return {"case_id": case_id, "code": code}

    # ---- student join by code (flow step 4 -> 5) ----------------------------
    def join(self, code: str, name: str, fields: dict | None = None) -> dict[str, Any]:
        """Student redeems an access code + registers, and a run is started."""
        case_id = self.store.lookup_code(access_code.normalize_code(code or ""))
        if case_id is None:
            raise ServiceError("invalid or expired access code", 404)
        pkg = self._load(case_id)
        if pkg.meta.get("status") not in _JOINABLE:
            raise ServiceError("this case is not open for students yet", 409)
        try:
            redeemed = access_code.RedeemResult(ok=True, case_id=case_id)
            student = access_code.register_student(redeemed, name=name, fields=fields)
        except access_code.JoinError as e:
            raise ServiceError(str(e), 400)
        run_id = str(uuid.uuid4())
        self.store.save_run(CaseRun(run_id=run_id, case_id=case_id,
                                    student_id=student.student_id, package=pkg))
        return {"case_id": case_id, "run_id": run_id,
                "student_id": student.student_id, "student_name": student.name}

    # ---- helpers ------------------------------------------------------------
    @staticmethod
    def _summary(pkg: CasePackage) -> dict[str, Any]:
        return {"status": pkg.meta.get("status"),
                "objectives": len(pkg.objectives),
                "decision_points": len(pkg.decision_points),
                "rubric": len(pkg.rubric), "exhibits": len(pkg.exhibits),
                "all_objectives_tested": pkg.all_objectives_tested(),
                "redteam_clean": pkg.redteam_clean()}
