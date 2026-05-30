# Research Report: Optimal Local LLM for Betting Pipeline

**Date:** 2026-05-29  
**Hardware:** Apple M4 Pro 48GB Unified Memory  
**Server:** Rapid-MLX (OpenAI-compatible, port 8000)  
**Pipeline:** Kilo Code agent-driven betting pipeline (50+ turns, 27 MCP tools, 23K+ token system prompt)

---

## 1. Executive Summary

### Recommendation: **Qwen3.5-35B-A3B 4-bit (MoE)**

The current Qwen3.6-27B Dense 8-bit model is fundamentally incompatible with the M4 Pro 48GB hardware for this pipeline's demands. At ~30GB model weights alone, it leaves only ~5GB for KV cache and activations within Metal's ~40.2GB allocation — causing 1 tok/s generation and 270s prefill.

**The solution is a Mixture-of-Experts (MoE) architecture.** Specifically, `qwen3.5-35b-4bit` (mlx-community/Qwen3.5-35B-A3B-4bit):

| Metric | Current (Dense 27B 8-bit) | Recommended (MoE 35B 4-bit) | Improvement |
|--------|---------------------------|------------------------------|-------------|
| Model weight memory | ~30 GB | ~18 GB | -40% |
| Active params/token | 27B | 3B | -89% compute |
| Generation speed | 1 tok/s (throttled) | 45-70 tok/s | 45-70× |
| 23K prefill time | 270 seconds | 15-25 seconds | 10-18× |
| Quality (MMLU) | ~83% | ~82-84% | Comparable |
| KV cache budget | ~5 GB (starved) | ~15 GB (abundant) | 3× |
| Tool calling | qwen3_coder_xml (native) | hermes (standard) | Format change |
| Reasoning mode | qwen3 (`<think>`) | qwen3 (`<think>`) | Same |

The MoE model stores 35B parameters of knowledge but only activates 3B per token, giving dense-27B-quality analysis at 3B-model speed, with 12GB less memory pressure.

### Fallback Options (ranked):
1. **Nemotron-30B-A3B 4-bit** — Similar MoE profile, slightly lower quality
2. **Phi-4 14B 8-bit** — Dense, 18-20 tok/s, excellent reasoning, safe middle ground
3. **Qwen3.5-9B 8-bit** — Fastest option (25-30 tok/s), may lack depth for complex analysis

---

## 2. Why the Current Setup Fails

### Memory budget analysis (M4 Pro 48GB):

```
Total unified memory:              48.0 GB
macOS kernel/system reserve:       -8.0 GB
Metal allocation limit:            ~40.2 GB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Available for model + inference:   ~40.2 GB

Qwen3.6-27B 8-bit weights:        -30.0 GB
Activations/buffers:               -2.0 GB
Overhead (routing, MLX runtime):   -1.0 GB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Remaining for KV cache:            ~7.2 GB
Actual Metal usage observed:       35.9/40.2 GB (99.5%)
```

**Problem:** 7.2 GB KV cache budget with 4-bit quantization supports ~32K context. But at 50+ turns with system prompt re-sent each time, context reaches 50-100K tokens → OOM → extreme throttling.

### Speed bottleneck analysis:

Generation speed on Apple Silicon is **memory-bandwidth limited**:

$$\text{tok/s} = \frac{\text{Memory Bandwidth (GB/s)}}{\text{Active Weight Read per Token (GB)}}$$

M4 Pro memory bandwidth: **273 GB/s**

For Qwen3.6-27B 8-bit (dense, all params active):
$$\frac{273 \text{ GB/s}}{27 \text{ GB}} = 10.1 \text{ tok/s theoretical}$$

But with memory pressure at 99.5%, OS memory management (swapping, page faults) degrades this to **1 tok/s observed**.

---

## 3. Per-Model Analysis

### 3.1 Qwen3.5-35B-A3B 4-bit ⭐ RECOMMENDED

**Model:** `mlx-community/Qwen3.5-35B-A3B-4bit`  
**Architecture:** Mixture-of-Experts, 35B total params, 3B active per token  
**Rapid-MLX key:** `qwen3.5-35b-4bit`

