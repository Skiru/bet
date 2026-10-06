# `sofa` — dokumentacja jedynego obowiązującego pipeline'u

Statystyki: **Sofascore**. Ceny: **Superbet**. Produkt: **jeden kupon
`runs/sofa/<data>/KUPON_<data>.pdf`** dla wszystkich sportów — piłka i
tenis, a od 2026-10-05 08:30Z także hokej, koszykówka, siatkówka i CS2.
Pewność jest wyłącznie ze statystyk (od 2026-10-05 07:15Z), cena jest tylko
warunkiem zakładu (pewność × kurs ≥ 0,90, marża ≤ 15%). Jedynym artefaktem
kuponu jest `11_coupon.json`; PDF zapisuje obok `12_printed.json`.

**Nie ma etapu `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` ani
`TIPSTERS`.** To słownik wycofanego pipeline'u `simple`, usuniętego z repozytorium
2026-10-05 (jest w historii gita). Oba pipeline'y nie dzielą ani linii kodu,
ani jednej nazwy etapu.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ───────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ──────────────────┤
                                     COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ produkt
   w przebudowie, przed CONFIDENCE:  FIXTURE_CHECK
              osobno i świadomie:  SETTLE → FIT
```

## Co czytać

| chcesz | czytaj |
|---|---|
| przeprowadzić dzień | [`RUNBOOK.md`](RUNBOOK.md) — kolejność, czas, decyzje, „co gdy…" |
| zrozumieć pipeline do dna | [`PIPELINE.md`](PIPELINE.md) — każdy etap, pole, bramka i stała |
| pracować agentami | [`AGENTIC_FLOW.md`](AGENTIC_FLOW.md) — komendy, agenci, kontrakty, przekazania |
| zweryfikować gotowy kupon | [`VERIFY_PROTOCOL.md`](VERIFY_PROTOCOL.md) — protokół adwersaryjny |
| ruszyć stałą lub bazę ligową | [`CONFIG.md`](CONFIG.md) — pliki konfiguracyjne i pętla fitowania |
| wiedzieć, co odpowiada API | [`REFERENCE.md`](REFERENCE.md) — Sofascore, i dlaczego bez mostu 403 |

## Zawartość katalogu

| ścieżka | co to |
|---|---|
| `RUNBOOK.md`, `PIPELINE.md`, `AGENTIC_FLOW.md`, `VERIFY_PROTOCOL.md`, `CONFIG.md`, `REFERENCE.md` | dokumentacja obowiązująca |
| `MODELE_HOKEJ_KOSZ_SIATKA.md` | model wyników hokeja, koszykówki i siatkówki (i silnik CS2): pomiar, a od 2026-10-05 przez krzywą kalibracji źródło pewności nóg tych sportów |
| [`history/`](history/) | datowane raporty przebiegów, znaleziska, plany i audyty. **Zapis historyczny**: opisuje stan z dnia napisania i bywa nieaktualny |
| `evidence/` | surowe payloady API — **dowody i jednocześnie fikstury testów** (`tests/sofa/` czyta z tych ścieżek) |
| `scripts/` | jednorazowe skrypty badawcze z audytu API; nie są częścią pipeline'u |

## Język

Dokumentacja operacyjna i pipeline'owa jest **po polsku** (tak pisze operator).
Konfiguracja agentowa w `.claude/` i kod są **po angielsku**. To świadoma
granica, nie bałagan: `.claude/*.md` to kontrakty czytane razem z kodem.

## Zasady, które kosztowały pieniądze

1. **`06_coupon.json` nie jest kuponem. Kuponem jest PDF** (z
   `11_coupon.json`). Single VALUE: −20,4% (2026-09-20), PDF tego samego
   dnia: +8,2%.
2. **Selekcja po cenie jest antyselektywna wobec błędu w `p`** — nadwyżka
   rośnie, gdy `p` jest zawyżone (selektor `06_coupon.json`). Nadwyżka >
   +0,40 jest podejrzana z definicji.
3. **`PARTIAL` to normalny kształt zdrowego przebiegu.** Zatrzymuje tylko
   `FAILED`.
4. **`NOT_FITTED` to wynik, nie luka.** Nigdy nie podstawiaj wartości
   domyślnej i nigdy nie usuwaj notki `UNFITTED_CONSTANTS`.
5. **Nigdy nie fituj stałych w środku dnia.**
