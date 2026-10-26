# Measured-sport event protocol - the section it produces

One section per match of the read-set file, in its order. Dense: the
operator reads it folded under the leg (HTML) and in the PDF's appendix.
No artifact tables copied - the page shows each leg's pewność, kurs, x,
próbka. At most ~4,000 characters a match; a quiet match needs less.

```markdown
### <Gospodarz> – <Gość> — <rozgrywki> · sofa:<sofascore_event_id>
**Start:** 2026-10-25 23:00Z (sport_fixtures 23:00Z, FIXTURE_CHECK 23:00Z) · nierozpoczęty o 18:40Z
**Tożsamość:** IDENTIFIED (<match_method>), nazwy <Superbet> = <Sofascore>, home_is_team1 <true>; best_of <3> (CS2)
**Cena:** snapshot <czas>, <ruch linii z dossier albo „bez ruchu”>
**Punkt wyjścia:** pewność nóg 0.74-0.81; oczekuję <liczba w jednostkach rynku> (<skąd>).
**Fakty zabójcze (przed siecią):** <bramkarz rezerwowy / gwiazda Out / zmiennik / odpoczynek atakującego - 1 linia>

**Dossier.** <forma z okresami / mapami, odpoczynek i back-to-back, tabela, h2h na metryce nóg, skład / roster / pula map - 3-6 punktów>
**Kontekst (web).** <obowiązkowe sprawdzenia sportu i wynik, każde z [WEB: domena, publ., fetched]; co robi której nodze, albo „nic istotnego dla tych nóg”>

**Nogi.**
- <superbet_market: superbet_selection> — KEEP / WATCH / NO_BET: <jedno zdanie: oczekiwanie vs linia, fakt>
- …

**Ekspozycja:** <dwie nogi, które są jednym zakładem - albo pomiń>
```

A match with `prior_analysis` gets the same heading; **Dossier** as
"[wcześniej: <report>]" plus what changed; **Kontekst (web)** = the delta
pass (a goalie confirmed since, a status change, a stand-in).

## Rules for the section

- The `sofa:<id>` token is in the heading - `merge_reads.py` files the
  section under the match by it.
- Identity is checked before anything; a wrong field is a NO_BET naming it.
- Scope is stated only where `superbet_market` differs from the code's
  scope - otherwise silent.
- What you could not check (a European goalie, a volleyball six, a CS2 veto)
  is `UNVERIFIED` in the section and listed in **Czego zabrakło**, never a
  removal by itself.
- Never a combined price; never a stake.
