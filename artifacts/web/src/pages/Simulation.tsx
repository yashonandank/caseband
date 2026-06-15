import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  XCircle,
  Sliders,
  Send,
  Sparkles,
  ClipboardList,
  MessageSquare,
  ShieldCheck,
  ShieldAlert,
  Copy,
  Eye,
  Wand2,
  GraduationCap,
  LifeBuoy,
  ArrowLeft,
} from "lucide-react";
import { api, PENDING, isPending } from "../api";
import { useAuth } from "../context/AuthContext";
import { useCourse } from "../context/CourseContext";
import type {
  CaseSummary,
  RedteamResult,
  StudentCaseView,
  DecisionVariable,
  RubricCriterion,
  RunResponse,
  Grade,
  InterviewTurn,
  AccessCodeResponse,
  JoinResponse,
  CoachResponse,
  ReviseResponse,
  Feedback,
} from "../types";

export default function Simulation() {
  const { user } = useAuth();
  return user?.role === "professor" ? (
    <ProfessorFlow />
  ) : (
    <StudentFlow />
  );
}

/* ──────────────────────────── shared helpers ──────────────────────────── */

type ChatMsg = { role: "assistant" | "user"; text: string };

function ErrorStrip({ msg }: { msg: string }) {
  return (
    <div className="strip strip-error mb-4">
      <AlertCircle size={16} className="mt-px shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

function PendingStrip({ msg }: { msg: string }) {
  return (
    <div className="strip strip-info mb-4">
      <Sparkles size={16} className="mt-px shrink-0" />
      <span>{msg}</span>
    </div>
  );
}

function Stat({ num, lbl }: { num: number | string; lbl: string }) {
  return (
    <div className="stat">
      <div className="num">{num}</div>
      <div className="lbl">{lbl}</div>
    </div>
  );
}

function dpVariables(dp: {
  decision_variables?: DecisionVariable[];
  variables?: DecisionVariable[];
}): DecisionVariable[] {
  return dp.decision_variables ?? dp.variables ?? [];
}

function critLabel(c: RubricCriterion): string {
  return c.text ?? c.prompt ?? c.key;
}

/** Chat transcript + composer used by authoring and revise loops. */
function ChatPanel({
  messages,
  busy,
  placeholder,
  onSend,
  disabled,
}: {
  messages: ChatMsg[];
  busy: boolean;
  placeholder: string;
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function submit() {
    const t = draft.trim();
    if (!t || busy || disabled) return;
    setDraft("");
    onSend(t);
  }

  return (
    <div>
      <div className="mb-3 max-h-[420px] space-y-3 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={
                m.role === "user"
                  ? "max-w-[78%] rounded-[12px] rounded-br-sm bg-[var(--navy)] px-3.5 py-2.5 text-[14px] text-white"
                  : "max-w-[82%] whitespace-pre-wrap rounded-[12px] rounded-bl-sm border border-[var(--line)] bg-[var(--panel2)] px-3.5 py-2.5 text-[14px] text-[var(--ink2)]"
              }
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-[12px] rounded-bl-sm border border-[var(--line)] bg-[var(--panel2)] px-3.5 py-2.5 text-[13px] text-[var(--ink3)]">
              <span className="spinner" /> thinking…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div className="flex gap-2">
        <textarea
          className="field"
          rows={2}
          placeholder={placeholder}
          value={draft}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="btn btn-primary shrink-0 self-end"
          onClick={submit}
          disabled={busy || disabled || !draft.trim()}
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}

/* ══════════════════════════════ PROFESSOR ══════════════════════════════ */

type ProfStep = "author" | "generating" | "preview";

function ProfessorFlow() {
  const { course } = useCourse();
  const [step, setStep] = useState<ProfStep>("author");

  // ── authoring chat (POST /caseband/cases/interview) ──
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [interviewState, setInterviewState] = useState<unknown>(undefined);
  const [collected, setCollected] = useState<InterviewTurn["collected"]>();
  const [pending, setPending] = useState<InterviewTurn["pending"]>();
  const [ready, setReady] = useState(false);
  const [brief, setBrief] = useState<InterviewTurn["brief"]>();
  const [checkpoints, setCheckpoints] = useState<number | undefined>();
  const [chatBusy, setChatBusy] = useState(false);
  const [authorErr, setAuthorErr] = useState<string | null>(null);
  const started = useRef(false);

  // ── generated case ──
  const [summary, setSummary] = useState<(CaseSummary & { case_id?: string }) | null>(null);
  const caseId = summary?.case_id;

  // start the interview once
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void runInterview(undefined, undefined, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runInterview(
    message: string | undefined,
    state: unknown,
    isStart: boolean,
  ) {
    setAuthorErr(null);
    setChatBusy(true);
    if (message) setChat((c) => [...c, { role: "user", text: message }]);
    try {
      const body: { state?: unknown; message?: string } = {};
      if (!isStart) {
        body.state = state;
        if (message) body.message = message;
      }
      const turn = await api.post<InterviewTurn>(
        "/caseband/cases/interview",
        body,
      );
      if (turn.reply) {
        setChat((c) => [...c, { role: "assistant", text: turn.reply! }]);
      }
      setInterviewState(turn.state ?? state);
      setCollected(turn.collected);
      setPending(turn.pending);
      setReady(Boolean(turn.ready));
      setBrief(turn.brief);
      setCheckpoints(turn.checkpoints);
    } catch (e) {
      setAuthorErr((e as Error).message);
    } finally {
      setChatBusy(false);
    }
  }

  async function onGenerate() {
    if (!brief) return;
    setStep("generating");
    setAuthorErr(null);
    try {
      const res = await api.post<CaseSummary & { case_id?: string }>(
        "/caseband/cases",
        {
          title: brief.title ?? "Untitled case",
          objectives: brief.objectives ?? [],
          document: brief.document,
          model: {},
          live: true,
        },
      );
      setSummary(res);
      setStep("preview");
    } catch (e) {
      setAuthorErr((e as Error).message);
      setStep("author");
    }
  }

  const collectedList = normalizeKv(collected);
  const pendingList = normalizePending(pending);

  return (
    <div className="fade-up">
      <div className="page-header">
        <div className="page-label">
          {course ? `${course.code} · ${course.name}` : "Faculty"} · Authoring
        </div>
        <h1>Design a case</h1>
        <p className="subtitle">
          Talk through your assignment with the authoring agent. When it has
          enough, it generates a provably-solvable case you can preview, revise,
          and publish.
        </p>
      </div>

      <StepRail
        steps={["Author", "Generate", "Preview & publish"]}
        active={step === "preview" ? 2 : step === "generating" ? 1 : 0}
      />

      {(step === "author" || step === "generating") && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
          <div className="card">
            <div className="mb-3 flex items-center gap-2">
              <Wand2 size={18} className="text-[var(--navy2)]" />
              <h2 className="text-[16px] font-semibold">Authoring chat</h2>
              <span className="badge badge-navy ml-auto">Live LLM</span>
            </div>
            {authorErr && <ErrorStrip msg={authorErr} />}
            <ChatPanel
              messages={chat}
              busy={chatBusy || step === "generating"}
              disabled={step === "generating"}
              placeholder="Answer the agent — course, assignment, materials/links, duration…"
              onSend={(t) => void runInterview(t, interviewState, false)}
            />
            {ready && step === "author" && (
              <div className="mt-4 border-t border-[var(--line)] pt-4">
                <div className="strip strip-ok mb-3">
                  <CheckCircle2 size={16} className="mt-px shrink-0" />
                  <span>
                    Enough context gathered
                    {checkpoints ? ` · ${checkpoints} checkpoints` : ""}. Ready
                    to generate the case.
                  </span>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={onGenerate}
                  disabled={chatBusy}
                >
                  <Wand2 size={15} /> Generate case
                </button>
              </div>
            )}
            {step === "generating" && (
              <div className="mt-4 border-t border-[var(--line)] pt-4">
                <div className="strip strip-info">
                  <span className="spinner" />
                  <span>
                    Generating case — writing objectives, decision points, an
                    outcome model, and a rubric…
                  </span>
                </div>
              </div>
            )}
          </div>

          <aside className="space-y-4">
            <div className="card">
              <div className="label">Collected</div>
              {collectedList.length === 0 ? (
                <p className="muted text-[13px]">Nothing yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {collectedList.map((kv, i) => (
                    <li key={i} className="text-[13px]">
                      <span className="text-[var(--ink3)]">{kv.label}: </span>
                      <span className="text-[var(--ink2)]">{kv.value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="card">
              <div className="label">Still needed</div>
              {pendingList.length === 0 ? (
                <p className="muted text-[13px]">
                  {ready ? "All set." : "—"}
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {pendingList.map((p, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-[13px] text-[var(--ink2)]"
                    >
                      <AlertCircle
                        size={13}
                        className="mt-0.5 shrink-0 text-[var(--amber)]"
                      />
                      {p}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>
      )}

      {step === "preview" && caseId && (
        <PreviewAndPublish
          caseId={caseId}
          summary={summary!}
          onBack={() => setStep("author")}
        />
      )}
    </div>
  );
}

/* ── Step 3+4: preview in student mode, revise loop, redteam-gated publish, access code ── */

function PreviewAndPublish({
  caseId,
  summary,
  onBack,
}: {
  caseId: string;
  summary: CaseSummary & { case_id?: string };
  onBack: () => void;
}) {
  const [view, setView] = useState<StudentCaseView | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // revise chat
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [revisePending, setRevisePending] = useState(false);

  // redteam
  const [redteaming, setRedteaming] = useState(false);
  const [redteam, setRedteam] = useState<RedteamResult | null>(null);
  const [redteamErr, setRedteamErr] = useState<string | null>(null);

  // publish + access code
  const [published, setPublished] = useState(false);
  const [accessCode, setAccessCode] = useState<string | null>(null);
  const [codePending, setCodePending] = useState(false);
  const [copied, setCopied] = useState(false);

  const redteamClean = redteam?.validated ?? summary.redteam_clean ?? false;

  async function loadPreview() {
    setLoading(true);
    setLoadErr(null);
    try {
      const res = await api.get<StudentCaseView>(
        `/caseband/cases/${caseId}?view=student`,
      );
      setView(res);
    } catch (e) {
      setLoadErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  async function onRevise(message: string) {
    setChat((c) => [...c, { role: "user", text: message }]);
    setChatBusy(true);
    setRevisePending(false);
    try {
      const res = await PENDING.reviseCase<ReviseResponse>(caseId, message);
      setChat((c) => [
        ...c,
        {
          role: "assistant",
          text: res.reply ?? "Revision applied. Reloading preview…",
        },
      ]);
      // a revision may change the case — refresh the preview
      void loadPreview();
    } catch (e) {
      if (isPending(e)) {
        setRevisePending(true);
        setChat((c) => c.slice(0, -1)); // drop the optimistic user msg
      } else {
        setChat((c) => [
          ...c,
          { role: "assistant", text: `Error: ${(e as Error).message}` },
        ]);
      }
    } finally {
      setChatBusy(false);
    }
  }

  async function onRedteam() {
    setRedteamErr(null);
    setRedteaming(true);
    try {
      const res = await api.post<RedteamResult>(
        `/caseband/cases/${caseId}/redteam`,
      );
      setRedteam(res);
    } catch (e) {
      setRedteamErr((e as Error).message);
    } finally {
      setRedteaming(false);
    }
  }

  async function onPublish() {
    setPublished(true);
    setCodePending(false);
    try {
      const res = await PENDING.getAccessCode<AccessCodeResponse>(caseId);
      setAccessCode(res.code);
    } catch (e) {
      if (isPending(e)) {
        setCodePending(true);
        setAccessCode("CODE-PENDING");
      } else {
        setAccessCode("CODE-PENDING");
        setCodePending(true);
      }
    }
  }

  function copyCode() {
    if (!accessCode) return;
    void navigator.clipboard?.writeText(accessCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const title = view?.meta?.title ?? "Case";
  const brief = view?.meta?.brief ?? view?.meta?.summary;
  const decisionPoints = view?.decision_points ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          <ArrowLeft size={14} /> Back to authoring
        </button>
        <div className="flex flex-wrap gap-2">
          <span
            className={`badge ${summary.all_objectives_tested ? "badge-green" : "badge-amber"}`}
          >
            {summary.all_objectives_tested ? (
              <CheckCircle2 size={13} />
            ) : (
              <AlertCircle size={13} />
            )}
            All objectives tested
          </span>
          <span className={`badge ${redteamClean ? "badge-green" : "badge-amber"}`}>
            {redteamClean ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />}
            Red-team {redteamClean ? "clean" : "pending"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Student-mode preview */}
        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            <Eye size={18} className="text-[var(--navy2)]" />
            <h2 className="text-[16px] font-semibold">Preview (student view)</h2>
          </div>
          {loading && (
            <div className="strip strip-info">
              <span className="spinner" /> <span>Loading preview…</span>
            </div>
          )}
          {loadErr && <ErrorStrip msg={loadErr} />}
          {view && (
            <div className="fade-up">
              <h3 className="text-[16px] font-semibold">{title}</h3>
              {brief && (
                <p className="mt-2 whitespace-pre-wrap text-[14px] text-[var(--ink2)]">
                  {brief}
                </p>
              )}
              <div className="mt-4 grid grid-cols-4 gap-3">
                <Stat num={summary.objectives} lbl="Objectives" />
                <Stat num={summary.decision_points} lbl="Decisions" />
                <Stat num={summary.rubric} lbl="Rubric" />
                <Stat num={summary.exhibits} lbl="Exhibits" />
              </div>
              {view.objectives && view.objectives.length > 0 && (
                <div className="mt-4">
                  <div className="label">Objectives</div>
                  <ul className="space-y-1.5">
                    {view.objectives.map((o) => (
                      <li
                        key={o.key}
                        className="flex items-start gap-2 text-[14px] text-[var(--ink2)]"
                      >
                        <CheckCircle2
                          size={15}
                          className="mt-0.5 shrink-0 text-[var(--navy2)]"
                        />
                        {o.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {decisionPoints.length > 0 && (
                <div className="mt-4">
                  <div className="label">Decision points</div>
                  <ul className="space-y-1.5">
                    {decisionPoints.map((dp, i) => (
                      <li
                        key={dp.key ?? i}
                        className="text-[14px] text-[var(--ink2)]"
                      >
                        {dp.prompt ?? dp.text ?? `Decision ${i + 1}`}
                        {dpVariables(dp).length > 0 && (
                          <span className="ml-1 text-[var(--ink4)]">
                            ({dpVariables(dp).map((v) => v.key).join(", ")})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Revise chat */}
        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            <MessageSquare size={18} className="text-[var(--navy2)]" />
            <h2 className="text-[16px] font-semibold">Revise</h2>
          </div>
          <p className="muted mb-3 text-[13px]">
            Suggest changes, add questions, or adjust difficulty. Re-preview
            after each round; publish when you&apos;re happy.
          </p>
          {revisePending && (
            <PendingStrip msg="Revise endpoint pending — wiring is being built in parallel." />
          )}
          <ChatPanel
            messages={chat}
            busy={chatBusy}
            placeholder="e.g. Make the pricing decision harder; add a question on cash flow."
            onSend={(t) => void onRevise(t)}
          />
        </div>
      </div>

      {/* Prove solvable */}
      <div className="card">
        <div className="mb-3 flex items-center gap-2">
          <ShieldCheck size={18} className="text-[var(--green2)]" />
          <h2 className="text-[16px] font-semibold">Prove solvable</h2>
        </div>
        <p className="muted mb-4 text-[13px]">
          Run the red-team loop to confirm a winning path exists. Publishing is
          gated on a clean result.
        </p>
        {redteamErr && <ErrorStrip msg={redteamErr} />}
        <button className="btn" onClick={onRedteam} disabled={redteaming}>
          {redteaming ? <span className="spinner" /> : <ShieldCheck size={15} />}
          {redteaming ? "Red-teaming…" : "Prove solvable"}
        </button>
        {redteam && (
          <div className="mt-4 fade-up">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`badge ${redteam.validated ? "badge-green" : "badge-red"}`}
              >
                {redteam.validated ? (
                  <CheckCircle2 size={13} />
                ) : (
                  <XCircle size={13} />
                )}
                {redteam.validated ? "Validated · solvable" : "Not validated"}
              </span>
              <span
                className={`badge ${redteam.converged ? "badge-navy" : "badge-amber"}`}
              >
                {redteam.converged ? "Converged" : "Did not converge"}
              </span>
            </div>
            {redteam.findings?.length > 0 ? (
              <div className="mt-3">
                <div className="label">Findings</div>
                <ul className="space-y-1.5">
                  {redteam.findings.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 text-[13px] text-[var(--ink2)]"
                    >
                      <AlertCircle
                        size={14}
                        className="mt-0.5 shrink-0 text-[var(--amber)]"
                      />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="strip strip-ok mt-3">
                <CheckCircle2 size={16} className="mt-px shrink-0" />
                <span>No outstanding findings.</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Publish + access code */}
      <div className="card">
        {!published ? (
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[15px] font-semibold">Publish to course</div>
              <p className="muted text-[13px]">
                {redteamClean
                  ? "Red-team is clean — ready for students."
                  : "Prove the case solvable before publishing."}
              </p>
            </div>
            <button
              className="btn btn-primary"
              disabled={!redteamClean}
              onClick={() => void onPublish()}
            >
              <Send size={15} /> Approve &amp; publish
            </button>
          </div>
        ) : (
          <div className="fade-up">
            <div className="mb-3 flex items-center gap-2">
              <CheckCircle2 size={18} className="text-[var(--green2)]" />
              <h2 className="text-[16px] font-semibold">Published</h2>
              <span className="badge badge-green ml-auto">Live</span>
            </div>
            {codePending && (
              <PendingStrip msg="Access-code endpoint pending — showing a placeholder until it's live." />
            )}
            <p className="muted mb-2 text-[13px]">
              Share this access code with your students to let them join:
            </p>
            <div className="flex items-center gap-2">
              <div className="rounded-[var(--radius-sm)] border border-[var(--line2)] bg-[var(--bg2)] px-4 py-3 font-mono text-[20px] font-bold tracking-[0.18em] text-[var(--ink)]">
                {accessCode}
              </div>
              <button className="btn btn-sm" onClick={copyCode}>
                <Copy size={14} /> {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════ STUDENT ══════════════════════════════ */

type StudentStep = "join" | "play" | "done";

function StudentFlow() {
  const { user } = useAuth();
  const { course } = useCourse();

  const [step, setStep] = useState<StudentStep>("join");

  // join
  const [code, setCode] = useState("");
  const [name, setName] = useState(user?.name ?? "");
  const [joining, setJoining] = useState(false);
  const [joinErr, setJoinErr] = useState<string | null>(null);
  const [joinPending, setJoinPending] = useState(false);

  // case / play
  const [caseId, setCaseId] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [view, setView] = useState<StudentCaseView | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const [assignment, setAssignment] = useState<Record<string, string>>({});
  const [rubricScores, setRubricScores] = useState<Record<string, number>>({});

  // submit / feedback
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [result, setResult] = useState<Grade & Feedback>();

  async function loadCase(id: string) {
    setLoadErr(null);
    try {
      const res = await api.get<StudentCaseView>(
        `/caseband/cases/${id}?view=student`,
      );
      setView(res);
    } catch (e) {
      setLoadErr((e as Error).message);
    }
  }

  async function onJoin() {
    setJoinErr(null);
    setJoinPending(false);
    setJoining(true);
    try {
      let resolvedCaseId = code.trim();
      let resolvedRunId: string | null = null;
      try {
        const res = await PENDING.joinByCode<JoinResponse>(
          code.trim(),
          name.trim(),
        );
        resolvedCaseId = res.case_id;
        resolvedRunId = res.run_id ?? null;
      } catch (e) {
        if (isPending(e)) {
          // fallback: treat the entered code as a case ID directly
          setJoinPending(true);
        } else {
          throw e;
        }
      }
      setCaseId(resolvedCaseId);
      setRunId(resolvedRunId);
      await loadCase(resolvedCaseId);
      setStep("play");
    } catch (e) {
      setJoinErr((e as Error).message);
    } finally {
      setJoining(false);
    }
  }

  async function onSubmit() {
    setSubmitErr(null);
    setSubmitting(true);
    try {
      let activeRunId = runId;
      if (!activeRunId) {
        const run = await api.post<RunResponse>("/caseband/runs", {
          case_id: caseId,
          student_id: user?.id ?? "stu_demo_001",
        });
        activeRunId = run.run_id;
        setRunId(activeRunId);
      }
      const numericAssignment: Record<string, number> = {};
      for (const [k, v] of Object.entries(assignment)) {
        if (v !== "") numericAssignment[k] = Number(v);
      }
      const res = await api.post<Grade & Feedback>(
        `/caseband/runs/${activeRunId}/submit`,
        { assignment: numericAssignment, rubric_scores: rubricScores },
      );
      setResult(res);
      setStep("done");
    } catch (e) {
      setSubmitErr((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const decisionPoints = view?.decision_points ?? [];
  const rubric = view?.rubric ?? [];
  const title = view?.meta?.title ?? "Case";
  const brief = view?.meta?.brief ?? view?.meta?.summary;

  return (
    <div className="fade-up">
      <div className="page-header">
        <div className="page-label">
          {course ? `${course.code} · ${course.name}` : "Caseband"} · Play
        </div>
        <h1>{step === "done" ? "Your feedback" : "Play a case"}</h1>
        <p className="subtitle">
          {step === "join"
            ? "Enter the access code your professor gave you to join."
            : step === "play"
              ? "Work through the case, ask the coach if you're stuck, then submit."
              : "Formative feedback on your submission."}
        </p>
      </div>

      <StepRail
        steps={["Join", "Play", "Feedback"]}
        active={step === "done" ? 2 : step === "play" ? 1 : 0}
      />

      {step === "join" && (
        <div className="card max-w-md">
          {joinErr && <ErrorStrip msg={joinErr} />}
          <div className="space-y-4">
            <div>
              <label className="label">Access code</label>
              <input
                className="field font-mono tracking-widest"
                placeholder="e.g. ABCD-1234"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Your name</label>
              <input
                className="field"
                placeholder="How you'll appear to your professor"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <button
              className="btn btn-primary"
              onClick={() => void onJoin()}
              disabled={joining || !code.trim() || !name.trim()}
            >
              {joining ? <span className="spinner" /> : <GraduationCap size={15} />}
              {joining ? "Joining…" : "Join case"}
            </button>
          </div>
        </div>
      )}

      {step === "play" && (
        <>
          {joinPending && (
            <PendingStrip msg="Join-by-code endpoint pending — treating your code as the case ID for now." />
          )}
          {loadErr && <ErrorStrip msg={loadErr} />}

          {view && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
              <div className="space-y-4">
                {/* Brief */}
                <div className="card">
                  <div className="mb-1 text-[12px] font-semibold text-[var(--navy2)]">
                    Brief
                  </div>
                  <h2 className="text-[17px] font-semibold">{title}</h2>
                  {brief && (
                    <p className="mt-2 whitespace-pre-wrap text-[14px] text-[var(--ink2)]">
                      {brief}
                    </p>
                  )}
                  {view.objectives && view.objectives.length > 0 && (
                    <div className="mt-4">
                      <div className="label">Objectives</div>
                      <ul className="space-y-1.5">
                        {view.objectives.map((o) => (
                          <li
                            key={o.key}
                            className="flex items-start gap-2 text-[14px] text-[var(--ink2)]"
                          >
                            <CheckCircle2
                              size={15}
                              className="mt-0.5 shrink-0 text-[var(--navy2)]"
                            />
                            {o.text}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Decisions */}
                <div className="card">
                  <div className="mb-3 flex items-center gap-2">
                    <Sliders size={18} className="text-[var(--navy2)]" />
                    <h2 className="text-[16px] font-semibold">Your decisions</h2>
                  </div>
                  {decisionPoints.length === 0 && (
                    <p className="muted text-[13px]">
                      No decision points in this case.
                    </p>
                  )}
                  <div className="space-y-5">
                    {decisionPoints.map((dp, i) => {
                      const vars = dpVariables(dp);
                      return (
                        <div key={dp.key ?? i}>
                          {(dp.prompt ?? dp.text) && (
                            <div className="mb-2 text-[14px] font-medium text-[var(--ink)]">
                              {dp.prompt ?? dp.text}
                            </div>
                          )}
                          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            {vars.map((v) => (
                              <div key={v.key}>
                                <label className="label">
                                  {v.key}
                                  {v.bounds && (
                                    <span className="ml-1 font-normal text-[var(--ink4)]">
                                      [{v.bounds[0]} – {v.bounds[1]}]
                                    </span>
                                  )}
                                </label>
                                <input
                                  className="field"
                                  type="number"
                                  step="any"
                                  min={v.bounds?.[0]}
                                  max={v.bounds?.[1]}
                                  value={assignment[v.key] ?? ""}
                                  onChange={(e) =>
                                    setAssignment((a) => ({
                                      ...a,
                                      [v.key]: e.target.value,
                                    }))
                                  }
                                />
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Rubric */}
                {rubric.length > 0 && (
                  <div className="card">
                    <div className="mb-3 flex items-center gap-2">
                      <ClipboardList size={18} className="text-[var(--navy2)]" />
                      <h2 className="text-[16px] font-semibold">
                        Rubric responses
                      </h2>
                    </div>
                    <div className="space-y-4">
                      {rubric.map((c) => (
                        <div key={c.key}>
                          <div className="mb-2 text-[14px] text-[var(--ink2)]">
                            {critLabel(c)}
                          </div>
                          <div className="flex gap-2">
                            {[0, 1, 2].map((s) => {
                              const active = rubricScores[c.key] === s;
                              return (
                                <button
                                  key={s}
                                  className={`btn btn-sm ${active ? "btn-primary" : ""}`}
                                  onClick={() =>
                                    setRubricScores((r) => ({
                                      ...r,
                                      [c.key]: s,
                                    }))
                                  }
                                >
                                  {s}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Submit */}
                <div className="card">
                  {submitErr && <ErrorStrip msg={submitErr} />}
                  <button
                    className="btn btn-primary"
                    onClick={() => void onSubmit()}
                    disabled={submitting}
                  >
                    {submitting ? (
                      <span className="spinner" />
                    ) : (
                      <Send size={15} />
                    )}
                    {submitting ? "Submitting…" : "Submit"}
                  </button>
                </div>
              </div>

              {/* Socratic coach */}
              <CoachPanel runId={runId} caseId={caseId} />
            </div>
          )}
        </>
      )}

      {step === "done" && result && <FeedbackCard result={result} />}
    </div>
  );
}

/* ── Socratic coach side panel (pending endpoint, graceful) ── */

function CoachPanel({
  runId,
  caseId,
}: {
  runId: string | null;
  caseId: string;
}) {
  const { user } = useAuth();
  const [chat, setChat] = useState<ChatMsg[]>([
    {
      role: "assistant",
      text: "I'm your coach. I won't hand you the answer, but I'll help you reason it out. What are you stuck on?",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const localRun = useRef<string | null>(runId);

  async function ensureRun(): Promise<string | null> {
    if (localRun.current) return localRun.current;
    try {
      const run = await api.post<RunResponse>("/caseband/runs", {
        case_id: caseId,
        student_id: user?.id ?? "stu_demo_001",
      });
      localRun.current = run.run_id;
      return run.run_id;
    } catch {
      return null;
    }
  }

  async function onAsk(message: string) {
    setChat((c) => [...c, { role: "user", text: message }]);
    setBusy(true);
    setPending(false);
    try {
      const rid = (await ensureRun()) ?? "pending";
      const res = await PENDING.askCoach<CoachResponse>(rid, message);
      setChat((c) => [...c, { role: "assistant", text: res.reply }]);
    } catch (e) {
      if (isPending(e)) {
        setPending(true);
        setChat((c) => c.slice(0, -1));
      } else {
        setChat((c) => [
          ...c,
          { role: "assistant", text: `Error: ${(e as Error).message}` },
        ]);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="card self-start lg:sticky lg:top-2">
      <div className="mb-3 flex items-center gap-2">
        <LifeBuoy size={18} className="text-[var(--navy2)]" />
        <h2 className="text-[16px] font-semibold">Socratic coach</h2>
      </div>
      {pending && (
        <PendingStrip msg="Coach pending — endpoint is being built in parallel." />
      )}
      <ChatPanel
        messages={chat}
        busy={busy}
        placeholder="Ask the coach for a hint…"
        onSend={(t) => void onAsk(t)}
      />
    </aside>
  );
}

/* ── Step 6: qualitative feedback (no numeric grade surfaced) ── */

function FeedbackCard({ result }: { result: Grade & Feedback }) {
  const hasNumeric =
    typeof result.overall_pass === "boolean" ||
    typeof result.kpi_value === "number";
  const qualitative =
    result.feedback ?? result.comments ?? defaultQualitative(result);
  const strengths = result.strengths ?? [];
  const improvements = result.improvements ?? [];

  return (
    <div className="card fade-up">
      <div className="mb-4 flex items-center gap-2">
        <MessageSquare size={18} className="text-[var(--navy2)]" />
        <h2 className="text-[16px] font-semibold">Feedback</h2>
        <span className="badge badge-amber ml-auto">
          Grade pending professor approval
        </span>
      </div>

      <p className="whitespace-pre-wrap text-[14px] text-[var(--ink2)]">
        {qualitative}
      </p>

      {strengths.length > 0 && (
        <div className="mt-4">
          <div className="label">Strengths</div>
          <ul className="space-y-1.5">
            {strengths.map((s, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[14px] text-[var(--ink2)]"
              >
                <CheckCircle2
                  size={15}
                  className="mt-0.5 shrink-0 text-[var(--green2)]"
                />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {improvements.length > 0 && (
        <div className="mt-4">
          <div className="label">To work on</div>
          <ul className="space-y-1.5">
            {improvements.map((s, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[14px] text-[var(--ink2)]"
              >
                <AlertCircle
                  size={15}
                  className="mt-0.5 shrink-0 text-[var(--amber)]"
                />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasNumeric && result.rubric_breakdown?.length > 0 && (
        <div className="mt-4">
          <div className="label">Where you landed</div>
          <div className="space-y-1.5">
            {result.rubric_breakdown.map((b, i) => (
              <div
                key={b.key ?? i}
                className="flex items-center justify-between border-b border-[var(--line)] pb-1.5 text-[13px] last:border-0"
              >
                <span className="text-[var(--ink2)]">
                  {b.criterion ?? b.key ?? `Criterion ${i + 1}`}
                </span>
                <span className="font-semibold">{b.score ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="strip strip-info mt-4">
        <AlertCircle size={16} className="mt-px shrink-0" />
        <span>
          This is formative feedback to help you learn. Your professor reviews
          and releases the final grade.
        </span>
      </div>
    </div>
  );
}

/* ──────────────────────────── small utilities ──────────────────────────── */

function StepRail({ steps, active }: { steps: string[]; active: number }) {
  return (
    <div className="tabs">
      {steps.map((s, i) => (
        <div
          key={s}
          className={`tab ${i === active ? "active" : ""} pointer-events-none flex items-center gap-2`}
        >
          <span
            className={`grid h-5 w-5 place-items-center rounded-full text-[11px] font-bold ${
              i < active
                ? "bg-[var(--green)] text-white"
                : i === active
                  ? "bg-[var(--navy2)] text-white"
                  : "bg-[var(--panel2)] text-[var(--ink4)]"
            }`}
          >
            {i < active ? "✓" : i + 1}
          </span>
          {s}
        </div>
      ))}
    </div>
  );
}

function normalizeKv(
  collected: InterviewTurn["collected"],
): { label: string; value: string }[] {
  if (!collected) return [];
  if (Array.isArray(collected)) {
    return collected.map((v, i) => ({
      label: String(i + 1),
      value: stringify(v),
    }));
  }
  return Object.entries(collected).map(([k, v]) => ({
    label: k,
    value: stringify(v),
  }));
}

function normalizePending(pending: InterviewTurn["pending"]): string[] {
  if (!pending) return [];
  if (Array.isArray(pending)) return pending.map(stringify);
  return Object.entries(pending).map(([k, v]) =>
    v && v !== true ? `${k}: ${stringify(v)}` : k,
  );
}

function stringify(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function defaultQualitative(result: Grade & Feedback): string {
  if (result.overall_pass === true) {
    return "Strong work — your decisions hit the target the case was built around. Review the breakdown below to see where you were strongest.";
  }
  if (result.overall_pass === false) {
    return "You're on the right track but didn't fully reach the target yet. Look at the levers you set and consider which one most affects the outcome.";
  }
  return "Your submission has been recorded. Detailed feedback will appear here once it's processed.";
}
