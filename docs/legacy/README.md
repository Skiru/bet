# `docs/legacy` — dokumentacja wycofanych pipeline'ów

**Nic w tym katalogu nie opisuje kodu, który dziś jedzie.** Zapis historyczny:
trzymany, bo artefakty, wiersze w bazie i decyzje, które opisuje, nadal leżą
na dysku i bywają czytane.

Obowiązujący pipeline to **`sofa`** — [`../sofa/`](../sofa/).

## Co tu jest

| ścieżka | pipeline / temat | status |
|---|---|---|
| `SIMPLE_STATS_RUNBOOK.md`, `MORNING.md`, `PLAN_BOGATE_STATYSTYKI.md`, `PLAN_NAPRAWY_SIMPLE_PIPELINE_2026-09-10.md`, `PIPELINE_SIMPLIFICATION_PLAN.md` | `simple`: DISCOVER → SUPERBET → ENRICH → MARKET_CONTEXT → TIPSTERS → ANALYZE | wycofane |
| `PLAN_ESPN_BZZOIRO_COOPERATION.md`, `PLAN_FOOTBALL_BZZOIRO_ONLY_2026-09-04.md`, `espn/` | dostawcy statystyk sprzed Sofascore (bzzoiro, ESPN, highlightly) | wycofane jako źródło próbek |
| `AUDYT_TIPSTERZY_2026-09-01.md`, `pipeline/` (kontrakty tipsterskie, ZawodTyper, runbooki sesji) | etap TIPSTERS | **`sofa` nie przyjmuje cudzej opinii w ogóle** |
| `PLAN_RYNKI_SUPERBET.md`, `SUPERBET_BET_BUILDER_METHOD_v3.md` | metodyka rynków i Bet Builderów sprzed `sofa` | zastąpione przez `src/bet/sofa/confidence.py` i zmierzony narzut korelacyjny |
| `PLAN_MLB_2026-09-14.md`, `PLAN_LOL_ESPORT_2026-09-14.md`, `multisport_enrichment/` | sporty poza piłką i tenisem | **`sofa` zna dwa sporty**: `SPORT_IDS = {"football": 5, "tennis": 2}` |
| `BET_V5_*.md`, `V5_*.md`, `prompts/`, `odds_production_review.md` | stos S0–S10 i jego certyfikacja | wycofane; kod w `legacy/` nawet się nie importuje |
| `AUDYT_KUPONU_2026-09-02.md`, `AUDYT_KUPONU_2026-09-09.md`, `PLAN_EDGE_INTEGRITY_2026-09-03.md`, `PLAN_SETTLEMENT_TRACE_2026-09-07.md` | audyty dni `simple` | historia; liczby dotyczą `p_low`, nie `p_bar` |

## Czego stąd nie brać

- **Nazw etapów.** `sofa` nie ma DISCOVER, ENRICH, ANALYZE, MARKET_CONTEXT ani
  TIPSTERS, i nie istnieje mapowanie między słownikami.
- **Wielkości.** `simple` rankował po `p_low` i tierach
  `CALL`/`LEAN`/`WEAK`/`DROP`, kluczem meczu był 64-znakowy hash `event_id`.
  `sofa` rankuje po `p_central` → `p_bar`, a kluczem jest całkowite
  `sofascore_event_id`.
- **Nazw artefaktów.** `<date>_event_dossiers_stats_sheet.json`,
  `<date>_superbet_comparison.json`, `<date>_kupony.md` nie istnieją w `sofa`.

Agentowa konfiguracja tamtego pipeline'u jest zaparkowana osobno:
`.claude/legacy/` (Claude Code) i `.kilo/legacy/` (Kilocode). Też nie jest
ładowana.
