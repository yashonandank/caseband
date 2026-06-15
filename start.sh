#!/usr/bin/env bash
# Boot the two API services for Caseband:
#   1. Python FastAPI orchestrator (the agent "brain") on :8099
#   2. Express api-server (platform/auth, proxies /api/caseband -> Python) on :8088
# The React web app runs separately in dev: `pnpm --filter @caseband/web dev`
# (or build it with `pnpm --filter @caseband/web build` and serve dist/ statically).
set -euo pipefail

echo "[caseband] installing python deps..."
pip install -r requirements.txt

echo "[caseband] installing node deps..."
pnpm install

echo "[caseband] starting orchestrator on :8099..."
python3 -m uvicorn services.api.app:app --host 0.0.0.0 --port 8099 --app-dir . &
ORCH_PID=$!
trap 'kill $ORCH_PID 2>/dev/null || true' EXIT

echo "[caseband] starting api-server on :8088..."
ORCHESTRATOR_URL="http://127.0.0.1:8099" pnpm --filter @caseband/api-server start
