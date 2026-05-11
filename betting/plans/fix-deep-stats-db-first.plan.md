# Plan: Fix deep_stats_report.py — DB Column Names, ESPN Rendering, DB-First Loading

**Created:** 2026-05-11
**Priority:** P1 > P2 > P3
**Files affected:** `scripts/deep_stats_report.py` (primary), `scripts/db_data_loader.py` (minor)

---

## Problem Summary

`deep_stats_report.py` has 3 categories of bugs causing silent data loss:

1. **Wrong SQL column names** (P1 — CRITICAL): 4 SQL queries reference non-existent columns (`team_name`, `player_name`, `position`, `zone`). All fail silently via `except Exception: pass`, causing data quality scores to always miss injury/standings points.
2. **ESPN data not rendered** (P2): ESPN enrichment data is loaded into `stats_a["espn_enrichment"]` / `stats_b["espn_enrichment"]` but no section builder renders it in the markdown report.
3. **JSON-only candidate loading** (P3): Violates R2 (DB-FIRST). No DB loading path exists for shortlist/pool candidates.

---

## Phase 1 — Fix Broken SQL Column Names (P1 — CRITICAL)

**Root cause:** All 4 broken queries use `team_name` to query tables that use `team_id` (INTEGER FK → `teams.id`). They fail silently because every query is wrapped in `except Exception: pass`.

**Fix strategy:** Create a shared helper `_resolve_team_ids()` that uses `TeamRepo.resolve()` (the canonical pattern from `db_data_loader.py` and `repositories.py`). Then fix each query to use `team_id` with proper column names. Replace all `except Exception: pass` with `except Exception as e: print(...)`.

### Task 1.1 — Add `_resolve_team_ids()` helper function

**[MODIFY]** `scripts/deep_stats_report.py`

Add a new helper function in the "Helpers" section (after `_safe_avg`, around line 58):

```python
def _resolve_team_ids(conn, team_a: str, team_b: str, sport: str) -> tuple[int | None, int | None]:
    """Resolve team names to DB IDs via TeamRepo.resolve().

    Returns (team_id_a, team_id_b). Either may be None if not found.
    """
    from bet.db.repositories import SportRepo, TeamRepo

    sr = SportRepo(conn)
    s = sr.get_by_name(sport)
    if not s:
        return None, None

    tr = TeamRepo(conn)
    ta = tr.resolve(team_a, s.id)
    tb = tr.resolve(team_b, s.id)
    return (ta.id if ta else None), (tb.id if tb else None)
```

**Rationale:** Avoids duplicating `SportRepo.get_by_name() → TeamRepo.resolve()` in 4 different locations. Matches the pattern used in `db_data_loader.py` lines 173-185 (`load_team_form_from_db`) and `load_espn_enrichment_for_team`.

**Definition of done:**
- [ ] Function exists in the Helpers section of `deep_stats_report.py`
- [ ] Imports `SportRepo`, `TeamRepo` from `bet.db.repositories`
- [ ] Returns `(None, None)` if sport not found
- [ ] Returns `(id, None)` or `(None, id)` if only one team resolves
- [ ] No external test needed — will be validated through tasks 1.2-1.5

---

### Task 1.2 — Fix `compute_data_quality()` injuries query (lines 100-105)

**[MODIFY]** `scripts/deep_stats_report.py`

**Current (BROKEN):**
```python
row = conn.execute(
    "SELECT COUNT(*) FROM injuries WHERE team_name IN (?, ?)",
    (stats_a.get("team", ""), stats_b.get("team", "")),
).fetchone()
```

**Problem:** `injuries` table has `team_id` (INTEGER), not `team_name` (TEXT). Column `athlete_name` exists, not `player_name`. Query always fails → `injuries_ok` is always `False` → data quality score always misses +1 point.

**Fix:** Use `_resolve_team_ids()` to get IDs, then query by `team_id`:

