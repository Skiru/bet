---
description: Rebuild one day's coupons file from the artifacts already on disk — no DISCOVER, no ENRICH, no provider stats calls. For when code changed, the analyst produced vetoes, or the offer went stale.
argument-hint: dzisiaj | jutro | YYYY-MM-DD
---

Rebuild `runs/<date>/<date>_kupony.md` from artifacts that already exist. This is
the last mile of `/run-day` on its own: ANALYZE's sheet in, the operator's file
out. **Nothing here re-discovers or re-enriches a day**, because both cost quota
and DISCOVER on a second pass *shrinks* the slate — a fixture found once by a
provider that has since spent its budget does not come back (see the memory note
`rerunning-a-day-resume-at-enrich`).

Use it when: the pipeline's code changed since the sheet was built, the analyst
handed back vetoes or downgrades, the Superbet offer behind the file has gone
stale, or you simply want the file regenerated. Do **not** use it to fix a thin
day — see the hard rules.

Run every step. **Do not stop to ask permission between them**; nothing in this
command writes to a provider or to the DB except the optional re-analyse in
Step 3c, which is offline. Stop only where a step says to stop.

## Step 0 — Resolve the day and take inventory

`$ARGUMENTS` is `dzisiaj`/`today`, `jutro`/`tomorrow`, or `YYYY-MM-DD`; empty
means today. Resolve in **UTC** — the pipeline's betting day is UTC, and
`ts` fields in the artifacts print local time unlabelled (memory:
`pipeline-timestamps-are-local-not-utc`):

```bash
date -u +%F                        # dzisiaj
date -u -v+1d +%F                  # jutro (macOS)
ls -la runs/<date>/
```

State the resolved date, then check the one input that is not optional:

* **`<date>_event_dossiers_stats_sheet.json` missing** → there is nothing to
  rebuild. Say so and stop: the day needs `/run-day <date>`, not this command.
* **`<date>_event_list.json` missing** → stop as well. Without it the coupon
  cannot name its fixtures *and* ANALYZE's best-of-five tennis gate goes
  silently inert, which puts ATP tautologies at the top of the sheet (memory:
  `analyze-event-list-is-not-optional`).
* Everything else — `_analyst_vetoes.json`, `_market_context.json`,
  `_superbet_offer.json`, `_tipster_signal.json`, `_tipster_claims.json` — is
  optional, and **a missing file is the default healthy state, not an error.**
  Say which ones are absent and what each absence costs: no offer means no
  price column and therefore no value test at all; no vetoes means the
  analyst's read is not in the file.

All of them resolve from `--date` alone. Do not pass paths unless one lives
somewhere non-default.

## Step 1 — Live day or played-out day?

This single fact decides three flags, so establish it before touching anything:

```bash
python3 - <<'PY'
import json, datetime, pathlib
d = json.loads(pathlib.Path("runs/<date>/<date>_event_list.json").read_text())
now = datetime.datetime.now(datetime.timezone.utc)
ahead = [e for e in d["events"]
         if datetime.datetime.fromisoformat(e["start_time"]) > now]
print(f"{len(ahead)} of {len(d['events'])} fixtures still ahead of kickoff")
print("offer generated:", json.loads(pathlib.Path(
    "runs/<date>/<date>_superbet_offer.json").read_text())["generated_at"])
PY
```

A day is usually *partly* played, so the question is not "is the day over" but
"is this file meant to be bet or read":

* **Rebuilding a file to bet from** → no `--include-started`. Fixtures that have
  kicked off are dropped and reported under `excluded.kickoff_passed`; the freed
  single slots refill from the sheet, so the count does not drop. This matters
  most on a same-day rebuild started late: without it a match that finished
  overnight sits at the top of the file with 84% confidence beside it, looking
  like the best bet of the day. Refresh the offer (Step 3b) and verify the
  fixtures at the end (Step 5).
* **Reviewing a past day, or reproducing an earlier file** → pass
  `--include-started`, or every row is filtered and exit code 1 reads as "thin
  day" when the day was full. Do **not** refresh the offer: the point of a
  review rebuild is that it is reproducible, and a finished match re-priced
  against a board that has moved on is a fiction. Say in the report that the
  file contains started fixtures and is not bettable.

If none are ahead, only the second reading is available — say so rather than
producing an empty file and calling the day thin.

## Step 2 — Preserve the file you are about to replace

The whole value of this command is the before/after, and `build_coupons.py`
overwrites in place:

```bash
mkdir -p runs/<date>/_pre_rebuild_$(date -u +%H%M)
cp runs/<date>/<date>_kupony.md runs/<date>/<date>_coupons.json \
   runs/<date>/_pre_rebuild_$(date -u +%H%M)/
```

