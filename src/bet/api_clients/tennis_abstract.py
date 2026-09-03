"""Tennis Abstract adapter — scrapes tennisabstract.com for detailed player stats.

Provides per-match serve/return statistics: aces, double faults, 1st serve %,
1st/2nd serve win %, break points saved/faced, hold %, break %, tiebreak records.

Data source: https://www.tennisabstract.com (no API key required, rate-limited).
Inspired by TheCommishDeuce/tennisabstract scraping approach.

Every page this module reads is identity-checked before a single row of it is
parsed, because tennisabstract answers 200 for players it does not have on the
route being asked. ``/cgi-bin/player-classic.cgi?p=<any WTA player>`` returns
Benoit Paire's page -- the same 605 KB, byte for byte, for Sabalenka, Swiatek,
Gauff, Kostyuk and Shnaider alike -- complete with a real ``var matchmx``.
Nothing in that response says "wrong player": the status is 200, the table is
real, and the numbers are somebody's. Parsing it puts one player's serve line
in another player's dossier, which is the worst thing this pipeline can do:
fabricate a number that looks measured. So the page's own ``var fullname``
decides whose page it is, and a page that does not name the player we asked for
is discarded rather than scored.
"""

import ast
import io
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from .base_client import BaseAPIClient, APIError, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from .tennis_score import parse_tennis_score
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisabstract.com"
REQUEST_DELAY = 0.6  # polite scraping delay

# tennisabstract's own claim about whose page this is. Present on every route
# that carries a match table, which is what makes the check below possible.
_FULLNAME_RE = re.compile(r"var\s+fullname\s*=\s*'([^']*)'")

# How stale a route's freshest match may be before it stops counting as this
# player's *recent* form. Identity is necessary but not sufficient: the site
# still serves /jsmatches/JannikSinner.js, and its last row is from November
# 2018, so a route can be the right player and still be the wrong era. Anyone
# we are pricing a fixture for played this season, so a route whose newest
# match predates that is kept only as a fallback.
STALE_ROUTE_DAYS = 400

# (label, url template), in the order they are tried. Order is about coverage
# and cost only -- never about trust, since all three are identity-checked.
#
#   player-classic   ATP's live table, inline in the HTML (~400-600 KB). Also
#                    the route that serves Benoit Paire to every WTA request.
#   jsmatches        WTA's live table. The WTA shell page
#                    (/cgi-bin/wplayer-classic.cgi) carries no ``matchmx`` of
#                    its own -- it loads exactly this file -- so this *is* the
#                    WTA route, and asking for it directly saves a request.
#                    For ATP names the same path exists but is abandoned 2018
#                    data, which is what STALE_ROUTE_DAYS is for.
#   jsmatchesCareer  Pre-current-season career file. Identity-provable but
#                    stale by construction, so it only wins when nothing
#                    fresher does.
_ROUTES: tuple[tuple[str, str], ...] = (
    ("player-classic", "{base}/cgi-bin/player-classic.cgi?p={name}"),
    ("jsmatches", "{base}/jsmatches/{name}.js"),
    ("jsmatches-career", "{base}/jsmatches/{name}Career.js"),
)


def _fold_player_name(name: str) -> frozenset[str]:
    """Player name -> comparable token set (ASCII-folded, punctuation-free)."""
    nfkd = unicodedata.normalize("NFKD", name or "")
    ascii_name = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    return frozenset(token for token in re.split(r"[^a-z0-9]+", ascii_name) if token)


def _abbreviates(short: frozenset[str], full: frozenset[str]) -> bool:
    """Is every token of ``short`` a token of ``full``, or a first initial of one?"""
    if len(short) != len(full) or not short:
        return False
    remaining = set(full)
    for token in sorted(short):  # sorted: frozenset order is arbitrary
        match = token if token in remaining else None
        if match is None and len(token) == 1:
            match = next(
                (other for other in sorted(remaining) if other.startswith(token)), None
            )
        if match is None:
            return False
        remaining.discard(match)
    return not remaining