```python
# Also check DB injuries table
if not injuries_ok:
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(
                conn, stats_a.get("team", ""), stats_b.get("team", ""),
                sport,
            )
            ids = [i for i in (tid_a, tid_b) if i is not None]
            if ids:
                placeholders = ",".join("?" * len(ids))
                row = conn.execute(
                    f"SELECT COUNT(*) FROM injuries WHERE team_id IN ({placeholders})",
                    ids,
                ).fetchone()
                if row and row[0] > 0:
                    injuries_ok = True
    except Exception as e:
        print(f"[deep_stats] DB injuries check failed: {e}")
```

**Note:** The `sport` variable is available as a parameter of `compute_data_quality(stats_a, stats_b, h2h, sport)`.

**Definition of done:**
- [ ] Query uses `team_id IN (...)` instead of `team_name IN (?, ?)`
- [ ] Uses `_resolve_team_ids()` for name-to-ID resolution
- [ ] `except Exception: pass` replaced with `except Exception as e: print(...)`
- [ ] Handles case where one or both teams don't resolve (empty `ids` list → skip query)

---

### Task 1.3 — Fix `compute_data_quality()` standings query (lines 118-121)

**[MODIFY]** `scripts/deep_stats_report.py`

**Current (BROKEN):**
```python
row = conn.execute(
    "SELECT COUNT(*) FROM standings WHERE team_name IN (?, ?)",
    (stats_a.get("team", ""), stats_b.get("team", "")),
).fetchone()
```

**Problem:** `standings` table has `team_id` (INTEGER), not `team_name`. Query always fails → `league_ok` is always `False` → data quality score always misses +1 point. This is despite 361 rows existing in standings.

**Fix:** Same pattern as Task 1.2:

```python
league_ok = False
try:
    from bet.db.connection import get_db
    with get_db() as conn:
        tid_a, tid_b = _resolve_team_ids(
            conn, stats_a.get("team", ""), stats_b.get("team", ""),
            sport,
        )
        ids = [i for i in (tid_a, tid_b) if i is not None]
        if ids:
            placeholders = ",".join("?" * len(ids))
            row = conn.execute(
                f"SELECT COUNT(*) FROM standings WHERE team_id IN ({placeholders})",
                ids,
            ).fetchone()
            if row and row[0] > 0:
                league_ok = True
except Exception as e:
    print(f"[deep_stats] DB standings check failed: {e}")
```

**Definition of done:**
- [ ] Query uses `team_id IN (...)` instead of `team_name IN (?, ?)`
- [ ] Uses `_resolve_team_ids()` for name-to-ID resolution
- [ ] `except Exception: pass` replaced with `except Exception as e: print(...)`

---

### Task 1.4 — Fix `_build_league_context()` standings query (lines 838-841)

**[MODIFY]** `scripts/deep_stats_report.py`

**Current (BROKEN):**
```python
rows = conn.execute(
    "SELECT team_name, position, points, zone FROM standings WHERE team_name IN (?, ?)",
    (team_a, team_b),
).fetchall()
```

**Problems (3 column errors):**
1. `team_name` → does not exist; table has `team_id`
2. `position` → does not exist; column is `rank`
3. `zone` → does not exist at all

**Actual standings columns:** `id, competition_id, team_id, season, rank, wins, draws, losses, goals_for, goals_against, goal_diff, points, form, home_wins, home_draws, home_losses, away_wins, away_draws, away_losses, streak, source, updated_at`

**Fix:** JOIN with `teams` table, use correct column names, derive zone from `rank`:

