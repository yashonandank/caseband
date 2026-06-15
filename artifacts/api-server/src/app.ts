import express from "express";
import cors from "cors";
import { api } from "./routes/index";

export function createApp() {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: "2mb" }));
  app.use("/api", api);
  return app;
}
