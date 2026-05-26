# Post-Mortem: Kupon v1 z 2026-05-26 — Dlaczego był śmieciowy?

> Data: 2026-05-26 | Analiza: po pełnym cyklu pipeline (2× run)
> Werdykt: **FUNDAMENTALNIE WADLIWY** — 5 krytycznych błędów, 0 postawione (przebudowa na v2)

---

## TL;DR

Kupon v1 miał 5 krytycznych defektów wynikających z 3 luk systemowych:
1. Gate checker nie ma **minimalnego progu safety score** → Bologna (safety 0.0) przeszła
2. Gate checker stosuje **próg hit ≥7 na denominator /10** → Waltert (6/8 = 75%) odrzucona jako "słaba"
3. Pipeline nie ma **walidacji kierunku względem kontekstu** → Fürth UNDER przy desperackim ataku

---

## 5 Krytycznych Błędów Kuponu v1

### BUG 1: Matryca rozpoczyna się od meczów, które już trwały

**Objaw:** TOP 4 matrycy to Cerundolo (13:00 UTC), Quinn (13:00), Darderi (13:00), Bublik (11:50) — LIVE w momencie budowy kuponu (13:38 UTC).

**Root cause:** Coupon builder sortuje matrycę po safety score DESC. `_filter_past_events()` filtruje picke z sekcji BET, ale **matryca informacyjna wyświetla WSZYSTKIE approved picks** bez oznaczenia "LIVE/STARTED". Użytkownik widzi je na górze i zakłada, że to bettable.

**Fix potrzebny:**
- Matryca powinna oznaczać kickoff < now jako ❌ STARTED
- Alternatywnie: sortować matrycę po kickoff ASC (najpierw najbliższe mecze)

---

### BUG 2: Fürth Shots UNDER 13.5 — sprzeczność kierunku z kontekstem

**Objaw:** Gate approved Fürth Shots UNDER 13.5 mimo że:
- Fürth przegrała 0-1 w pierwszym meczu relegation playoff
- MUSI atakować u siebie → więcej strzałów, nie mniej
- avg = 13.5 = DOKŁADNIE linia (zero marginesu!)
- l5_avg = 13.8 > linia (ostatnie 5 meczów są OVER!)

**Root cause:**
1. `compute_safety_scores.py` wybrał UNDER bo L10 avg ≤ linii (13.5 ≤ 13.5) — granica kwalifikacyjna bez marginesu
2. Gate checker NIE SPRAWDZA kontekstu sytuacyjnego (awans/spadek, motywacja, leg1 wynik)
3. Brak "motivation override" w `context_checks.py` — SIGNIFICANCE:HIGH flaga nie powoduje rewizji kierunku

**Dane z DB:**
```json
{
  "direction": "UNDER",
  "line": 13.5,
  "team_a_avg": 13.5,
  "l5_avg": 13.8,
  "combined_avg": 13.5,
  "margin": 1.0,
  "h2h_blind": true
}
```

**Fix potrzebny:**
- Gdy `margin ≤ 0.5` AND `l5_avg` jest po DRUGIEJ stronie linii → FLAG jako CONFLICTED
- Context_checks powinien oznaczać relegation/promotion jako DIRECTION_OVERRIDE_REQUIRED
- Gate checker: jeśli THREE-WAY CONFLICT + margin ≤ 0.5 → REJECT lub minimum EXTEND

---

### BUG 3: Bologna/Trento Points U73.5 — safety 0.0 przeszła gate

**Objaw:** Pick z safety_score = 0.0 (dosłownie ZERO statystycznej przewagi) został APPROVED.

**Root cause:** Gate checker operuje na 19-kryterialnym checklisty (V1-V19). Safety score to zaledwie 1 z 19 kryteriów. Pick z safety 0.0 może przejść 11/19 kryteriów (poprawny fixture, poprawny sport, poprawna liga, etc.) i zostać APPROVED.

**Brak minimalnego progu:** Nigdzie w kodzie nie ma:
```python
if safety_score < 0.20:
    reject("MINIMUM_SAFETY_FLOOR")
```

**Fix potrzebny:**
- Dodać hard floor: `safety_score < 0.15` → auto-REJECT
- Dodać soft floor: `safety_score < 0.30` → auto-EXTEND (nie APPROVE)

---

### BUG 4: Waltert vs Siniakova (BEST pick dnia!) błędnie w EXTENDED

