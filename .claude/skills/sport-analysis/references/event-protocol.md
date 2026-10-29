# Measured-sport event protocol - the section it produces

One section per match of the read-set file, in its order. The operator
reads it on a phone, folded under the leg (HTML) and in the PDF's appendix.
Write it **to be read**:

- full Polish sentences; a team or player by full name, never "A" / "B";
- every number with its unit and what it means ("Kraken tracą średnio 3.1
  gola na mecz w ostatnich 10"), never a bare chain of numbers;
- technical fields (`match_method`, `home_is_team1`, `calibrated_on`,
  `sb:` / `line_offset`, snapshot, estimator, dossier field names such as
  `roster_latest` / `map_pool_90d`) only in the closing **Szczegóły
  techniczne** line;
- no artifact tables copied and no rung tables - the page shows each leg's
  pewność, kurs, x, próbka; ~4,000 characters a match, a quiet one less.

```markdown
### <Gospodarz> – <Gość> — <rozgrywki> · sofa:<sofascore_event_id>
**W skrócie:** <2-3 zdania prostym językiem: kto faworytem i czemu, jak mecz się prawdopodobnie ułoży, co decyduje o nogach>
**Start:** 2026-10-25 23:00Z (FIXTURE_CHECK 23:00Z) · tożsamość sprawdzona · nierozpoczęty o 18:40Z
**Fakty zabójcze (przed siecią):** <co złamałoby te nogi: bramkarz rezerwowy / gwiazda Out / zmiennik w piątce / odpoczynek atakującego - 1 linia>
**Kluczowe przed meczem:** <prostym językiem: hokej - bramkarze obu (potwierdzony / przewidywany / niesprawdzone, źródło, godz.); kosz - raport kontuzji obu (nie zagra / niepewny / limit minut); CS2 - czy piątki obu są takie jak ostatnio, do ilu map, LAN czy online, ile razy każda drużyna grała mapę nogi w 90 dniach; siatkówka - atakujący / rozgrywający / przyjmujący (zwykle niesprawdzone), format>

**Czynniki rynku.** <dla każdej rodziny rynku: czynniki z market-drivers.md i ich wartości pełnymi zdaniami (forma z okresami / mapami, odpoczynek, tabela, h2h na metryce nóg); oczekiwanie w jednostkach rynku wobec linii>
**Kontekst (web).** <obowiązkowe sprawdzenia sportu i wynik, każde z [WEB: domena, publ. <data>, fetched <czas>]; co robi której nodze, albo „nic istotnego dla tych nóg”>
**Cena.** <ruch linii z dossier; ruch sam w sobie nie jest powodem>

**Nogi.**
- <superbet_market: superbet_selection> (<rynek, podmiot, kierunek>) — KEEP / WATCH / NO_BET: <jedno zdanie: oczekiwanie vs linia, fakt>
- …

**Ekspozycja:** <dwie nogi, które są jednym zakładem>
**Za / Przeciw:** <najmocniejszy argument każdej strony, jedna linia>
**Szczegóły techniczne:** <match_method, home_is_team1, best_of (CS2), calibrated_on, sb: / line_offset, snapshot, estymator, nazwy pól dossier - jedna linia>
```

**Nogi** holds one line per family (market, subject, direction) and every
removed leg on its own line. A single-leg match with no finding may skip
**Ekspozycja**, **Cena** (line unmoved) and **Za / Przeciw**.

A re-read (`prior_analysis`) - the delta section: the same heading; first
body line `**W skrócie:**`, second `[wcześniej: <report>,
<recorded_at_utc>]`; then only what changed (a goalie confirmed since, a
status change, a stand-in), and always a `**Kontekst (web).**` line
("delta: pełny przegląd <czas>, nic nowego" is allowed).

## Rules for the section

- The `sofa:<id>` token is in the heading - `merge_reads.py` files the
  section under the match by it.
- Identity is checked before anything; a wrong field is a NO_BET written
  `DEFEKT: sport_fixtures.json <field> ...`. Removals: the agent file's
  table only.
- Scope is stated only where `superbet_market` differs from the code's
  scope - otherwise silent.
- What you could not check (a European goalie, a volleyball six, a CS2 veto,
  a dossier `header` with only identity and clocks, an absent `table`) is
  `UNVERIFIED` in the section and listed once in the report's **Czego
  zabrakło**, never a removal by itself.
- Never a combined price; never a stake.
