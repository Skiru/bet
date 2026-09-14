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

The site also rate-limits by IP, through Cloudflare, and answers with a real
429 and an explicit ``Retry-After`` header -- not a connection reset, not a
timeout. Verified live on 2026-09-14: eight ``player-classic`` requests fired
from ``ThreadPoolExecutor(max_workers=8)`` (the concurrency ``enrich.py`` uses)
drew 429s on every request past the first three to five, each carrying
``Retry-After`` counting down to the window's reset (10, 8, 6, 4, 2 seconds
apart, arriving in a single burst -- consistent with a rolling ~15s window
capping this IP at a handful of requests). Retrying at the moment ``Retry-After``
said to always produced a 200 with fresh 2026 rows. ``REQUEST_DELAY`` was
written to be "a polite scraping delay", but it sleeps *inside one call*, so
eight threads each doing their own 0.6s sleep still fire within the same
window of each other -- the pacing was never actually cross-thread, which is
exactly the gap that let this look like a per-player mystery instead of a
process-wide one. The old retry budget (``retries=2``, a flat
``REQUEST_DELAY * attempt`` backoff) gives up in ~1.2s, an order of magnitude
short of the window's real reset time, so a 429 on the live route was silently
read as "no page here" and the loop fell through to the deliberately-stale
``jsmatches`` route -- the right player, eight-year-old data.
"""

import ast
import logging
import random
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from bet.models.normalized import NormalizedFixture, NormalizedMatchStats

from .base_client import CACHE_DIR, BaseAPIClient
from .rate_limiter import RateLimiter
from .tennis_score import parse_tennis_score

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisabstract.com"
REQUEST_DELAY = 0.6  # polite scraping delay

# tennisabstract's own claim about whose page this is. Present on every route
# that carries a match table, which is what makes the check below possible.
_FULLNAME_RE = re.compile(r"var\s+fullname\s*=\s*'([^']*)'")

# --- cross-thread pacing ----------------------------------------------------
#
# get_client() (api_clients/__init__.py) builds a brand-new TennisAbstractClient
# -- and a brand-new requests.Session -- on every call, so there is no per-
# instance state that survives across the several players enrich.py's
# ThreadPoolExecutor(max_workers=8) fetches concurrently. REQUEST_DELAY's
# sleep is per-instance, per-call, so it never actually spaced anything out
# across those eight threads; this lock and timestamp are process-wide
# (module-level) for exactly that reason. It does not need to be perfect --
# tennisabstract's real limit is a short rolling window that a handful of
# threads will still exceed even spaced out -- it only needs to turn the
# thundering-herd first request (all eight probes departing within
# milliseconds of each other) into a staggered one, which is the cheapest,
# least-clever fix that costs no extra requests.
_PACE_LOCK = threading.Lock()
_next_allowed_request_time = 0.0


def _pace(min_interval: float = REQUEST_DELAY) -> None:
    """Block until at least ``min_interval`` has passed since the last call.

    Shared by every TennisAbstractClient instance in this process (module
    globals, not ``self``), which is the only thing that can coordinate
    threads that each hold their own client and session.
    """
    global _next_allowed_request_time
    with _PACE_LOCK:
        now = time.monotonic()
        wait = _next_allowed_request_time - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _next_allowed_request_time = now + min_interval


# How many attempts a route gets before ``_make_scrape_request`` gives up.
# ``player-classic`` is worth fighting for -- it is the correct, current-season
# route for the overwhelming majority of names -- so it gets more attempts
# than the fallback routes, which exist precisely so a handful of failed
# attempts there does not strand a fixture with nothing.
_ROUTE_RETRIES: dict[str, int] = {"player-classic": 5}
_DEFAULT_RETRIES = 2

# Bounds on how long a single retry may wait, whether it is honouring the
# site's own ``Retry-After`` or backing off after a generic connection error.
# Uncapped would make one throttled player able to stall the whole
# ThreadPoolExecutor batch; too short would make the retry pointless (the
# 2026-09-14 probe saw ``Retry-After`` values up to 10s, and a heavier
# 14-concurrent-request stress test saw the site's own countdown run past that).
_MIN_RETRY_WAIT = 1.0
_MAX_RETRY_WAIT = 16.0
_JITTER = 0.4  # seconds, spread so parallel threads do not retry in lockstep


def _retry_after_seconds(response: requests.Response | None, attempt: int) -> float:
    """How long to wait before the next attempt.

    Prefers the server's own ``Retry-After`` (present on every 429 observed
    live) over a guess; falls back to exponential backoff with jitter for
    connection errors and timeouts, which carry no such header.
    """
    wait: float | None = None
    if response is not None:
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                wait = float(header)
            except (TypeError, ValueError):
                wait = None
    if wait is None:
        wait = REQUEST_DELAY * (2 ** attempt)
    wait = max(_MIN_RETRY_WAIT, min(_MAX_RETRY_WAIT, wait))
    return wait + random.uniform(0, _JITTER)


@dataclass
class _ScrapeAttempt:
    """The outcome of one ``_make_scrape_request`` call.

    ``response`` is ``None`` for both a clean "nothing here" (404, or every
    retry exhausted) and a rate-limited exhaustion -- ``failed`` is what tells
    those two apart. A 404 is not ``failed``: the page does not exist and
    retrying it would only be impolite. A 429 or connection error that
    survived every retry *is* ``failed`` -- the route was never actually
    proven empty, the site just never let this process look.
    """

    response: requests.Response | None
    failed: bool = False

# How stale a route's freshest match may be before it stops counting as this
# player's *recent* form. Identity is necessary but not sufficient: the site
# still serves /jsmatches/JannikSinner.js, and its last row is from November
# 2018, so a route can be the right player and still be the wrong era. Anyone
# we are pricing a fixture for played this season, so a route whose newest
# match predates that is kept only as a fallback.
STALE_ROUTE_DAYS = 400

# A cached fallback that only happened because the live route was rate-limited
# or erroring -- not because it was ever proven not to have this player -- is
# not trustworthy for the normal 6h TTL. tennisabstract's own throttling
# window resets in well under this (Retry-After values observed live topped
# out at 10s), so a retry a few minutes later is very likely to get the real,
# fresh route instead of the stale one this process settled for under load.
TRANSIENT_FALLBACK_TTL_HOURS = 0.25  # 15 minutes

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

        A route that never actually answered -- every attempt rate-limited
        (429) or errored -- is a third outcome, distinct from both "proved him"
        and "proved someone else": the route was never examined, so it must
        not be allowed to look like a clean "he's not here" the way a 404 or a
        wrong-name page does. When that is *why* a stale fallback got used
        (``any_route_failed``), the cached record says so and is trusted for a
        much shorter window (see ``TRANSIENT_FALLBACK_TTL_HOURS``) instead of
        the normal 6h, so the next read a few minutes later -- likely past
        tennisabstract's own throttling window -- gets a chance at the real
        route instead of repeating this run's bad luck for six hours.
        """
        url_name = self._url_name(player_name)
        cache_key = f"tennis-abstract/player/{url_name}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        # Entries without ``proved_name`` predate the identity check and may
        # hold whoever's page happened to answer, so they are re-fetched rather
        # than trusted. A failure-driven stale fallback outside its short TTL
        # is treated the same way -- not because it is wrong, but because a
        # retry now is likely to do better and six hours is too long to wait
        # to find out.
        if cached and cached.get("proved_name"):
            if (
                cached.get("fallback_reason") == "transient_failure"
                and not self._cache_entry_is_fresh_enough(
                    cached, TRANSIENT_FALLBACK_TTL_HOURS
                )
            ):
                cached = None
            if cached:
                self._proved_names[url_name] = cached["proved_name"]
                return cached.get("matches")

        best: dict | None = None
        refused: list[str] = []
        failed: list[str] = []
        for label, template in _ROUTES:
            route = self._fetch_route(
                template.format(base=BASE_URL, name=url_name), label, player_name
            )
            if route is None:
                continue
            if route.get("failed"):
                failed.append(route["failed"])
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
                "[tennis-abstract] no page proved to be '%s'%s%s",
                player_name,
                f" (refused: {'; '.join(refused)})" if refused else "",
                f" (unreachable: {', '.join(failed)})" if failed else "",
            )
            return None

        # Distinguishes "this stale route is all that exists" from "the live
        # route may well exist, we just couldn't get through to it this time"
        # -- the two things Step 2.3 of the fix requires stay tellable apart.
        fallback_is_due_to_failure = bool(failed) and not self._is_fresh(best["newest"])

        if not self._is_fresh(best["newest"]):
            logger.warning(
                "[tennis-abstract] '%s' resolved only via %s, whose newest match "
                "is %s -- this is the player but not his current form%s",
                player_name, best["label"], best["newest"] or "unknown",
                f" ({', '.join(failed)} could not be reached this attempt)"
                if failed else "",
            )

        logger.info(
            "[tennis-abstract] %d matches for '%s' via %s (page names '%s')",
            len(best["matches"]), player_name, best["label"], best["proved_name"],
        )
        self._proved_names[url_name] = best["proved_name"]
        cache_record = {
            "matches": best["matches"],
            # The evidence, kept with the data: which page was accepted,
            # what it called the player, and how fresh it was.
            "proved_name": best["proved_name"],
            "route": best["label"],
            "newest_match": best["newest"],
        }
        if fallback_is_due_to_failure:
            cache_record["fallback_reason"] = "transient_failure"
        self._save_to_cache(cache_key, cache_record)
        return best["matches"]

    @staticmethod
    def _cache_entry_is_fresh_enough(cached: dict, ttl_hours: float) -> bool:
        """Is this cache entry younger than ``ttl_hours``?

        Separate from ``BaseAPIClient._check_cache`` because that call already
        happened (at the standard 6h TTL) by the time the fallback reason is
        known -- this re-checks the same ``last_updated`` field against a
        shorter window for the one record type that needs one.
        """
        last_updated = cached.get("last_updated")
        if not last_updated:
            return False
        try:
            updated_dt = datetime.fromisoformat(last_updated)
        except ValueError:
            return False
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600
        return age_hours < ttl_hours

    def _fetch_route(self, url: str, label: str, player_name: str) -> dict | None:
        """Fetch one route and return its rows only if the page names the player.

        Returns None when the route cleanly has nothing (404, no identity
        claim, no parseable table -- the site looked and there was nothing to
        find), ``{"refused": ...}`` when it served a page for someone else,
        ``{"failed": label}`` when every attempt was rate-limited or errored
        and the route was never actually examined (do not read this as "he's
        not here" -- see ``_fetch_player_matches``), and the parsed rows
        otherwise.
        """
        try:
            attempt = self._make_scrape_request(url, label=label)
        except Exception as exc:  # noqa: BLE001 - a dead route is not an error
            logger.debug("[tennis-abstract] %s failed for %s: %s", label, player_name, exc)
            return {"failed": label}
        if attempt.failed:
            return {"failed": label}
        response = attempt.response
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

    def _make_scrape_request(
        self, url: str, label: str = "", retries: int | None = None
    ) -> _ScrapeAttempt:
        """Make one HTTP request with cross-thread pacing, backoff and retry.

        Verified live 2026-09-14: under ``ThreadPoolExecutor(max_workers=8)``
        (the concurrency ``enrich.py`` runs at), tennisabstract answers a real
        HTTP 429 through Cloudflare, with an explicit ``Retry-After`` header
        (observed 2-10s), to most requests past the first handful in a short
        rolling window -- not a connection reset or a timeout. Retrying once
        that header's wait had elapsed produced a 200 every time in the
        reproduction. The old ``retries=2`` / ``REQUEST_DELAY``-flat backoff
        gave up in about a second, an order of magnitude short of that window,
        which is what let a live 429 be read as "no page here".

        ``retries`` defaults to ``_ROUTE_RETRIES[label]`` -- more chances for
        ``player-classic`` than for the fallback routes -- so the caller does
        not have to know the policy; passing it explicitly (as the tests do)
        overrides that.

        A 404 returns immediately, un-retried: it is not going to change
        between attempts, and retrying it would only be impolite for no gain.
        """
        if retries is None:
            retries = _ROUTE_RETRIES.get(label, _DEFAULT_RETRIES)
        for attempt in range(retries):
            _pace()
            try:
                response = self._session.get(url, timeout=15)
            except requests.RequestException as exc:
                if attempt == retries - 1:
                    logger.debug(
                        "[tennis-abstract] %s: request failed after %d attempt(s): %s",
                        url, retries, exc,
                    )
                    return _ScrapeAttempt(response=None, failed=True)
                time.sleep(_retry_after_seconds(None, attempt))
                continue

            if response.status_code == 404:
                return _ScrapeAttempt(response=None, failed=False)

            if response.status_code == 429:
                if attempt == retries - 1:
                    logger.info(
                        "[tennis-abstract] %s: still rate-limited (429) after "
                        "%d attempt(s), giving up on this route for now "
                        "(Retry-After=%s) -- not the same as this player "
                        "having no page here",
                        url, retries, response.headers.get("Retry-After"),
                    )
                    return _ScrapeAttempt(response=None, failed=True)
                time.sleep(_retry_after_seconds(response, attempt))
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                if attempt == retries - 1:
                    logger.debug(
                        "[tennis-abstract] %s: HTTP error after %d attempt(s): %s",
                        url, retries, exc,
                    )
                    return _ScrapeAttempt(response=None, failed=True)
                time.sleep(_retry_after_seconds(response, attempt))
                continue

            return _ScrapeAttempt(response=response, failed=False)

        return _ScrapeAttempt(response=None, failed=True)

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
        if "," in ascii_name:
            parts = [p.strip() for p in ascii_name.split(",", 1)]
            if len(parts) == 2 and parts[1]:
                ascii_name = f"{parts[1]} {parts[0]}"
        # Remove spaces, hyphens, apostrophes, dots
        return ascii_name.replace(" ", "").replace("-", "").replace("'", "").replace(".", "")

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
        from datetime import datetime, timezone
        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        cache_file.write_text(json.dumps(data, default=str), encoding="utf-8")
