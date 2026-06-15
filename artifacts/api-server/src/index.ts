import { createApp } from "./app";
import { orchestratorBase } from "./lib/orchestrator";

const port = Number(process.env.PORT ?? 8088);
createApp().listen(port, () => {
  console.log(`caseband api-server on :${port} -> orchestrator ${orchestratorBase}`);
});
