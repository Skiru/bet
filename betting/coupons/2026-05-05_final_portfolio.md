# PORTFEL KUPONÓW — 2026-05-05 (FINAL v2)

> **Bankroll:** 61,91 PLN | **Ekspozycja dzienna:** 5,0–15,0 PLN | **Max stawka:** 2,0 PLN/kupon
> **Bukmacher:** Betclic PL | **Wersja:** v2-final (builder review)

---

## 🔴 DECYZJA KRYTYCZNA: NYY-TEX HR U3.0 @1,96

| Parametr | Wartość | Ocena |
|----------|---------|-------|
| Safety score | 0,40 | ❌ Poniżej progu 0,60 |
| Hit rate L10 | 4/10 (40%) | ❌ Poniżej 50% |
| EV | 0,40 × 1,96 = 0,784 | ❌ **UJEMNE EV** (< 1,0) |
| Challenger | Tier C | ⚠️ CAUTION |
| Gate score | 13/17 (failed #12) | ⚠️ Safety gate failed |
| Kelly 1/4 | 0 PLN | ❌ Kelly mówi: NIE STAWIAJ |

**→ USUNIĘTY z Core 2. Przeniesiony do EXTENDED POOL.**
Combo z NYY-TEX dostępne w COMBO MENU ale oznaczone ⚠️.

---

## ═══════════════════════════════════════════
## 1. CORE PORTFOLIO (kupony do postawienia)
## ═══════════════════════════════════════════

### KUPON 1: CP-20260505-CORE1 — AKO2 BASEBALL UNDERS

| # | Wydarzenie | Rynek | Linia | Kierunek | Kurs | Safety | 3-Way |
|---|-----------|-------|-------|----------|------|--------|-------|
| 1 | Detroit Tigers vs Boston Red Sox (MLB) | Łączna l. home runów | 2,5 | PONIŻEJ | **2,49** | 0,70 | 3/3 ✅ |
| 2 | Kansas City Royals vs Cleveland Guardians (MLB) | Biegi Cleveland Guardians | 4,5 | PONIŻEJ | **2,00** | 0,70 | 2/3 |

| Parametr | Wartość |
|----------|---------|
| Kurs łączny | **4,98** |
| Stawka | **2,00 PLN** |
| Potencjalna wygrana | 9,96 PLN |
| Tier | MS (Medium Safety) |
| Kelly 1/4 | 5,57 PLN → cap 2,00 PLN ✅ |

**STRESS TEST:**
- P(kupon) = 0,70 × 0,70 = **0,49** (49%)
- Najsłabsza noga: KC-CLE (L5 avg=5,6 vs linia 4,5 — trend wzrostowy ⚠️)
- Katastrofa: Przegrywa jeśli KC-CLE Runs > 4,5 (L5 trend rośnie)
- Korelacja: ≥2 nogi MLB (różne mecze, różne drużyny — akceptowalne)
- **Ocena: SOLIDNY** — oba safety 0,70, najwyższe w puli

---

### KUPON 2: CP-20260505-CORE2 — AKO2 J-LEAGUE STRZAŁY CELNE

| # | Wydarzenie | Rynek | Linia | Kierunek | Kurs | Safety | 3-Way |
|---|-----------|-------|-------|----------|------|--------|-------|
| 1 | Shimizu S-Pulse vs Cerezo Osaka (J-League) | Strzały celne Cerezo Osaka | 4,5 | PONIŻEJ | **2,625** | 0,60 | 2/2 ✅ |
| 2 | V-Varen Nagasaki vs Fagiano Okayama (J-League) | Strzały celne łącznie | 6,5 | PONIŻEJ | **2,80** | 0,60 | 3/3 ✅ |

| Parametr | Wartość |
|----------|---------|
| Kurs łączny | **7,35** |
| Stawka | **2,00 PLN** |
| Potencjalna wygrana | 14,70 PLN |
| Tier | MS (Medium Safety) |
| Kelly 1/4 | 4,02 PLN → cap 2,00 PLN ✅ |

**STRESS TEST:**
- P(kupon) = 0,60 × 0,60 = **0,36** (36%)
- Najsłabsza noga: Shimizu (H2H avg=0,0 → podejrzane, tylko 1 mecz H2H)
- Katastrofa: Przegrywa jeśli Cerezo Osaka > 4,5 strzałów celnych
- Korelacja: ⚠️ ≥2 nogi J-League (ale różne dywizje/mecze)
- **Ocena: UMIARKOWANY** — dobre kursy kompensują niższe p, dywersyfikacja sport vs Core 1

> ⚡ **ZMIANA vs skrypt:** Usunięto NYY-TEX HR U3.0 @1,96 (safety 0,40, EV ujemne).
> Kupon przebudowany z AKO3 (odds 14,41) na AKO2 (odds 7,35).
> Wynik: wyższa P(kupon), brak negatywnego EV w nogach.

---

### PODSUMOWANIE CORE

| Kupon | Kurs | Stawka | P(kupon) | Potencjał | Sport |
|-------|------|--------|----------|-----------|-------|
| CORE1 | 4,98 | 2,00 PLN | 49% | 9,96 PLN | ⚾ Baseball |
| CORE2 | 7,35 | 2,00 PLN | 36% | 14,70 PLN | ⚽ Football |
| **RAZEM** | — | **4,00 PLN** | — | **24,66 PLN** | 2 sporty ✅ |

---

## ═══════════════════════════════════════════
## 2. SINGLE (indywidualne zakłady)
## ═══════════════════════════════════════════

Ranking wg adjusted confidence (statistician + challenger):

| # | ID | Wydarzenie | Rynek | Linia | Kier. | Kurs | Safety | Conf. | Stawka | EV check |
|---|-----|-----------|-------|-------|-------|------|--------|-------|--------|----------|
| 1 | S7 | DET Tigers vs BOS Red Sox | HR łącznie | 2,5 | PON. | **2,49** | 0,70 | 0,60 | 2,00 PLN | 0,70×2,49=**1,74** ✅ |
| 2 | S9 | KC Royals vs CLE Guardians | Biegi CLE | 4,5 | PON. | **2,00** | 0,70 | 0,55 | 2,00 PLN | 0,70×2,00=**1,40** ✅ |
| 3 | S15 | Shimizu vs Cerezo Osaka | SoT Cerezo | 4,5 | PON. | **2,625** | 0,60 | 0,52 | 2,00 PLN | 0,60×2,625=**1,58** ✅ |
| 4 | S16 | V-Varen vs Fagiano Okayama | SoT łącznie | 6,5 | PON. | **2,80** | 0,60 | 0,50 | 2,00 PLN | 0,60×2,80=**1,68** ✅ |
| 5 | S8 | NYY Yankees vs TEX Rangers | HR łącznie | 3,0 | PON. | **1,96** | 0,40 | 0,40 | ~~1,00~~ | 0,40×1,96=**0,78** ❌ |

> ⚠️ **Single #5 (NYY-TEX): EV UJEMNE.** Kelly mówi 0 PLN.
> Umieszczony w Extended Pool — stawiaj TYLKO jeśli Betclic da kurs ≥ 2,50 (min. kurs dla 40% HR).

**Koszt singli (bez NYY-TEX):** 4 × 2,00 = **8,00 PLN**

---

## ═══════════════════════════════════════════
## 3. COMBO MENU (dodatkowe kombinacje do wyboru)
## ═══════════════════════════════════════════

### COMBO REKOMENDOWANE (bez NYY-TEX)

| # | ID | Nogi | Kurs | Stawka | P(kupon) | Motyw |
|---|-----|------|------|--------|----------|-------|
| 1 | COMBO-LR1 | DET-BOS @2,49 + KC-CLE @2,00 + Shimizu @2,625 | 13,07 | 2,00 PLN | 29% | 🛡️ Najwyższe safety |
| 2 | COMBO-LR2 | DET-BOS @2,49 + KC-CLE @2,00 + V-Varen @2,80 | 13,94 | 2,00 PLN | 29% | 🛡️ Safety + najlepszy 3-way |
| 3 | COMBO-LR3 | DET-BOS @2,49 + V-Varen @2,80 | 6,97 | 2,00 PLN | 42% | 🎯 Cross-sport 2-nogi |
| 4 | COMBO-MS2 | DET-BOS @2,49 + Shimizu @2,625 | 6,54 | 2,00 PLN | 42% | 🔄 Dywersyfikacja |
| 5 | COMB2x7 | KC-CLE @2,00 + Shimizu @2,625 | 5,25 | 2,00 PLN | 42% | 🔄 Dywersyfikacja |
| 6 | COMB2x8 | KC-CLE @2,00 + V-Varen @2,80 | 5,60 | 2,00 PLN | 42% | 🎯 Cross-sport |
| 7 | COMB2x12 | Shimizu @2,625 + V-Varen @2,80 | 7,35 | 2,00 PLN | 36% | ⚽ J-League pakiet |
| 8 | COMB2x13 | DET-BOS @2,49 + KC-CLE @2,00 | 4,98 | 2,00 PLN | 49% | ⚾ MLB pakiet |
| 9 | COMB3x16 | KC-CLE + Shimizu + V-Varen | 14,70 | 2,00 PLN | 25% | 🎰 High odds |
| 10 | COMB3x17 | DET-BOS + Shimizu + V-Varen | 18,33 | 2,00 PLN | 25% | 🎰 Premium |

### COMBO Z NYY-TEX ⚠️ (Tier C — user decides)

| # | ID | Nogi | Kurs | Stawka | P(kupon) | Uwaga |
|---|-----|------|------|--------|----------|-------|
| 11 | COMBO-MS1 | DET-BOS @2,49 + NYY-TEX @1,96 | 4,88 | 2,00 PLN | 28% | ⚠️ NYY safety=0,40 |
| 12 | COMB2x9 | NYY-TEX @1,96 + KC-CLE @2,00 | 3,92 | 2,00 PLN | 28% | ⚠️ |
| 13 | COMB2x10 | NYY-TEX @1,96 + Shimizu @2,625 | 5,14 | 2,00 PLN | 24% | ⚠️ |
| 14 | COMB2x11 | NYY-TEX @1,96 + V-Varen @2,80 | 5,49 | 2,00 PLN | 24% | ⚠️ |
| 15–20 | COMB3x14–20 | AKO3 z NYY-TEX | 10,29–14,41 | 2,00 PLN | 10-17% | ⚠️⚠️ |

> Combo 11-20 zawierają NYY-TEX (safety 0,40, EV ujemne przy 1,96).
> Stawiaj TYLKO jeśli Betclic oferuje NYY-TEX ≥ 2,50.

---

## ═══════════════════════════════════════════
## 4. WATCH LIST (stats-first — sprawdź w Betclic)
## ═══════════════════════════════════════════

Poniższe zdarzenia mają wsparcie statystyczne ale BRAK KURSÓW w API.
Otwórz Betclic → znajdź wydarzenie → sprawdź czy rynek istnieje → oblicz EV.

**Formuła:** `hit_rate × kurs > 1,0` → TAK = pozytywne EV → STAWIAJ

| # | Sport | Wydarzenie | Rynek | Linia | Kier. | Safety | 3-Way | Min. kurs |
|---|-------|-----------|-------|-------|-------|--------|-------|-----------|
| 1 | 🏒 Hockey | COL Avalanche vs MIN Wild | Minuty karne łącznie (PIM) | 19,0 | PON. | 0,60 | 3/3 ✅ | **≥1,67** |
| 2 | 🏒 Hockey | TB Lightning vs MTL Canadiens | Strzały łącznie | 50,5 | PON. | 0,57 | 3/3 ✅ | **≥1,75** |
| 3 | 🏀 NBA | Detroit vs Orlando | Asysty łącznie | 42,5 | PON. | 0,57 | 2/3 | **≥1,75** |
| 4 | 🏒 Hockey | Vegas Golden Knights vs Anaheim Ducks | Strzały łącznie | 62,0 | PON. | 0,57 | 2/3 | **≥1,75** |
| 5 | ⚾ MLB | Houston Astros vs LA Dodgers | HR łącznie | 1,5 | POWYŻEJ | 0,56 | 2/3 | **≥1,79** |
| 6 | ⚾ MLB | Seattle Mariners vs Atlanta Braves | Biegi ATL | 6,0 | PON. | 0,60 | 2/3 | **≥1,67** |

> **SEA-ATL:** Challenger flaguje — L5 avg=6,8 vs linia 6,0, trend wzrostowy. Ostrożnie.
> **COL-MIN:** Challenger — playoff intensity? Margines bardzo cienki. Kurs min. 1,67.

---

## ═══════════════════════════════════════════
## 5. EXTENDED POOL (EV>0 ale gate-failed)
## ═══════════════════════════════════════════

| # | Sport | Wydarzenie | Rynek | Safety | Problem |
|---|-------|-----------|-------|--------|---------|
| 1 | ⚾ MLB | NYY Yankees vs TEX Rangers | HR U3.0 @1,96 | 0,40 | EV ujemne (0,78), hit rate 40%, min kurs 2,50 |
| 2 | ⚾ MLB | SF Giants vs SD Padres | Biegi SF O2.5 | 0,44 | L5 trend spadkowy (2,0 vs L10 2,67) |
| 3 | ⚾ MLB | LA Angels vs CHI White Sox | Biegi CHW O4.5 | 0,50 | Hit rate 50%, margines 1,022 |
| 4 | 🏀 NBA | Cleveland vs Toronto | Zbiórki łącznie U84.5 | 0,57 | 1/3 CONFLICT — L5 trend rośnie (90,8!) |
| 5 | ⚽ Football | Madura Utd vs Bali Utd | Gole U4.5 | 0,40 | **FALSE POSITIVE** — challenger: REMOVE |

---

## ═══════════════════════════════════════════
## 6. KALKULACJA EKSPOZYCJI
## ═══════════════════════════════════════════

### Scenariusze (user wybiera):

| Scenariusz | Skład | Koszt | W limicie? |
|------------|-------|-------|-----------|
| **A) AKO-fokus** 🏆 | Core 1 + Core 2 | **4,00 PLN** | ✅ (min 5 → dodaj 1 combo) |
| **B) AKO + combo** | Core 1 + Core 2 + COMBO-LR3 | **6,00 PLN** | ✅ |
| **C) AKO + single** | Core 1 + Core 2 + 2 najlepsze single | **8,00 PLN** | ✅ |
| **D) Mixed** | Core 1 + Core 2 + 4 single (bez NYY) | **12,00 PLN** | ✅ |
| **E) Full menu** | Core 1 + Core 2 + 4 single + 2 combo | **16,00 PLN** | ⚠️ 1 PLN nad cap |

