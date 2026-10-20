# The web context pass - every match, every sport

Operator 2026-10-20: the statistics are half the read; the other half is
what no statistic holds. Every match not yet started gets this pass, after
the dossier (`dossier.md`) and before the verdicts. Sources by sport:
`context-sources.md`.

## What to look for

Start from the dossier's `web_checklist`, then what its blocks raise (a new
CS2 name, a back-to-back, a losing run, a moved line). Search in the match's
own language too - local press, the clubs' / teams' / players' channels.

1. **News and facts** - lineups and absences, injuries, suspensions, a
   stand-in, the starting goalie / setter, a postponement, a format change.
2. **Conditions** - weather at the venue at the local start hour (rain,
   wind, heat, snow, a heavy pitch), roof, altitude, travel. Outdoor only.
3. **Morale and the backstage** - dressing-room conflict, a coach under
   pressure or just sacked, unpaid wages, a strike or boycott, fan protests,
   a dispute with the federation, an organisation in turmoil (CS2), a
   player's public row.
4. **What the result is worth** - stakes, a decided tie, a dead rubber, the
   next match they rest for.
5. **Opinions** - previews, journalists, coaches' and players' words, a
   tipster's *reasoning* (never a pick alone).

Budget: up to ~8 searches / fetches per match; more for a leg on a printed
builder or a chat slip when a lead needs a second domain. Queries that cannot
return a scoreline (the fact and its period, never the two names alone). Pages
published before the start only; a leaked result is named and the claim
marked `CANNOT VERIFY`.

## How much it weighs

| what you found | may carry |
|---|---|
| a fact on two independent domains | `NO_BET` (a defect of the leg as printed) |
| a fact on one domain, a reasoned opinion, a mood report | at most `WATCH`, and only through **this leg's variable** - name the mechanism ("ulewa w Tangerang o 19:00 -> mniej dośrodkowań i rożnych"), never "atmosfera zła" alone |
| nothing relevant | KEEP, with "nic istotnego dla tych nóg" in the section |

Context only removes; it never raises a confidence or admits a leg. Tag
every claim `[WEB: <domain>, publ. <time>, fetched <UTC>]`; one domain alone
is `niepotwierdzone`, a view is `opinia`. A removal carrying a `context` tag
(`MOTIVATION`, `ROTATION`, `ABSENCES`, `DERBY`, `SCHEDULE`, `CONDITIONS`,
`MORALE`) names its source in `reason`. `UNVERIFIED` is an honest answer
for a source that does not exist (ITF, a youth league) - write it rather
than invent one.

## What the report shows

Each match section has a **Kontekst (web)** paragraph: the queries' topics,
what was found (tagged), what it does to which leg, or "nic istotnego dla
tych nóg". A KEEP `reason` carries three things:

1. the expectation in the market's units (from the dossier / samples),
2. at least one dossier fact (form, table, rest, map pool, line move),
3. the context finding.

Good: `"rożne: Dewa 10.2 / Persijap 9.1 śr., 15/18 > 7.5; tabela 2. vs 18.;
pogoda Tangerang 19:00 bez opadów [WEB: bmkg.go.id, publ. 10-20, fetched
06:20Z]"`. Not a read: `"15/18"`.

## The check

`scripts/sofa/check_analyst_report.py --report <path>` (`bet.sofa.report_check`)
lists what is missing: a KEEP match without "Kontekst (web)", a report that
never mentions the dossier, a KEEP reason that is a bare count or under 40
characters, a context removal without a source. The project's PostToolUse
hook runs the same check on every report written and sends the findings back
- rewrite the report until it is clean, then validate with `merge_reads.py
--dry-run`.