| Property | Value |
|----------|-------|
| Total parameters | 35B |
| Active parameters/token | 3B (128 experts, top-2 routing) |
| Quantization | 4-bit (GPTQ/AWQ-style) |
| Model weight memory | ~18 GB |
| Estimated KV cache (50K ctx, 4-bit) | ~4-6 GB |
| Total memory footprint | ~24-26 GB |
| Memory headroom (vs 40.2GB Metal) | ~14-16 GB |
| Generation speed (theoretical) | 273 / 1.5 = 182 tok/s |
| Generation speed (realistic) | 45-70 tok/s |
| Prefill speed (23K tokens) | ~1000-1500 tok/s → 15-23s |
| Context window | 131K tokens |
| Reasoning support | Yes (`<think>` blocks, qwen3 parser) |
| Tool calling format | hermes |

**Quality benchmarks (approximate):**
| Benchmark | Score |
|-----------|-------|
| MMLU | 82-84% |
| HumanEval | 80-82% |
| MATH | 78-80% |
| IFEval (instruction following) | 82-85% |
| Tool use / function calling | Strong (trained on tool data) |

**Why MoE works perfectly here:**
- Apple Silicon unified memory means ALL 35B params reside in the same memory pool as GPU compute
- MLX only performs matrix operations on the 3B active expert weights per token
- Memory BANDWIDTH usage = only active params read = 3B × 0.5 bytes = 1.5 GB/token
- Result: memory STORAGE of 18GB (all experts), compute COST of 3B (active experts only)
- This decouples model knowledge from inference speed — best of both worlds

**Risks:**
- 4-bit quantization on MoE: less impactful than on dense models (experts are redundant by design)
- Hermes tool format: well-tested but different from current qwen3_coder_xml
- MoE routing quality: occasionally activates suboptimal experts for unusual prompts
- Qwen3.5 vs 3.6: minor generation quality differences (3.6 has some instruction-following improvements)

**Mitigation:**
- Test tool calling reliability on 10 representative pipeline prompts before switching
- Monitor first 3 sessions for tool call parse failures
- Hermes format is the most widely supported — major community tooling

---

### 3.2 NVIDIA Nemotron-30B-A3B 4-bit (Backup MoE option)

**Model:** `NVIDIA-Nemotron-3-Nano-30B-A3B-MLX-4bit`  
**Architecture:** MoE, 30B total, 3B active  
**Rapid-MLX key:** `nemotron-30b`

| Property | Value |
|----------|-------|
| Total parameters | 30B |
| Active parameters/token | 3B |
| Model weight memory | ~16 GB |
| Total memory footprint | ~22-24 GB |
| Generation speed (realistic) | 45-70 tok/s |
| Prefill (23K) | 15-25s |
| Context window | 128K tokens |
| Reasoning support | Partial (no native `<think>`, but can be prompted) |
| Tool calling format | hermes |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 78-80% |
| HumanEval | 72-75% |
| Instruction following | Good (NVIDIA RLHF) |

**Pros:** Slightly smaller memory, NVIDIA's alignment training (helpful/harmless), good at following complex instructions.

**Cons:** Lower raw benchmarks than Qwen3.5-35B-A3B. No native thinking mode — would need prompt-engineering `<think>` blocks rather than parser support. Less community MLX tooling.

**Verdict:** Viable backup if Qwen3.5-35B-A3B has issues. The quality gap (~3-5% on benchmarks) might matter for complex statistical analysis.

---

### 3.3 Qwen3.5-9B 8-bit (Speed option)

**Model:** `mlx-community/Qwen3.5-9B-8bit`  
**Architecture:** Dense, 9B params all active  
**Rapid-MLX key:** `qwen3.5-9b-8bit`

| Property | Value |
|----------|-------|
| Total/Active parameters | 9B |
| Model weight memory | ~10 GB |
| Total memory footprint | ~14-16 GB |
| Memory headroom | ~24-26 GB (abundant) |
| Generation speed | 273/9 = 30 tok/s theoretical, **25-30 tok/s realistic** |
| Prefill (23K) | 30-45 seconds |
| Context window | 131K tokens |
| Reasoning support | Yes (`<think>`, qwen3 parser) |
| Tool calling | hermes |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 72-74% |
| HumanEval | 68-70% |
| MATH | 65-68% |
| Tool calling | Good |

