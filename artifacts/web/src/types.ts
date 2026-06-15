// Shared types mirroring the frozen API contract.

export type Role = "professor" | "student";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface Course {
  id: string;
  code: string;
  name: string;
  semester: string;
  professor_id: string;
}

export interface Objective {
  key: string;
  text: string;
}

export interface CaseSummary {
  case_id?: string;
  status: string;
  objectives: number;
  decision_points: number;
  rubric: number;
  exhibits: number;
  all_objectives_tested: boolean;
  redteam_clean: boolean;
}

export interface RedteamResult extends CaseSummary {
  converged: boolean;
  validated: boolean;
  findings: string[];
}

export interface DecisionVariable {
  key: string;
  bounds?: [number, number];
}

export interface DecisionPoint {
  key?: string;
  prompt?: string;
  text?: string;
  decision_variables?: DecisionVariable[];
  variables?: DecisionVariable[];
}

export interface RubricCriterion {
  key: string;
  text?: string;
  prompt?: string;
  weight?: number;
}

export interface StudentCaseView {
  meta?: {
    title?: string;
    brief?: string;
    summary?: string;
    [k: string]: unknown;
  };
  objectives?: Objective[];
  decision_points?: DecisionPoint[];
  outcome_model?: { kpi_key?: string; [k: string]: unknown };
  rubric?: RubricCriterion[];
  exhibits?: unknown[];
}

export interface FacultyCaseView extends StudentCaseView {
  solvability?: { value?: number; comparator?: string; units?: string; [k: string]: unknown };
  redteam_findings?: string[];
}

export interface RunResponse {
  run_id: string;
  case_id: string;
  status: string;
}

export interface RubricBreakdownItem {
  key?: string;
  criterion?: string;
  score?: number;
  weight?: number;
  [k: string]: unknown;
}

export interface Grade {
  status: string;
  kpi_key: string;
  kpi_value: number;
  numeric_pass: boolean;
  rubric_score: number;
  rubric_pass: boolean;
  overall_pass: boolean;
  rubric_breakdown: RubricBreakdownItem[];
}

export interface FacultyEditResult {
  diff: unknown;
  approvable: boolean;
  reason: string;
  applied: boolean;
}

/* ── Chat-authoring interview (POST /caseband/cases/interview) ── */

export interface InterviewBrief {
  title?: string;
  document?: string;
  objectives?: Objective[];
  [k: string]: unknown;
}

export interface InterviewTurn {
  /** Opaque conversation state to pass back on the next turn. */
  state?: unknown;
  /** Collected fields so far (label -> value or summary). */
  collected?: Record<string, unknown> | unknown[];
  /** What the agent still needs. */
  pending?: string[] | Record<string, unknown>;
  /** True once enough context has been gathered to generate the case. */
  ready?: boolean;
  /** The assistant's message for this turn. */
  reply?: string;
  /** Present when ready — feed into POST /caseband/cases. */
  brief?: InterviewBrief;
  /** Number of checkpoints derived from duration. */
  checkpoints?: number;
}

/* ── Pending (parallel-built) endpoint shapes — see PENDING section in api.ts ── */

export interface AccessCodeResponse {
  code: string;
  case_id?: string;
  expires_at?: string;
}

export interface JoinResponse {
  case_id: string;
  run_id?: string;
  student_id?: string;
  student_name?: string;
}

export interface CoachResponse {
  reply: string;
}

export interface ReviseResponse {
  reply?: string;
  /** Optional refreshed summary after a revision was applied. */
  summary?: CaseSummary & { case_id?: string };
}

/** Defensive feedback shape — submit may evolve from Grade -> feedback object. */
export interface Feedback {
  feedback?: string;
  comments?: string;
  strengths?: string[];
  improvements?: string[];
  status?: string;
  [k: string]: unknown;
}
