import { Router } from "express";
import { health } from "./health";
import { caseband } from "./caseband";
import { auth } from "./auth";
import { courses } from "./courses";

// app.ts -> routes/index.ts -> per-feature routers, all mounted under /api.
export const api = Router();
api.use("/health", health);
api.use("/auth", auth);
api.use("/courses", courses);
api.use("/caseband", caseband);
