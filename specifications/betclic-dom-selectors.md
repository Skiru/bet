# Betclic DOM Selector Map

> Comprehensive DOM analysis of betclic.pl Angular SPA  
> Last updated: 2026-05-13

## URL Patterns

| Pattern | Example | Notes |
|---------|---------|-------|
| Sport listing | `/pilka-nozna-s1`, `/tenis-s2`, `/koszykowka-s4`, `/siatkowka-s18`, `/hokej-na-lodzie-s13` | Max ~20 events per page |
| League | `/sport-ssport/league-name-cNNN` | `cNNN` = competition ID |
| Match | `/sport-ssport/league-name-cNNN/team1-team2-mNNNNNNNNNNNNNNN` | `mNNNN...` = 15-16 digit match ID |

Internal URL slugs: `sfootball`, `stennis`, `sbasketball`, `svolleyball`, `shockey`.

## Listing Page Selectors

### Event Cards

```
sports-events-event-card              → wraps each event
├── a.cardEvent[href]                 → match link (/sport-ssport/league-cN/teams-mNNN)
│   ├── .is-live                      → class present on live matches
│   ├── [data-qa="contestant-1-label"]→ home team name
│   ├── [data-qa="contestant-2-label"]→ away team name
│   ├── [data-qa="scoreboard-score"]  → live score (spans: scoreboard_score-1, scoreboard_score-2)
│   ├── .breadcrumb_itemLabel         → league name (e.g., "OFC Pro Liga")
│   ├── .event_infoTime               → kickoff time or match minute ("40' • P1", "4:53 • K2")
│   └── sports-events-event-market-count → "+N zakł." (market count, regex \d+)
└── button[bcdkbetbutton]             → bet buttons (1X2 or ML)
    ├── bcdk-bet-button-label.btn_label.is-top  → team name (split: span.ellipsis + span.clip)
    ├── bcdk-bet-button-label.btn_label:not(.is-top) → odds value (text node, Polish: "8,25")
    └── bcdk-bet-button-addon-odds-arrow → trend arrow (is-up / hidden)
```

### Groups & Navigation

```
.groupEvents                          → competition group container
├── .groupEvents_headTitle            → group name: "Teraz" (LIVE) / "Dzisiaj" (Today)
└── sports-events-event-card[]        → events in this group

sports-competition-list a[href]       → sidebar competition links
[data-qa^="pinned-competition-tile-"] → pinned/favorite competitions
```

### Odds Button Internal Structure

```html
<button bcdkbetbutton betbuttontype="odd" size="large" class="btn is-large is-odd is-up has-iconRight">
  <bcdk-bet-button-addon-odds-arrow class="icon_arrowUpFilled icons"/>
  <bcdk-bet-button-label class="btn_label is-top">
    <span class="ellipsis">Tahiti Unite</span>
    <span class="clip">d FC</span>
  </bcdk-bet-button-label>
  <bcdk-bet-button-label class="btn_label">
    <!----> 8,25 <!---->
  </bcdk-bet-button-label>
  <bcdk-bet-button-trends-bar/>  <!-- optional, only on some -->
</button>
```

**Notes:**
- Team name is split across `span.ellipsis` + `span.clip` (use `get_text()` to merge)
- Odds value is a text node between HTML comments (use `get_text(strip=True)`)
- Polish locale: comma decimals ("8,25" = 8.25, "1,07" = 1.07)
- `is-up` class = odds went up, `is-down` = odds went down

## Match Detail Page Selectors

### Market Tabs

```
[data-qa="tab-btn"]                   → tab buttons (only active tab content renders)
.tab_item.isActive                    → currently active tab
```

**Tabs by sport:**

| Sport | Tab 0 | Tab 1 (default) | Tab 2 | Tab 3 | Tab 4 | Tab 5 | Tab 6 | Tab 7 |
|-------|-------|------------------|-------|-------|-------|-------|-------|-------|
| Football | MyCombi | **Top** | Wynik | Strzelcy | Gole | Metoda gola | Wynik / Handicap | Statystyki |
| Basketball | MyCombi | **Top** | Wynik | Punkty | — | — | — | — |
| Tennis | MyCombi | **Top** | Mecz | Sety | — | — | — | — |
| Volleyball | MyCombi | **Top** | Mecz | Sety | — | — | — | — |
| Hockey | MyCombi | **Top** | Wynik | Gole | Statystyki | — | — | — |