def identity_matches(requested: str, claimed: str) -> bool:
    """Is ``claimed`` (the page's ``var fullname``) the player we asked for?

    Deliberately not a similarity score. What this rejects is a page for an
    entirely different person -- 'Benoit Paire' served for 'Iga Swiatek' --
    which needs no threshold to catch, and which a threshold loose enough to
    accept 'Jiri Lehecka' for 'Jiří Lehečka' would eventually wave through.
    Fuzzy matching is how the fabrication survived this long; the site states
    the name outright, so the name is compared, not scored.

    This replaced ``_fuzzy_opponent_match`` (rapidfuzz ratio >= 85, plus a
    "same surname over three characters" fallback that matched Alexander Zverev
    to Mischa Zverev). It was deleted rather than left unused: an unused fuzzy
    name matcher in this file is a loaded gun, and the next reader looking for
    "how do we compare player names here" must find only this.

    Accepted: the same tokens in any order once both sides are ASCII-folded
    ('Jiří Lehečka' / 'Jiri Lehecka', 'Sabalenka Aryna' / 'Aryna Sabalenka'),
    and the same tokens with one side's forename abbreviated to its initial
    ('C. Alcaraz' / 'Carlos Alcaraz'). The initials rule cannot separate two
    players who share a surname and a first initial; a feed that supplies only
    initials is ambiguous at the source, and no page-side check can fix that.
    """
    want, got = _fold_player_name(requested), _fold_player_name(claimed)
    if not want or not got:
        return False
    if want == got:
        return True
    return _abbreviates(want, got) or _abbreviates(got, want)