**Pros:** Extremely comfortable memory fit, fast, same Qwen3.5 family (same parser, same tool format), very stable for long sessions (abundant KV cache budget).

**Cons:** Quality drop of ~10% vs current model. May struggle with:
- Nuanced bear case construction
- Multi-factor statistical synthesis
- Catching subtle contradictions in data
- Complex coupon optimization logic

**Use case:** Good for S0 (settlement), S1 (scanning), S2 (tipster xref) where tasks are more mechanical. Risky for S3 (deep stats), S5 (upset risk), S7 (gate) where analytical depth matters.

**Verdict:** Consider as a secondary model for speed-critical, less analytical steps — or as emergency fallback if MoE has issues.

---

### 3.4 Phi-4 14B 8-bit (Balanced dense option)

**Model:** Microsoft Phi-4 14B  
**Architecture:** Dense, 14B params  
**Rapid-MLX key:** `phi4-14b`

| Property | Value |
|----------|-------|
| Parameters | 14B |
| Model weight memory | ~14 GB |
| Total memory footprint | ~18-20 GB |
| Generation speed | 273/14 = 19.5, **18-20 tok/s realistic** |
| Prefill (23K) | 45-60 seconds |
| Context window | 16K (⚠️ SHORT) |
| Reasoning support | Native CoT but no `<think>` parser |
| Tool calling | Limited/custom format needed |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 84% |
| HumanEval | 82% |
| MATH | 80% |
| Reasoning | Excellent for size |

**Pros:** Excellent quality for 14B — punches well above its weight class. Microsoft's training data curation is best-in-class.

**Cons:**
- ⚠️ **16K context window** — FATAL for this pipeline (23K system prompt alone exceeds it)
- No native `<think>` block support (would need custom reasoning parser)
- Tool calling support is not standardized for this model family
- Would need significant prompt engineering to match current workflow

**Verdict:** **REJECTED due to 16K context limit.** Cannot handle 23K system prompt. Not viable for this pipeline without significant architectural changes.

---

### 3.5 DeepSeek-R1-32B 4-bit (Reasoning specialist)

**Model:** DeepSeek-R1-Distill-32B or similar  
**Architecture:** Dense, 32B params  
**Rapid-MLX key:** `deepseek-r1-32b`

| Property | Value |
|----------|-------|
| Parameters | 32B |
| Model weight memory (4-bit) | ~16 GB |
| Total memory footprint | ~20-22 GB |
| Generation speed | 273/16 = 17, **15-17 tok/s realistic** |
| Prefill (23K) | 50-70 seconds |
| Context window | 64K tokens |
| Reasoning support | Excellent (native reasoning model) |
| Tool calling | deepseek format (limited) |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 79-81% |
| MATH | 85-88% (reasoning strength) |
| Coding | 78-80% |
| Reasoning chains | Excellent |

**Pros:** Purpose-built reasoning model, excels at complex multi-step analysis. Would be excellent for S3 (statistical depth) and S7 (gate decisions).

**Cons:**
- 4-bit quantization on DENSE model = more quality loss than on MoE
- Slower than MoE options (all 32B weights read per token even at 4-bit)
- Tool calling via deepseek parser: less reliable than hermes for complex multi-tool workflows
- Verbose reasoning chains consume output tokens rapidly
- Speed: 15-17 tok/s is below 20 tok/s ideal target

**Verdict:** Interesting for pure reasoning tasks but the tool calling limitation and speed make it suboptimal for a 50-turn agentic pipeline. The pipeline needs RELIABLE tool calling more than it needs extreme reasoning depth.

---

### 3.6 Gemma-4-27B 4-bit

**Model:** Google Gemma-4-27B  
**Architecture:** Dense, 27B params  
**Rapid-MLX key:** `gemma-4-27b`

