"""Flashscore deep client — Playwright-based DOM scraping.

Uses stealth Playwright to load flashscore.com pages and extract:
- Fixtures: events for a date, grouped by league
- Match statistics: post-match stats (corners, shots, fouls, etc.)
- H2H: head-to-head history between teams
- Team form: recent W/D/L results
"""
import logging
import re

from .base_client import APIError
from .rate_limiter import RateLimiter
from .playwright_base import PlaywrightBaseClient

logger = logging.getLogger(__name__)

# Flashscore sport URL slugs
SPORT_SLUGS = {
    "football": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "hockey": "hockey",
    "volleyball": "volleyball",
    "ice-hockey": "hockey",
}

# Stat name normalization: Flashscore label → our key
STAT_NAME_MAP = {
    "ball possession": "possession",
    "goal attempts": "shots",
    "shots on goal": "shots_on_target",
    "shots off goal": "shots_off_target",
    "blocked shots": "blocked_shots",
    "free kicks": "free_kicks",
    "corner kicks": "corners",
    "corners": "corners",
    "offsides": "offsides",
    "throw-ins": "throw_ins",
    "goalkeeper saves": "saves",
    "fouls": "fouls",
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "total passes": "total_passes",
    "completed passes": "completed_passes",
    "tackles": "tackles",
    "attacks": "attacks",
    "dangerous attacks": "dangerous_attacks",
    "crosses": "crosses",
    # Basketball
    "rebounds": "rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "points": "points",
    # Hockey
    "penalty minutes": "pim",
    "hits": "hits",
    "faceoff won": "faceoff_won",
    "power plays": "power_plays",
    # Volleyball
    "aces": "aces",
    "errors": "errors",
    "attack %": "attack_pct",
    # Tennis
    "double faults": "double_faults",
    "1st serve %": "first_serve_pct",
    "break points won": "break_points_won",
}

