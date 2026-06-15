import { Router } from "express";
import { orchestratorBase } from "../lib/orchestrator";

export const health = Router();

health.get("/", (_req, res) => {
  res.json({ status: "ok", service: "caseband-api", orchestrator: orchestratorBase });
});
