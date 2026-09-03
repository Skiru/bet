# Decision record: ESPN/Bzzoiro football cooperation

**Stan:** zamknięte — nie ma pracy do wykonania · **Punkt odniesienia:**
`runs/2026-09-03/` (135 football dossiers), kod na `main` @ `8233602b`.

This document has been rewritten twice, each time smaller.

1. The **first** version was an 89-section spec assuming a from-scratch global
   football catalog: new provider registry entries, a seasons table, a global
   ESPN scoreboard, a second identity subsystem, a 20-gate E2E harness.
   Refuted: that machinery already exists and already works (§1).
2. The **second** version replaced it with two workstreams — WS1 "surface
   unpriceable cards/fouls/SOT evidence", WS2 "controlled experiment on
   `skip_corroborators`". **Both are refuted by measurement against
   `runs/2026-09-03/` (§2, §3).** WS1 targets a condition that does not exist;
   WS2's ceiling is three fixtures a day.
3. This version records why, so the topic is not reopened a fourth time from
   the same wrong premise.

The conclusion is negative and that is the finding: **ESPN/Bzzoiro football
cooperation is complete. Nothing here is worth building.** The football
pipeline's real constraint is elsewhere and is named in §5.

Every claim below is a `file:line` citation or a number reproduced from
`runs/2026-09-03/2026-09-03_event_dossiers.json` /
`..._stats_sheet.json` / `..._coupons.json`. The commands that produce each
number are in §6.

---

## 1. What already works — verified, do not rebuild

