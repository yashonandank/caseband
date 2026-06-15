// Caseband feature router — the platform-facing surface for the case lifecycle.
// For now it proxies to the Python orchestrator; auth + course scoping layer in here.
import { Router, type Request, type Response } from "express";
import { orch, OrchestratorError } from "../lib/orchestrator";

export const caseband = Router();

const wrap =
  (fn: (req: Request) => Promise<unknown>) =>
  async (req: Request, res: Response) => {
    try {
      res.json(await fn(req));
    } catch (e) {
      const status = e instanceof OrchestratorError ? e.status : 502;
      res.status(status).json({ error: (e as Error).message });
    }
  };

caseband.post("/ingest", wrap((req) => orch("POST", "/ingest", req.body)));
caseband.post("/cases/interview", wrap((req) => orch("POST", "/cases/interview", req.body)));
caseband.post("/cases", wrap((req) => orch("POST", "/cases", req.body)));
caseband.post(
  "/cases/:id/redteam",
  wrap((req) => orch("POST", `/cases/${req.params.id}/redteam`)),
);
caseband.get(
  "/cases/:id",
  wrap((req) =>
    orch("GET", `/cases/${req.params.id}?view=${req.query.view ?? "faculty"}`),
  ),
);
caseband.post(
  "/cases/:id/whatif",
  wrap((req) => orch("POST", `/cases/${req.params.id}/whatif`, req.body)),
);
caseband.post("/runs", wrap((req) => orch("POST", "/runs", req.body)));
caseband.post(
  "/runs/:id/submit",
  wrap((req) => orch("POST", `/runs/${req.params.id}/submit`, req.body)),
);
caseband.post(
  "/cases/:id/faculty/edit",
  wrap((req) => orch("POST", `/cases/${req.params.id}/faculty/edit`, req.body)),
);

caseband.post(
  "/cases/:id/revise",
  wrap((req) => orch("POST", `/cases/${req.params.id}/revise`, req.body)),
);
caseband.post(
  "/cases/:id/access-code",
  wrap((req) => orch("POST", `/cases/${req.params.id}/access-code`, req.body)),
);
caseband.post("/join", wrap((req) => orch("POST", "/join", req.body)));
caseband.post(
  "/runs/:id/coach",
  wrap((req) => orch("POST", `/runs/${req.params.id}/coach`, req.body)),
);
caseband.post(
  "/runs/:id/finalize",
  wrap((req) => orch("POST", `/runs/${req.params.id}/finalize`, req.body)),
);
caseband.get(
  "/runs/:id/grade",
  wrap((req) =>
    orch("GET", `/runs/${req.params.id}/grade?view=${req.query.view ?? "student"}`),
  ),
);
