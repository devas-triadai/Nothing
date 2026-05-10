#!/bin/bash
# AGRA - Llama-Server Startup Script
# Clones, compiles (with CUDA), and runs the native llama-server for true continuous batching

cd /workspace/Nothing/agent

# Ensure CMake is installed
if ! command -v cmake &> /dev/null; then
    echo "CMake not found. Installing via apt-get..."
    apt-get update && apt-get install -y cmake
fi

if [ ! -d "llama.cpp" ]; then
    echo "Cloning llama.cpp repository..."
    git clone https://github.com/ggerganov/llama.cpp
    cd llama.cpp
    echo "Compiling with CUDA support via CMake (Ampere/Ada Architecture)..."
    cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="86;89"
    cmake --build build --config Release -j
else
    echo "llama.cpp already exists."
    cd llama.cpp
    # Just in case it wasn't built yet
    if [ ! -f "build/bin/llama-server" ]; then
        echo "Building missing binary (Ampere/Ada Architecture)..."
        cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="86;89"
        cmake --build build --config Release -j
    fi
fi

echo "Starting llama-server with --parallel 5..."
# Note: Adjust paths if models are stored differently.
./build/bin/llama-server \
  -m ../../models/gemma4-31b-it/google_gemma-4-31B-it-Q4_K_L.gguf \
  --mmproj ../../models/gemma4-31b-it/mmproj-gemma-4-31b-f16.gguf \
  -c 8192 \
  -ngl 99 \
  --parallel 5 \
  --port 8080 \
  --host 0.0.0.0