- **Discovery.** Football fixtures come from `OddsAPIEventsAdapter`,
  `HighlightlyDiscoveryAdapter`, `BzzoiroDiscoveryAdapter`
  ([discover.py:691-694](../src/bet/simple_stats/discover.py#L691)). ESPN is
  **not** a discovery source for football, by design: it is name-driven
  ([providers.py:55](../src/bet/simple_stats/providers.py#L55)) and resolved
  against each `EventRecord`'s team names, so it inherits fixture identity
  from the shared `EventRecord`. There is no cross-provider "is this the same
  real match" step to build.

- **Cross-provider fusion.** `_cross_provider_agreement`
  ([analyze.py:1056](../src/bet/simple_stats/analyze.py#L1056)) buckets
  same-metric `ProviderValue` observations by day, fuzzy-clusters by opponent,
  and returns `AGREE`/`DISAGREE`/`SINGLE_SOURCE`/`NOT_APPLICABLE`, gated by
  `MIN_CORROBORATED_MATCHES = 2`
  ([analyze.py:1034](../src/bet/simple_stats/analyze.py#L1034)). It is
  provider-name-agnostic and metric-agnostic by construction — literally the
  same code tennis rides for `total_games`. Disagreeing values are never
  averaged away. **This is the cooperation mechanism, and it works.**

- **The gate that prevents a known failure mode.** `_build_tasks`
  ([enrich.py:152](../src/bet/simple_stats/enrich.py#L152)) only schedules
  espn-football once bzzoiro already has native identity for the fixture.
  Before it (pre-2026-09-02) espn-football was the *sole* source of 578 rows
  wearing the label of corroboration. Confirmed live in `runs/2026-09-03`:
  espn-football appears in 14 of 135 football dossiers and bzzoiro is present
  in **all 14**. Zero leakage.

- **Identity infrastructure.** `TeamSourceAliasRepo` /
  `resolve_provider_team_id()` / `build_provider_team_variants()`
  ([provider_identity.py](../src/bet/provider_identity.py)) back espn-football's
  name-driven path. Bzzoiro is native-id-driven
  ([providers.py:91](../src/bet/simple_stats/providers.py#L91)) and needs none
  of it. **No new identity subsystem is needed for either provider.**

- **The two providers do agree.** Of 866 football `AGREE` rows on
  `runs/2026-09-03`, 629 (73%) involve espn-football — 474 bzzoiro+espn pairs
  and 155 bzzoiro+espn+highlightly triples. The cooperation produces exactly
  what it was built to produce.

## 2. Why WS1 is void: the evidence is already priced end-to-end

The previous version claimed `cards_total`, `fouls_total` and
`shots_on_target_total` "can never receive a price or a signal" and are
"discarded at the pricing boundary", and proposed adding a consumer to surface
them as evidence-only rows.

**Every part of that is false.** From `runs/2026-09-03`:

| market | sheet rows | AGREE | Superbet field | Superbet `OFFERED` | `market_signal` |
|---|---|---|---|---|---|
| `cards_total` | 152 | 104 | 152 | 134 | none |
| `shots_on_target_total` | 190 | 142 | 190 | 126 | none |
| `fouls_total` | 112 | 74 | 112 | 22 | none |
| `corners_total` | 258 | 186 | 258 | 258 | present |
| `goals_total` | 262 | 60 | 262 | 262 | present |

These rows are **not absent, not dropped, and not unpriced**:

- They are in `..._stats_sheet.json` today, with full `p_low`, `hit_rate`,
  `sample_size` and `cross_provider_agreement`.
- They carry a **live Superbet price** — e.g. a `cards_total` row with
  `{"availability": "OFFERED", "price": 1.48, "source_market_name": "Liczba
  kartek"}`. Per [superbet-is-the-only-real-price], that is *the* price the
  operator can take; bzzoiro's ~88 bookmakers do not include Superbet.
- They reach the **top sheet**: 36 `shots_on_target_total`, 23 `cards_total`,
  10 `fouls_total` rows of 3,998.
- They reach the **final coupon**: of 15 singles on
  `2026-09-03_coupons.json`, one is `cards_total`, one `fouls_total`, one
  `cards_for`, one `fouls_for`.

The single thing these families lack is the `market_signal` column — bzzoiro's
odds-feed-vs-model triangulation. That absence is **correct and deliberate**,
not a gap: bzzoiro's feed publishes no cards, fouls or SOT market
([contracts.py:911](../src/bet/simple_stats/contracts.py#L911), comment at
907-910) and the CatBoost model publishes no probability for them, so
`SIGNAL_MARKETS` ([market_context.py:415](../src/bet/simple_stats/market_context.py#L415))
deliberately omits them and `market_signal_for_row`
([market_context.py:609](../src/bet/simple_stats/market_context.py#L609))
returns `None`. Its docstring already distinguishes `None` ("not the kind of
row a signal can address") from `NO_MARKET_DATA` ("in scope, data absent") and
names a cards row as the worked example. Extending `SIGNAL_MARKETS` would
require inventing a probability from nothing.

**WS1 would have shipped a no-op** — a second, redundant rendering of rows the
sheet already carries — and its acceptance criterion ("a row … appears in
output instead of being absent") would have passed against `main` before any
code was written.

## 3. Why WS2 is not worth running: the ceiling is three fixtures

WS2 proposed shadow-running espn-football ungated on bzzoiro-blind fixtures and
backtesting whether espn-only rows hit at a usable rate.

The population it would measure is much smaller than the plan assumed. On
`runs/2026-09-03`, of 135 football fixtures:

```
109  bzzoiro never discovered the fixture  -> blocked by SlateGate rule 1
 14  of those 109 are in a competition ESPN's name map even resolves
  3  of those 14 also carry a Superbet price
```

The other 95 are `AFC U20 Asian Cup` (20), `Liga Alef` (6), `Kazakhstan First
Division` (5), then a long tail of `Copa Uruguay`, `Iraqi League`,
`Bulgaria Second League`, `1. Lig` and the like at 3-4 fixtures each —
leagues ESPN has no team directory for, which
`_provider_client` correctly refuses via `ProviderLeagueUnsupported`
([providers.py:1228](../src/bet/simple_stats/providers.py#L1228)) rather than
silently answering with an `eng.1` club.

So the maximum yield of relaxing the gate is **three actionable fixtures a
day**, each single-source ESPN — 9 metrics
([providers.py:163](../src/bet/simple_stats/providers.py#L163)) against
bzzoiro's 55, which is precisely the "first opinion from the weaker instrument
wearing the label of a second one" the gate was built to stop. At three
fixtures a day, the evidence bar WS2 set for itself (statistically
distinguishable from zero, per
[bet_builder_draft.py:342](../src/bet/simple_stats/bet_builder_draft.py#L342))
cannot be cleared inside any useful horizon.

**Do not relax `skip_corroborators`.** Not "not yet, pending a backtest" —
the backtest is not worth the slate it would take to run.

## 4. Rejected outright (evidence already in this repo)

- **Do not require AGREE for CALL tier.** Tried and removed 2026-09-02 after
  backtesting: AGREE − SINGLE_SOURCE = **+0.4pp, 95% CI [−2.3, +3.4]**, 37.6%
  of resamples negative ([bet_builder_draft.py:342-372](../src/bet/simple_stats/bet_builder_draft.py#L342)).
  This is also why "more ESPN coverage" has no value on its own: the quantity
  ESPN produces has been measured against real results and predicts nothing.
- **Do not extend `MARKET_CODES` or `SIGNAL_MARKETS`** to cover cards/fouls/SOT.
  Both are closed to what bzzoiro's feed and the model actually publish; adding
  entries would manufacture a signal, the one failure mode
  `market_signal_for_row` exists to prevent.
- **Do not build a second provider registry**, a global ESPN scoreboard client,
  a seasons table, or revive `enrichment/football/` /
  `football_data_foundation/` — all dormant and unreferenced by `simple_stats`.
- **Do not touch tennis contracts, providers, or gates.** `PROVIDER_NAMES`
  ([contracts.py:15](../src/bet/simple_stats/contracts.py#L15)) and
  `_cross_provider_agreement` are shared. Nothing in this document changes them.

## 5. The real constraint, and where it belongs

The number that matters on this slate is not in the cooperation layer at all:

> **113 of 135 football dossiers (84%) are empty** — zero observations from any
> provider. 109 of them because bzzoiro never discovered the fixture
> (`SlateGate.verdict` rule 1,
> [enrich.py:677](../src/bet/simple_stats/enrich.py#L677)).

Only 22 football fixtures carry any data, and ESPN corroborates 14 of those 22.
The football pipeline's output is bounded by **bzzoiro's discovery coverage**,
not by how well its two providers cooperate on the fixtures bzzoiro does see.

That is a real, large problem. It is **out of scope for this document** and
must not be solved by loosening a corroborator gate — §3 shows ESPN reaches at
most 3 of the 109 with a price. It belongs with discovery/provider coverage
(cf. [highlightly-drives-discovery], [coupon-value-is-the-binding-constraint]),
where the question is which primary-grade source can address those leagues at
all — not whether a 9-metric corroborator may stand in for a 55-metric source
of record.

## 6. Reproducing every number here

```bash
R=runs/2026-09-03
# §1 espn/bzzoiro co-occurrence, §5 empty dossiers
python3 - <<'PY'
import json, collections
d = json.load(open('runs/2026-09-03/2026-09-03_event_dossiers.json'))
fb = [x for x in d['dossiers'] if x['sport'] == 'football']
slots = ('team_a_l10', 'team_b_l10', 'h2h')
present, empty = collections.Counter(), 0
for x in fb:
    provs = {pv['provider'] for mv in x['metrics'].values()
             for s in slots for pv in (mv.get(s) or [])}
    if not provs:
        empty += 1
    for p in provs:
        present[p] += 1
espn = [x for x in fb if any(pv['provider'] == 'espn-football'
        for mv in x['metrics'].values() for s in slots for pv in (mv.get(s) or []))]
both = [x for x in espn if any(pv['provider'] == 'bzzoiro'
        for mv in x['metrics'].values() for s in slots for pv in (mv.get(s) or []))]
print('football', len(fb), 'empty', empty, 'by provider', dict(present))
print('espn', len(espn), 'espn+bzzoiro', len(both))
PY

# §2 the table: rows, AGREE, superbet, market_signal per market
python3 - <<'PY'
import json, collections
rows = json.load(open('runs/2026-09-03/2026-09-03_event_dossiers_stats_sheet.json'))['rows']
for m in ('cards_total', 'shots_on_target_total', 'fouls_total',
          'corners_total', 'goals_total'):
    rs = [r for r in rows if r.get('market') == m]
    av = collections.Counter((r.get('superbet') or {}).get('availability') for r in rs)
    print(f'{m:22s} rows={len(rs):4d}'
          f' AGREE={sum(1 for r in rs if r.get("cross_provider_agreement") == "AGREE"):4d}'
          f' superbet={sum(1 for r in rs if r.get("superbet")):4d}'
          f' signal={sum(1 for r in rs if r.get("market_signal")):4d} {dict(av)}')
PY

# §2 coupon singles by market
python3 -c "import json,collections; print(collections.Counter(s['market'] for s in json.load(open('$R/2026-09-03_coupons.json'))['singles']))"

# §3 ESPN reachability of the bzzoiro-blind fixtures
python3 - <<'PY'
import json, collections
from bet.api_clients.espn import get_espn_league_for_competition
d = json.load(open('runs/2026-09-03/2026-09-03_event_dossiers.json'))
evs = {e['event_id']: e for e in
       json.load(open('runs/2026-09-03/2026-09-03_event_list.json'))['events']}
priced = {r['event_id'] for r in
          json.load(open('runs/2026-09-03/2026-09-03_superbet_offer.json'))['events']
          if r.get('event_id') and (r.get('market_count') or 0) > 0}
blocked = [x['event_id'] for x in d['dossiers'] if x['sport'] == 'football'
           and any('did not discover this fixture' in str(g) for g in (x.get('data_gaps') or []))]
mapped = [e for e in blocked if (c := (evs.get(e) or {}).get('competition'))
          and get_espn_league_for_competition(c)]
print('blocked', len(blocked), 'espn-mappable', len(mapped),
      'and priced', sum(1 for e in mapped if e in priced))
print(collections.Counter((evs.get(e) or {}).get('competition') for e in blocked
      if e not in mapped).most_common(8))
PY
```

## 7. If this is reopened

Reopen only with a number that contradicts §2 or §3 — for example a slate where
espn-mappable *and* Superbet-priced bzzoiro-blind fixtures run into the dozens
rather than three, sustained across enough days to power the
[bet_builder_draft.py:342](../src/bet/simple_stats/bet_builder_draft.py#L342)
bar. Re-run §6 on that slate first. A plan that begins "ESPN and bzzoiro should
cooperate better" without such a number is this document again.

No code change is proposed. No tests are needed, because nothing ships. The
`simple_stats` suite's current baseline (69 known-failing tests, 23 collection
errors in the quarantined `pipeline/**` stack) is untouched by this document.