Name the directory in your report. Do not delete an earlier `_pre_*` directory
— those are the only record of what the operator was shown before.

## Step 3 — Three freshness gates, in this order

### 3a — Is the offer filed under the current market names? (always)

`SuperbetOfferV1` stores each line under a *canonical* market name resolved at
collection time. When that mapping changes, an offer already on disk is filed
under the old name and the new sheet asks for a market the artifact does not
contain — it does not error, it reports the line as **not offered**. That is
exactly what happened on 2026-09-03 when `Liczba kartek` was repointed from
`cards_total` (yellows) to `cards_points_total` (booking points): the day's own
offer still filed the Grenal's five-rung card ladder under the old name, so
every card row priced against no price at all.

Probe first, apply only if there is something to re-file:

```bash
python3 scripts/simple/renormalise_offer_markets.py \
  --offer runs/<date>/<date>_superbet_offer.json --dry-run
```

Zero lines to re-file is the healthy answer on any offer collected by current
code — say so and move on. Non-zero → re-run without `--dry-run` and report the
count per market. This is a re-normalisation, not a repair: `classify_market`
is re-run on the stored `source_market_name`, the same input the original
normalisation used. Nothing is guessed and nothing is re-fetched.

### 3b — Is the offer stale? (live rebuilds only)

The coupon is read minutes after it is written and the offer behind it can be
hours old. On 2026-09-02 a stale offer reported 52 VALUE rows against the 82 the
live board actually had. If `generated_at` from Step 1 is more than ~45 minutes
old and the day is live, add `--refresh-offer` in Step 4 — about one request per
matched fixture plus one for the board, roughly 110 on a normal slate, against
**no metered quota**. It overwrites the offer artifact, which is why it stays
off by default and off entirely on a review rebuild.

`--refresh-offer` also makes 3a moot, since the board is re-collected by current
code. Run 3a anyway when you are not refreshing.

### 3c — Was the sheet built by current code?

Timestamps lie about this — a commit made *after* a run is normal — so check the
sheet's **content** for the fingerprints current code leaves:

```bash
python3 - <<'PY'
import json, pathlib
rows = json.loads(pathlib.Path(
    "runs/<date>/<date>_event_dossiers_stats_sheet.json").read_text())["rows"]
markets = {r["market"] for r in rows}
print("cards_points_total present:", "cards_points_total" in markets)
print("cards_total present (stale):", "cards_total" in markets)
print("possession present (stale):", any("possession" in m for m in markets))
print("rows with mode:", sum(1 for r in rows if r.get("mode") is not None), "/", len(rows))
PY
```

Current code gives: `cards_points_total` present, `cards_total` and
`possession` absent, `mode` set on **every** row. If any of those is wrong the
sheet predates the merge of `edge-integrity-2026-09-03` and the coupon built
from it will price the wrong quantity. Re-analyse — offline, no provider calls:

```bash
python3 scripts/simple/run_analyze.py \
  --dossier runs/<date>/<date>_event_dossiers.json \
  --event-list runs/<date>/<date>_event_list.json \
  --market-context runs/<date>/<date>_market_context.json \
  --superbet-offer runs/<date>/<date>_superbet_offer.json \
  --tipster-signal runs/<date>/<date>_tipster_signal.json \
  --output-dir runs/<date>
```

`--event-list` is not optional here even though the CLI calls it so. Note in
your report that the sheet was rebuilt, not just the coupon.

**If the dossiers themselves are missing or predate the merge**, stop. Resuming
at ENRICH is a different operation with different risks — pin the clock with
`run_enrich.py --now <ISO>` so the diff is about code rather than about which
matches kicked off, and read
`docs/SIMPLE_STATS_RUNBOOK.md` first. Hand that decision back to the operator
rather than starting it inside this command.

### 3d — Fresh analyst vetoes? (optional, only when the read may have changed)

A rebuild reuses `<date>_analyst_vetoes.json` as it stands. When the reason for
the rebuild is that the *read* changed — a referee named since the morning, a
lineup out, a second-leg aggregate the morning pass never saw, a tennis time
moved — re-run the analyst for the affected sport before building:
`bet-analyst-football` for football events, `bet-analyst-tennis` for tennis
(both read `runs/<date>/`, neither writes). Merge and validate their JSON
exactly as `/run-day` Step 5 does, save it over the old file, and say in the
report which entries changed. Do not re-run an analyst just to make the file
fuller; its job is to remove rows, not to add them.

## Step 4 — Build

```bash
python3 scripts/simple/build_coupons.py --date <date> \
  [--include-started]   # review rebuild only
  [--refresh-offer]     # live rebuild with a stale offer only
```