class TennisAbstractClient(BaseAPIClient):
    """Scrapes tennisabstract.com for ATP/WTA player match stats."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="tennis-abstract",
            base_url=BASE_URL,
            rate_limiter=rate_limiter,
        )
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._last_matches_cache: dict[str, tuple[dict, str]] = {}
        # url-name -> the ``var fullname`` of the page that was accepted for it.
        # Populated by _fetch_player_matches so resolve_team_id can answer with
        # the site's own name for the player without paying a second request.
        self._proved_names: dict[str, str] = {}

    # ─── BaseAPIClient overrides ─────────────────────────────────────

    def _load_api_key(self) -> str:
        """No API key needed — public website."""
        return "tennis-abstract-no-key"

    def is_available(self) -> bool:
        return True

    def _build_headers(self) -> dict:
        return dict(self._session.headers)

    def get_fixtures(self, date: str) -> list:
        """Not applicable — Tennis Abstract doesn't provide fixture lists."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Return stats for a fixture from the internal cache (populated by get_team_last_fixtures)."""
        cached = self._last_matches_cache.get(fixture_id)
        if not cached:
            return None
        match, player_name = cached
        return self._match_to_normalized(match, player_name)

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """H2H meetings between two players, in the shape the caller can read.

        Two things were wrong here and they cancelled out into silence.

        The rows returned were the raw ``matchmx`` dicts, which carry
        ``date``/``opp``/``aces`` but no id of any kind. The generic H2H loop
        (providers._fetch_h2h_generic) reads ``id``/``fixture_id`` off each
        meeting and skips the ones without -- so it skipped all of them, every
        time, and emitted no data_gap either, because from its point of view
        nothing had gone wrong. tennis-abstract H2H therefore returned exactly
        nothing for its entire existence, and returned it *quietly*, which left
        ANALYZE unable to tell "these two have never met" from "this provider
        was never really called".

        And the opponent was matched fuzzily, at a rapidfuzz ratio of 85, which
        is the same mistake that let another player's whole page through
        upstream. It does not need to be fuzzy: ``team2_id`` is now the *proved*
        name tennisabstract itself gave for player two, and ``opp`` is how
        tennisabstract spells the opponent in player one's own row. Both strings
        come from the same source, so they are compared, not scored.
        """
        matches = self._fetch_player_matches(team1_id)
        if matches is None:
            return []

        meetings = []
        for match in matches:
            if not identity_matches(team2_id, match.get("opp", "") or ""):
                continue
            fixture_id = self._fixture_id(team1_id, match)
            # The stats live behind get_fixture_stats(fixture_id), so the row
            # has to be reachable by that id or the caller gets an id it cannot
            # redeem.
            self._last_matches_cache[fixture_id] = (match, team1_id)
            meetings.append({**match, "id": fixture_id, "fixture_id": fixture_id})
            if len(meetings) >= last_n:
                break

        return meetings

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Prove the site has *this* player, and answer with its own name for him.

        For tennis the "team id" is a name, so this used to hand the caller's
        string straight back. That made resolution unfailable: every player
        resolved, including players tennisabstract has never heard of, and the
        question of whose page had actually been served was pushed down into
        the parser where nobody asked it. Resolution now costs what it should
        -- one fetch, cached, so the history call that follows is free -- and a
        player the site cannot prove is simply unresolved, which the enrichment
        loop already knows how to report.
        """
        if not team_name:
            return None
        return self.resolve_player_identity(team_name)

    def resolve_player_identity(self, player_name: str) -> str | None:
        """tennisabstract's own ``var fullname`` for this player, or None.

        The single question the verification script asks per player: not "is
        there a page" (there always is) but "does the page name him".
        """
        url_name = self._url_name(player_name)
        if url_name in self._proved_names:
            return self._proved_names[url_name]
        self._fetch_player_matches(player_name)
        return self._proved_names.get(url_name)

    @staticmethod
    def _fixture_id(player_name: str, match: dict) -> str:
        """One spelling of a match's id, shared by every path that mints one.

        get_team_last_fixtures, get_h2h and _match_to_normalized each used to
        build this string themselves; three copies of a format is three chances
        for get_fixture_stats to be handed an id nothing is filed under.
        """
        return f"ta_{player_name}_{match.get('date', '')}_{match.get('opp', '')}"

    # Grand Slam qualifying is best-of-three and carries the same ``level`` as
    # the main draw; only the round separates them. "QF" is a quarter-final and
    # must not match, so the pattern is Q followed by a digit.
    _QUALIFYING_ROUND = re.compile(r"^\s*q\d", re.IGNORECASE)

    @classmethod
    def _of_level(cls, matches: list[dict], level: str | None) -> list[dict]:
        """The player's matches from one draw, newest first, or all of them.

        ``level`` is the site's own column: "G" is Grand Slam. Asking for it
        excludes qualifying, because qualifying at a Slam is best-of-three and
        the only caller that asks is a best-of-five fixture -- measured while
        reading the sample this built, where four of six selected matches for
        Blockx-Trungelliti were Q1/Q2/Q3.

        Filtering here rather than after slicing is the whole point -- the last
        ten matches of an ATP player in September are Cincinnati,
        Winston-Salem and the odd Challenger, so "the last ten, of which keep
        the slams" yields nothing to price a five-set tie from. Measured on the
        2026-09-03 slate: the fifteen men's dossiers held 170 aces
        observations, **none** of them from a Grand Slam, while the same
        players' caches held 51 to 201 Grand Slam matches each.

        It costs no requests. ``_fetch_player_matches`` returns the player's
        whole career off one cached scrape (1,055 rows for Struff), so this
        chooses which of them to read and fetches nothing extra. The 500-day
        window ``providers._is_recent`` enforces on the way out still applies,
        which bounds it at roughly the last four to six Slams.
        """
        if not level:
            return matches
        wanted = level.upper()
        return [
            m for m in matches
            if str(m.get("level") or "").strip().upper() == wanted
            and not (wanted == "G" and cls._QUALIFYING_ROUND.match(str(m.get("round") or "")))
        ]

    def get_team_last_fixtures(
        self, team_id: str, last_n: int = 10, level: str | None = None
    ) -> list[NormalizedFixture]:
        """Fetch last N matches for a player from Tennis Abstract.

        ``level`` restricts them to one draw before the slice; see
        ``_of_level``. Callers that do not pass it get exactly the behaviour
        they had before it existed.
        """
        matches = self._of_level(self._fetch_player_matches(team_id), level)
        if not matches:
            return []

        fixtures = []
        for m in matches[:last_n]:
            fixture_id = self._fixture_id(team_id, m)
            # Store raw stats in a stash for get_fixture_stats_from_match
            nf = NormalizedFixture(
                fixture_id=fixture_id,
                source="tennis-abstract",
                sport="tennis",
                competition=m.get("tourn", ""),
                home_team=team_id,
                away_team=m.get("opp", ""),
                kickoff=m.get("date", ""),
                status="FT",
            )
            fixtures.append(nf)

        # Cache match data for fixture_stats lookup. Updated rather than
        # replaced: get_h2h files its meetings in the same dict, and this used
        # to wipe them whenever the two ran against one client.
        self._last_matches_cache.update(
            {self._fixture_id(team_id, m): (m, team_id) for m in matches[:last_n]}
        )
        return fixtures

    def get_fixture_stats_for_player(
        self, player_name: str, last_n: int = 10, level: str | None = None
    ) -> list[NormalizedMatchStats]:
        """Convenience: fetch player matches and return NormalizedMatchStats directly.

        This is the primary method used by the enrichment pipeline. ``level``
        means what it means in ``get_team_last_fixtures``, and is accepted here
        so the two entry points cannot disagree about which matches a
        best-of-five fixture may be priced from.
        """
        matches = self._of_level(self._fetch_player_matches(player_name), level)
        if not matches:
            return []

        stats_list = []
        for m in matches[:last_n]:
            stats = self._match_to_normalized(m, player_name)
            if stats:
                stats_list.append(stats)
        return stats_list

    # ─── Scraping logic ──────────────────────────────────────────────

    def _fetch_player_matches(self, player_name: str) -> list[dict] | None:
        """This player's match rows, or None when no route proved to be his.

        Never returns another player's matches. Each route in _ROUTES answers
        200 whether or not the site has the player *on that route*, so the
        response body's ``var fullname`` is what decides, and a body that names
        someone else is dropped with a warning rather than parsed.

        Routes are tried in order and the first *fresh* proven one wins. A
        proven-but-stale route (the abandoned 2018 ATP ``/jsmatches`` files,
        the pre-season ``Career`` files) is held as a fallback instead of being
        accepted, because being the right player is not the same as being this
        player's recent form -- and a 2018 L10 labelled "last 10" is the same
        class of lie as another player's, just quieter.
        """
        url_name = self._url_name(player_name)
        cache_key = f"tennis-abstract/player/{url_name}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        # Entries without ``proved_name`` predate the identity check and may
        # hold whoever's page happened to answer, so they are re-fetched rather
        # than trusted.
        if cached and cached.get("proved_name"):
            self._proved_names[url_name] = cached["proved_name"]
            return cached.get("matches")

        best: dict | None = None
        refused: list[str] = []
        for label, template in _ROUTES:
            route = self._fetch_route(
                template.format(base=BASE_URL, name=url_name), label, player_name
            )
            if route is None:
                continue
            if route.get("refused"):
                refused.append(route["refused"])
                continue
            if best is None or route["newest"] > best["newest"]:
                best = route
            if self._is_fresh(route["newest"]):
                break

        if best is None:
            logger.info(
                "[tennis-abstract] no page proved to be '%s'%s",
                player_name,
                f" (refused: {'; '.join(refused)})" if refused else "",
            )
            return None

        if not self._is_fresh(best["newest"]):
            logger.warning(
                "[tennis-abstract] '%s' resolved only via %s, whose newest match "
                "is %s -- this is the player but not his current form",
                player_name, best["label"], best["newest"] or "unknown",
            )

        logger.info(
            "[tennis-abstract] %d matches for '%s' via %s (page names '%s')",
            len(best["matches"]), player_name, best["label"], best["proved_name"],
        )
        self._proved_names[url_name] = best["proved_name"]
        self._save_to_cache(
            cache_key,
            {
                "matches": best["matches"],
                # The evidence, kept with the data: which page was accepted,
                # what it called the player, and how fresh it was.
                "proved_name": best["proved_name"],
                "route": best["label"],
                "newest_match": best["newest"],
            },
        )
        return best["matches"]

    def _fetch_route(self, url: str, label: str, player_name: str) -> dict | None:
        """Fetch one route and return its rows only if the page names the player.

        Returns None when the route has nothing (404, network error, no match
        table), ``{"refused": ...}`` when it served a page for someone else,
        and the parsed rows otherwise.
        """
        try:
            response = self._make_scrape_request(url)
        except Exception as exc:  # noqa: BLE001 - a dead route is not an error
            logger.debug("[tennis-abstract] %s failed for %s: %s", label, player_name, exc)
            return None
        if not response or response.status_code != 200:
            return None

        body = response.text
        claimed = _FULLNAME_RE.search(body)
        if not claimed:
            # No identity claim at all: a soft 404, or a shell page that loads
            # its table from somewhere else. Either way there is nothing here
            # we are entitled to attribute to anybody.
            logger.debug("[tennis-abstract] %s: no fullname at %s", label, url)
            return None
        proved_name = claimed.group(1)
        if not identity_matches(player_name, proved_name):
            logger.warning(
                "[tennis-abstract] %s served '%s' for '%s' -- refusing the page "
                "rather than filing another player's matches under his name (%s)",
                label, proved_name, player_name, url,
            )
            return {"refused": f"{label} named '{proved_name}'"}

        raw = self._parse_matches_from_html(body) or self._parse_matches_from_js(body)
        if not raw:
            return None
        matches = self._create_match_dicts(raw)
        if not matches:
            return None
        return {
            "label": label,
            "proved_name": proved_name,
            "matches": matches,
            # _create_match_dicts sorts newest-first.
            "newest": str(matches[0].get("date") or ""),
        }

    @staticmethod
    def _is_fresh(newest_date: str) -> bool:
        """Is this route's newest match recent enough to be called recent form?"""
        try:
            then = datetime.strptime(newest_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return False
        return (datetime.now(timezone.utc) - then).days <= STALE_ROUTE_DAYS

    def _make_scrape_request(self, url: str, retries: int = 2) -> requests.Response | None:
        """Make HTTP request with rate limiting and retry."""
        for attempt in range(retries):
            try:
                time.sleep(REQUEST_DELAY)
                response = self._session.get(url, timeout=15)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt == retries - 1:
                    logger.debug(f"[tennis-abstract] Request failed: {url}: {e}")
                    return None
                time.sleep(REQUEST_DELAY * (attempt + 1))
        return None

    def _parse_matches_from_html(self, html_content: str) -> list | None:
        """Extract match data array from HTML player page (var matchmx = [...])."""
        try:
            start_marker = "var matchmx = ["
            start_pos = html_content.find(start_marker)
            if start_pos == -1:
                return None

            start_pos += len(start_marker) - 1  # include the '['
            end_marker = "];"
            end_pos = html_content.find(end_marker, start_pos)
            if end_pos == -1:
                return None

            matches_str = html_content[start_pos : end_pos + 1]
            # Replace JS nulls with Python None
            matches_str = matches_str.replace("null", "None")
            return ast.literal_eval(matches_str)
        except Exception as e:
            logger.debug(f"[tennis-abstract] HTML parse error: {e}")
            return None

    def _parse_matches_from_js(self, js_content: str) -> list | None:
        """Parse match data from JavaScript file (matchmx = [...])."""
        try:
            if "matchmx = [" not in js_content:
                return None
            matches_str = js_content.split("matchmx = [")[1].split("];")[0]
            matches_str = "[" + matches_str + "]"
            matches_str = matches_str.replace("null", "None")
            return ast.literal_eval(matches_str)
        except Exception as e:
            logger.debug(f"[tennis-abstract] JS parse error: {e}")
            return None

    def _create_match_dicts(self, raw_matches: list) -> list[dict]:
        """Convert raw match arrays to structured dicts."""
        # Column mapping from Tennis Abstract's array format
        COLUMNS = {
            0: "date", 1: "tourn", 2: "surf", 3: "level", 4: "wl",
            8: "round", 9: "score", 11: "opp", 12: "orank",
            21: "aces", 22: "dfs", 23: "pts", 24: "firsts",
            25: "fwon", 26: "swon", 27: "games",
            28: "saved", 29: "chances",
            30: "oaces", 31: "odfs", 32: "opts", 33: "ofirsts",
            34: "ofwon", 35: "oswon", 36: "ogames",
            37: "osaved", 38: "ochances",
        }

        results = []
        for match_row in raw_matches:
            if not isinstance(match_row, (list, tuple)):
                continue
            if len(match_row) < 12:
                continue

            m = {}
            for idx, key in COLUMNS.items():
                if idx < len(match_row):
                    m[key] = match_row[idx]
                else:
                    m[key] = None

            # Format date: "20260515" → "2026-05-15"
            date_raw = m.get("date", "")
            if date_raw and isinstance(date_raw, (str, int)):
                ds = str(date_raw)
                if len(ds) == 8 and ds.isdigit():
                    m["date"] = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"

            # Skip walkovers
            score = m.get("score", "")
            if score in ("W/O", "", None):
                continue

            results.append(m)

        # Sort by date descending (most recent first)
        results.sort(key=lambda x: x.get("date", ""), reverse=True)
        return results

    def _match_to_normalized(self, match: dict, player_name: str) -> NormalizedMatchStats | None:
        """Convert a single match dict to NormalizedMatchStats with computed serve stats."""
        pts = self._safe_int(match.get("pts"))
        aces = self._safe_int(match.get("aces"))
        dfs = self._safe_int(match.get("dfs"))
        firsts = self._safe_int(match.get("firsts"))
        fwon = self._safe_int(match.get("fwon"))
        swon = self._safe_int(match.get("swon"))
        games = self._safe_int(match.get("games"))
        saved = self._safe_int(match.get("saved"))
        chances = self._safe_int(match.get("chances"))
        ogames = self._safe_int(match.get("ogames"))
        osaved = self._safe_int(match.get("osaved"))
        ochances = self._safe_int(match.get("ochances"))

        # If no serve data, skip this match
        if not pts:
            return None

        # Compute percentages
        second_serves = pts - firsts if pts and firsts else 0
        stats = {
            "aces": aces or 0,
            "double_faults": dfs or 0,
            # The opponent's serve line is present in the raw row (oaces/odfs)
            # but was not exposed, so a consumer could only ever see half of a
            # match's aces -- which silently understates any "Total Aces"
            # market built on top of it.
            "opponent_aces": self._safe_int(match.get("oaces")) or 0,
            "opponent_double_faults": self._safe_int(match.get("odfs")) or 0,
            "first_serve_pct": round(firsts / pts * 100, 1) if pts else 0,
            "first_serve_win_pct": round(fwon / firsts * 100, 1) if firsts else 0,
            "second_serve_win_pct": round(swon / second_serves * 100, 1) if second_serves else 0,
            "break_points_saved": saved or 0,
            "break_points_faced": chances or 0,
            "break_points_saved_pct": round(saved / chances * 100, 1) if chances else 0,
            "hold_pct": round((1 - (chances - saved) / games) * 100, 1) if games else 0,
            "break_pct": round((ochances - osaved) / ogames * 100, 1) if ogames else 0,
            "service_games": games or 0,
            "return_games": ogames or 0,
            "surface": match.get("surf", ""),
            # Which draw the match belonged to -- "G" is the Grand Slam main
            # draw, and men's Grand Slam main-draw singles is the whole of
            # best-of-five in professional tennis. Parsed into column 3 since
            # this client existed and never exposed, so every consumer of a
            # men's sample had to guess best-of-five from set counts; see
            # ProviderValue.match_level for what that guess cost.
            "level": match.get("level", ""),
            "round": match.get("round", ""),
            "result": match.get("wl", ""),
            "opponent_rank": self._safe_int(match.get("orank")) or 0,
        }

        # The set score, and the two figures the pipeline used to derive from
        # the wrong columns.
        #
        # ``games``/``ogames`` are **service** games. A tie-break game has no
        # server and appears in neither, so ``service_games + return_games`` --
        # which is how ``providers.py`` built ``total_games`` -- is short by
        # exactly one game per tie-break set. Measured on this client's own
        # cache, 56,280 completed rows carrying serve data: the shortfall
        # equalled the number of tie-break sets on **98.37%** of them (0 short
        # on 38,036 tie-break-free rows; 1 short on 14,733 one-tie-break rows;
        # 2 on 2,387; 3 on 200).
        #
        # It is not a rounding error, it is one-directional: every affected row
        # understated the Total Games market's own quantity, and the shift sat
        # inside ANALYZE's 1.0 agreement tolerance, so espn-tennis -- which
        # transcribes the published score exactly -- kept certifying it AGREE.
        #
        # The score column has been on every row all along (column 9, present
        # on 78,750 of 78,750 cached rows) and was parsed only far enough to
        # skip walkovers.
        parsed = parse_tennis_score(match.get("score"))
        stats["score"] = str(match.get("score") or "")
        stats["completed"] = bool(parsed.completed) if parsed is not None else False
        if parsed is not None:
            stats["total_games"] = parsed.games
            stats["total_sets"] = float(parsed.sets)
            own_games = self._player_games_won(parsed, match.get("wl"))
            if own_games is not None:
                stats["games_won"] = own_games

        return NormalizedMatchStats(
            fixture_id=self._fixture_id(player_name, match),
            source="tennis-abstract",
            sport="tennis",
            home_team=player_name,
            away_team=match.get("opp", ""),
            date=match.get("date", ""),
            stats=stats,
        )

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _player_games_won(parsed, result: object) -> float | None:
        """The games *this* player won, or None when the row cannot say.

        The score is written **winner-first**, not player-first. Measured on
        the whole cache: on 31,141 rows marked ``L`` the first-listed side had
        won more sets 31,109 times, and on 45,261 rows marked ``W`` it had
        45,218 times. So the side is recoverable -- from ``wl`` -- but only
        because ``wl`` and the score agree, and roughly one row in six hundred
        they do not.

        Those rows return None rather than a coin flip. A per-player games
        figure attributed to the wrong player is not a small error: it is the
        opponent's line filed under this player's name, which is the Benoit
        Paire class of fabrication in miniature.
        """
        wl = str(result or "").strip().upper()
        if wl not in ("W", "L") or not parsed.set_scores:
            return None
        first = sum(1 for a, b in parsed.set_scores if a > b)
        second = len(parsed.set_scores) - first
        # The first-listed side must be the one that won, because that is what
        # the spelling means. Where it is not -- 32 of 31,141 ``L`` rows and 43
        # of 45,261 ``W`` rows -- the row cannot say which side is which, and
        # the answer is no answer.
        if first <= second:
            return None
        index = 0 if wl == "W" else 1
        return float(sum(pair[index] for pair in parsed.set_scores))


    @staticmethod
    def _url_name(player_name: str) -> str:
        """Convert player name to URL format (remove spaces, special chars, transliterate diacritics).

        Tennis Abstract uses ASCII-only names without spaces:
        - "Vit Kopřiva" → "VitKopriva"
        - "Jiří Lehečka" → "JiriLehecka"
        - "Carlos Alcaraz" → "CarlosAlcaraz"
        """
        import unicodedata
        # Transliterate diacritics to ASCII (ř→r, á→a, č→c, etc.)
        nfkd = unicodedata.normalize("NFKD", player_name)
        ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
        # Remove spaces, hyphens, apostrophes
        return ascii_name.replace(" ", "").replace("-", "").replace("'", "")

    @staticmethod
    def _safe_int(val) -> int | None:
        """Safely convert value to int."""
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _save_to_cache(self, cache_key: str, data: dict) -> None:
        """Save data to stats_cache with last_updated for BaseAPIClient compatibility."""
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        cache_file.write_text(json.dumps(data, default=str), encoding="utf-8")
