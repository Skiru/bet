# What bzzoiro can price, and what to say when it cannot

> **Historical (the archived pipeline, 2026-08-30/31).** bzzoiro is not a data
> source of `sofa` (CLAUDE.md: Sofascore and Superbet only); nothing here may be
> fetched, called or reproduced today. It is kept as the evidence of why "no
> evidence" is a complete answer. The sofa equivalents of a coverage hole are in
> `../SKILL.md` pattern 6.

Three of the nine losses on 2026-08-30/31 were on fixtures the source of record
cannot see at all. Not thinly covered — absent. There was no consensus price, no
team history, and no match stats before or after, so no verdict on those bets
was ever available.

## The league list was 83 long (measured 2026-08-31)

It was checked against the provider's own league endpoint then; that source is
no longer reachable from this repository and the check is not repeated.

Present, among others: Premier League, La Liga, Serie A, Bundesliga, Ligue 1 (+
Ligue 2), Eredivisie, Pro League, Liga Portugal (+ 2), Süper Lig, Ekstraklasa,
Allsvenskan, Eliteserien, Danish Superliga, Veikkausliiga, Parva Liga, Super
League Greece, Liga I, Brasileirão A/B, Liga Profesional, Primera A, Liga MX,
MLS, J1, CSL, Botola, NPL Queensland, English League One/Two/National League,
the domestic cups and the UEFA competitions.

**Absent, and each one cost money:**

| Fixture | Competition | Result |
|---|---|---|
| Hajduk Split – Lokomotiva Zagreb | Croatian HNL | lost |
| Sumgayit – Qarabag | Azerbaijan Premier League | lost |
| Aurora FC – Malacateco | Guatemala Liga Nacional | lost |
| Real España – Atlético Choloma | Honduras Liga Nacional | won |
| Real Madrid – Malaga | billed as La Liga; **not in the feed at all** for 2026-08-30 | won |

The last row deserves its own note. La Liga *is* covered, and bzzoiro's
2026-08-30 slate has Celta–Athletic and Deportivo–Valencia but no Real Madrid
fixture. A competition being covered does not mean the fixture in front of you
exists in the feed. Check the event, not the league.

## Coverage is also per-fixture

Inter Turku 1–0 KuPS (event 207305, Veikkausliiga) sits in a covered league.
`/events/207305/stats/` returns **every field null** — no shots, no corners, no
possession, no xG, for either side. Other Veikkausliiga matches the same day
have full stats; this one does not, before the bet and still now.

So `has_xg` and league membership are not sufficient. Call `/events/{id}/stats/`
and look at what came back before promising any read that depends on it.

## Tennis

`bzzoiro-tennis` answers:

```
{"error": "Sports Addon required", "code": "addon_required",
 "detail": "Tennis, CS:GO, darts, hockey, basketball and horse racing APIs
            require the Sports Addon ($5/mo)."}
```

Confirmed again 2026-09-01. Both tennis legs on the ledger are therefore
unpriceable, and reporting a read on them would be invention. This matches the
standing note of the time (`provider-entitlement-faults`, a memory note that is
not in this repository).

## How to say it

When there is no consensus and no stats, the answer is **"no evidence"**, and it
is a complete answer. Do not:

- substitute a league-wide constant and present it as a fixture read;
- reason from team names, reputation, or a league's general reputation for goals;
- let the absence of a contrary signal read as a positive one.

Do say which of the three is missing — the league, the fixture, or the stats
block — because they are fixed differently. A missing league is a product
boundary; a missing fixture may be a naming or date problem worth one more
lookup; a missing stats block is a data gap on an otherwise usable event, and
the scoreline and the consensus odds are still there.