class FlashscoreClient(PlaywrightBaseClient):
    """Client for Flashscore — Playwright DOM scraping.

    Uses stealth Playwright to render flashscore.com and extract structured data.
    Lazy-initializes browser on first use; reuses context across calls.
    """

    _COOKIE_SELECTOR = "#onetrust-accept-btn-handler"

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("flashscore", "https://www.flashscore.com", rate_limiter)

    # ── JavaScript extraction functions ────────────────────────────────────

    _JS_EXTRACT_STATS = """() => {
        const stats = [];
        // Flashscore stat rows: .stat__row or similar
        const rows = document.querySelectorAll('[class*="stat__row"], [class*="_row_"]');
        for (const row of rows) {
            const cells = row.querySelectorAll('[class*="stat__"]');
            if (cells.length >= 3) {
                stats.push({
                    home: cells[0].textContent.trim(),
                    category: cells[1].textContent.trim(),
                    away: cells[2].textContent.trim(),
                });
            }
        }
        // Alternative: wcl-statistics pattern
        if (stats.length === 0) {
            const wclRows = document.querySelectorAll('[class*="wcl-statistics"]');
            for (const row of wclRows) {
                const cells = row.querySelectorAll(':scope > div, :scope > span');
                if (cells.length >= 3) {
                    stats.push({
                        home: cells[0].textContent.trim(),
                        category: cells[1].textContent.trim(),
                        away: cells[2].textContent.trim(),
                    });
                }
            }
        }
        return stats;
    }"""

    _JS_EXTRACT_FIXTURES = """() => {
        const results = [];

        // Each .sportName div groups a set of headers + matches for one sport
        const sportGroups = document.querySelectorAll('.sportName');

        for (const group of sportGroups) {
            let currentLeague = '';
            let currentCountry = '';

            // Iterate children in DOM order: headers and matches are siblings
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

                    // Team name fallbacks: older selectors
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

    _JS_EXTRACT_MATCH_INFO = """() => {
        const info = {};
        const home = document.querySelector('.duelParticipant__home .participant__participantName');
        const away = document.querySelector('.duelParticipant__away .participant__participantName');
        info.home = home ? home.textContent.trim() : '';
        info.away = away ? away.textContent.trim() : '';

        // Try multiple tournament selectors — prefer leaf elements over containers
        let tournament = document.querySelector('.tournamentHeader__country a');
        if (!tournament) tournament = document.querySelector('.tournamentHeader__country');
        if (!tournament) tournament = document.querySelector('[class*="tournamentHeader__title"]');
        if (!tournament) tournament = document.querySelector('.breadcrumb');
        
        info.tournament = tournament ? tournament.textContent.trim() : '';

        const startTime = document.querySelector('.duelParticipant__startTime');
        info.start_time = startTime ? startTime.textContent.trim() : '';

        const scoreH = document.querySelector('.duelParticipant__score .detailScore__wrapper span:first-child');
        const scoreA = document.querySelector('.duelParticipant__score .detailScore__wrapper span:last-child');
        info.score_home = scoreH ? scoreH.textContent.trim() : '';
        info.score_away = scoreA ? scoreA.textContent.trim() : '';

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
        """Get all fixtures for a sport on a specific date.

        Args:
            date: YYYY-MM-DD format
            sport: football, tennis, basketball, hockey, volleyball

        Returns:
            List of APIFixture objects.
        """
        from .api_football import APIFixture

        slug = SPORT_SLUGS.get(sport, sport)
        # Thread date into URL — without ?d= Flashscore always returns today's fixtures
        url = f"https://www.flashscore.com/{slug}/?d={date}"

        logger.info(f"[Flashscore] Fetching fixtures for {sport} on {date}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=5000)

            raw = page.evaluate(self._JS_EXTRACT_FIXTURES)
            logger.info(f"[Flashscore] Extracted {len(raw)} raw events from DOM")

            fixtures = []
            for ev in raw:
                try:
                    # Skip events with no ID — breaks dedup and stat lookups
                    if not ev.get("id"):
                        continue

                    # Build competition name from country + league
                    comp = ev.get("league", "")
                    if ev.get("country"):
                        comp = f"{ev['country']}: {comp}" if comp else ev["country"]
                    if not comp:
                        comp = "Unknown"

                    # Parse time → kickoff ISO string
                    time_str = ev.get("time", "")
                    kickoff = f"{date}T00:00:00Z"
                    if re.match(r"^\d{1,2}:\d{2}$", time_str):
                        kickoff = f"{date}T{time_str.zfill(5)}:00Z"

                    # Determine status
                    status = "scheduled"
                    status_text = ev.get("status", "").lower()
                    if ev.get("is_live"):
                        status = "live"
                    elif status_text in ("ft", "aet", "pen.", "after et", "after pen.", "finished", "ended"):
                        status = "finished"
                    elif status_text in ("canc.", "cancelled", "postp.", "postponed", "awd.", "awarded"):
                        status = "cancelled"
                    elif status_text in ("walkover", "w.o.", "retired", "ret."):
                        status = "cancelled"
                    elif ev.get("score_home") and ev.get("score_away"):
                        status = "finished"

                    fixtures.append(APIFixture(
                        external_id=ev.get("id", ""),
                        source="flashscore",
                        sport=sport,
                        competition_name=comp,
                        home_team_name=ev.get("home", "Unknown"),
                        away_team_name=ev.get("away", "Unknown"),
                        kickoff=kickoff,
                        status=status,
                    ))
                except Exception as e:
                    logger.debug(f"[Flashscore] Skipping event: {e}")
                    continue

            logger.info(f"[Flashscore] Returning {len(fixtures)} fixtures for {sport}")
            return fixtures

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Flashscore] get_fixtures failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_fixture_stats(self, event_id: str) -> list:
        """Get match statistics for a finished fixture.

        Args:
            event_id: Flashscore event ID (e.g., 'xfi4Ju8N')

        Returns:
            List of stat dicts: [{"category": "Corners", "home": "7", "away": "3"}, ...]
        """
        url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
        logger.info(f"[Flashscore] Fetching stats for event {event_id}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=5000)

            # Try structured DOM extraction first
            js_stats = page.evaluate(self._JS_EXTRACT_STATS)
            stats = []
            
            if js_stats:
                for st in js_stats:
                    cat = st.get("category", "")
                    norm_key = STAT_NAME_MAP.get(cat.lower(), cat.lower().replace(" ", "_"))
                    stats.append({
                        "category": cat,
                        "key": norm_key,
                        "home": st.get("home", ""),
                        "away": st.get("away", ""),
                    })
            else:
                # Get innerText from #detail section and parse stats as fallback
                detail_text = page.evaluate("""() => {
                    const d = document.querySelector('#detail');
                    return d ? d.innerText : '';
                }""")
    
                if detail_text and len(detail_text) >= 100:
                    stats = self._parse_stats_text(detail_text)

            logger.info(f"[Flashscore] Extracted {len(stats)} stat categories for event {event_id}")
            return stats

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Flashscore] get_fixture_stats failed for {event_id}: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H history. team1_id should be a Flashscore event ID.

        Note: Flashscore H2H is accessed via a match page, not directly by team IDs.
        Pass the event_id as team1_id. team2_id is ignored.

        Returns:
            List of H2H match dicts: [{"home": "...", "away": "...",
                "score_home": "2", "score_away": "1", "date": "..."}, ...]
        """
        event_id = team1_id  # Use event_id to access H2H
        url = f"https://www.flashscore.com/match/{event_id}/#/h2h/overall"
        logger.info(f"[Flashscore] Fetching H2H for event {event_id}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=4000)

            h2h_data = page.evaluate(self._JS_EXTRACT_H2H)
            logger.info(f"[Flashscore] Found {len(h2h_data)} H2H matches")
            return h2h_data[:last_n]

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Flashscore] get_h2h failed for {event_id}: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_match_preview(self, event_id: str) -> dict:
        """Get match preview including form, H2H summary, and venue.

        Returns a dict with keys: home, away, tournament, form_home, form_away,
        h2h, venue, match_info_text.
        """
        url = f"https://www.flashscore.com/match/{event_id}/#/match-summary"
        logger.info(f"[Flashscore] Fetching match preview for {event_id}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=5000)

            match_info = page.evaluate(self._JS_EXTRACT_MATCH_INFO)

            # Extract form (W/D/L sequences)
            form_data = page.evaluate("""() => {
                const result = {home: [], away: []};
                
                // Try to find the form section
                const formContainers = document.querySelectorAll('.formTable, [class*="form"]');
                
                // Flashscore often splits home/away somehow or relies on columns.
                // We'll try the older structure with fallback to icon search
                const teams = document.querySelectorAll('.detailTeamForm__team');
                if (teams.length > 0) {
                    for (const team of teams) {
                        const isHome = team.classList.contains('detailTeamForm__team--home');
                        const formEls = team.querySelectorAll('.detailTeamForm__icon');
                        const forms = [];
                        for (const f of formEls) {
                            const title = f.getAttribute('title') || f.textContent.trim();
                            if (title.startsWith('W') || title === 'W') forms.push('W');
                            else if (title.startsWith('D') || title === 'D') forms.push('D');
                            else if (title.startsWith('L') || title === 'L') forms.push('L');
                            else forms.push(title.charAt(0));
                        }
                        if (isHome) result.home = forms;
                        else result.away = forms;
                    }
                } else {
                    // Try looking for W/D/L icons globally and split them roughly in half
                    const allIcons = document.querySelectorAll('[title*="win" i], [title*="draw" i], [title*="loss" i], [class*="win" i], [class*="draw" i], [class*="loss" i]');
                    const totalForms = [];
                    for (const f of allIcons) {
                        const title = (f.getAttribute('title') || f.textContent.trim() || f.className).toLowerCase();
                        if (title.includes('win') || title === 'w') totalForms.push('W');
                        else if (title.includes('draw') || title === 'd') totalForms.push('D');
                        else if (title.includes('loss') || title === 'l') totalForms.push('L');
                    }
                    // Only split if we have exactly 10 (5+5); other counts are ambiguous
                    if (totalForms.length === 10) {
                        result.home = totalForms.slice(0, 5);
                        result.away = totalForms.slice(5, 10);
                        result._fallback = true;
                    }
                }
                return result;
            }""")

            if form_data.get("_fallback"):
                logger.debug(f"[Flashscore] Form data for {event_id} used positional fallback — may be inaccurate")

            # Extract venue
            detail_text = page.evaluate("""() => {
                const d = document.querySelector('#detail');
                return d ? d.innerText : '';
            }""")

            venue = ""
            venue_match = re.search(r"VENUE:\s*\n(.+?)(?:\n|$)", detail_text)
            if venue_match:
                venue = venue_match.group(1).strip()

            # Get H2H from the same page (it's in the match summary)
            h2h_data = page.evaluate(self._JS_EXTRACT_H2H)

            return {
                "home": match_info.get("home", ""),
                "away": match_info.get("away", ""),
                "tournament": match_info.get("tournament", ""),
                "start_time": match_info.get("start_time", ""),
                "score_home": match_info.get("score_home", ""),
                "score_away": match_info.get("score_away", ""),
                "form_home": form_data.get("home", []),
                "form_away": form_data.get("away", []),
                "h2h": h2h_data[:5],
                "venue": venue,
            }

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Flashscore] get_match_preview failed for {event_id}: {e}")
            return {}
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get recent results from a Flashscore team page.

        Args:
            team_id: Flashscore team slug or URL path segment

        Returns list of match result dicts.
        """
        url = f"https://www.flashscore.com/team/{team_id}/results/"
        logger.info(f"[Flashscore] Fetching team results for {team_id}")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=5000)

            results = page.evaluate("""() => {
                const results = [];
                let currentLeague = '';
                const rows = document.querySelectorAll('.sportName > div');
                for (const row of rows) {
                    if (row.classList.contains('headerLeague__wrapper')) {
                        const leagueEl = row.querySelector('.headerLeague__title');
                        const metaEl = row.querySelector('.headerLeague__meta');
                        const league = leagueEl ? leagueEl.textContent.trim() : '';
                        const country = metaEl ? metaEl.textContent.trim().replace(/:$/, '').replace(/\\s+/g, ' ') : '';
                        currentLeague = country ? `${country}: ${league}` : league;
                        continue;
                    }

                    if (row.classList.contains('event__match')) {
                        const home = row.querySelector('.event__participant--home') || row.querySelector('.event__homeParticipant');
                        const away = row.querySelector('.event__participant--away') || row.querySelector('.event__awayParticipant');
                        const scoreH = row.querySelector('.event__score--home');
                        const scoreA = row.querySelector('.event__score--away');
                        const timeEl = row.querySelector('.event__time');

                        if (home && away && scoreH && scoreA) {
                            const rawId = row.id || '';
                            results.push({
                                id: rawId.replace(/^g_\\d+_/, ''),
                                league: currentLeague,
                                home: home.textContent.trim(),
                                away: away.textContent.trim(),
                                score_home: scoreH.textContent.trim(),
                                score_away: scoreA.textContent.trim(),
                                date: timeEl ? timeEl.textContent.trim() : '',
                            });
                        }
                    }
                }
                return results;
            }""")

            logger.info(f"[Flashscore] Found {len(results)} team results")
            return results[:last_n]

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[Flashscore] get_team_last_fixtures failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_stats_text(detail_text: str) -> list[dict]:
        """Parse match statistics from the #detail innerText.

        Flashscore renders stats as consecutive lines:
            Ball Possession
            65%
            35%
            Goal Attempts
            15
            8
            ...

        Returns list of {"category": ..., "home": ..., "away": ...} dicts.
        """
        stats = []
        lines = [l.strip() for l in detail_text.split("\n") if l.strip()]

        # Find the STATISTICS section or look for stat patterns
        stat_start = None
        for i, line in enumerate(lines):
            if line.upper() in ("MATCH STATISTICS", "STATISTICS", "STATS"):
                stat_start = i + 1
                break
            # Also match "1ST HALF" / "2ND HALF" stat headers
            if line.upper() in ("1ST HALF", "2ND HALF", "MATCH"):
                stat_start = i + 1
                break

        if stat_start is None:
            # Try pattern-based detection: stat_name then two numeric values
            for i in range(len(lines) - 2):
                low = lines[i].lower()
                if low in STAT_NAME_MAP or any(kw in low for kw in (
                    "possession", "shots", "corner", "foul", "offside",
                    "saves", "passes", "crosses", "tackles",
                )):
                    stat_start = i
                    break

        if stat_start is None:
            return stats

        # Parse triplets: category, home_value, away_value
        i = stat_start
        while i < len(lines) - 2:
            cat = lines[i]

            # Stop at known non-stat sections
            if cat.upper() in ("LINEUPS", "STANDINGS", "NEWS", "VIDEO",
                                "H2H", "HEAD-TO-HEAD", "ODDS", "FORM"):
                break

            home_val = lines[i + 1]
            away_val = lines[i + 2]

            # Validate: values should be numeric (possibly with %)
            if re.match(r"^\d+%?$", home_val) and re.match(r"^\d+%?$", away_val):
                # Normalize category name
                norm_key = STAT_NAME_MAP.get(cat.lower(), cat.lower().replace(" ", "_"))
                stats.append({
                    "category": cat,
                    "key": norm_key,
                    "home": home_val,
                    "away": away_val,
                })
                i += 3
            else:
                i += 1

        return stats
