// Tiny fetch client. Base `/api`, attaches Bearer token from localStorage,
// throws Error(json.error) on non-OK responses.

const BASE = "/api";
export const TOKEN_KEY = "caseband.token";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type Method = "GET" | "POST" | "PUT" | "DELETE";

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const msg =
      (data && typeof data === "object" && "error" in data
        ? String((data as { error: unknown }).error)
        : null) ||
      (typeof data === "string" && data) ||
      `Request failed (${res.status})`;
    throw new ApiError(msg, res.status);
  }

  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/* ════════════════════════════════════════════════════════════════════════
   PENDING ENDPOINTS — built in parallel; shapes NOT yet frozen.
   See docs/API_CONTRACT.md. Each fn below targets a guessed endpoint and
   MUST degrade gracefully: callers catch ApiError(status===404) and show a
   small "pending" strip instead of crashing.

   When the backend lands these, update the paths/shapes here AND the
   contract. The assumed request/response shapes are documented inline.
   ════════════════════════════════════════════════════════════════════════ */

export const PENDING = {
  /**
   * Faculty revise loop — professor gives free-text comments / change
   * requests against a generated case.
   * TODO(contract): confirm path + shape.
   *   req:  POST /caseband/cases/:id/revise  { message }
   *   resp: { reply?: string, summary?: CaseSummary & { case_id } }
   */
  reviseCase: <T>(caseId: string, message: string) =>
    request<T>("POST", `/caseband/cases/${caseId}/revise`, { message }),

  /**
   * Access code for distributing a published case to students.
   * TODO(contract): confirm path + shape.
   *   req:  POST /caseband/cases/:id/access-code  {}
   *   resp: { code: string, case_id?, expires_at? }
   */
  getAccessCode: <T>(caseId: string) =>
    request<T>("POST", `/caseband/cases/${caseId}/access-code`, {}),

  /**
   * Student joins a case by access code + display name.
   * TODO(contract): confirm path + shape.
   *   req:  POST /caseband/join  { code, name }
   *   resp: { case_id: string, run_id?, student_id?, student_name? }
   */
  joinByCode: <T>(code: string, name: string) =>
    request<T>("POST", `/caseband/join`, { code, name }),

  /**
   * Socratic coach — student asks for help mid-run; never leaks the answer.
   * TODO(contract): confirm path + shape.
   *   req:  POST /caseband/runs/:id/coach  { message }
   *   resp: { reply: string }
   */
  askCoach: <T>(runId: string, message: string) =>
    request<T>("POST", `/caseband/runs/${runId}/coach`, { message }),
};

/** True when an error means the pending endpoint isn't live yet. */
export function isPending(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 404 || e.status === 501);
}