> ⚠️ Only the **active tab** content is rendered in the DOM. Default is "Top".

### Market Sections

```
sports-markets-single-market.marketElement → wraps one market
├── .marketBox_headTitle                   → market name (Polish)
├── .marketBox_body                        → layout container
│   ├── .is-2col                           → 2-column layout (O/U, BTTS, handicap)
│   ├── .is-3col                           → 3-column layout (correct score)
│   └── .is-main.is-3col                   → primary 1X2/ML market
├── .marketBox_label                       → selection name ("Powyżej 2,5", "Tak")
└── .marketBox_lineSelection               → odds container
    └── button[bcdkbetbutton]              → bet button (same structure as listing)
```

### MyCombi (Bet Builder)

```
sports-my-combi-card                  → pre-built combination bets
├── .market_title                     → description
└── .market_odds                      → combined odds button
```

### Other Elements

```
sports-events-event-form-results      → last 5 match results (form)
bcdk-breadcrumb-item .breadcrumb_itemLabel → league breadcrumb path
scoreboards-scoreboard                → live scoreboard
scoreboards-timer                     → match time / period
```

## Market Names by Sport (Polish → English)

### Football

| Polish | English | Layout |
|--------|---------|--------|
| Wynik meczu (z wyłączeniem dogrywki) | Match Result (1X2) | 3-col main |
| Podwójna Szansa | Double Chance | 3 selections |
| Gole Powyżej/Poniżej | Goals Over/Under | 2-col, lines: 0.5, 1.5, 2.5 |
| Oba zespoły strzelą gola | Both Teams to Score | 2-col: Tak/Nie |
| 1. połowa Wynik | 1st Half Result | 3 selections |
| Dokładny wynik | Correct Score | 3-col grid |
| Która drużyna strzeli pierwszego gola? | First Team to Score | 3 selections |

### Basketball

| Polish | English | Layout |
|--------|---------|--------|
| Zwycięzca meczu | Match Winner (ML) | 2-col |
| Przewaga N punktami lub wygrana | Win by N points or Win | 2-col |
| Wynik handicap | Handicap | 2-col, lines: -8.5, -7.5, -6.5 |
| Suma punktów | Total Points | 2-col, lines: 196.5, 197.5, 198.5 |
| {Team} Suma punktów | Team Total Points | 2-col |
| N. kw. Suma punktów | Quarter N Total Points | 2-col |
| N. kw. Zwycięzca | Quarter N Winner | 2-col |

### Tennis

| Polish | English | Layout |
|--------|---------|--------|
| Zwycięzca meczu | Match Winner (ML) | 2-col |
| Łączna liczba gemów | Total Games | 2-col |
| Wynik w setach | Set Score | multi |
| Handicap setowy | Set Handicap | 2-col |
| Czy obaj zawodnicy wygrają seta | Both Players Win a Set | 2-col |
| N. set - Zwycięzca | Set N Winner | 2-col |
| N. set - Gem M - Zwycięzca | Set N Game M Winner | 2-col |

## Standard Betclic Market Catalog by Sport

> Only the active tab's **odds values** render in the DOM, but the market **structure is standardized** per sport on Betclic. The offerings below are stable — Betclic doesn't change them between matches. The parser can assume these markets exist and click the appropriate tab to extract odds.

### Football (tabs: MyCombi | Top | Wynik | Strzelcy | Gole | Metoda gola | Wynik / Handicap | Statystyki)