**REKOMENDACJA: Scenariusz B lub C** — 6-8 PLN, w limicie, dobra dywersyfikacja.

### Uwaga: NIE PODWAJAJ EKSPOZYCJI
Jeśli stawiasz Core 1 (DET-BOS + KC-CLE), **nie stawiaj** singli na te same mecze.
Singli #1-4 używaj jako ALTERNATYWY, nie jako dodatek do Core.

---

## ═══════════════════════════════════════════
## 7. KOLEJNOŚĆ OBSTAWIANIA
## ═══════════════════════════════════════════

1. **Core 1** — AKO2 baseball (DET-BOS + KC-CLE) @ 4,98 × 2,00 PLN
2. **Core 2** — AKO2 J-League (Shimizu + V-Varen) @ 7,35 × 2,00 PLN
3. *Opcjonalnie:* COMBO-LR3 (DET-BOS + V-Varen) @ 6,97 × 2,00 PLN
4. *Opcjonalnie:* Single V-Varen SoT U6.5 @ 2,80 × 2,00 PLN (najlepszy EV z singli)
5. **Watch List** — sprawdź Betclic app po kursy

---

## 8. PROFIL SESJI

| Metryka | Wartość |
|---------|---------|
| Picks z kursami | 5 (4 Tier A-B + 1 Tier C) |
| Picks stats-first | 6 (Watch List) |
| Extended pool | 5 |
| Sporty w core | 2 (baseball, football) |
| Sporty w Watch List | 3 (hockey, basketball, baseball) |
| Kierunek dominujący | UNDER (10/11 picks) |
| Średni safety (core) | 0,65 |
| P(≥1 core trafi) | 1 - (1-0,49)×(1-0,36) = **67%** |
| Betclic sweet spot | AKO2-3, stat markets ✅ |

---

*Wygenerowano: 2026-05-05 | Builder review: v2-final*
*Źródła: ESPN-baseball, ESPN-football, The-Odds-API (bet365)*
*Następny krok: Otwórz Betclic → sprawdź kursy → postaw wg kolejności*