**Objaw:** Najlepszy pick dnia (L5 5/5, safety 0.47) wyrzucony do EXTENDED pool zamiast APPROVED.

**Root cause:** Gate checker linia 1677:
```python
_synthetic_strong = (hit_num >= 7 and l5_num >= 4)
```
Waltert ma `hit_rate_l10 = "6/8"` → `hit_num = 6`. Próg wymaga ≥7, ale **przy denominatorze /8** to 75% hit rate! Próg jest dostosowany do denominatora /10, nie do rzeczywistego %. 

**Problem arytmetyczny:**
- 6/8 = 75% → BETTER than 7/10 = 70%!
- Ale `hit_num = 6 < 7` → FAIL

**Dodatkowa kara:** `SYNTHETIC_DATA_WEAK: source=db-synthetic, hit=6/8` → automatyczny EXTEND

**Fix potrzebny:**
```python
# Use percentage, not absolute number:
_synthetic_strong = (hit_rate_val >= 0.70 and l5_num >= 4)
# OR: normalize to /10:
_hit_normalized = round(hit_rate_val * 10)
_synthetic_strong = (_hit_normalized >= 7 and l5_num >= 4)
```

---

### BUG 5: Brak kickoff-guard w sekcji SINGLE BETS

**Objaw:** Marikina (08:00 UTC) pojawia się w matrycy jako #8 pick.

**Root cause:** `_filter_past_events()` działa poprawnie na liście `approved` PRZED budową kuponów, ale matryca jest generowana z pełnej listy gate_results BEZ tego filtra.

**Kod (coupon_builder.py:2022):**
```python
all_approved = _filter_past_events(gr.get("approved", []))  # ← filtruje
```
Ale matryca renderowana w innej funkcji bierze CAŁĄ approved listę z gate_results bez filtrowania.

---

## Diagram przyczynowo-skutkowy

```
PIPELINE GAP                    → EFEKT NA KUPONIE
─────────────────────────────────────────────────────
Gate: brak min safety floor     → Bologna 0.0 approved
Gate: hit_num vs hit_rate_val   → Waltert 6/8 demoted  
Gate: brak context override     → Fürth UNDER approved
Builder: matryca bez filtra     → Started events na top
Builder: sort by safety only    → Misleading hierarchy
```

---

## Wpływ na bankroll

| Scenariusz | Wpływ |
|-----------|-------|
| Gdyby postawiony v1 | Prawdopodobna strata 5-7 PLN (Fürth wrong direction, Bologna no edge) |
| v2 (przebudowany) | Oczekiwana wartość: +2-4 PLN |
| Oszczędzone przez audyt | ~7 PLN potencjalnych strat |

---

## Rekomendacje zmian w kodzie (priorytet)

| # | Plik | Zmiana | Priorytet |
|---|------|--------|-----------|
| 1 | `gate_checker.py` | Dodać `safety_floor = 0.15` → auto-REJECT | 🔴 CRITICAL |
| 2 | `gate_checker.py` | Zmienić `hit_num >= 7` na `hit_rate_val >= 0.70` | 🔴 CRITICAL |
| 3 | `gate_checker.py` | Dodać `safety < 0.30` → auto-EXTEND | 🟡 HIGH |
| 4 | `context_checks.py` | DIRECTION_OVERRIDE przy relegation/promotion + margin ≤ 0.5 | 🟡 HIGH |
| 5 | `coupon_builder.py` | Filtrować matrycę przez `_filter_past_events` | 🟢 MEDIUM |
| 6 | `coupon_builder.py` | Oznaczać STARTED events w matrycy | 🟢 MEDIUM |
| 7 | `compute_safety_scores.py` | Flag CONFLICTED gdy l5_avg contradicts direction | 🟡 HIGH |

---

## Lekcje dla orchestratora

1. **ZAWSZE sprawdzaj kickoff vs current time PRZED prezentacją kuponu użytkownikowi**
2. **NIGDY nie akceptuj safety=0.0 w jakimkolwiek kuponie** — nawet jeśli gate APPROVED
3. **Przy margin < 0.5: weryfikuj kierunek kontekstowo** (relegacja, forma ostatnich 5, motywacja)
4. **Nie ufaj gate_score 11/19 = APPROVED bez walidacji edge'a** — 11/19 to checklist formalny, nie merytoryczny
5. **Waltert-type picks (L5 5/5 ale niski gate) = always rescue** — hit rate consistency > data completeness

---

*Wygenerowano: 2026-05-26T16:00 CET*
