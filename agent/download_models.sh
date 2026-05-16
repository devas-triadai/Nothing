#!/usr/bin/env bash
# ============================================================================
#  AGRA Phase 2 — Model Download Script
#  Downloads all required models for fully offline operation.
#  Run this ONCE on an internet-connected machine, then transfer
#  the agent/models/ directory to the air-gapped deployment.
#
#  Usage:
#    cd Nothing
#    chmod +x agent/download_models.sh
#    bash agent/download_models.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/models"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AGRA Phase 2 — Model Download Script               ║"
echo "║  Target directory: ${MODELS_DIR}                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Suppress common dependency warnings ──
export PYTHONWARNINGS="ignore:urllib3"

# ── Detect the correct HuggingFace CLI command ──
# huggingface_hub >= 1.x uses "hf", older versions use "huggingface-cli"
HF_CMD=""

if command -v hf &> /dev/null; then
    HF_CMD="hf"
    echo "✔  Found HuggingFace CLI: hf"
elif command -v huggingface-cli &> /dev/null; then
    HF_CMD="huggingface-cli"
    echo "✔  Found HuggingFace CLI: huggingface-cli"
else
    echo "⚠  HuggingFace CLI not found. Installing..."
    pip install -U "huggingface_hub[cli]" hf_transfer
    # After install, check which command is available
    if command -v hf &> /dev/null; then
        HF_CMD="hf"
    elif command -v huggingface-cli &> /dev/null; then
        HF_CMD="huggingface-cli"
    else
        echo "❌ Failed to install HuggingFace CLI. Please install manually:"
        echo "   pip install -U huggingface_hub"
        exit 1
    fi
    echo "✔  Installed HuggingFace CLI: ${HF_CMD}"
fi

# ── Ensure hf_transfer is installed if enabled ──
if [[ "${HF_HUB_ENABLE_HF_TRANSFER:-0}" == "1" ]]; then
    if ! python3 -c "import hf_transfer" &> /dev/null; then
        echo "⚠  hf_transfer enabled but not found. Installing..."
        pip install hf_transfer
    fi
fi

echo "   Using command: ${HF_CMD}"
echo ""

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
echo "  Size:  ~20 GB (this will take a while)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$HF_CMD download \
    bartowski/google_gemma-4-31B-it-GGUF \
    --include "google_gemma-4-31B-it-Q4_K_L.gguf" \
    --local-dir "${MODELS_DIR}/gemma4-31b-it"

echo "  Downloading Multimodal Projector (mmproj) for VLM..."
$HF_CMD download \
    bartowski/google_gemma-4-31B-it-GGUF \
    --include "mmproj-google_gemma-4-31B-it-f16.gguf" \
    --local-dir "${MODELS_DIR}/gemma4-31b-it"

echo "✅ Gemma 4 31B-IT and projector downloaded successfully."

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

$HF_CMD download \
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

$HF_CMD download \
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
echo "║  │   ├── google_gemma-4-31B-it-Q4_K_L.gguf    (~20 GB)     ║"
echo "║  │   └── mmproj-gemma-4-31b-f16.gguf           (~1 GB)      ║"
echo "║  ├── bge-m3/                                                ║"
echo "║  │   └── (sentence-transformers model files)   (~2.2 GB)    ║"
echo "║  └── bge-reranker-v2-m3/                                    ║"
echo "║      └── (cross-encoder model files)           (~2.2 GB)    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Total: ~24.4 GB                                            ║"
echo "║  VRAM at runtime: ~23 GB (LLM + embedder + reranker)       ║"
echo "║  Fits on: 1x RTX 6000 Ada (48 GB) with room to spare       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "To start the agent:"
echo "  bash agent/start_agent.sh"