```python
def _build_league_context(sport: str, team_a: str, team_b: str) -> str:
    """§S3.11 League Context — standings, rank, points gap from DB."""
    lines = ["§S3.11 League Context"]
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(conn, team_a, team_b, sport)
            ids = [i for i in (tid_a, tid_b) if i is not None]
            if not ids:
                lines.append("⚠️ Teams not found in DB — verify league context manually")
                lines.append("")
                return "\n".join(lines)

            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT t.name, s.rank, s.points, s.wins, s.draws, s.losses, s.form "
                f"FROM standings s JOIN teams t ON s.team_id = t.id "
                f"WHERE s.team_id IN ({placeholders}) "
                f"ORDER BY s.updated_at DESC",
                ids,
            ).fetchall()
            if rows:
                # Deduplicate (take most recent per team)
                seen = set()
                unique_rows = []
                for row in rows:
                    if row[0] not in seen:
                        seen.add(row[0])
                        unique_rows.append(row)

                lines.append("| Team | Rank | Points | W-D-L | Form |")
                lines.append("|------|------|--------|-------|------|")
                for row in unique_rows:
                    form = row[6] if row[6] else "N/A"
                    lines.append(
                        f"| {row[0]} | {row[1]} | {row[2]} | "
                        f"{row[3]}-{row[4]}-{row[5]} | {form} |"
                    )
                # Points gap
                if len(unique_rows) >= 2:
                    gap = abs((unique_rows[0][2] or 0) - (unique_rows[1][2] or 0))
                    lines.append(f"Points gap: {gap}")
            else:
                lines.append("⚠️ No standings data in DB — verify league context manually")
    except Exception as e:
        print(f"[deep_stats] League context query failed: {e}")
        lines.append("⚠️ Standings query failed — verify league context manually")
    lines.append("")
    return "\n".join(lines)
```

**Design decisions:**
- Removed `zone` column entirely (doesn't exist, can't be reliably derived without league-specific rules)
- Added `W-D-L` and `Form` columns instead (actually exist in DB, more useful)
- Uses `ORDER BY s.updated_at DESC` + deduplication to get most recent standing per team
- Uses `_resolve_team_ids()` for consistency

**Definition of done:**
- [ ] Query JOINs `standings` with `teams` on `team_id = t.id`
- [ ] Uses `rank` instead of `position`
- [ ] No reference to `zone` column
- [ ] Table shows Team, Rank, Points, W-D-L, Form
- [ ] `except Exception: pass` replaced with `except Exception as e: print(...)`
- [ ] Points gap calculation preserved

---

### Task 1.5 — Fix `_build_injuries_section()` query (lines 871-874)

**[MODIFY]** `scripts/deep_stats_report.py`

**Current (BROKEN):**
```python
rows = conn.execute(
    "SELECT player_name, injury_type, status FROM injuries WHERE team_name = ?",
    (team,),
).fetchall()
```

**Problems:**
1. `player_name` → column is `athlete_name`
2. `team_name` → column is `team_id`

**Actual injuries columns:** `id, team_id, athlete_name, sport, status, injury_type, expected_return, source, fetched_at`

**Fix:** Resolve team name to ID, use correct column names:

```python
def _build_injuries_section(sport: str, team_a: str, team_b: str) -> str:
    """§S3.12 Injuries (DB) — current injuries per team from injuries table."""
    lines = ["§S3.12 Injuries (DB)"]
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(conn, team_a, team_b, sport)
            for team, tid in ((team_a, tid_a), (team_b, tid_b)):
                if tid is None:
                    lines.append(f"**{team}**: Team not found in DB")
                    continue
                rows = conn.execute(
                    "SELECT athlete_name, injury_type, status, expected_return "
                    "FROM injuries WHERE team_id = ?",
                    (tid,),
                ).fetchall()
                if rows:
                    lines.append(f"**{team}** ({len(rows)} injuries):")
                    for row in rows:
                        status = row[2] if row[2] else "OUT"
                        ret = f", return: {row[3]}" if row[3] else ""
                        lines.append(f"  - {row[0]}: {row[1]} ({status}{ret})")
                else:
                    lines.append(f"**{team}**: No injury records in DB")
    except Exception as e:
        print(f"[deep_stats] Injuries query failed: {e}")
        lines.append("⚠️ Injuries table not available — check Flashscore/Sofascore")
    lines.append("")
    return "\n".join(lines)
```

**Improvements over original:**
- Single `_resolve_team_ids()` call for both teams (one DB connection)
- Added `expected_return` to output (useful context, exists in DB)
- Each team handled separately with clear "not found" vs "no injuries" messaging

**Definition of done:**
- [ ] Query uses `team_id = ?` instead of `team_name = ?`
- [ ] Uses `athlete_name` instead of `player_name`
- [ ] Includes `expected_return` in output when available
- [ ] `except Exception: pass` replaced with `except Exception as e: print(...)`
- [ ] Handles case where team doesn't resolve in DB (shows "Team not found")

