# AGRA Phase 2 — RunPod Separated Deployment Guide

This document outlines the exact, step-by-step terminal commands required to run the entirely air-gapped system across 4 separated instances in your RunPod Linux Environment.

---

### Terminal 1: Super Admin Backend (Port 8000)
*This terminal acts as your central orchestrator, so start it first.*
```bash
cd /workspace
git clone https://github.com/devasphn/Nothing || true
cd /workspace/Nothing/backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Terminal 2: Super Admin UI (Port 3000)
*This script runs your Node.js setup! Make sure to run `source ~/.bashrc` so the terminal recognizes the new `npm` binary.*
```bash
cd /workspace/Nothing
chmod +x agent/setup_node.sh
bash agent/setup_node.sh
source ~/.bashrc

cd /workspace/Nothing/frontend
npm install --legacy-peer-deps
npm run dev
```

### Terminal 3: Agent Backend API (Port 8005)
*This will download your 30-Billion parameter LLMs, Embedding models, and build the Python API.*
```bash
cd /workspace/Nothing
chmod +x agent/download_models.sh
bash agent/download_models.sh

cd /workspace/Nothing/agent
CMAKE_ARGS="-DGGML_CUDA=on" pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8005 --workers 1
```

### Terminal 4: Agent UI (Port 7860)
*Because Terminal 2 already installed Node.js globally, you just need to `source` the bashrc to activate it in this window!*
```bash
cd /workspace/Nothing
source ~/.bashrc

cd /workspace/Nothing/agent/ui
npm install --legacy-peer-deps
npm run build
npx -y serve -s dist -l 7860
```
