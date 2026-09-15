"""Sackmann-schema adapter — ATP/WTA Tour match stats via stats.tennismylife.org.

Restored 2026-09-15. Removed 2026-08-28 because the original host --
github.com/JeffSackmann/tennis_atp and tennis_wta -- 404'd at the repository
level. stats.tennismylife.org republishes the identical column schema
(tourney_id, w_ace, w_df, w_svpt, w_1stIn, w_1stWon, w_2ndWon, w_SvGms,
w_bpSaved, w_bpFaced, mirrored l_*) under a live, free, MIT-licensed API, and
was cross-checked 2026-09-15 against tennis-abstract's own cache -- Nadia
Podoroska's last 10 double-faults values matched exactly on every match the
two providers shared.

Coverage, checked directly against the file listing, not the marketing page:
ATP Tour, ATP Challenger, ATP qualifying, WTA Tour. No ITF, no WTA Challenger
-- both remain tennis-abstract-only. This makes the provider a corroborator
for Tour-level matches, never a replacement: PROVIDERS_BY_SPORT keeps
tennis-abstract first, and a player this provider cannot find (any ITF or WTA
Challenger name) is a silent zero-match result, not a wrong one -- the same
"absent, not fabricated" contract every provider in this pipeline follows.

Data source: https://stats.tennismylife.org (season files, per-tour) plus its
"ongoing_tourneys" files, which hold matches from tournaments still in
progress -- folded into the season file only once the event finishes, so a
match from earlier today or yesterday lives there first.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime, timezone

import requests

from .base_client import BaseAPIClient
from .rate_limiter import RateLimiter
from .tennis_abstract import identity_matches
from .tennis_score import parse_tennis_score
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats
from bet.scrapers.constants import (
    SACKMANN_ATP_CHALLENGER_ONGOING_URL,
    SACKMANN_ATP_CHALLENGER_URL,
    SACKMANN_ATP_ONGOING_URL,
    SACKMANN_ATP_URL,
    SACKMANN_WTA_ONGOING_URL,
    SACKMANN_WTA_URL,
)

logger = logging.getLogger(__name__)

# tour -> [(url template or literal url, needs_year)]. ATP additionally pulls
# the Challenger season + ongoing files -- Challenger draws are common enough
# in this pipeline's slate that skipping them here would just reproduce the
# 2026-08-28 gap one tier down.
_TOUR_SOURCES: dict[str, list[tuple[str, bool]]] = {
    "ATP": [
        (SACKMANN_ATP_ONGOING_URL, False),
        (SACKMANN_ATP_URL, True),
        (SACKMANN_ATP_CHALLENGER_ONGOING_URL, False),
        (SACKMANN_ATP_CHALLENGER_URL, True),
    ],
    "WTA": [
        (SACKMANN_WTA_ONGOING_URL, False),
        (SACKMANN_WTA_URL, True),
    ],
}


class SackmannClient(BaseAPIClient):
    """ATP/WTA Tour match stats from stats.tennismylife.org's Sackmann-schema CSVs.

    One player's match row carries aces, double faults, serve points, and the
    published set score -- the same shape ``TennisAbstractClient`` normalizes
    to, so it plugs into the same alias table (``_TENNIS_MATCH_STAT_ALIASES``
    in ``simple_stats/providers.py``) without a new one.
    """

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="sackmann",
            base_url="https://stats.tennismylife.org",
            rate_limiter=rate_limiter,
        )
        self._last_match_rows: dict[str, tuple[dict, bool]] = {}  # fixture_id -> (row, is_winner)

    # ─── BaseAPIClient overrides ─────────────────────────────────────

    def _load_api_key(self) -> str:
        """No API key needed — public, free, MIT-licensed CSVs."""
        return "sackmann-no-key"

    def is_available(self) -> bool:
        return True

    def _build_headers(self) -> dict:
        return {"Accept": "text/csv", "User-Agent": "bet-pipeline/1.0"}

    def get_fixtures(self, date: str) -> list:
        """Not applicable — this provider is queried by player, not by date."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Return per-match stats from the cache (populated by get_team_last_fixtures)."""
        entry = self._last_match_rows.get(fixture_id)
        if not entry:
            return None
        row, is_winner = entry
        return self._row_to_stats(fixture_id, row, is_winner)

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """H2H between two players, most recent first, across every tour/file."""
        rows = self._all_rows()
        h2h_matches: list[tuple[str, dict]] = []
        for row in rows:
            winner, loser = row.get("winner_name", ""), row.get("loser_name", "")
            if (identity_matches(team1_id, winner) and identity_matches(team2_id, loser)) or (
                identity_matches(team2_id, winner) and identity_matches(team1_id, loser)
            ):
                h2h_matches.append((row.get("tourney_date", ""), {
                    "date": row.get("tourney_date", ""),
                    "tournament": row.get("tourney_name", ""),
                    "surface": row.get("surface", ""),
                    "winner": winner,
                    "loser": loser,
                    "score": row.get("score", ""),
                    "round": row.get("round", ""),
                }))
        h2h_matches.sort(key=lambda pair: pair[0], reverse=True)
        return [match for _date, match in h2h_matches[:last_n]]

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """For tennis, the player's name (as asked) is the id."""
        return team_name if team_name else None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """A player's last N matches across every tour/file this client reads.

        ``identity_matches`` is the same accent-insensitive, token-based check
        ``tennis_abstract.py`` uses ('Jiří Lehečka' / 'Jiri Lehecka' match;
        'Benoit Paire' does not match 'Iga Swiatek') -- one comparison
        function for how this pipeline decides two tennis names refer to the
        same person, not a second, looser one invented here.
        """
        rows = self._all_rows()
        matches: list[tuple[str, NormalizedFixture, dict, bool]] = []
        seen_match_keys: set[tuple[str, str]] = set()
        for row in rows:
            winner, loser = row.get("winner_name", ""), row.get("loser_name", "")
            is_winner = identity_matches(team_id, winner)
            is_loser = not is_winner and identity_matches(team_id, loser)
            if not is_winner and not is_loser:
                continue
            # The ongoing file and the season file can both carry the same
            # finished match once a tournament wraps mid-scrape; a match is
            # itself, not a match per file, so the second copy is dropped.
            match_key = (str(row.get("tourney_id", "")), str(row.get("match_num", "")))
            if match_key in seen_match_keys:
                continue
            seen_match_keys.add(match_key)

            # ``home_team`` echoes ``team_id`` (the resolved query), the same
            # convention ``tennis_abstract.py``'s ``get_team_last_fixtures``
            # uses (``home_team=team_id`` there too) -- ``_opponent_of`` does
            # exact-string matching against the resolved id, and tennismylife
            # spells names without diacritics ("Jiri Lehecka") while a caller
            # may resolve with them ("Jiří Lehečka"), so echoing the query is
            # what keeps that comparison exact-matchable. The real defence
            # against a Benoit-Paire-class bug (this provider serving one
            # person's row under another's label) already ran above --
            # ``identity_matches(team_id, winner)`` / ``(..., loser)`` against
            # the CSV's own ``winner_name``/``loser_name`` columns, before this
            # row was ever accepted -- the same place tennis-abstract checks
            # its scraped ``var fullname`` against the query, before it
            # constructs anything.
            opponent = loser if is_winner else winner
            fixture_id = f"sack_{row.get('tourney_id', '')}_{row.get('match_num', '')}"
            date = row.get("tourney_date", "")
            matches.append((
                date,
                NormalizedFixture(
                    fixture_id=fixture_id,
                    source="sackmann",
                    sport="tennis",
                    competition=row.get("tourney_name", ""),
                    home_team=team_id,
                    away_team=opponent,
                    kickoff=self._format_date(date),
                    status="FT",
                ),
                row,
                is_winner,
            ))

        matches.sort(key=lambda m: m[0], reverse=True)
        top = matches[:last_n]
        self._last_match_rows = {m[1].fixture_id: (m[2], m[3]) for m in top}
        return [m[1] for m in top]

    # ─── Row -> NormalizedMatchStats ──────────────────────────────────

    def _row_to_stats(self, fixture_id: str, row: dict, is_winner: bool) -> NormalizedMatchStats | None:
        prefix = "w_" if is_winner else "l_"
        player_name = row.get("winner_name" if is_winner else "loser_name", "")
        opponent = row.get("loser_name" if is_winner else "winner_name", "")

        svpt = self._safe_int(row.get(f"{prefix}svpt"))
        first_in = self._safe_int(row.get(f"{prefix}1stIn"))
        first_won = self._safe_int(row.get(f"{prefix}1stWon"))
        second_won = self._safe_int(row.get(f"{prefix}2ndWon"))
        bp_saved = self._safe_int(row.get(f"{prefix}bpSaved"))
        bp_faced = self._safe_int(row.get(f"{prefix}bpFaced"))
        aces = self._safe_int(row.get(f"{prefix}ace"))
        dfs = self._safe_int(row.get(f"{prefix}df"))

        if not svpt:
            # No serve line at all (e.g. a walkover row) -- nothing to report,
            # not a zero to report.
            return None

        second_serves = svpt - first_in if svpt > first_in else 0
        stats: dict[str, object] = {
            "aces": aces,
            "double_faults": dfs,
            "first_serve_pct": round(first_in / svpt * 100, 1) if svpt else 0,
            "first_serve_win_pct": round(first_won / first_in * 100, 1) if first_in else 0,
            "second_serve_win_pct": round(second_won / second_serves * 100, 1) if second_serves else 0,
            "break_points_saved": bp_saved,
            "break_points_faced": bp_faced,
            "break_points_saved_pct": round(bp_saved / bp_faced * 100, 1) if bp_faced else 0,
            "surface": row.get("surface", ""),
            "level": row.get("tourney_level", ""),
            "round": row.get("round", ""),
            "result": "W" if is_winner else "L",
            "opponent_rank": self._safe_int(row.get("loser_rank" if is_winner else "winner_rank")) or 0,
        }

        # The set score, read the same way tennis_abstract.py reads it (see
        # its docstring on ``_player_games_won`` for why this is not derived
        # from serve-games counts). tennismylife's score is always written
        # winner-first, the standard tennis-notation convention, and we
        # already know which side ``player_name`` is from ``winner_name`` /
        # ``loser_name`` directly -- no W/L-vs-score cross-check needed, this
        # provider states it structurally rather than transcribing a sentence.
        parsed = parse_tennis_score(row.get("score"))
        stats["score"] = str(row.get("score") or "")
        stats["completed"] = bool(parsed.completed) if parsed is not None else False
        if parsed is not None and parsed.set_scores:
            stats["total_games"] = parsed.games
            stats["total_sets"] = float(parsed.sets)
            stats["games_won"] = float(
                sum(a for a, b in parsed.set_scores)
                if is_winner
                else sum(b for a, b in parsed.set_scores)
            )

        return NormalizedMatchStats(
            fixture_id=fixture_id,
            source="sackmann",
            sport="tennis",
            home_team=player_name,
            away_team=opponent,
            date=self._format_date(row.get("tourney_date", "")),
            stats=stats,
        )

    # ─── CSV fetching ────────────────────────────────────────────────

    def _all_rows(self, year: str | None = None) -> list[dict]:
        """Every row this client can see: both tours, season + ongoing (+
        Challenger for ATP), for one calendar year. Cheap to call repeatedly
        within one process -- each file is cached separately and independently
        of the others."""
        year = year or str(datetime.now(timezone.utc).year)
        rows: list[dict] = []
        for tour, sources in _TOUR_SOURCES.items():
            for url_template, needs_year in sources:
                url = url_template.format(year=year) if needs_year else url_template
                rows.extend(self._fetch_csv(url))
        return rows

    def _fetch_csv(self, url: str) -> list[dict]:
        """Fetch and parse one CSV. Cached 6h -- shorter than tennis-abstract's
        168h, because the ongoing-tourneys files are stated to update same-day
        and a stale cache here would mean missing a match played hours ago."""
        cache_key = f"sackmann/csv/{self._cache_slug(url)}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached is not None:
            rows = cached.get("rows")
            if isinstance(rows, list):
                return rows

        try:
            time.sleep(0.2)
            resp = requests.get(url, headers=self._build_headers(), timeout=30)
            if resp.status_code != 200:
                logger.debug("[sackmann] HTTP %s for %s", resp.status_code, url)
                self._save_cache(cache_key, {"rows": []})
                return []
            reader = csv.DictReader(io.StringIO(resp.text))
            rows = list(reader)
            self._save_cache(cache_key, {"rows": rows})
            return rows
        except requests.RequestException as exc:
            logger.debug("[sackmann] Failed to fetch %s: %s", url, exc)
            return []

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _cache_slug(url: str) -> str:
        return url.rsplit("/", 1)[-1].replace(".csv", "").replace("{year}", "y")

    @staticmethod
    def _format_date(date_str: str) -> str:
        """Convert '20260115' -> '2026-01-15'."""
        if date_str and len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    @staticmethod
    def _safe_int(val) -> int:
        if val is None or val == "":
            return 0
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0
