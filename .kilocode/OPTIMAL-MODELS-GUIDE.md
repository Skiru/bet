# Kilo Code — Optymalny Dobór Modeli (Maj 2026)

> **TL;DR:** Laguna M.1 (FREE) jest LEPSZA niż Gemini 2.5 Flash i jest #1 najczęściej używanym modelem w Kilo Code. Cały pipeline może działać za $0.

---

## 🏆 Ranking Modeli — Real-World Usage (kilo.ai/leaderboard, 27.05.2026)

### Code Mode (implementacja, skrypty)
| # | Model | Usage% | Cena/1M | Free? |
|---|-------|--------|---------|-------|
| 1 | **Poolside: Laguna M.1** | 24.3% | $0.00 | ✅ FREE |
| 2 | StepFun: Step 3.5 Flash | 22.1% | $0.10 | ❌ |
| 3 | xAI: Grok Code Fast 1 | 16.4% | $0.20 | ✅ `:optimized:free` |
| 4 | **NVIDIA: Nemotron 3 Super 120B** | 11.8% | $0.00 | ✅ FREE |
| 5 | Owl Alpha | 4.8% | ? | ? |
| 6 | Poolside: Laguna XS.2 | 3.1% | ? | ? |
| 7 | Qwen3.6 Plus | 2.7% | $0.33 | ❌ |
| 8 | Claude Sonnet 4.6 | 2.5% | $3.00 | ❌ |

### Plan Mode (planowanie, architektura)
| # | Model | Usage% | Cena/1M | Free? |
|---|-------|--------|---------|-------|
| 1 | **Laguna M.1** | 19.9% | $0.00 | ✅ FREE |
| 2 | Step 3.5 Flash | 15.8% | $0.10 | ❌ |
| 3 | Grok Code Fast 1 | 13.9% | $0.20 | ✅ free variant |
| 4 | **Nemotron 3 Super** | 10.4% | $0.00 | ✅ FREE |
| 5 | Claude Opus 4.7 | 9.0% | $5.00 | ❌ |

### Ask Mode (Q&A, analiza)
| # | Model | Usage% | Cena/1M | Free? |
|---|-------|--------|---------|-------|
| 1 | **Grok Code Fast 1** | 20.8% | $0.00 | ✅ `:optimized:free` |
| 2 | Step 3.5 Flash | 20.3% | $0.10 | ❌ |
| 3 | **Laguna M.1** | 18.5% | $0.00 | ✅ FREE |
| 4 | **Nemotron 3 Super** | 9.9% | $0.00 | ✅ FREE |

### Debug Mode
| # | Model | Usage% | Cena/1M | Free? |
|---|-------|--------|---------|-------|
| 1 | **Laguna M.1** | 24.5% | $0.00 | ✅ FREE |
| 2 | Step 3.5 Flash | 20.5% | $0.10 | ❌ |
| 3 | **Nemotron 3 Super** | 10.7% | $0.00 | ✅ FREE |

---

## 📊 Porównanie: Stary Setup vs Optymalny

