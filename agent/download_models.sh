#!/usr/bin/env bash
# ============================================================================
#  AGRA Phase 2 — Model Download Script
#  Downloads all required models for fully offline operation.
#  Run this ONCE on an internet-connected machine, then transfer
#  the agent/models/ directory to the air-gapped deployment.
#
#  Usage:
#    cd Nothing/agent
#    chmod +x download_models.sh
#    ./download_models.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AGRA Phase 2 — Model Download Script               ║"
echo "║  Target directory: ${MODELS_DIR}                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Ensure huggingface-cli is installed
if ! command -v huggingface-cli &> /dev/null; then
    echo "⚠  huggingface-cli not found. Installing..."
    pip install -U "huggingface_hub[cli]"
fi

mkdir -p "${MODELS_DIR}"

# ─────────────────────────────────────────────────────────────────
# 1. Gemma 4 31B-IT — Q4_K_L Quantization (GGUF)
#    Source: bartowski/google_gemma-4-31B-it-GGUF
#    File:   google_gemma-4-31B-it-Q4_K_L.gguf (~20GB)
#    This is the dense 31B model with Q4 quantization and
#    embed/output weights at Q8_0 for improved quality.
# ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [1/3] Downloading Gemma 4 31B-IT (Q4_K_L) GGUF..."
echo "  Repo:  bartowski/google_gemma-4-31B-it-GGUF"
echo "  File:  google_gemma-4-31B-it-Q4_K_L.gguf"
echo "  Size:  ~20 GB"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

huggingface-cli download \
    bartowski/google_gemma-4-31B-it-GGUF \
    --include "google_gemma-4-31B-it-Q4_K_L.gguf" \
    --local-dir "${MODELS_DIR}/gemma4-31b-it"

echo "✅ Gemma 4 31B-IT downloaded successfully."

# ─────────────────────────────────────────────────────────────────
# 2. BAAI/bge-m3 — Embedding Model
#    Dense (1024d) + Sparse + ColBERT, multilingual (100+ langs)
#    Loaded via sentence-transformers for offline use.
# ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [2/3] Downloading BAAI/bge-m3 (embedding model)..."
echo "  Repo:  BAAI/bge-m3"
echo "  Size:  ~2.2 GB"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

huggingface-cli download \
    BAAI/bge-m3 \
    --local-dir "${MODELS_DIR}/bge-m3"

echo "✅ bge-m3 downloaded successfully."

# ─────────────────────────────────────────────────────────────────
# 3. BAAI/bge-reranker-v2-m3 — Cross-Encoder Reranker
#    Used for reranking top retrieval candidates before LLM.
# ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [3/3] Downloading BAAI/bge-reranker-v2-m3 (reranker)..."
echo "  Repo:  BAAI/bge-reranker-v2-m3"
echo "  Size:  ~2.2 GB"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

huggingface-cli download \
    BAAI/bge-reranker-v2-m3 \
    --local-dir "${MODELS_DIR}/bge-reranker-v2-m3"

echo "✅ bge-reranker-v2-m3 downloaded successfully."

# ─────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   All models downloaded!                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  models/                                                    ║"
echo "║  ├── gemma4-31b-it/                                         ║"
echo "║  │   └── google_gemma-4-31B-it-Q4_K_L.gguf    (~20 GB)     ║"
echo "║  ├── bge-m3/                                                ║"
echo "║  │   └── (sentence-transformers model files)   (~2.2 GB)    ║"
echo "║  └── bge-reranker-v2-m3/                                    ║"
echo "║      └── (cross-encoder model files)           (~2.2 GB)    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Total: ~24.4 GB                                            ║"
echo "║  VRAM at runtime: ~20 GB (Gemma 4 Q4_K_L)                  ║"
echo "║  Fits on: 1x RTX 6000 Ada (48 GB) with room to spare       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "To start the agent API:"
echo "  cd agent && uvicorn api.main:app --host 0.0.0.0 --port 8001"