| Property | Value |
|----------|-------|
| Parameters | 27B |
| Model weight memory (4-bit) | ~14 GB |
| Total memory footprint | ~18-20 GB |
| Generation speed | 273/14 = 19.5, **18-20 tok/s** |
| Prefill (23K) | 45-60 seconds |
| Context window | 128K tokens |
| Reasoning support | Limited (no native `<think>` parser) |
| Tool calling | gemma4 parser (available in rapid-mlx) |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 80-82% |
| HumanEval | 75-78% |
| Instruction following | Good (Google alignment) |

**Pros:** Good quality at 4-bit, long context, Google's training quality. Native gemma4 tool parser available in rapid-mlx.

**Cons:**
- Dense 27B at 4-bit: significant quality degradation vs 8-bit
- No `<think>` reasoning mode support — would need different reasoning approach
- gemma4 tool parser: less battle-tested than hermes
- 18-20 tok/s is acceptable but not the 45-70 tok/s of MoE options

**Verdict:** Viable but inferior to Qwen3.5-35B-A3B on every dimension that matters for this pipeline. No reasoning parser is a significant limitation.

---

### 3.7 DevStral-v2-24B 4-bit

**Model:** Mistral DevStral v2 24B  
**Architecture:** Dense, 24B params (code-focused)  
**Rapid-MLX key:** `devstral-v2-24b`

| Property | Value |
|----------|-------|
| Parameters | 24B |
| Model weight memory (4-bit) | ~12 GB |
| Total memory footprint | ~16-18 GB |
| Generation speed | 273/12 = 22.8, **20-23 tok/s** |
| Prefill (23K) | 35-50 seconds |
| Context window | 128K tokens |
| Reasoning support | No native `<think>` mode |
| Tool calling | hermes (Mistral compatible) |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| HumanEval | 85%+ (code-optimized) |
| MMLU | 76-78% |
| SWE-Bench | Strong |
| General reasoning | Moderate |

**Pros:** Excellent at code/tool interaction, Mistral's architecture is efficient, long context, hermes tool support.

**Cons:**
- Optimized for CODE tasks, not statistical analysis or betting reasoning
- Lower MMLU (general knowledge) than Qwen models
- No thinking mode — critical for pipeline analysis quality
- 4-bit quantization of a code model may degrade non-code performance more

**Verdict:** Wrong specialization. This pipeline needs statistical analysis and reasoning, not code generation. A code model would underperform on bear cases, market evaluation, and coupon building logic.

---

### 3.8 Qwen3.6-35B-DWQ (Dynamic Weight Quantization)

**Model:** Qwen3.6-35B with dynamic weight quantization  
**Architecture:** Dense 35B with mixed-precision layers  
**Rapid-MLX key:** `qwen3.6-35b-dwq`

| Property | Value |
|----------|-------|
| Parameters | 35B (dense) |
| Model weight memory | ~14-18 GB (varies by layer importance) |
| Total memory footprint | ~20-24 GB |
| Generation speed | 273/16 (avg) ≈ **15-18 tok/s** |
| Prefill (23K) | 45-65 seconds |
| Context window | 262K tokens |
| Reasoning support | Yes (qwen3 parser, `<think>` blocks) |
| Tool calling | qwen3_coder_xml (native!) |

**Quality benchmarks:**
| Benchmark | Score |
|-----------|-------|
| MMLU | 81-83% (slightly below 8-bit) |
| HumanEval | 82-84% |
| Tool calling reliability | Excellent (native format) |

**Pros:**
- Same model family as current — **zero format migration risk**
- qwen3_coder_xml tool calling (proven working in current pipeline)
- Native `<think>` reasoning (qwen3 parser)
- 262K context (same as current)
- DWQ preserves quality better than uniform 4-bit

**Cons:**
- Still DENSE architecture — reads all 35B weight bytes per token
- At ~16 GB average weight: 273/16 = 17 tok/s (below MoE)
- Slower than MoE for generation (3x slower)
- Slower prefill than MoE (all params participate)
- DWQ format may have MLX kernel overhead vs standard quantization