| Tab | Market (Polish) | Market (English) | Typical Lines |
|-----|----------------|-------------------|---------------|
| Top | Wynik meczu (z wyłączeniem dogrywki) | 1X2 | 1 / X / 2 |
| Top | Bezpieczny wynik | Safe Result (promoted) | special |
| Top | Przewaga N bramkami lub wygrana | Win by N+ goals or Win | Home / Away |
| Top | Podwójna Szansa | Double Chance | 1X / 12 / X2 |
| Top | Gole Powyżej/Poniżej | Goals O/U | 0.5, 1.5, 2.5 |
| Top | Oba zespoły strzelą gola | BTTS | Tak / Nie |
| Top | 1. połowa Wynik | 1st Half Result | 1 / X / 2 |
| Top | Dokładny wynik | Correct Score | grid |
| Top | Która drużyna strzeli pierwszego gola? | First to Score | Home / None / Away |
| Wynik | Wynik meczu | 1X2 | (same) |
| Wynik | Podwójna Szansa | Double Chance | (same) |
| Wynik | Połowa/Koniec meczu | Half-Time / Full-Time | 9 combos |
| Wynik | Zwycięstwo do zera | Win to Nil | Home / Away |
| Wynik | Remis i oba strzelą | Draw & BTTS | Tak / Nie |
| Strzelcy | Strzelec gola (dowolny) | Anytime Goalscorer | player list |
| Strzelcy | Strzelec pierwszego gola | First Goalscorer | player list |
| Strzelcy | Strzelec ostatniego gola | Last Goalscorer | player list |
| Strzelcy | Strzelec 2+ goli | 2+ Goals Scorer | player list |
| Gole | Gole Powyżej/Poniżej | Goals O/U | 0.5 – 6.5 |
| Gole | Oba zespoły strzelą gola | BTTS | Tak / Nie |
| Gole | {Drużyna} Gole Powyżej/Poniżej | Team Goals O/U | 0.5, 1.5, 2.5 |
| Gole | Parzyste/Nieparzyste gole | Odd/Even Goals | Parzyste / Niep. |
| Gole | Multi-Gol | Multi-Goal | 1-2, 1-3, 2-3, etc. |
| Gole | Liczba goli - {Drużyna} | Team Exact Goals | 0, 1, 2, 3+ |
| Metoda gola | Pierwszy gol - metoda | First Goal Method | header / free kick / penalty / own goal / shot |
| Metoda gola | Ostatni gol - metoda | Last Goal Method | (same) |
| Wynik / Handicap | Handicap europejski | European Handicap | ±1, ±2 |
| Wynik / Handicap | Handicap azjatycki | Asian Handicap | ±0.5 – ±2.5 |
| Wynik / Handicap | Remis nie stawia | Draw No Bet | Home / Away |
| Statystyki | Rzuty rożne Powyżej/Poniżej | Corners O/U | 7.5, 8.5, 9.5, 10.5, 11.5 |
| Statystyki | {Drużyna} Rzuty rożne Powyżej/Poniżej | Team Corners O/U | 3.5, 4.5, 5.5 |
| Statystyki | Kartki Powyżej/Poniżej | Cards O/U | 2.5, 3.5, 4.5, 5.5 |
| Statystyki | {Drużyna} Kartki Powyżej/Poniżej | Team Cards O/U | 1.5, 2.5 |
| Statystyki | Strzały na bramkę Powyżej/Poniżej | Shots on Target O/U | 7.5, 8.5, 9.5 |
| Statystyki | Faule Powyżej/Poniżej | Fouls O/U | 19.5, 21.5, 23.5 |

### Basketball (tabs: MyCombi | Top | Wynik | Punkty)

| Tab | Market (Polish) | Market (English) | Typical Lines |
|-----|----------------|-------------------|---------------|
| Top | Zwycięzca meczu | ML | Home / Away |
| Top | Wynik handicap | Handicap | ±3.5 – ±12.5 |
| Top | Suma punktów | Total Points | ~190–210 |
| Top | {Drużyna} Suma punktów | Team Total | ~90–110 |
| Top | N. kw. Zwycięzca | Quarter N Winner | Home / Away |
| Top | N. kw. Suma punktów | Quarter N Total | ~45–55 |
| Top | Przewaga N pkt lub wygrana | Win by N or Win | Home / Away |
| Wynik | Zwycięzca meczu | ML | (same) |
| Wynik | Margines zwycięstwa | Winning Margin | ranges |
| Wynik | Wyścig do N punktów | Race to N Points | 20, 25, 30 |
| Punkty | Suma punktów | Total Points | extended lines |
| Punkty | {Drużyna} Suma punktów | Team Total | extended lines |
| Punkty | N. kw. Suma punktów | Quarter Totals | all quarters |
| Punkty | 1. poł. Suma punktów | 1st Half Total | ~95–105 |
| Punkty | Parzyste/Nieparzyste pkt | Odd/Even Points | Par. / Niep. |

### Tennis (tabs: MyCombi | Top | Mecz | Sety)

