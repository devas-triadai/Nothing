#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AGRA Agent — Startup Script
# Starts Agent API (port 8001) and Agent UI (port 7860)
# ═══════════════════════════════════════════════════════════════

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        AGRA Phase 2 — Agent Service Launcher              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Start Agent API ──
echo "[AGRA Agent] Starting Agent API on port 8001..."
cd /workspace/Nothing/agent/api
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 2 &
API_PID=$!
echo "[AGRA Agent] Agent API started (PID: $API_PID)"

# Wait for API to be ready
echo "[AGRA Agent] Waiting for API to initialise (this may take 2-5 minutes for model loading)..."
sleep 10

# ── 2. Build and Serve Agent UI ──
echo "[AGRA Agent] Building Agent UI..."
cd /workspace/Nothing/agent/ui

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "[AGRA Agent] Installing UI dependencies..."
    npm install --legacy-peer-deps
fi

echo "[AGRA Agent] Building production bundle..."
npm run build

echo "[AGRA Agent] Starting Agent UI on port 7860..."
npx -y serve -s dist -l 7860 &
UI_PID=$!
echo "[AGRA Agent] Agent UI started (PID: $UI_PID)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AGRA Agent Services Running:"
echo "  • Agent API:  http://0.0.0.0:8001  (PID: $API_PID)"
echo "  • Agent UI:   http://0.0.0.0:7860  (PID: $UI_PID)"
echo "  • API Docs:   http://0.0.0.0:8001/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Keep script running
wait