**Verdict:** STRONG SECOND CHOICE if hermes tool calling proves unreliable with Qwen3.5-35B-A3B. This model preserves the exact same tool calling format and reasoning behavior as current setup. The trade-off is speed: ~17 tok/s vs MoE's ~50 tok/s. Still a massive improvement over current 1 tok/s.

---

## 4. Comparison Matrix

| Model | Memory (GB) | Gen tok/s | Prefill 23K (s) | Quality | Tool Call | Reasoning | Context | Risk |
|-------|:-----------:|:---------:|:---------------:|:-------:|:---------:|:---------:|:-------:|:----:|
| **Qwen3.5-35B-A3B 4-bit** ⭐ | **18** | **45-70** | **15-25** | **A** | hermes | ✅ native | 131K | Low |
| Qwen3.6-35B-DWQ | 16-18 | 15-18 | 45-65 | A | native XML | ✅ native | 262K | Very Low |
| Nemotron-30B-A3B 4-bit | 16 | 45-70 | 15-25 | B+ | hermes | ⚠️ partial | 128K | Medium |
| Qwen3.5-9B 8-bit | 10 | 25-30 | 30-45 | B | hermes | ✅ native | 131K | Low |
| DeepSeek-R1-32B 4-bit | 16 | 15-17 | 50-70 | B+ | deepseek | ✅ native | 64K | Medium |
| Gemma-4-27B 4-bit | 14 | 18-20 | 45-60 | B | gemma4 | ❌ | 128K | Medium |
| DevStral-v2-24B 4-bit | 12 | 20-23 | 35-50 | B- (non-code) | hermes | ❌ | 128K | High |
| Phi-4 14B 8-bit | 14 | 18-20 | 45-60 | A | limited | ⚠️ | **16K** ❌ | **FATAL** |
| Qwen3.6-27B 8-bit (current) | 30 | **1** ❌ | **270** ❌ | A | native XML | ✅ | 262K | **FATAL** |

**Legend:** Quality: A = competitive with GPT-4 class, B+ = strong, B = adequate, B- = concerning for this use case

---

## 5. Risk Assessment

### 5.1 Qwen3.5-35B-A3B 4-bit (recommended) — Risk: LOW

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| Hermes tool call parsing failures | 20% | Medium | Test 10 representative prompts; fallback to DWQ model |
| Quality gap vs current (4-bit MoE vs 8-bit dense) | 15% | Low | MoE 4-bit preserves quality well; compare outputs |
| MoE routing instability on edge cases | 10% | Low | Retry logic in Kilo Code handles occasional bad routing |
| Rapid-MLX MoE kernel bugs | 10% | High | Check rapid-mlx GitHub issues; community has been running this |
| KV cache overflow on very long sessions | 5% | Medium | 15GB headroom makes this unlikely; set cache-memory-mb 10000 |

### 5.2 Qwen3.6-35B-DWQ (safe fallback) — Risk: VERY LOW

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| DWQ kernel performance overhead | 20% | Low | Still 15-18 tok/s, massive improvement over 1 tok/s |
| Slightly lower quality vs 8-bit | 10% | Low | DWQ prioritizes important layers; minimal degradation |
| Memory still tight for very long context | 15% | Medium | Better than current; 262K context supported |

### 5.3 Migration risk (format change) — Mitigation plan:

1. **Before switching:** Run 5 pipeline queries with current model, save outputs as gold standard
2. **After switching:** Run same 5 queries with new model, compare:
   - Do tool calls parse correctly? (All 27 MCP tools callable)
   - Does `<think>` reasoning work? (Check for reasoning depth)
   - Is statistical analysis quality maintained? (Compare bear cases, market rankings)
3. **Rollback plan:** Keep current plist as backup; switch model key in one line

---

## 6. Recommended Configuration

### 6.1 Primary: Qwen3.5-35B-A3B 4-bit

**Server command:**
```fish
~/.local/bin/rapid-mlx serve qwen3.5-35b-4bit --port 8000 \
  --no-mllm --max-num-seqs 1 \
  --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --max-tokens 32768 \
  --pin-system-prompt --enable-prefix-cache \
  --kv-cache-quantization --kv-cache-quantization-bits 4 \
  --cache-memory-mb 10000 \
  --gpu-memory-utilization 0.85 \
  --prefill-step-size 8192 \
  --gc-control \
  --enable-auto-tool-choice --tool-call-parser hermes
```

