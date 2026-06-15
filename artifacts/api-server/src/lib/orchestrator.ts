// HTTP client to the Python orchestrator service (the case-authoring/grading brain).
// Express owns platform concerns (auth, courses, Supabase) and delegates the deep
// multi-agent work here. Base URL is env-driven so it can point at a deployed service.
const BASE = process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8099";

export class OrchestratorError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function orch<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { "content-type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = (data && (data.detail ?? data.error)) ?? res.statusText;
    throw new OrchestratorError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      res.status,
    );
  }
  return data as T;
}

export const orchestratorBase = BASE;
