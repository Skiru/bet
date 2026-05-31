#!/usr/bin/env fish
# Start Rapid-MLX local model server for the betting pipeline
# Run this before starting Kilo Code sessions
#
# Model: Qwen3.6-35B-A3B MoE 4-bit
#   ~18GB VRAM, 35B total knowledge, only 3B active params per token
#   131K context, reasoning ALWAYS ON (<think> blocks)
#   MoE architecture: 45-70 tok/s generation, 15-25s prefill for 23K tokens
#   Tool calling: qwen3_coder_xml (native Qwen3.6 XML format)
#
# Usage:
#   ./scripts/start_local_model.sh              # default: full optimized config
#   ./scripts/start_local_model.sh --safe       # reduced GPU utilization (75%)
#   ./scripts/start_local_model.sh --minimal    # bare minimum flags (debugging)
#
# Hardware: Apple M4 Pro 48GB unified memory, 273 GB/s bandwidth
# Endpoint: http://localhost:8000/v1 (OpenAI-compatible)

set -l MODEL "qwen3.6-35b"
set -l PORT (test -n "$RAPID_MLX_PORT"; and echo $RAPID_MLX_PORT; or echo "8000")
set -l RAPID_MLX "$HOME/.local/bin/rapid-mlx"

# Check if rapid-mlx is installed
if not test -f "$RAPID_MLX"
    echo "❌ rapid-mlx not found at $RAPID_MLX"
    echo "   Install: pipx install rapid-mlx"
    exit 1
end

# Check if port is already in use
if lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1
    echo "⚠️  Port $PORT already in use (model server may be running)"
    echo "   Test: curl http://localhost:$PORT/v1/models"
    echo "   Kill: lsof -ti :$PORT | xargs kill"
    exit 0
end

# ═══════════════════════════════════════════════════════════════════
# OPTIMIZED FLAGS for Qwen3.6-35B-A3B MoE 4-bit on M4 Pro 48GB
# ═══════════════════════════════════════════════════════════════════
# --no-mllm:                  Skip vision encoder → frees memory for inference
# --max-num-seqs 1:           Single-user pipeline → ALL resources to active request
# --max-concurrent-requests 4: Admission cap — prevents queue buildup
# --reasoning-parser qwen3:   Parse <think>...</think> blocks (CRITICAL for pipeline)
# --default-temperature 0.6:  Qwen optimal — explores hypotheses without chaos
# --default-top-p 0.95:       Qwen optimal — diverse but controlled token selection
# --default-top-k 20:         Qwen optimal — prevents unlikely tokens in reasoning
# --max-tokens 32768:         Hard cap on output (thinking+content). Prevents infinite loops.
# --stream-interval 1:        Per-token streaming — SSE keepalive for Kilo
# --pin-system-prompt:        Agent instructions (~23K tokens) stay cached in memory
# --enable-prefix-cache:      Reuse computed KV for repeated prompt prefixes
# --kv-cache-turboquant:      3-bit V-cache compression (86% savings, K stays FP16)
# --cache-memory-mb 2000:     2GB prefix cache (proven safe with 0.9 GPU util)
# --gpu-memory-utilization 0.9: 90% of Metal (~36GB alloc) — proven stable
# --prefill-step-size 4096:   Safe chunks — prevents OOM at high token counts
# --chunked-prefill-tokens 4096: Matches prefill-step-size for consistency
# --gc-control:               No GC during generation → no latency spikes
# --timeout 1800:             Server-side 30min safety net per request
# --enable-auto-tool-choice:  Auto-detect when model wants to call a tool
# --tool-call-parser qwen3_coder_xml:  Parse Qwen3.6 XML tool calls (native format)
# ═══════════════════════════════════════════════════════════════════

set -l FLAGS \
    --no-mllm \
    --max-num-seqs 1 \
    --max-concurrent-requests 4 \
    --reasoning-parser qwen3 \
    --default-temperature 0.6 \
    --default-top-p 0.95 \
    --default-top-k 20 \
    --max-tokens 32768 \
    --stream-interval 1 \
    --pin-system-prompt \
    --enable-prefix-cache \
    --kv-cache-turboquant \
    --kv-cache-turboquant-bits 3 \
    --cache-memory-mb 2000 \
    --gpu-memory-utilization 0.9 \
    --prefill-step-size 4096 \
    --chunked-prefill-tokens 4096 \
    --gc-control \
    --timeout 1800 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder_xml

# Mode overrides
if contains -- --safe $argv
    set FLAGS \
        --no-mllm \
        --max-num-seqs 1 \
        --max-concurrent-requests 2 \
        --reasoning-parser qwen3 \
        --default-temperature 0.6 \
        --default-top-p 0.95 \
        --default-top-k 20 \
        --max-tokens 32768 \
        --stream-interval 1 \
        --pin-system-prompt \
        --enable-prefix-cache \
        --kv-cache-turboquant \
        --kv-cache-turboquant-bits 3 \
        --cache-memory-mb 1500 \
        --gpu-memory-utilization 0.75 \
        --prefill-step-size 4096 \
        --chunked-prefill-tokens 4096 \
        --gc-control \
        --timeout 1800 \
        --enable-auto-tool-choice \
        --tool-call-parser qwen3_coder_xml
    echo "🛡️  Safe mode: GPU utilization 75%, cache 1.5GB"
else if contains -- --minimal $argv
    set FLAGS \
        --no-mllm \
        --max-num-seqs 1 \
        --reasoning-parser qwen3 \
        --max-tokens 32768 \
        --enable-auto-tool-choice \
        --tool-call-parser qwen3_coder_xml
    echo "🔧 Minimal mode: basic flags only (debugging)"
end

echo "🚀 Starting Rapid-MLX server..."
echo "   Model:    $MODEL (MoE: 35B total, 3B active/token)"
echo "   Port:     $PORT"
echo "   Endpoint: http://localhost:$PORT/v1"
echo "   Thinking: ENABLED (qwen3 parser)"
echo "   Tools:    qwen3_coder_xml (native)"
echo "   Context:  131K tokens"
echo "   VRAM:     ~18GB (4-bit MoE quantization)"
echo "   Speed:    45-70 tok/s expected"
echo ""
echo "   Press Ctrl+C to stop"
echo ""

# Disable telemetry
set -x RAPID_MLX_TELEMETRY 0

exec $RAPID_MLX serve $MODEL --port $PORT $FLAGS