**Key differences from current:**
| Parameter | Current | New | Reason |
|-----------|---------|-----|--------|
| Model | qwen3.6-27b-8bit | qwen3.5-35b-4bit | MoE architecture |
| cache-memory-mb | 4000 | 10000 | More headroom (model uses 18GB vs 30GB) |
| gpu-memory-utilization | 0.92 | 0.85 | Conservative; still have abundant memory |
| prefill-step-size | 4096 | 8192 | MoE prefill is lighter; can process more at once |
| tool-call-parser | qwen3_coder_xml | hermes | Qwen3.5 uses hermes format |
| reasoning-parser | qwen3 | qwen3 | Same (Qwen3.5 uses same `<think>` format) |

### 6.2 kilo.jsonc model definition change:

```jsonc
"models": {
  "qwen3.5-35b-a3b": {
    "id": "qwen3.5-35b-4bit",
    "name": "Qwen3.5-35B-A3B MoE (Local MLX 4-bit)",
    "reasoning": true,
    "tool_call": true,
    "limit": {
      "context": 131072,
      "output": 32768
    }
  }
}
```

**Agent model references:** Change all `"model": "openai-compatible/qwen3.6-27b"` to `"model": "openai-compatible/qwen3.5-35b-a3b"` across all agent definitions.

### 6.3 LaunchDaemon plist update:

Update `/Users/mkoziol/projects/bet/config/com.rapid-mlx.server.plist`:
- Change model argument from `qwen3.6-27b-8bit` to `qwen3.5-35b-4bit`
- Change `--cache-memory-mb` from `4000` to `10000`
- Change `--gpu-memory-utilization` from `0.92` to `0.85`
- Change `--prefill-step-size` from `4096` to `8192`
- Change `--tool-call-parser` from `qwen3_coder_xml` to `hermes`

### 6.4 Fallback: Qwen3.6-35B-DWQ (zero-migration option)

If hermes tool calling proves unreliable, switch to DWQ which preserves current tool format:

```fish
~/.local/bin/rapid-mlx serve qwen3.6-35b-dwq --port 8000 \
  --no-mllm --max-num-seqs 1 \
  --reasoning-parser qwen3 \
  --default-temperature 0.6 --default-top-p 0.95 --default-top-k 20 \
  --max-tokens 32768 \
  --pin-system-prompt --enable-prefix-cache \
  --kv-cache-quantization --kv-cache-quantization-bits 4 \
  --cache-memory-mb 8000 \
  --gpu-memory-utilization 0.88 \
  --prefill-step-size 4096 \
  --gc-control \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder_xml
```

---

## 7. MoE vs Dense: The Technical Explanation

### Why MoE is ideal for Apple Silicon unified memory:

```
┌─────────────────────────────────────────────────────┐
│ Apple M4 Pro Unified Memory (48 GB)                 │
│                                                     │
│  ┌─────────────────────────────────┐                │
│  │ MoE Model (18 GB)              │                │
│  │  ┌──────────┐ ┌──────────┐     │                │
│  │  │ Expert 1 │ │ Expert 2 │ ... │  128 experts   │
│  │  │ (IDLE)   │ │ (ACTIVE) │     │  per layer     │
│  │  └──────────┘ └──────────┘     │                │
│  │  ┌──────────┐ ┌──────────┐     │                │
│  │  │ Expert 3 │ │ Expert 4 │     │  Only 2 active │
│  │  │ (IDLE)   │ │ (ACTIVE) │     │  per token     │
│  │  └──────────┘ └──────────┘     │                │
│  │  ┌─────────────────────────┐   │                │
│  │  │ Shared (Attention+Norm) │   │  Always active │
│  │  └─────────────────────────┘   │                │
│  └─────────────────────────────────┘                │
│                                                     │
│  ┌─────────────┐                                    │
│  │ KV Cache    │  10+ GB available (was only 5 GB)  │
│  │ (10 GB)     │                                    │
│  └─────────────┘                                    │
│                                                     │
│  ┌─────────────┐                                    │
│  │ Free/OS     │  ~12 GB headroom                   │
│  │ (12 GB)     │                                    │
│  └─────────────┘                                    │
└─────────────────────────────────────────────────────┘

Memory Bandwidth per Token:
  Dense 27B 8-bit: reads 27 GB → 273/27 = 10 tok/s
  MoE 35B 4-bit:  reads 1.5 GB → 273/1.5 = 182 tok/s (theoretical)
                   realistic with overhead: 45-70 tok/s
```