| Tab | Market (Polish) | Market (English) | Typical Lines |
|-----|----------------|-------------------|---------------|
| Top | Zwycięzca meczu | ML | P1 / P2 |
| Top | Łączna liczba gemów | Total Games | 18.5 – 24.5 |
| Top | Wynik w setach | Set Score | 2-0, 2-1, 0-2, 1-2 |
| Top | Handicap setowy | Set Handicap | ±1.5 |
| Top | Czy obaj wygrają seta | Both Win a Set | Tak / Nie |
| Top | N. set - Zwycięzca | Set N Winner | P1 / P2 |
| Mecz | Zwycięzca meczu | ML | (same) |
| Mecz | Handicap gemowy | Game Handicap | ±2.5 – ±6.5 |
| Mecz | Łączna liczba gemów | Total Games | extended lines |
| Sety | N. set - Zwycięzca | Set N Winner | P1 / P2 |
| Sety | N. set - Wynik | Set N Score | 6-0 through 7-6 |
| Sety | N. set - Gemy Powyżej/Poniżej | Set N Games O/U | 8.5, 9.5, 10.5 |

### Volleyball (tabs: MyCombi | Top | Mecz | Sety)

| Tab | Market (Polish) | Market (English) | Typical Lines |
|-----|----------------|-------------------|---------------|
| Top | Zwycięzca meczu | ML | Home / Away |
| Top | Handicap setowy | Set Handicap | ±1.5 |
| Top | Suma punktów | Total Points | ~160–200 |
| Top | Wynik w setach | Set Score | 3-0, 3-1, 3-2, etc. |
| Top | {Drużyna} Suma punktów | Team Total Points | ~80–100 |
| Mecz | Handicap punktowy | Point Handicap | ±4.5 – ±12.5 |
| Mecz | Parzyste/Nieparzyste pkt | Odd/Even Points | Par. / Niep. |
| Sety | N. set - Zwycięzca | Set N Winner | Home / Away |
| Sety | N. set - Suma pkt | Set N Total | ~44–52 |
| Sety | N. set - Handicap pkt | Set N Point Handicap | ±2.5 – ±6.5 |

### Hockey (tabs: MyCombi | Top | Wynik | Gole)

| Tab | Market (Polish) | Market (English) | Typical Lines |
|-----|----------------|-------------------|---------------|
| Top | Wynik meczu (czas regulam.) | 1X2 (Reg. Time) | 1 / X / 2 |
| Top | Zwycięzca meczu | ML (incl. OT) | Home / Away |
| Top | Gole Powyżej/Poniżej | Goals O/U | 3.5, 4.5, 5.5, 6.5 |
| Top | Puck Line | Puck Line (Handicap) | ±1.5 |
| Top | Oba zespoły strzelą gola | BTTS | Tak / Nie |
| Wynik | Wynik meczu (czas regulam.) | 1X2 (Reg. Time) | (same) |
| Wynik | Podwójna Szansa | Double Chance | 1X / 12 / X2 |
| Wynik | Dokładny wynik | Correct Score | low-scoring grid |
| Gole | Gole Powyżej/Poniżej | Goals O/U | 1.5 – 7.5 |
| Gole | {Drużyna} Gole Powyżej/Poniżej | Team Goals O/U | 0.5, 1.5, 2.5 |
| Gole | 1. tercja Gole Powyżej/Poniżej | 1st Period Goals O/U | 0.5, 1.5 |

> **Key insight:** Even without clicking tabs, knowing the sport tells you exactly what markets Betclic offers. The parser only needs to click tabs when it wants to extract **specific odds values** for those markets.

## Parser Implementation Notes

1. **Pagination:** Listing pages show max ~20 events. For full coverage, navigate to per-league pages (`/sport-ssport/league-cNNN`) or scroll for lazy loading.

2. **Tab rendering:** Only the active tab's markets appear in the DOM. The default "Top" tab provides the most important markets (1X2/ML, O/U, BTTS, Handicap). For advanced markets (corners, cards, shots), tab clicks are required.

3. **Odds parsing:** Replace comma with dot before float conversion (`"8,25"` → `8.25`).

4. **Over/Under lines:** Selection labels contain the line value in Polish: `"Powyżej 2,5"` → Over 2.5. Parse with regex: `(Powyżej|Poniżej)\s+(\d+[,.]\d+)`.

5. **Volleyball:** May show 0 events during off-season or late hours (all matches played).

6. **Live events:** Present with `a.cardEvent.is-live` class. Time shows match minute (`"40' • P1"` = 40th minute, 1st period). Valid for live betting.

7. **Competition structure:** URLs encode competition ID (`c39431`) and match ID (`m1112013945405440`). These are stable identifiers for deduplication.

8. **Angular SPA:** All content is client-rendered. Must use Playwright with `wait_for_timeout` after navigation and scrolling for content to load.
