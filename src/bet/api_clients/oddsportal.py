"""OddsPortal client — Playwright SPA for odds comparison.

Uses stealth Playwright to render oddsportal.com and extract:
- Fixtures with inline 1X2 odds across all 5 sports
- Per-match bookmaker odds from detail pages
- Dropping odds for value detection
"""
import logging
import re
from urllib.parse import urlparse

from .base_client import APIError
from .playwright_base import PlaywrightBaseClient
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class OddsPortalClient(PlaywrightBaseClient):
    """OddsPortal client — Playwright SPA for odds comparison.

    Extracts: match listings with inline odds, per-match bookmaker odds,
    dropping odds. Multi-sport support (football, tennis, basketball,
    hockey, volleyball).

    After calling get_fixtures(), inline 1X2 odds from the listing page
    are available via get_listing_odds().
    """

    _COOKIE_SELECTOR = "#onetrust-accept-btn-handler"

    SPORT_PATHS = {
        "football": "/matches/football/",
        "tennis": "/matches/tennis/",
        "basketball": "/matches/basketball/",
        "hockey": "/matches/hockey/",
        "volleyball": "/matches/volleyball/",
    }

    # ── JavaScript extraction functions ────────────────────────────────────

    _JS_EXTRACT_FIXTURES = """() => {
        const results = [];

        // Build league context from sport-country-league-item headers.
        // Each header sits above a group of match rows in the DOM.
        const allElements = document.querySelectorAll(
            '[data-testid="sport-country-league-item"], '
          + 'div.border-b.border-l.border-r.border-black-borders'
        );

        let currentLeague = '';
        allElements.forEach(el => {
            const testId = el.getAttribute('data-testid') || '';
            if (testId === 'sport-country-league-item') {
                // Extract league text: "Football / England / Premier League ..."
                const raw = el.textContent.trim();
                // Remove sport prefix, date suffix, and column headers (1 X 2)
                const parts = raw.split('/').map(s => s.trim());
                if (parts.length >= 3) {
                    // parts[0] = sport name (ignore), parts[1] = country, parts[2+] = league
                    const country = parts[1];
                    // League name might contain date info: "Premier League Dziś, 13 Maj 1 X 2"
                    let league = parts.slice(2).join(' / ').trim();
                    // Strip date and column headers
                    league = league.replace(/\\s*(Dziś|Jutro|Wczoraj|Today|Tomorrow|Yesterday),?\\s*\\d+\\s*\\w+.*$/i, '').trim();
                    league = league.replace(/\\s+\\d+\\s*X\\s*\\d+\\s*$/, '').trim();
                    currentLeague = country + ': ' + league;
                } else if (parts.length === 2) {
                    currentLeague = parts[1];
                } else {
                    currentLeague = raw.substring(0, 80);
                }
                return;
            }

            // Match row — contains a[href*="/h2h/"] link
            const link = el.querySelector('a[href*="/h2h/"]');
            if (!link) return;

            const href = link.getAttribute('href') || '';

            // Game row inside the link
            const gameRow = link.querySelector('[data-testid="game-row"]');
            if (!gameRow) return;

            // Time
            const timeEl = gameRow.querySelector('[data-testid="time-item"]');
            const time = timeEl ? timeEl.textContent.trim() : '';

            // Participants
            const partEl = gameRow.querySelector('[data-testid="event-participants"]');
            let homeTeam = '';
            let awayTeam = '';
            if (partEl) {
                // Try dedicated sub-elements first
                const hostEl = partEl.querySelector('[data-testid="game-host"]');
                const guestEl = partEl.querySelector('[data-testid="game-guest"]');
                if (hostEl && guestEl) {
                    homeTeam = hostEl.textContent.trim();
                    awayTeam = guestEl.textContent.trim();
                } else {
                    // Fallback: split by en-dash (scores may be concatenated)
                    const txt = partEl.textContent.trim();
                    const sep = txt.indexOf('\\u2013');  // en-dash
                    if (sep > 0) {
                        homeTeam = txt.substring(0, sep).trim();
                        awayTeam = txt.substring(sep + 1).trim();
                    } else {
                        homeTeam = txt;
                    }
                    // Strip leading/trailing score digits ONLY on fallback path
                    // where scores get concatenated with team names.
                    // NOT on game-host/game-guest path to preserve names like
                    // "1860 München", "76ers", "1899 Hoffenheim".
                    homeTeam = homeTeam.replace(/^\\d+/, '').replace(/\\d+$/, '').trim();
                    awayTeam = awayTeam.replace(/^\\d+/, '').replace(/\\d+$/, '').trim();
                }
            }

            // Odds — from flex-center cells inside the link but outside event-participants
            const oddsCells = link.querySelectorAll(
                'div.flex-center.border-black-borders p, '
              + '[data-testid="odd-container"] p, '
              + '[data-testid="odd-container-default"] p'
            );
            const odds = [];
            oddsCells.forEach(cell => {
                const t = cell.textContent.trim();
                const val = parseFloat(t);
                if (!isNaN(val) && val >= 1.01 && val <= 500) {
                    odds.push(val);
                }
            });

            // Match ID from URL hash
            let matchId = '';
            if (href.includes('#')) {
                matchId = href.split('#')[1];
            }

            results.push({
                match_id: matchId,
                time: time,
                home_team: homeTeam,
                away_team: awayTeam,
                league: currentLeague,
                url: href,
                odds_1: odds.length > 0 ? odds[0] : null,
                odds_x: odds.length > 1 ? odds[1] : null,
                odds_2: odds.length > 2 ? odds[2] : null,
            });
        });

        return results;
    }"""

    _JS_EXTRACT_ODDS = """() => {
        const result = {
            market: '1x2',
            average: {},
            bookmakers: [],
        };

        // All odds containers on the page
        const oddContainers = document.querySelectorAll(
            '[data-testid="odd-container"], [data-testid="odd-container-default"]'
        );

        // Collect all odds values
        const allOdds = [];
        oddContainers.forEach(container => {
            const pEls = container.querySelectorAll('p');
            pEls.forEach(p => {
                const t = p.textContent.trim();
                const val = parseFloat(t);
                if (!isNaN(val) && val >= 1.01 && val <= 500) {
                    allOdds.push(val);
                }
            });
        });

        // First triplet is typically the average/best odds
        if (allOdds.length >= 3) {
            result.average = {
                '1': allOdds[0],
                'X': allOdds[1],
                '2': allOdds[2],
            };
        }

        // Extract bookmaker-specific odds
        const bookmakerHeaders = document.querySelectorAll('[data-testid="bookmaker-header"]');
        bookmakerHeaders.forEach(header => {
            const nameEl = header.querySelector('a, span, p, img[alt]');
            let name = '';
            if (nameEl) {
                name = nameEl.textContent.trim() || nameEl.getAttribute('alt') || '';
            }
            // Odds for this bookmaker are in the same row/sibling structure
            const row = header.closest('div[class*="border"]') || header.parentElement;
            if (row) {
                const rowOdds = [];
                row.querySelectorAll(
                    '[data-testid="odd-container"] p, '
                  + '[data-testid="odd-container-default"] p'
                ).forEach(p => {
                    const val = parseFloat(p.textContent.trim());
                    if (!isNaN(val) && val >= 1.01 && val <= 500) {
                        rowOdds.push(val);
                    }
                });
                if (name && rowOdds.length >= 2) {
                    result.bookmakers.push({
                        name: name,
                        odds: rowOdds,
                    });
                }
            }
        });

        // Payout / margin
        const payoutEl = document.querySelector('[data-testid="payout-container"]');
        if (payoutEl) {
            const payoutText = payoutEl.textContent.trim();
            const match = payoutText.match(/(\\d+[.,]\\d+)%/);
            if (match) {
                result.payout = parseFloat(match[1].replace(',', '.'));
            }
        }

        return result;
    }"""

    _JS_EXTRACT_H2H = """() => {
        const matches = [];
        const section = document.querySelector('[data-testid="last-matches-section"]');
        if (!section) return matches;

        const rows = section.querySelectorAll('[data-testid="game-row"]');
        rows.forEach(row => {
            const hostEl = row.querySelector('[data-testid="game-host"]');
            const guestEl = row.querySelector('[data-testid="game-guest"]');
            const timeEl = row.querySelector(
                '[data-testid="game-time-item"], [data-testid="time-item"]'
            );
            const statusEl = row.querySelector('[data-testid="game-status-box"]');

            if (hostEl && guestEl) {
                matches.push({
                    home: hostEl.textContent.trim(),
                    away: guestEl.textContent.trim(),
                    date: timeEl ? timeEl.textContent.trim() : '',
                    score: statusEl ? statusEl.textContent.trim() : '',
                });
            }
        });

        return matches;
    }"""

    # ── Public API ─────────────────────────────────────────────────────────

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("oddsportal", "https://www.oddsportal.com", rate_limiter)
        # Cache inline odds from the last get_fixtures() call.
        # Keys: match_id or "home vs away", values: {odds_1, odds_x, odds_2}.
        self._last_listing_odds: dict[str, dict] = {}

    def get_listing_odds(self) -> dict[str, dict]:
        """Return inline 1X2 odds captured during the last get_fixtures() call.

        Returns:
            Dict keyed by match_id (or 'home vs away' fallback) with
            {odds_1, odds_x, odds_2} values.  Empty if get_fixtures()
            has not been called yet.
        """
        return dict(self._last_listing_odds)

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get fixtures for a sport from OddsPortal listing page.

        Args:
            date: YYYY-MM-DD format (used for kickoff construction and URL)
            sport: football, tennis, basketball, hockey, volleyball

        Returns:
            List of APIFixture objects.  Inline 1X2 odds are cached in
            ``_last_listing_odds`` — retrieve via ``get_listing_odds()``.
        """
        from .api_football import APIFixture

        # Validate date format
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            logger.error(f"[OddsPortal] Invalid date format: {date} (expected YYYY-MM-DD)")
            return []

        # Validate sport
        if sport not in self.SPORT_PATHS:
            logger.warning(
                f"[OddsPortal] Unknown sport '{sport}', "
                f"available: {list(self.SPORT_PATHS.keys())}. Defaulting to football."
            )

        path = self.SPORT_PATHS.get(sport, self.SPORT_PATHS["football"])
        # OddsPortal date format: /matches/football/20260513/
        # Falls back to dateless URL (today's fixtures) if date path returns empty.
        date_slug = date.replace("-", "")
        url = f"{self.base_url}{path}{date_slug}/"
        url_fallback = f"{self.base_url}{path}"

        logger.info(f"[OddsPortal] Fetching fixtures for {sport} on {date}")

        if not self.rate_limiter.can_request("oddsportal-scraper"):
            logger.warning("[OddsPortal] Rate limit exceeded")
            return []

        self._last_listing_odds = {}
        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=6000)
            self.rate_limiter.record_request("oddsportal-scraper", url[:100])

            raw = self._evaluate_js(page, self._JS_EXTRACT_FIXTURES)

            # Retry once if SPA not yet hydrated (handles tennis timing)
            if not raw:
                logger.info("[OddsPortal] Empty result, retrying after 4s wait...")
                page.wait_for_timeout(4000)
                raw = self._evaluate_js(page, self._JS_EXTRACT_FIXTURES)

            # Fallback: try without date slug (default = today's fixtures)
            if not raw and url != url_fallback:
                logger.info("[OddsPortal] Date URL empty, trying dateless fallback...")
                ctx.close()
                ctx, page = self._load_page(url_fallback, wait_ms=6000)
                raw = self._evaluate_js(page, self._JS_EXTRACT_FIXTURES)

            if not raw:
                logger.warning(f"[OddsPortal] No fixtures extracted for {sport}")
                return []
            logger.info(f"[OddsPortal] Extracted {len(raw)} raw events from DOM")

            fixtures = []
            odds_with_data = 0
            for ev in raw:
                try:
                    home = ev.get("home_team", "").strip()
                    away = ev.get("away_team", "").strip()
                    if not home or not away:
                        continue

                    # Parse time → kickoff ISO string
                    time_str = ev.get("time", "")
                    kickoff = f"{date}T00:00:00Z"
                    if re.match(r"^\d{1,2}:\d{2}$", time_str):
                        kickoff = f"{date}T{time_str.zfill(5)}:00Z"

                    league = ev.get("league", "Unknown")
                    match_id = ev.get("match_id", "")

                    fixtures.append(APIFixture(
                        external_id=match_id,
                        source="oddsportal",
                        sport=sport,
                        competition_name=league,
                        home_team_name=home,
                        away_team_name=away,
                        kickoff=kickoff,
                        status="scheduled",
                    ))

                    # Cache inline odds for downstream use
                    odds_1 = ev.get("odds_1")
                    odds_x = ev.get("odds_x")
                    odds_2 = ev.get("odds_2")
                    if odds_1 is not None or odds_2 is not None:
                        key = match_id if match_id else f"{home} vs {away}"
                        self._last_listing_odds[key] = {
                            "odds_1": odds_1,
                            "odds_x": odds_x,
                            "odds_2": odds_2,
                        }
                        odds_with_data += 1

                except Exception as e:
                    logger.debug(f"[OddsPortal] Skipping event: {e}")
                    continue

            logger.info(
                f"[OddsPortal] Returning {len(fixtures)} fixtures for {sport} "
                f"({odds_with_data} with inline odds)"
            )
            return fixtures

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[OddsPortal] get_fixtures failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_odds(self, match_url: str) -> dict:
        """Get bookmaker odds for a specific match.

        Args:
            match_url: Full URL or relative path to match detail page.

        Returns:
            Dict with 'average' odds, 'bookmakers' list, and optional 'payout'.
        """
        if not match_url.startswith("http"):
            if not match_url.startswith("/"):
                match_url = "/" + match_url
            match_url = f"{self.base_url}{match_url}"
        else:
            parsed = urlparse(match_url)
            if parsed.netloc not in ("www.oddsportal.com", "oddsportal.com"):
                logger.warning(f"[OddsPortal] Refusing non-OddsPortal URL: {match_url}")
                return {}

        if not self.rate_limiter.can_request("oddsportal-scraper"):
            logger.warning("[OddsPortal] Rate limit exceeded for get_odds")
            return {}

        logger.info(f"[OddsPortal] Fetching odds from {match_url}")

        ctx = page = None
        try:
            ctx, page = self._load_page(match_url, wait_ms=5000)
            self.rate_limiter.record_request("oddsportal-scraper", match_url[:100])

            odds_data = self._evaluate_js(page, self._JS_EXTRACT_ODDS)
            return odds_data if odds_data else {}

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[OddsPortal] get_odds failed: {e}")
            return {}
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_dropping_odds(self, sport: str = "football") -> list:
        """Get dropping odds page — events where odds moved significantly.

        Note: The dropping odds page uses a different DOM structure than
        the matches listing. This method attempts a generic extraction.

        Returns:
            List of dicts with event info and odds movement.
        """
        url = f"{self.base_url}/dropping-odds/"

        if not self.rate_limiter.can_request("oddsportal-scraper"):
            logger.warning("[OddsPortal] Rate limit exceeded for dropping odds")
            return []

        logger.info("[OddsPortal] Fetching dropping odds")

        ctx = page = None
        try:
            ctx, page = self._load_page(url, wait_ms=6000)

            # Dropping odds page has its own structure — extract links + text
            raw = self._evaluate_js(page, """() => {
                const results = [];
                const rows = document.querySelectorAll(
                    'a[href*="/h2h/"], [data-testid="game-row"]'
                );
                const seen = new Set();
                rows.forEach(el => {
                    const link = el.tagName === 'A' ? el : el.closest('a[href*="/h2h/"]');
                    if (!link) return;
                    const href = link.getAttribute('href') || '';
                    if (seen.has(href)) return;
                    seen.add(href);

                    const text = link.textContent.trim();
                    results.push({ url: href, text: text.substring(0, 300) });
                });
                return results;
            }""")
            return raw if raw else []

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[OddsPortal] get_dropping_odds failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass

    def get_fixture_stats(self, fixture_id: str) -> list:
        """OddsPortal does not provide match stats — returns empty list."""
        return []

    def get_h2h(self, team1_id: str, team2_id: str = "", last_n: int = 10) -> list:
        """Get H2H results from a match detail page.

        Note: OddsPortal H2H requires a match detail URL, not team IDs.
        Pass the full match URL as team1_id; team2_id is ignored.

        Args:
            team1_id: Full URL or relative path to match detail page.
            team2_id: Ignored (kept for BaseAPIClient signature compatibility).
            last_n: Maximum results to return.

        Returns:
            List of dicts with home, away, date, score.
        """
        match_url = team1_id
        if not match_url.startswith("http"):
            if not match_url.startswith("/"):
                match_url = "/" + match_url
            match_url = f"{self.base_url}{match_url}"
        else:
            parsed = urlparse(match_url)
            if parsed.netloc not in ("www.oddsportal.com", "oddsportal.com"):
                logger.warning(f"[OddsPortal] Refusing non-OddsPortal URL: {match_url}")
                return []

        if not self.rate_limiter.can_request("oddsportal-scraper"):
            logger.warning("[OddsPortal] Rate limit exceeded for H2H")
            return []

        logger.info(f"[OddsPortal] Fetching H2H from {match_url}")

        ctx = page = None
        try:
            ctx, page = self._load_page(match_url, wait_ms=5000)
            self.rate_limiter.record_request("oddsportal-scraper", match_url[:100])

            raw = self._evaluate_js(page, self._JS_EXTRACT_H2H)
            if raw:
                return raw[:last_n]
            return []

        except APIError:
            raise
        except Exception as e:
            logger.error(f"[OddsPortal] get_h2h failed: {e}")
            return []
        finally:
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass
