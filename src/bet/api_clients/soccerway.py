"""Soccerway client — Playwright-based football fixture discovery.

Soccerway is a JS SPA powered by LiveSport Media (same infrastructure
as Flashscore). Covers 200+ countries and 1000+ leagues — primary exotic
league fixture discovery source.

Requires Playwright for rendering; HTTP returns an empty SPA shell.
"""

import logging
import re
from urllib.parse import urlparse

from .base_client import APIError
from .rate_limiter import RateLimiter
from .playwright_base import PlaywrightBaseClient

_VALID_EVENT_ID = re.compile(r"^[a-zA-Z0-9_-]+$")

logger = logging.getLogger(__name__)


class SoccerwayClient(PlaywrightBaseClient):
    """Soccerway client — Playwright SPA for football fixture discovery.

    Uses stealth Playwright to render soccerway.com and extract fixtures.
    Football only (soccerway.com is football-specific).
    Covers 200+ countries, 1000+ leagues — critical for exotic league coverage.
    """

    _COOKIE_SELECTOR = "#onetrust-accept-btn-handler"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("soccerway", "https://www.soccerway.com", rate_limiter)

    # ── JavaScript extraction ──────────────────────────────────────────────

    _JS_EXTRACT_FIXTURES = """() => {
        const results = [];

        // Soccerway uses the same LiveSport event__match DOM as Flashscore
        const sportGroups = document.querySelectorAll('.sportName');

        for (const group of sportGroups) {
            let currentLeague = '';
            let currentCountry = '';

            for (const child of group.children) {
                // Header: extract league and country
                if (child.classList.contains('headerLeague__wrapper')) {
                    const leagueEl = child.querySelector('.headerLeague__title');
                    const metaEl = child.querySelector('.headerLeague__meta');
                    currentLeague = leagueEl ? leagueEl.textContent.trim() : '';
                    currentCountry = metaEl
                        ? metaEl.textContent.trim().replace(/:$/, '').replace(/\\s+/g, ' ')
                        : '';
                    continue;
                }

                // Match row
                if (child.classList.contains('event__match')) {
                    const home = child.querySelector('.event__participant--home');
                    const away = child.querySelector('.event__participant--away');
                    const timeEl = child.querySelector('.event__time');
                    const scoreH = child.querySelector('.event__score--home');
                    const scoreA = child.querySelector('.event__score--away');
                    const stage = child.querySelector('.event__stage--block');

                    const homeName = home
                        ? home.textContent.trim()
                        : (child.querySelector('.event__homeParticipant')
                            ? child.querySelector('.event__homeParticipant').textContent.trim()
                            : '');
                    const awayName = away
                        ? away.textContent.trim()
                        : (child.querySelector('.event__awayParticipant')
                            ? child.querySelector('.event__awayParticipant').textContent.trim()
                            : '');

                    if (homeName && awayName) {
                        const rawId = child.id || '';
                        const eventId = rawId.replace(/^g_\\d+_/, '');
                        results.push({
                            id: eventId,
                            league: currentLeague,
                            country: currentCountry,
                            home: homeName,
                            away: awayName,
                            time: timeEl ? timeEl.textContent.trim() : '',
                            score_home: scoreH ? scoreH.textContent.trim() : '',
                            score_away: scoreA ? scoreA.textContent.trim() : '',
                            status: stage ? stage.textContent.trim() : '',
                            is_live: child.classList.contains('event__match--live'),
                        });
                    }
                }
            }
        }
        return results;
    }"""

    _JS_EXTRACT_MATCH_DETAIL = """() => {
        const info = {};
        const home = document.querySelector('.duelParticipant__home .participant__participantName');
        const away = document.querySelector('.duelParticipant__away .participant__participantName');
        info.home = home ? home.textContent.trim() : '';
        info.away = away ? away.textContent.trim() : '';

        let tournament = document.querySelector('.tournamentHeader__country a');
        if (!tournament) tournament = document.querySelector('.tournamentHeader__country');
        if (!tournament) tournament = document.querySelector('[class*="tournamentHeader__title"]');
        if (!tournament) tournament = document.querySelector('.breadcrumb');
        info.tournament = tournament ? tournament.textContent.trim() : '';

        const startTime = document.querySelector('.duelParticipant__startTime');
        info.start_time = startTime ? startTime.textContent.trim() : '';

        return info;
    }"""

    _JS_EXTRACT_H2H = """() => {
        const matches = [];
        const rows = document.querySelectorAll('.h2h__row');
        for (const row of rows) {
            const home = row.querySelector('.h2h__homeParticipant');
            const away = row.querySelector('.h2h__awayParticipant');
            const result = row.querySelector('.h2h__result');
            const date = row.querySelector('.h2h__date');

            if (home && away) {
                let scoreH = '', scoreA = '';
                if (result) {
                    const spans = result.querySelectorAll('span');
                    if (spans.length >= 2) {
                        scoreH = spans[0].textContent.trim();
                        scoreA = spans[1].textContent.trim();
                    } else {
                        const text = result.textContent.trim();
                        const parts = text.split(/[-:]/);
                        if (parts.length === 2) {
                            scoreH = parts[0].trim();
                            scoreA = parts[1].trim();
                        }
                    }
                }
                matches.push({
                    home: home.textContent.trim(),
                    away: away.textContent.trim(),
                    score_home: scoreH,
                    score_away: scoreA,
                    date: date ? date.textContent.trim() : '',
                });
            }
        }
        return matches;
    }"""

    # ── Public API ─────────────────────────────────────────────────────────

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get football fixtures for a specific date.

        Args:
            date: YYYY-MM-DD format
            sport: ignored — Soccerway is football only

        Returns:
            List of APIFixture objects.
        """
        from .api_football import APIFixture

        # Validate date format and calendar validity
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            logger.error(f"[Soccerway] Invalid date format: {date}")
            return []
        try:
            from datetime import datetime as _dt
            _dt.strptime(date, "%Y-%m-%d")
        except ValueError:
            logger.error(f"[Soccerway] Invalid calendar date: {date}")
            return []

        if sport != "football":
            logger.warning(f"[Soccerway] sport={sport!r} ignored — Soccerway is football-only")

        cache_key = f"soccerway/fixtures_{date}"
        cached = self._check_cache(cache_key, ttl_hours=4)
        if cached and "fixtures" in cached:
            return [
                APIFixture(**f)
                for f in cached["fixtures"]
                if isinstance(f, dict) and "external_id" in f
            ]

        if not self.rate_limiter.can_request("soccerway-scraper"):
            logger.warning("[Soccerway] Rate limit exceeded")
            return []

        # Soccerway matches URL with date parameter
        url = f"https://www.soccerway.com/matches/?d={date}"
        logger.info(f"[Soccerway] Fetching fixtures for {date}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=6000)

            self.rate_limiter.record_request("soccerway-scraper", f"/matches/{date}")

            raw = self._evaluate_js(page, self._JS_EXTRACT_FIXTURES)
            if not raw:
                logger.warning("[Soccerway] No fixtures extracted from DOM")
                return []

            logger.info(f"[Soccerway] Extracted {len(raw)} raw events from DOM")

            fixtures = []
            for ev in raw:
                try:
                    if not ev.get("id"):
                        continue

                    # Build competition name
                    comp = ev.get("league", "")
                    if ev.get("country"):
                        comp = f"{ev['country']}: {comp}" if comp else ev["country"]
                    if not comp:
                        comp = "Unknown"

                    # Parse time → kickoff ISO
                    time_str = ev.get("time", "")
                    kickoff = f"{date}T00:00:00Z"
                    if re.match(r"^\d{1,2}:\d{2}$", time_str):
                        kickoff = f"{date}T{time_str.zfill(5)}:00Z"

                    # Determine status
                    status = "scheduled"
                    status_text = ev.get("status", "").lower()
                    if ev.get("is_live"):
                        status = "live"
                    elif status_text in (
                        "ft", "aet", "pen.", "after et", "after pen.",
                        "finished", "ended",
                    ):
                        status = "finished"
                    elif status_text in (
                        "canc.", "cancelled", "postp.", "postponed",
                        "awd.", "awarded",
                    ):
                        status = "cancelled"
                    elif ev.get("score_home") and ev.get("score_away"):
                        status = "finished"

                    fixtures.append(
                        APIFixture(
                            external_id=ev.get("id", ""),
                            source="soccerway",
                            sport="football",
                            competition_name=comp,
                            home_team_name=ev.get("home", "Unknown"),
                            away_team_name=ev.get("away", "Unknown"),
                            kickoff=kickoff,
                            status=status,
                        )
                    )
                except Exception as e:
                    logger.debug(f"[Soccerway] Skipping event: {e}")
                    continue

            logger.info(f"[Soccerway] Returning {len(fixtures)} fixtures")

            # Cache results
            self._save_cache(
                cache_key,
                {"fixtures": [vars(f) for f in fixtures]},
            )

            return fixtures

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Soccerway] get_fixtures failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_fixture_stats(self, fixture_id: str) -> list:
        """Get match statistics for a fixture. Not supported on Soccerway."""
        logger.debug(f"[Soccerway] get_fixture_stats not supported (id={fixture_id})")
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H history via match detail page.

        Since Soccerway shares LiveSport infrastructure, H2H is available
        through match detail pages. Pass event_id as team1_id.
        """
        event_id = team1_id
        if not event_id:
            return []
        if not _VALID_EVENT_ID.match(event_id):
            logger.warning(f"[Soccerway] Invalid event_id format: {event_id!r}")
            return []

        if not self.rate_limiter.can_request("soccerway-scraper"):
            logger.warning("[Soccerway] Rate limit exceeded for H2H")
            return []

        url = f"https://www.soccerway.com/match/{event_id}/#/h2h/overall"
        logger.info(f"[Soccerway] Fetching H2H for event {event_id}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=4000)
            self.rate_limiter.record_request("soccerway-scraper", f"/match/{event_id}/h2h")

            h2h_data = self._evaluate_js(page, self._JS_EXTRACT_H2H)
            if not h2h_data:
                return []

            logger.info(f"[Soccerway] Found {len(h2h_data)} H2H matches")
            return h2h_data[:last_n]

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Soccerway] get_h2h failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_match_detail(self, match_url: str) -> dict:
        """Get match detail (teams, tournament, time).

        Args:
            match_url: Full URL or event ID for the match.

        Returns:
            Dict with home, away, tournament, start_time.
        """
        if not match_url:
            return {}

        # If just an ID, build the URL
        if not match_url.startswith("http"):
            if not _VALID_EVENT_ID.match(match_url):
                logger.warning(f"[Soccerway] Invalid match ID format: {match_url!r}")
                return {}
            match_url = f"https://www.soccerway.com/match/{match_url}/"
        else:
            # Validate domain to prevent SSRF
            parsed = urlparse(match_url)
            if parsed.netloc not in ("www.soccerway.com", "soccerway.com", "pl.soccerway.com", "int.soccerway.com"):
                logger.error(f"[Soccerway] Rejected non-soccerway URL: {match_url}")
                return {}

        if not self.rate_limiter.can_request("soccerway-scraper"):
            logger.warning("[Soccerway] Rate limit exceeded for match detail")
            return {}

        logger.info(f"[Soccerway] Fetching match detail: {match_url}")

        ctx = page = None
        try:
            ctx, page = self._load_page(match_url, wait_ms=4000)
            self.rate_limiter.record_request("soccerway-scraper", match_url[:100])

            detail = self._evaluate_js(page, self._JS_EXTRACT_MATCH_DETAIL)
            return detail or {}

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Soccerway] get_match_detail failed: {e}")
            return {}
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_standings(self, competition_url: str) -> list[dict]:
        """Get standings for a competition. Not yet implemented."""
        logger.debug("[Soccerway] get_standings not yet implemented")
        return []