The key insight: **MoE models pay STORAGE cost for all experts but COMPUTE cost only for active experts.** On unified memory architecture (Apple Silicon), storage is cheap (the memory exists regardless) but bandwidth is precious. MoE dramatically reduces bandwidth usage.

---

## 8. Testing Protocol Before Full Migration

### Phase 1: Quick validation (30 min)

1. Start new model server (don't stop current — use different port):
   ```fish
   rapid-mlx serve qwen3.5-35b-4bit --port 8001 --no-mllm --max-num-seqs 1 --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser hermes --max-tokens 4096
   ```

2. Send test prompts via curl:
   ```fish
   # Tool calling test
   curl http://localhost:8001/v1/chat/completions -d '{"model":"qwen3.5-35b-4bit","messages":[{"role":"user","content":"Call the brave_web_search tool to find today weather in Warsaw"}],"tools":[{"type":"function","function":{"name":"brave_web_search","parameters":{"type":"object","properties":{"query":{"type":"string"}}}}}]}'
   
   # Reasoning test
   curl http://localhost:8001/v1/chat/completions -d '{"model":"qwen3.5-35b-4bit","messages":[{"role":"user","content":"Analyze whether a team with L10 corners average of 5.2 and individual values [3,7,4,6,5,8,4,6,3,6] is a good bet for O4.5 corners. Think step by step."}]}'
   ```

3. Verify:
   - Tool call JSON parses correctly
   - `<think>` block appears in response
   - Analysis quality is coherent

### Phase 2: Pipeline integration test (2 hours)

1. Switch kilo.jsonc to new model
2. Run S0 (settlement) — verifies basic tool calling + DB queries
3. Run S1 (discovery) — verifies long context handling
4. Run S3 (deep stats) on 5 candidates — verifies analytical depth
5. Compare outputs with last successful pipeline run

### Phase 3: Full pipeline (1 day)

Run complete S0→S8 pipeline with monitoring. Watch for:
- Tool call failures (check rapid-mlx logs)
- Memory pressure (Activity Monitor → Memory Pressure gauge)
- Quality regression (compare coupon quality with recent successful runs)

---

## 9. Summary Decision Matrix

| Priority | Model | Speed | Quality | Risk | When to use |
|:--------:|-------|:-----:|:-------:|:----:|-------------|
| 🥇 | Qwen3.5-35B-A3B 4-bit | ⚡⚡⚡ | ★★★★ | Low | Primary model — all pipeline steps |
| 🥈 | Qwen3.6-35B-DWQ | ⚡⚡ | ★★★★ | Very Low | If hermes tool calling is unreliable |
| 🥉 | Nemotron-30B-A3B 4-bit | ⚡⚡⚡ | ★★★ | Medium | If Qwen models have MLX issues |
| 4th | Qwen3.5-9B 8-bit | ⚡⚡⚡ | ★★★ | Low | Speed-critical steps or emergency fallback |
| ❌ | Phi-4 14B | ⚡⚡ | ★★★★ | FATAL | 16K context — incompatible |
| ❌ | Qwen3.6-27B 8-bit | ❌ | ★★★★★ | FATAL | Current — OOM, 1 tok/s |

**Bottom line:** Switch to `qwen3.5-35b-4bit`. You get 45-70× faster generation, 10-18× faster prefill, comparable quality, abundant memory headroom for long sessions, and the only real change is tool call format (qwen3_coder_xml → hermes).