---

## Phase 2 — ESPN Data Rendering (P2)

**Root cause:** `extract_team_stats()` loads ESPN data into `result["espn_enrichment"]` (via `load_espn_enrichment_for_team()` from `db_data_loader.py`), and it's carried through to `stats_a_summary.espn_enrichment` in the output JSON. But no section builder reads or renders this data.

### Task 2.1 — Add `_build_s314_espn()` section builder

**[MODIFY]** `scripts/deep_stats_report.py`

Add a new section builder after `_build_expert_sentiment()` (around line 920):

```python
def _build_s314_espn(stats_a: dict, stats_b: dict) -> str:
    """§S3.14 ESPN Enrichment — ATS, O/U records, power index, standings."""
    lines = ["§S3.14 ESPN Enrichment"]

    espn_a = stats_a.get("espn_enrichment") or {}
    espn_b = stats_b.get("espn_enrichment") or {}

    if not espn_a and not espn_b:
        lines.append("⚠️ No ESPN enrichment data available")
        lines.append("")
        return "\n".join(lines)

    team_a = stats_a["team"]
    team_b = stats_b["team"]

    # ATS Records
    ats_a = espn_a.get("ats_record")
    ats_b = espn_b.get("ats_record")
    if ats_a or ats_b:
        lines.append("**ATS (Against The Spread):**")
        lines.append("| Team | W-L-P | Cover% | Home W-L | Away W-L |")
        lines.append("|------|-------|--------|----------|----------|")
        for team, ats in ((team_a, ats_a), (team_b, ats_b)):
            if ats:
                lines.append(
                    f"| {team} | {ats['wins']}-{ats['losses']}-{ats['pushes']} "
                    f"| {ats['cover_pct']}% "
                    f"| {ats['home_wins']}-{ats['home_losses']} "
                    f"| {ats['away_wins']}-{ats['away_losses']} |"
                )
        lines.append("")

    # O/U Records
    ou_a = espn_a.get("ou_record")
    ou_b = espn_b.get("ou_record")
    if ou_a or ou_b:
        lines.append("**Over/Under Records:**")
        lines.append("| Team | O-U-P | Over% | Home O-U | Away O-U |")
        lines.append("|------|-------|-------|----------|----------|")
        for team, ou in ((team_a, ou_a), (team_b, ou_b)):
            if ou:
                lines.append(
                    f"| {team} | {ou['overs']}-{ou['unders']}-{ou['pushes']} "
                    f"| {ou['over_pct']}% "
                    f"| {ou['home_overs']}-{ou['home_unders']} "
                    f"| {ou['away_overs']}-{ou['away_unders']} |"
                )
        lines.append("")

    # Standings (from ESPN)
    std_a = espn_a.get("standing")
    std_b = espn_b.get("standing")
    if std_a or std_b:
        lines.append("**ESPN Standings:**")
        lines.append("| Team | Rank | W-L-D | Pts | Home | Away | Form | Streak |")
        lines.append("|------|------|-------|-----|------|------|------|--------|")
        for team, std in ((team_a, std_a), (team_b, std_b)):
            if std:
                lines.append(
                    f"| {team} | {std.get('rank', 'N/A')} "
                    f"| {std.get('wins', 0)}-{std.get('losses', 0)}-{std.get('draws', 0)} "
                    f"| {std.get('points', 'N/A')} "
                    f"| {std.get('home_record', 'N/A')} "
                    f"| {std.get('away_record', 'N/A')} "
                    f"| {std.get('form', 'N/A')} "
                    f"| {std.get('streak', 'N/A')} |"
                )
        lines.append("")

    # Power Index
    pi_a = espn_a.get("power_index")
    pi_b = espn_b.get("power_index")
    if pi_a or pi_b:
        lines.append("**Power Index:**")
        for team, pi in ((team_a, pi_a), (team_b, pi_b)):
            if pi:
                lines.append(f"  - {team}: {pi}")
        lines.append("")

    if not any([ats_a, ats_b, ou_a, ou_b, std_a, std_b, pi_a, pi_b]):
        lines.append("ESPN data loaded but all sub-sections empty")
        lines.append("")

    return "\n".join(lines)
```

