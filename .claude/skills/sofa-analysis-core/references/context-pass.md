# The web context pass - every match, every sport

Operator 2026-10-20: the statistics are half the read; the other half is what
no statistic holds. Every match not yet started gets this pass, after the
dossier (`dossier.md`) and before the verdicts. Sources by sport:
`context-sources.md` (the index) -> `sources-<sport>.md`. Why these rules:
`literature.md`.

## What the pass is for (measured, 2026-10-26)

The price already holds what is public and old: home advantage, form, the
referee's rate, table stakes, last week's injuries. Reads 10-13..10-25 removed
legs that realised exactly like the kept ones (-0.9 pp [-5.9, +4.2]): an
opinion about the match removes volume, not losers. The pass looks for two
things only:

1. **A defect of the leg as printed** - the match moved / postponed, a format
   the line does not assume, a prop player who does not start, a backup
   goalie under a goalie-dependent line, a CS2 stand-in under a roster-based
   line, a second squad, a market Superbet settles otherwise.
2. **A fact newer than the price** (or than the model's sample) acting
   through the leg's own variable - a confirmed XI / goalie / five, an
   absence announced since the price's `fetched_at_utc`, a referee change, a
   fan ban, an extreme condition.

Everything else - mood, narrative, "must-win", a derby, a preview's pick - is
read and named, and at most a WATCH when it acts through the leg's variable
by a named mechanism.

## The order - never reverse it

1. **Base rate first.** Write the leg's printed confidence as the outside
   view, and the expectation in the market's units (dossier / samples).
2. **Kill facts before the search** (premortem). Per match, write in one line
   which facts would break its legs ("Union bez Biondica -> gole Union 2.5
   OVER; deszcz nie zmienia nic") and **print that line in your output before
   the match's first WebSearch**. Search for those. More information raises
   confidence faster than accuracy - a list fixed before the search is what
   keeps the pass honest.
3. **Search** (budget below), starting from the dossier's `web_checklist` and
   the sport's mandatory checks (`sources-<sport>.md`, "Mandatory").
4. **Verdict per leg**: did a kill fact turn up, through which variable, on
   how many domains, published when relative to the price?

## Weight

| what you found | may carry |
|---|---|
| a defect of the leg as printed, on an artifact or two independent domains | `NO_BET` |
| a fact on two independent domains, newer than the price, breaking the leg's premise | `NO_BET` |
| a fact on one domain (named reporter / official channel), or a reasoned opinion, acting through **this leg's variable** by a named mechanism | at most `WATCH` |
| a mood report, a narrative, a derby, "they need the points" (`MORALE` / `MOTIVATION` / `DERBY`) | at most `WATCH`, only through the leg's variable by a named mechanism (operator 2026-10-20); the literature measures ~0 here - name it, KEEP by default |
| a tipster's pick, a preview's prediction | nothing - a lead to verify |
| what the price / model already carries (home advantage, the named referee's rate - football cards / fouls since 2026-10-21, form, table, closeness) | nothing, unless the **input changed** (a new referee, a neutral venue, closed doors) |
| rest, back-to-back | a note: rest is in no model (football / tennis show it in `schedule` / `context_flags`), the price probably holds it; a WATCH only through who rests, announced since the price |
| market-driver evidence from the dossier (`style.matchup`) | football only: at most `WATCH` as `RYNEK:` (core, "What a removal's reason must name") - not a web finding, written in **Styl gry i zestawienie** |
| nothing relevant | KEEP, with "nic istotnego dla tych nóg" in the section |

Source rank: the league / club / federation's own channel > a named beat
reporter > a national outlet > an aggregator > a fan site / forum (`opinia`)
> a tipster (a lead to verify, never a source). Volume is not weight: ten
aggregators copying one rumour are one domain.

Priors per tag (literature, to be confirmed by audit 7e / 7i): ABSENCES and
ROTATION carry real information; SCHEDULE some; CONDITIONS only when
extreme; MOTIVATION, MORALE and DERBY near zero on their own. A WATCH on
MOTIVATION / MORALE / DERBY needs the mechanism to reach the leg's variable
through a lineup ("dead rubber -> the coach named five reserves -> fewer
shots"), never the mood alone.

## Budget and the delta pass

- **First read of a match**: up to ~6 searches / fetches, the mandatory
  checks first; a leg on a printed builder or a chat slip may take more when
  a lead needs its second domain. Stop when the kill facts are answered.
- **A leg with `prior_analysis`** (the match was analysed earlier today -
  `read_set.py` sets it): read that section and, when it is a delta, the
  full pass it cites (`prior_analysis.full_pass_report`) first -
  `jq -r --arg a <report> --arg b <full_pass_report> '.events["<id>"][] | select(.report==$a or .report==$b) | .markdown' runs/sofa/<d>/analyses.json`; take
  its dossier and context findings as yours (cite them "[wcześniej: <report>,
  <recorded_at_utc>]"), and do a **delta pass** only: what can have changed
  since `recorded_at_utc` - a confirmed lineup / goalie / five now published,
  a late absence, a postponement - about 2 searches, more only when a lead
  needs its second domain. Redo the full pass when
  `prior_analysis.full_pass_at_utc` is empty (no earlier section made a full
  pass with a web source) or older than 6 h - a delta section never restarts
  that clock. Mark a delta section by citing "[wcześniej: ...]". The kill facts
  are inherited (restate them only when one changed). A full pass under
  1 h old with no lineup / goalie / five due since: no search at all - the
  delta reads only the dossier's fresh fields (`lineups` asked_at, line
  moves) and says so in its **Kontekst (web).** line ("delta: pełny przegląd
  <czas>, nic nowego"). The new legs still each get their own verdict.
- Queries that cannot return a scoreline (the fact and its period, never the
  two names alone). Pages published before the start only; a leaked result
  is named and the claim marked `CANNOT VERIFY`.
- A source that is blocked (Cloudflare, JS-only - `sources-<sport>.md` lists
  them) is not retried: use the named alternative or a site-limited search,
  and list the check under **Czego zabrakło**.
- Where context does not exist (ITF, youth / reserve leagues, most volleyball
  starting sixes, European hockey goalies) write `UNVERIFIED` and move on: a
  missing source is not a reason to remove a leg.

## Timing

Every leg has its price time (`04_offer.json` rung `fetched_at_utc`; a sport
leg `price_fetched_at_utc`). A fact published **after** that time is news the
price may not hold; one published days before is almost surely priced - name
which. A leg whose premise hangs on a lineup that is not out yet (a prop, a
goalie-dependent total) and whose start is close: say when the lineup comes
(`sources-<sport>.md`), and WATCH only when there is a concrete reason to
expect a change (a doubt, a rotation announced), never on the mere absence
of the XI.

## Tags and the report

Tag every claim `[WEB: <domain>, publ. <time>, fetched <UTC>]`; one domain
alone is `niepotwierdzone`, a view is `opinia`. A removal carrying a
`context` tag (`MOTIVATION`, `ROTATION`, `ABSENCES`, `DERBY`, `SCHEDULE`,
`CONDITIONS`, `MORALE`) names its source in `reason`. Context only removes;
it never raises a confidence or admits a leg.

Each match section has a **Kontekst (web)** block: the kill facts you
fixed, what you searched, what was found (tagged), what it does to which leg,
or "nic istotnego dla tych nóg". A KEEP `reason` carries:

1. the expectation in the market's units (from the dossier / samples),
2. at least one dossier fact (form, table, rest, map pool, line move),
3. the context finding (or "nic istotnego").

Good: `"rożne: oczekuję ~10 (Dewa 10.2 / Persijap 9.1 śr.), 15/18 > 7.5;
tabela 2. vs 18.; skład bez zmian, pogoda bez opadów [WEB: bmkg.go.id, publ.
10-20, fetched 06:20Z]"`. Not a read: `"15/18"`.

## The check

`scripts/sofa/check_analyst_report.py --report <path>` (`bet.sofa.report_check`;
analysts' and verifier's `_weryfikacja` reports) lists, by the label it
prints:

| finding | what is wrong |
|---|---|
| `KONTEKST` | a match with a KEEP has no "Kontekst (web)" |
| `DOSSIER` | the report never mentions the dossier |
| `SEKCJA BEZ TOKENU` | a read match's heading lacks its `sofa:<id>` |
| `TAG WEB BEZ DATY` | a `[WEB: …]` tag without `publ. <data>` |
| `FAKTY ZABÓJCZE` | a full section without its kill facts (a delta inherits them) |
| `W SKRÓCIE` | a read section, a delta included, without `**W skrócie:**` |
| `ZESTAWIENIE` | a full football section with a count-market read lacks the **Styl gry i zestawienie** paragraph and its table |
| `PRZECIW BEZ ODCZYTU` | a table row `ZESTAWIENIE PRZECIW` with no read of that match carrying a `line` |
| `KEEP ZBIORCZY` | a KEEP with `market: null` - one read per family |
| `KEEP BEZ UZASADNIENIA` | a KEEP reason that is a bare count or under 40 characters |
| `USUNIĘCIE BEZ FAKTU` | a WATCH / NO_BET without a dated WEB tag, a real `DEFEKT:` or (football WATCH) `RYNEK:` with a k/n - outside football `RYNEK:` counts as none, so does a `DEFEKT:` citing rest_days / games_7d / back-to-back / 2. noc / form / seria / h2h / tabela / a rating counts as none |
| `RYNEK TYLKO WATCH` | a NO_BET resting on `RYNEK:` |
| `RYNEK BEZ TAGU` | a `RYNEK:` WATCH without `context: "MARKET"` |
| `ŹRÓDŁO` | a context removal without a source |
| `WETO BEZ FAKTU` | a veto without a dated WEB tag or a real `DEFEKT:` (`RYNEK:` never) |

Order: write the report -> `check_analyst_report.py` until clean ->
`merge_reads.py --dry-run --read-set <file>` (core, "Output contract").