No other flags. In particular: `--bar` stays at its default `p_central`, which
measures −0.000 against realised results over 5,036 settled rows; pass `p_low`
only to reproduce a file built before that switch, and say so if you do.

Exit code 1 means nothing cleared the bar. **That is a real answer about a thin
day, not an error**, and not a reason to change a threshold.

## Step 5 — Read the diff, then verify the fixtures

Say what actually moved, per row, with a reason — the operator has already seen
the old file:

```bash
python3 - <<'PY'
import json, pathlib
def key(s):  return (s["event_id"], s["market"], s.get("subject"), s["line"], s["direction"])
def load(p): return {key(s): s for s in json.loads(pathlib.Path(p).read_text())["singles"]}
old = load("runs/<date>/_pre_rebuild_<HHMM>/<date>_coupons.json")
new = load("runs/<date>/<date>_coupons.json")
for k in sorted(old.keys() - new.keys()): print("GONE   ", k)
for k in sorted(new.keys() - old.keys()): print("NEW    ", k)
for k in sorted(old.keys() & new.keys()):
    a, b = old[k], new[k]
    if a.get("tier") != b.get("tier") or round(a.get("min_acceptable_odds") or 0, 2) != round(b.get("min_acceptable_odds") or 0, 2):
        print("MOVED  ", k, a.get("tier"), "->", b.get("tier"),
              a.get("min_acceptable_odds"), "->", b.get("min_acceptable_odds"))
PY
```

Then read the new file's own header and report **its** numbers verbatim: the bar
basis and its two caps, the market `k`, every gate's row count, and the supply
funnel. **Never recompute a threshold in prose** — every one of them comes from
tested code in `src/bet/simple_stats/coupons.py`, and a minimum odds re-derived
by hand is exactly the failure `wilson_lower_bound` exists to prevent. If a
figure looks wrong, read the function, not your arithmetic.

**Read the funnel before calling a day thin.** The ceiling above it is the
provider of record's midweek coverage, not our matcher: on 2026-09-03 Superbet's
board carried 150 football fixtures in window and bzzoiro carried 29, of which
the matcher claimed 24 — 83% of what existed, 16% of what was offered. A short
file on a Wednesday is usually that, not a bug.

**On a live rebuild only**, verify every fixture that reached the file. The
script filters on the clock, and a clock cannot see a postponement, a venue
switch or an abandonment:

```
mcp__bzzoiro__get_match_detail(match_id = <event's source_ids.bzzoiro>)
```

Read `status` and `event_date`. Anything but `notstarted`, or an `event_date`
that no longer matches the artifact's `start_time` → strike that fixture from
the coupons file and say why. A moved kickoff invalidates a bet without changing
a single statistic. Football is uncapped, so a dozen fixtures costs a dozen free
calls. An event with no `source_ids.bzzoiro` could not be verified — say that,
rather than implying it was. **Never present an unverified coupon as verified**;
silence about a check you skipped reads exactly like a check that passed.

## Step 6 — Report back

Short. The operator opens the file, not the chat:

```
KUPONY:   runs/<date>/<date>_kupony.md — <n> singli (<n> warte ceny), <n> BB
POPRZEDNI: runs/<date>/_pre_rebuild_<HHMM>/
POWÓD:    <what made the rebuild necessary: code / vetoes (piłka|tenis) / stale offer>
ZMIANY:   <n> zniknęło, <n> nowych, <n> przesunięć — <the one that matters most, one line>
OFERTA:   <refreshed at <time> | reused from <generated_at> | <n> lines re-filed>
SPRAWDZONE: <n> meczów przez bzzoiro, <n> wykreślonych
UWAGA:    <the single biggest weakness of the file, one line>
```

Do not paste the file's tables into the chat.

## Hard rules

- **Never re-run DISCOVER to rebuild a coupon.** It cannot add a fixture and it
  can lose several.
- **Never widen a gate to make the file fuller.** `TIER_MARGIN` and `p_low` are
  not inputs to this command. If seven of fifteen singles beat their price, the
  answer is seven — the market being roughly efficient is the finding, not a
  bug, and only ~10 rows a day have ever beaten their own bar.
- **Never print a combined / Bet Builder / parlay price**, however hedged. Legs
  in one match are positively correlated, so the product understates the slip's
  probability in the direction that flatters the bet. The contract types that
  field `None`; do not reintroduce it in prose.
- No stake sizing. No EV. No automated placement.
- Never invent a number, a fixture or an odds quote. Quoted `market_price` is
  the best of ~88 bookmakers and **Superbet is not among them** — label it a
  market reference, never the operator's price.
- Never read, echo or log `.env` values, keys or tokens.