**Rationale:** Separate section (§S3.14) rather than embedding in §S3.2 (form) because:
- ESPN data is sport-specific (basketball/hockey only currently)
- It's a distinct data source that should be visually separated
- Keeps `_build_s32_form()` focused on L10/L5 stat averages

**Definition of done:**
- [ ] Function `_build_s314_espn(stats_a, stats_b)` exists
- [ ] Renders ATS record table when data present
- [ ] Renders O/U record table when data present
- [ ] Renders ESPN standings table when data present
- [ ] Renders power index when data present
- [ ] Shows "No ESPN enrichment data" when both teams lack data
- [ ] Gracefully handles partial data (one team has data, other doesn't)

---

### Task 2.2 — Wire `_build_s314_espn()` into the section assembly

**[MODIFY]** `scripts/deep_stats_report.py`

In the `analyze_candidate()` function (around line 1015), add the new section to the `sections` dict and the rendering loop:

**Current:**
```python
sections = {
    "s31": _build_s31_h2h(sport, h2h),
    ...
    "s313": _build_expert_sentiment(sport, home, away),
}
```

**New:**
```python
sections = {
    "s31": _build_s31_h2h(sport, h2h),
    ...
    "s313": _build_expert_sentiment(sport, home, away),
    "s314": _build_s314_espn(stats_a, stats_b),
}
```

And update the rendering loop:
```python
for key in ["s31", "s32", "s33", "s34", "s35", "s36", "s37", "s38", "s39", "s310",
            "s311", "s312", "s313", "s314"]:
```

**Definition of done:**
- [ ] `s314` key added to `sections` dict
- [ ] `s314` added to the rendering loop's key list
- [ ] ESPN section appears in markdown output after Expert Sentiment (§S3.13)

---

## Phase 3 — DB-First Candidate Loading (P3)

**Root cause:** `generate_deep_stats()` only loads candidates from JSON files (`_load_candidates_from_pool` reads `analysis_pool_{date}.json`, `_load_candidates_from_shortlist` reads a shortlist JSON). This violates R2 (DB-FIRST).

**Available DB data:** `fixtures` table has 12,162+ rows for a typical date. `load_fixtures_from_db()` in `db_data_loader.py` already handles loading with garbage filtering.

### Task 3.1 — Add `_load_candidates_from_db()` function

**[MODIFY]** `scripts/deep_stats_report.py`

Add after `_load_candidates_from_shortlist()` (around line 1205):

```python
def _load_candidates_from_db(date: str) -> list[dict]:
    """Load candidates from fixtures DB table (R2 DB-FIRST).

    Falls back to _load_candidates_from_pool() if DB is empty.
    """
    try:
        from db_data_loader import load_fixtures_from_db
        fixtures = load_fixtures_from_db(date)
        if not fixtures:
            return []
        candidates = []
        for f in fixtures:
            candidates.append({
                "sport": f.get("sport", f.get("sport_name", "football")),
                "home_team": f.get("home_team", ""),
                "away_team": f.get("away_team", ""),
                "competition": f.get("competition", f.get("competition_name", "")),
                "kickoff": f.get("kickoff", f.get("kickoff_utc", "")),
                "safety_markets": None,
                "n_odds_markets": 0,
                "fixture_verified": True,  # DB fixtures are verified
            })
        print(f"[deep_stats] Loaded {len(candidates)} candidates from DB fixtures")
        return candidates
    except Exception as e:
        print(f"[deep_stats] DB fixture loading failed: {e}")
        return []
```

**Rationale:**
- Reuses `load_fixtures_from_db()` which already handles `FixtureRepo.get_by_date_with_teams()`, garbage filtering, and sport name aliasing
- Maps fixture fields to the candidate dict format expected by `generate_deep_stats()`
- `fixture_verified=True` because DB fixtures have gone through validation
- `safety_markets=None` — will be computed during analysis

**Definition of done:**
- [ ] Function exists and returns `list[dict]` matching the candidate format
- [ ] Uses `load_fixtures_from_db()` from `db_data_loader`
- [ ] Maps all required fields: sport, home_team, away_team, competition, kickoff
- [ ] Returns empty list (not None) on failure
- [ ] Prints diagnostic message with count

---

### Task 3.2 — Add `--from-db` CLI flag

**[MODIFY]** `scripts/deep_stats_report.py`

In the `argparse` section (around line 1450):

```python
parser.add_argument(
    "--from-db",
    action="store_true",
    default=False,
    help="Load candidates from DB fixtures table (R2 DB-FIRST, ignores analysis pool JSON)",
)
```

Pass it through to `generate_deep_stats()`:

```python
result = generate_deep_stats(
    args.date, args.shortlist, args.top,
    no_enrich=args.no_enrich, from_db=args.from_db,
)
```

**Definition of done:**
- [ ] `--from-db` flag added to argparse
- [ ] Flag value passed to `generate_deep_stats()` function

---

### Task 3.3 — Update `generate_deep_stats()` candidate loading order

**[MODIFY]** `scripts/deep_stats_report.py`

Update the `generate_deep_stats()` function signature and candidate loading logic:

**Current:**
```python
def generate_deep_stats(date, shortlist_path=None, top=None, no_enrich=False):
    if shortlist_path:
        candidates = _load_candidates_from_shortlist(shortlist_path)
        source = f"shortlist:{shortlist_path}"
    else:
        candidates = _load_candidates_from_pool(date)
        source = f"analysis_pool_{date}.json"
```

**New:**
```python
def generate_deep_stats(date, shortlist_path=None, top=None, no_enrich=False, from_db=False):
    if shortlist_path:
        # Explicit shortlist file overrides everything
        candidates = _load_candidates_from_shortlist(shortlist_path)
        source = f"shortlist:{shortlist_path}"
    elif from_db:
        # Explicit DB-first mode
        candidates = _load_candidates_from_db(date)
        source = f"db:fixtures:{date}"
        if not candidates:
            # Fallback to JSON pool
            candidates = _load_candidates_from_pool(date)
            source = f"analysis_pool_{date}.json (DB fallback)"
    else:
        # Default: try DB first (R2), fall back to JSON pool
        candidates = _load_candidates_from_db(date)
        source = f"db:fixtures:{date}"
        if not candidates:
            candidates = _load_candidates_from_pool(date)
            source = f"analysis_pool_{date}.json (DB empty)"
```

**Loading priority:**
1. `--shortlist path.json` → explicit file (always honored)
2. `--from-db` → DB fixtures, JSON pool fallback
3. Default → DB fixtures first (R2), JSON pool fallback

**Definition of done:**
- [ ] `from_db` parameter added to function signature with `False` default
- [ ] When `--shortlist` provided: JSON file used (no change)
- [ ] Default path: tries DB first, falls back to JSON pool
- [ ] `source` field accurately reflects where candidates came from
- [ ] Backward-compatible: existing `--shortlist` usage unchanged

---

## Verification Checklist

After all phases are complete, verify:

- [ ] **P1 Smoke test:** Run `python3 scripts/deep_stats_report.py --date 2026-05-10 --top 3 --no-enrich --verbose` — data quality scores should now show `injuries: True` and `league_context: True` for teams that exist in DB
- [ ] **P1 Column check:** No SQL errors in output (previously silent, now printed)
- [ ] **P2 ESPN test:** For basketball/hockey candidates, §S3.14 section appears with ATS/O-U/standings data
- [ ] **P3 DB loading:** Run with `--from-db` flag — should load from fixtures table, print count
- [ ] **P3 Fallback:** With empty DB, should fall back to JSON pool silently
- [ ] **Backward compat:** `--shortlist path.json` still works identically

---

## Files Changed Summary

| File | Change Type | Tasks |
|------|-------------|-------|
| `scripts/deep_stats_report.py` | MODIFY | 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3 |

**No new files. No schema changes. No new dependencies.**
