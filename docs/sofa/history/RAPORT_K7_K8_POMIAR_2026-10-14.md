# K7 (sporty mierzone) i K8 (piłka / tenis RESOLVE): zmierzone, niewłączone — 2026-10-14

Plan: `docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md`. Oba kroki kończą się
pomiarem i decyzją dla operatora — żaden przełącznik nie został włączony.

## K8 — kotwica dnia dla piłki w RESOLVE

Ta sama reguła co K2 (jedyny mecz znanej drużyny w ±1 h, nazwa przeciwnika
ukryta), na meczach piłkarskich RESOLVE 10-05..10-14
(`docs/sofa/evidence/identity_coverage_2026-10-14/k8_football_anchor_backtest.py`,
wynik `k8_football_anchor_out.txt`; id kotwicy z `sofa_entity`, najnowsza
pobrana wersja meczu; RESOLVE sam dopuszcza dziś 24 h i wymaga nazwy
przeciwnika):

| wariant | zmostkowane mecze: trafione | błędne | luki RESOLVE: reguła wskazuje |
|---|---|---|---|
| bez warunku orientacji | 3 458 | 3 | 115 |
| **z orientacją jak w Superbecie (bramka F25)** | **3 458** | **1** | **109** (~11 dziennie) |
| + nazwa przeciwnika znana indeksowi jako inna drużyna → odmowa | 3 446 | 1 | 105 |

Dwa „błędy” bez orientacji to pary podwojone przez Sofascore z zamienionym
gospodarzem, jedna przełożona: Pacific – Forge 10-07 (RESOLVE przypiął kopię
później przełożoną; rozegrany był 17258203 Forge – Pacific — tu kotwica miała
rację), Chernihiv – Prykarpattia 10-11. Warunek orientacji je odrzuca.

**Pozostały jeden przypadek:** Superbet „Hapoel Petah Tikva U19 – Hapoel Haifa
U19” 10-11 15:30. RESOLVE przypiął 16893171 (dziś nie ma go w indeksie), a
jedyny mecz Hapoel Haifa U19 o tej godzinie w Sofascore to **Maccabi** Petach
Tikva U19 – Hapoel Haifa U19 17329555 (finished). Albo Sofascore poprawił
przeciwnika i usunął stary mecz (kotwica miałaby rację), albo to dwa różne
mecze — z danych nie da się rozstrzygnąć. Próg planu (100% na zmostkowanych)
nie jest spełniony, więc **reguła nie jest włączona**. Tenis — wyłączony z
zasady (K0: podmieniony przeciwnik, Biro – Pankratova jako Biró – Kalyakina).

Do decyzji operatora: włączyć piłkarską kotwicę z warunkiem orientacji (zysk
~11 meczów dziennie, 1 nierozstrzygnięty przypadek na 3 459), czy czekać na
nowe dni.

## K7 — zawodnicy hokeja i kosza

`player_model` ma już własną regułę nazwisko + imię (`names_agree`:
równe, inicjał albo prefiks ≥ 3), więc reguła piłkarska z K7 nic tu nie
dodaje. `NOT_IN_HISTORY` (10-05..10-14: hokej 55 pozycji / 30 nazwisk, kosz
62 / 48) znaczy: nikogo bliskiego w ostatnich meczach **dwóch drużyn meczu**.
Sprawdzone po wszystkich zapisanych składach sportu z ostatnich 150 dni (hokej
1 383 mecze, kosz 3 734):

| | nazwiska | dokładnie jeden zawodnik w innej drużynie | kilku | nigdzie |
|---|---|---|---|---|
| hokej | 30 | **25** (Varlamov, Pickard, Cossa, Fowler, Bunting, Jiricek…) | 2 | 3 |
| kosz | 48 | **20** | 3 | 25 |

Tożsamość jest więc znajdowalna — to głównie bramkarze wracający do składu i
zawodnicy po transferze. Ale użycie jej oznacza wycenę zawodnika z meczów
**innej drużyny**, a to decyzja modelu, nie mapowania (od 10-14
`PLAYER_TEAM_FROM_SIDE` celowo wiąże próbę z drużyną meczu) — wymaga pomiaru
log-loss, zanim cokolwiek się zmieni. Niewłączone.

CS2: `NOT_IN_HISTORY` 6 pozycji w 10 dni, `EVENT_NOT_IDENTIFIED` 30 (naprawia
je poziom meczu) — bez osobnej zmiany.

## Co zostaje otwarte w planie

- K8 piłka: decyzja operatora (wyżej).
- K7 sporty: pomiar wyceny z historii innej drużyny (log-loss na wierszach
  przed meczem), potem ewentualny przełącznik.
- Wszystkie reguły z 10-15 (K1, K2, K3, K4, K5, K7 piłka) pierwszy raz na
  żywo po 00:00Z; miernik: `measure_team_identity.py --from 2026-10-15`
  (test `T-IDENTITY-unexplained`, PROPOSED).