| Aspekt | Stary (Gemini 2.5 Flash BYOK) | Nowy (Kilo Gateway FREE) |
|--------|-------------------------------|--------------------------|
| Cena | $0 (free tier) | $0 (free models) |
| Rate limit | 1,500 RPD / 15 RPM | Brak dziennego limitu* |
| API key setup | Wymagany (Google AI Studio) | NIE wymagany (login Kilo) |
| Context window | 1M tokens | 128K (Laguna) / 120B (Nemotron) |
| Coding quality | Dobra (24.6 coding index) | Lepsza (Laguna = #1 w usage) |
| SWE-bench | ~? | Laguna = enterprise-grade |
| Thinking/reasoning | Tak (budgetTokens) | Tak (Trinity Large Thinking) |
| Multi-model | Jeden model | Różne modele per tryb |

*Per-minute throttling może wystąpić; przełącz na inny free model.

---

## 🆓 Dostępne DARMOWE Modele (Kilo Gateway, maj 2026)

| Model ID | Opis | Zastosowanie |
|----------|------|-------------|
| `poolside/laguna-m.1:free` | Flagship coding agent — **#1 w Kilo** | Orchestrator, Code, Plan |
| `x-ai/grok-code-fast-1:optimized:free` | Optimized z test-time compute | Ask, szybkie taski |
| `nvidia/nemotron-3-super-120b-a12b:free` | 120B MoE, 12B active | Review, Debug, fallback |
| `inclusionai/ling-2-6-1t:free` | 1T params — ogromny model | Ciężka analiza |
| `inclusionai/ring-2-6-1t:free` | 1T thinking model | Reasoning, gate decisions |
| `tencent/hy3-preview:free` | MoE, configurable reasoning | Backup |
| `google/gemma-4-26b-a4b-it:free` | Google MoE, 3.8B active | Small tasks, titles |
| `inclusionai/ling-2-6-flash:free` | 104B/7.4B active, fast | Background, summaries |
| `arcee-ai/trinity-large-thinking:free` | Reasoning model | Complex decisions |
| `kilo-auto/free` | Auto-routing do najlepszego | Fallback — zero config |

---

## 🎯 REKOMENDOWANA KONFIGURACJA — Pipeline Betting

### Strategia: Multi-Model per Agent

| Agent/Mode | Rekomendowany Model | Dlaczego |
|------------|-------------------|----------|
| **bet-orchestrator** | `poolside/laguna-m.1:free` | #1 w Plan+Code, koordynuje pipeline |
| **bet-statistician** | `poolside/laguna-m.1:free` | Ciężka analiza statystyczna |
| **bet-challenger** | `inclusionai/ring-2-6-1t:free` | Thinking model — bear cases, gate |
| **bet-builder** | `poolside/laguna-m.1:free` | Portfolio, formatting, validation |
| **bet-scanner** | `x-ai/grok-code-fast-1:optimized:free` | Szybki scan, szybkie decyzje |
| **bet-settler** | `nvidia/nemotron-3-super-120b-a12b:free` | Settlement, PnL |
| **bet-scout** | `x-ai/grok-code-fast-1:optimized:free` | Tipster analysis |
| **bet-enricher** | `nvidia/nemotron-3-super-120b-a12b:free` | Data quality validation |
| **bet-valuator** | `nvidia/nemotron-3-super-120b-a12b:free` | EV, odds, drift |
| **bet-db-analyst** | `google/gemma-4-26b-a4b-it:free` | Prosty audit, read-only |
| **Small Model** | `inclusionai/ling-2-6-flash:free` | Titles, summaries |
| **Autocomplete** | Codestral (Mistral BYOK) | Najlepszy FIM |

### Strategia Budżetowa ($3-5/mies. = FRONTIER access)

Jeśli chcesz TOP jakość za minimalne pieniądze:

| Agent/Mode | Model | Cena/1M |
|------------|-------|---------|
| Orchestrator + Builder | `stepfun/step-3.5-flash` | $0.10 |
| Statistician + Challenger | `deepseek/deepseek-v4-flash` | $0.13 |
| Reszta | `poolside/laguna-m.1:free` | $0.00 |
| **Szacunkowy koszt dziennie** | ~50-80 calls × ~5K tokens | ~$0.10-0.20 |

### Strategia Premium ($20-50/mies.)

| Agent/Mode | Model | Cena/1M |
|------------|-------|---------|
| Orchestrator | `anthropic/claude-opus-4.7` | $5.00 |
| Challenger (gate) | `anthropic/claude-sonnet-4.6` | $3.00 |
| Reszta | `poolside/laguna-m.1:free` | $0.00 |
| **Szacunkowy koszt** | ~10 calls/day na Claude | ~$1-2/day |

---

## ⚙️ Krok po Kroku — Konfiguracja

### 1. Zaloguj się do Kilo Code

1. Otwórz Kilo Code panel w VS Code
2. Kliknij **Sign In** (lub przejdź do https://app.kilo.ai)
3. Stwórz konto — dostajesz **$20 FREE credits** na start!
4. Te $20 wystarczy na ~2 tygodnie użycia płatnych modeli

### 2. Wybierz modele w Settings → Models

1. Kliknij ⚙️ (gear) w Kilo Code
2. Zakładka **Models**
3. Ustaw:
   - **Default Model:** `poolside/laguna-m.1:free`
   - **Small Model:** `inclusionai/ling-2-6-flash:free`
   - **Subagent Model:** `poolside/laguna-m.1:free`
   - **Autocomplete:** Codestral (domyślne, darmowe z Mistral BYOK)

### 3. Model per Mode (z Settings UI)

W sekcji **Model per Mode**:
- **Code:** `poolside/laguna-m.1:free`
- **Ask:** `x-ai/grok-code-fast-1:optimized:free`
- **Debug:** `poolside/laguna-m.1:free`
- **Plan:** `poolside/laguna-m.1:free`
- **Orchestrator:** `poolside/laguna-m.1:free`
- **Bet-orchestrator:** `poolside/laguna-m.1:free`

### 4. Per-Agent Model w kilo.jsonc

Dodaj `"model"` do każdego agenta w kilo.jsonc:
```jsonc
"bet-orchestrator": {
  "model": "poolside/laguna-m.1:free",
  // ...reszta konfiguracji
}
```

### 5. BYOK (opcjonalne, dla autocomplete)

Darmowe autocomplete z Codestral:
1. Utwórz konto na https://console.mistral.ai/codestral
2. Skopiuj Codestral API key
3. W Kilo → Settings → BYOK → dodaj key typ "codestral"

### 6. VS Code LM API (bonus — używaj Copilota!)

Skoro masz GitHub Copilot:
1. Settings → Providers → VS Code LM API
2. Możesz użyć modeli Copilot (Claude Sonnet 4.6, GPT-5.4) przez Kilo!
3. Dobre jako backup dla krytycznych decyzji (S7 gate)

---

## ⚠️ Ważne Uwagi

### Data Privacy (Auto Free)
> Auto Free (`kilo-auto/free`) może routować do NVIDIA endpoints, które logują prompts.
> Nie używaj do wrażliwych danych. Lepiej wybrać konkretny model.

### Rate Limits
- FREE modele mogą mieć per-minute throttling
- Jeśli 429 error → poczekaj 60s lub przełącz na inny free model
- Laguna M.1 = najpopularniejszy, więc może mieć najwyższy throttle w peak hours
- Strategia: Nemotron jako fallback gdy Laguna jest throttled

### Context Window
- Laguna M.1: 128K context (wystarczy dla ~30 kandydatów w jednym call)
- Nemotron 3 Super: duże context window
- Grok Code Fast 1: 256K context
- Gemini 2.5 Flash (stary): 1M (największe, ale niepotrzebne dla naszego use case)

### Stabilność
- Kilo Gateway free models mogą się zmieniać (nowe pojawiają się, stare mogą zniknąć)
- Laguna M.1 jest tu od dłuższego czasu i jest flagship Poolside — raczej zostanie
- Zawsze trzymaj `kilo-auto/free` jako ultimate fallback

---

## 📈 Porównanie z Gemini 2.5 Flash (stary setup)

| Metryka | Gemini 2.5 Flash | Laguna M.1 |
|---------|-----------------|------------|
| Kilo Coding Index | 24.6 | Brak danych (za nowy) |
| Usage w Kilo (Code) | nie w top-10 | **#1 (24.3%)** |
| Usage w Kilo (Plan) | nie w top-10 | **#1 (19.9%)** |
| SWE-bench | ? | Enterprise-grade |
| Cena | $0.30/1M (via gateway) | **$0.00/1M** |
| Rate limit | 1500 RPD | Per-minute only |
| API Key needed | TAK (Google AI Studio) | NIE (login Kilo) |
| Tool calling | Tak | Tak |
| Reasoning | Tak (thinking) | Tak |

**Wniosek: Laguna M.1 jest LEPSZA i DARMOWA. Gemini 2.5 Flash nie jest nawet w top-10 najczęściej używanych modeli.**

---

## 🔄 Plan Migracji

1. **Zaloguj się do Kilo** → $20 free credits
2. **Ustaw Default Model** → `poolside/laguna-m.1:free`
3. **Ustaw Small Model** → `inclusionai/ling-2-6-flash:free`
4. **Dodaj `model` field** do agentów w kilo.jsonc
5. **Przetestuj pipeline** → `@bet-orchestrator settle and run`
6. **Zachowaj Google AI Studio** jako backup (już skonfigurowane)
7. **$20 credits** → użyj na Claude Opus 4.7 do najtrudniejszych gate decisions

---

## 🏗️ Schema Update (WAŻNE!)

Nowa wersja Kilo Code extension (rebuilt na CLI) używa:
- `bash` zamiast `command` w permissions
- `.kilo/agents/` lub `.kilocode/agents/` dla markdown agent files
- `provider/model-id` format dla modeli (np. `poolside/laguna-m.1:free`)
- Model pinning per agent w kilo.jsonc

Sprawdź czy Twoja wersja rozpoznaje `command` czy `bash`:
- Jeśli "Bet-orchestrator" pojawia się w Settings → Models per Mode — config działa!
- Kilo Code automatycznie migruje stare formaty przy starcie
