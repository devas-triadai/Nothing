#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AGRA Agent — Startup Script
# Configurable ports via environment variables:
#   AGENT_API_PORT  (default: 8005)
#   AGENT_UI_PORT   (default: 7860)
# ═══════════════════════════════════════════════════════════════

set -e

# ── Port configuration (override via env vars) ──
AGENT_API_PORT="${AGENT_API_PORT:-8005}"
AGENT_UI_PORT="${AGENT_UI_PORT:-7860}"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        AGRA Phase 2 — Agent Service Launcher              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ── Ensure persistent data dir exists ──
AGRA_DATA_DIR="${AGRA_DATA_DIR:-/workspace/agra_data}"
mkdir -p "$AGRA_DATA_DIR"
export AGRA_DATA_DIR

# ── Check Node.js version ──
NODE_MAJOR=$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [ -z "$NODE_MAJOR" ] || [ "$NODE_MAJOR" -lt 18 ] 2>/dev/null; then
    echo "⚠  Node.js $(node -v 2>/dev/null || echo 'not found') is too old. Running upgrade..."
    bash /workspace/Nothing/agent/setup_node.sh
fi

# ── 1. Start Agent API ──
echo "[AGRA Agent] Starting Agent API on port $AGENT_API_PORT..."
cd /workspace/Nothing/agent
uvicorn api.main:app --host 0.0.0.0 --port "$AGENT_API_PORT" --workers 1 &
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

# Pass port config to Vite build
export VITE_AGENT_API_PORT="$AGENT_API_PORT"
export VITE_AGENT_UI_PORT="$AGENT_UI_PORT"

echo "[AGRA Agent] Building production bundle..."
npm run build

echo "[AGRA Agent] Starting Agent UI on port $AGENT_UI_PORT..."
npx -y serve -s dist -l "$AGENT_UI_PORT" &
UI_PID=$!
echo "[AGRA Agent] Agent UI started (PID: $UI_PID)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AGRA Agent Services Running:"
echo "  • Agent API:  http://0.0.0.0:$AGENT_API_PORT  (PID: $API_PID)"
echo "  • Agent UI:   http://0.0.0.0:$AGENT_UI_PORT  (PID: $UI_PID)"
echo "  • API Docs:   http://0.0.0.0:$AGENT_API_PORT/docs"
echo "  • Data Dir:   $AGRA_DATA_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Keep script running
wait
