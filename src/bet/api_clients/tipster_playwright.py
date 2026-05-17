"""Playwright-based tipster site scraper — deep DOM inspection for picks + reasoning."""

import json
import logging
import re
import time
from datetime import datetime, timezone

from .base_client import APIError
from .playwright_base import PlaywrightBaseClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JavaScript extraction snippets for each site type
# ---------------------------------------------------------------------------

# Generic: extract all "vs" events with surrounding context from rendered DOM
_JS_EXTRACT_GENERIC = """() => {
    const results = [];
    const body = document.body.innerText || '';
    
    // Find all elements that might contain match/event info
    const allElements = document.querySelectorAll('article, .prediction, .tip, .match, .event, .pick, [class*="prediction"], [class*="match"], [class*="tip"], [class*="pick"], [class*="event"]');
    
    for (const el of allElements) {
        const text = el.innerText || '';
        if (text.length < 20 || text.length > 5000) continue;
        
        // Look for "vs" or " - " patterns indicating a match
        const vsMatch = text.match(/([A-ZÀ-Ž][A-Za-zÀ-ž.\\s]+?)\\s+(?:vs?\\.?|[-–—]|@)\\s+([A-ZÀ-Ž][A-Za-zÀ-ž.\\s]+)/u);
        if (!vsMatch) continue;
        
        const home = vsMatch[1].trim();
        const away = vsMatch[2].trim();
        if (home.length < 3 || away.length < 3 || home.length > 40 || away.length > 40) continue;
        
        // Extract reasoning from nearby elements
        let reasoning = '';
        const reasoningEl = el.querySelector('.reasoning, .analysis, .description, .content, .tip-content, .prediction-content, .expert-analysis, p');
        if (reasoningEl) reasoning = (reasoningEl.innerText || '').trim();
        if (!reasoning) reasoning = text.substring(text.indexOf(away) + away.length).trim();
        
        // Extract odds
        let odds = null;
        const oddsMatch = text.match(/@\\s*(\\d+\\.\\d+)|odds?\\s*[:=]?\\s*(\\d+\\.\\d+)|(\\d+\\.\\d{2})\\b/i);
        if (oddsMatch) {
            const val = parseFloat(oddsMatch[1] || oddsMatch[2] || oddsMatch[3]);
            if (val >= 1.01 && val <= 100) odds = val;
        }
        
        // Extract market from text
        let market = 'N/A';
        const marketPatterns = [
            /(?:corners?|ck)\\s*(?:over|under|o|u)\\s*\\d+\\.?\\d*/i,
            /(?:over|under)\\s*\\d+\\.?\\d*\\s*(?:goals?|corners?|cards?|fouls?|games?|sets?|points?)?/i,
            /btts|both\\s*teams?\\s*(?:to\\s*)?score/i,
            /double\\s*chance/i,
            /draw\\s*no\\s*bet/i,
            /(?:to\\s*win|winner|moneyline)/i,
            /handicap\\s*[+-]?\\s*\\d+\\.?\\d*/i,
        ];
        for (const pat of marketPatterns) {
            const m = text.match(pat);
            if (m) { market = m[0].trim(); break; }
        }
        
        // Extract accuracy
        let accuracy = null;
        const accMatch = text.match(/(\\d{1,3})\\s*%/);
        if (accMatch) {
            const val = parseInt(accMatch[1]);
            if (val > 0 && val <= 100) accuracy = val;
        }
        
        // Extract tipster name
        let tipster = '';
        const tipsterEl = el.querySelector('.tipster, .author, .expert, .username, [class*="tipster"], [class*="author"]');
        if (tipsterEl) tipster = (tipsterEl.innerText || '').trim();
        
        // Extract competition/league
        let competition = '';
        const compEl = el.querySelector('.league, .competition, .tournament, [class*="league"], [class*="competition"]');
        if (compEl) competition = (compEl.innerText || '').trim();
        
        results.push({
            home: home,
            away: away,
            reasoning: reasoning.substring(0, 800),
            odds: odds,
            market: market,
            accuracy: accuracy,
            tipster: tipster,
            competition: competition,
            full_text: text.substring(0, 1500),
        });
    }
    
    return results;
}"""

# ZawodTyper: structural HTML with id="match-name{ID}" and id="type{ID}"
_JS_EXTRACT_ZAWODTYPER = """() => {
    const results = [];
    const matchIds = [];
    
    // Find all match-name elements
    document.querySelectorAll('[id^="match-name"]').forEach(el => {
        const id = el.id.replace('match-name', '');
        if (id) matchIds.push(id);
    });
    
    for (const mid of matchIds) {
        const matchEl = document.querySelector('#match-name' + mid);
        const typeEl = document.querySelector('#type' + mid);
        if (!matchEl) continue;
        
        // Get the searched-in div inside
        const searchDiv = matchEl.querySelector('.searched-in') || matchEl;
        const matchText = (searchDiv.innerText || searchDiv.textContent || '').trim();
        
        const typeDiv = typeEl ? (typeEl.querySelector('.searched-in') || typeEl) : null;
        const typeText = typeDiv ? (typeDiv.innerText || typeDiv.textContent || '').trim() : '';
        
        // Parse "Team A - Team B" or "Team A vs Team B"
        let home = '', away = '';
        const dashMatch = matchText.match(/(.+?)\\s*[-–—]\\s*(.+)/);
        const vsMatch = matchText.match(/(.+?)\\s+vs\\.?\\s+(.+)/i);
        if (dashMatch) { home = dashMatch[1].trim(); away = dashMatch[2].trim(); }
        else if (vsMatch) { home = vsMatch[1].trim(); away = vsMatch[2].trim(); }
        else continue;
        
        if (home.length < 3 || away.length < 3) continue;
        
        // Get surrounding block for reasoning and context
        const parentBlock = matchEl.closest('.tip-block, .prediction-block, .row, article, section') || matchEl.parentElement;
        const blockText = parentBlock ? (parentBlock.innerText || '').trim() : '';
        
        // Extract reasoning from block
        let reasoning = '';
        if (parentBlock) {
            const reasoningEl = parentBlock.querySelector('.argument, .reasoning, .uzasadnienie, .description, p');
            if (reasoningEl) reasoning = (reasoningEl.innerText || '').trim();
        }
        
        // Extract odds from the block
        let odds = null;
        const oddsMatch = blockText.match(/kurs\\s*[:=]?\\s*(\\d+\\.\\d+)|@\\s*(\\d+\\.\\d+)|(\\d+\\.\\d{2})\\b/i);
        if (oddsMatch) {
            const val = parseFloat(oddsMatch[1] || oddsMatch[2] || oddsMatch[3]);
            if (val >= 1.01 && val <= 100) odds = val;
        }
        
        // Extract accuracy from block
        let accuracy = null;
        const accMatch = blockText.match(/(\\d{1,3})\\s*%/);
        if (accMatch) {
            const val = parseInt(accMatch[1]);
            if (val > 0 && val <= 100) accuracy = val;
        }
        
        // Tipster name
        let tipster = 'ZawodTyper';
        const tipsterMatch = blockText.match(/(?:Typer|Tipster|Autor):\\s*(\\S+)/i);
        if (tipsterMatch) tipster = tipsterMatch[1];
        
        results.push({
            home: home,
            away: away,
            market: typeText || 'N/A',
            reasoning: reasoning.substring(0, 800) || blockText.substring(0, 800),
            odds: odds,
            accuracy: accuracy,
            tipster: tipster,
            competition: '',
            full_text: blockText.substring(0, 1500),
        });
    }
    
    return results;
}"""

# PicksWise: Next.js — extract from __NEXT_DATA__ + rendered expert predictions
_JS_EXTRACT_PICKSWISE = """() => {
    const results = [];
    
    // Method 1: Extract from __NEXT_DATA__
    try {
        const ndEl = document.querySelector('#__NEXT_DATA__');
        if (ndEl) {
            const nd = JSON.parse(ndEl.textContent);
            const state = nd?.props?.pageProps?.initialState || {};
            const sp = state.sportPredictions || {};
            for (const [key, pageData] of Object.entries(sp)) {
                if (!Array.isArray(pageData)) continue;
                for (const dayGroup of pageData) {
                    for (const pred of (dayGroup.predictions || [])) {
                        const event = pred.event || '';
                        const parts = event.split(/\\s+vs?\\.?\\s+/i);
                        if (parts.length !== 2) continue;
                        results.push({
                            home: parts[0].trim(),
                            away: parts[1].trim(),
                            market: 'N/A',
                            reasoning: pred.title || '',
                            odds: null,
                            accuracy: null,
                            tipster: 'PicksWise',
                            competition: '',
                            full_text: JSON.stringify(pred).substring(0, 1500),
                        });
                    }
                }
            }
        }
    } catch(e) {}
    
    // Method 2: Extract from rendered Expert Predictions section
    const expertSection = document.querySelector('[class*="expert"], [class*="prediction-detail"], article');
    if (expertSection) {
        const picks = expertSection.querySelectorAll('[class*="pick"], [class*="bet"], [class*="selection"]');
        for (const pickEl of picks) {
            const pickText = (pickEl.innerText || '').trim();
            if (pickText.length < 10) continue;
            
            // Extract the pick type and value
            const lines = pickText.split('\\n').map(l => l.trim()).filter(l => l);
            if (lines.length >= 2) {
                const market = lines[0];
                const value = lines[1];
                
                // Find reasoning nearby
                let reasoning = '';
                const next = pickEl.nextElementSibling;
                if (next && next.textContent.length > 30) {
                    reasoning = next.innerText.trim();
                }
                
                results.push({
                    home: '',
                    away: '',
                    market: market + ': ' + value,
                    reasoning: reasoning.substring(0, 800),
                    odds: null,
                    accuracy: null,
                    tipster: 'PicksWise Expert',
                    competition: '',
                    full_text: pickText.substring(0, 1500),
                    is_detail_pick: true,
                });
            }
        }
    }
    
    return results;
}"""

# Sportsgambler: match cards with team names and prediction links
_JS_EXTRACT_SPORTSGAMBLER = """() => {
    const results = [];
    
    // Find prediction link blocks
    const predLinks = document.querySelectorAll('a[href*="/betting-tips/"][href*="/predictions/"]');
    for (const link of predLinks) {
        const text = (link.innerText || '').trim();
        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
        
        let home = '', away = '', competition = '';
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].toLowerCase() === 'vs' || lines[i].toLowerCase() === 'v') {
                if (i > 0 && i < lines.length - 1) {
                    home = lines[i - 1];
                    away = lines[i + 1];
                    if (i >= 2) competition = lines[i - 2];
                }
                break;
            }
            // Also try "vs" within a line
            const vsMatch = lines[i].match(/([A-ZÀ-Ž][A-Za-zÀ-ž.\\s]+?)\\s+vs?\\.?\\s+([A-ZÀ-Ž][A-Za-zÀ-ž.\\s]+)/u);
            if (vsMatch) {
                home = vsMatch[1].trim();
                away = vsMatch[2].trim();
                break;
            }
        }
        
        if (!home || !away || home.length < 3 || away.length < 3) continue;
        
        // Detect sport from URL
        let sport = 'football';
        const href = link.getAttribute('href') || '';
        if (href.includes('/tennis/')) sport = 'tennis';
        else if (href.includes('/basketball/') || href.includes('/nba/')) sport = 'basketball';
        else if (href.includes('/hockey/') || href.includes('/nhl/')) sport = 'hockey';
        
        results.push({
            home: home,
            away: away,
            market: 'N/A',
            reasoning: 'Prediction available: ' + href,
            odds: null,
            accuracy: null,
            tipster: 'Sportsgambler',
            competition: competition,
            full_text: text.substring(0, 1500),
            sport: sport,
        });
    }
    
    // Also find match cards in the main content
    const matchCards = document.querySelectorAll('.match-card, .prediction-card, [class*="match-item"]');
    for (const card of matchCards) {
        const text = (card.innerText || '').trim();
        const vsMatch = text.match(/([A-ZÀ-Ž][A-Za-zÀ-ž.'\\s]+?)\\s+vs?\\.?\\s+([A-ZÀ-Ž][A-Za-zÀ-ž.'\\s]+)/u);
        if (!vsMatch) continue;
        
        const home = vsMatch[1].trim();
        const away = vsMatch[2].trim();
        if (home.length < 3 || away.length < 3) continue;
        
        results.push({
            home: home,
            away: away,
            market: 'N/A',
            reasoning: text.substring(text.indexOf(away) + away.length).trim().substring(0, 800),
            odds: null,
            accuracy: null,
            tipster: 'Sportsgambler',
            competition: '',
            full_text: text.substring(0, 1500),
        });
    }
    
    return results;
}"""

# Deep reasoning extraction — finds expert analysis, comments, tipster arguments
_JS_EXTRACT_DEEP_REASONING = """() => {
    const sections = [];
    
    // Look for analysis/reasoning sections
    const selectors = [
        '.analysis', '.reasoning', '.expert-analysis', '.prediction-analysis',
        '.tip-reasoning', '.bet-analysis', '.preview', '.match-preview',
        '[class*="analysis"]', '[class*="reasoning"]', '[class*="preview"]',
        '[class*="expert"]', '[class*="insight"]',
        // Polish sites
        '.uzasadnienie', '.argument', '.opis',
        // Comment sections
        '.comments', '.user-comments', '[class*="comment"]',
    ];
    
    for (const sel of selectors) {
        const elements = document.querySelectorAll(sel);
        for (const el of elements) {
            const text = (el.innerText || '').trim();
            if (text.length < 50 || text.length > 5000) continue;
            
            // Find parent event context
            let eventContext = '';
            const parent = el.closest('article, .prediction, .tip, .match, [class*="prediction"]');
            if (parent) {
                const headerEl = parent.querySelector('h1, h2, h3, h4, .title, .event-name');
                if (headerEl) eventContext = (headerEl.innerText || '').trim();
            }
            
            // Extract stats mentioned
            const stats = [];
            const statPatterns = [
                /\\d+\\.?\\d*\\s*(?:corners?|ck)/gi,
                /\\d+\\.?\\d*\\s*(?:fouls?|faul)/gi,
                /\\d+\\.?\\d*\\s*(?:cards?|kart)/gi,
                /\\d+\\.?\\d*\\s*(?:shots?|strzał)/gi,
                /average\\s*[:=]?\\s*\\d+\\.?\\d*/gi,
                /last\\s*\\d+\\s*[:=]?\\s*\\d+\\.?\\d*/gi,
            ];
            for (const pat of statPatterns) {
                const matches = text.match(pat);
                if (matches) stats.push(...matches.map(m => m.trim()));
            }
            
            sections.push({
                text: text.substring(0, 2000),
                event_context: eventContext,
                stats_cited: stats.slice(0, 10),
                element_class: el.className || '',
            });
        }
    }
    
    return sections;
}"""


class TipsterPlaywrightClient(PlaywrightBaseClient):
    """Playwright-based tipster site scraper.

    Uses stealth Playwright to render tipster pages and extract picks
    from the actual DOM instead of parsing raw HTML with regex.
    Inherits circuit breaker, cookie dismiss, Cloudflare handling.
    """

    _COOKIE_SELECTOR = "#onetrust-accept-btn-handler, .qc-cmp2-summary-buttons [mode='primary'], [class*='cookie'] button, [class*='consent'] button, .accept-cookies, #accept-cookies"
    _COOKIE_TIMEOUT = 3000

    def __init__(self):
        super().__init__(
            api_name="tipster",
            base_url="https://tipster-sites.example.com",
            rate_limiter=None,
        )

    def fetch_site(self, site_config: dict, date_str: str) -> list[dict]:
        """Fetch a single tipster site using Playwright DOM extraction.

        Args:
            site_config: Site configuration dict with name, url/urls, parser, etc.
            date_str: Target date in YYYY-MM-DD format

        Returns:
            List of pick dicts with keys: source_site, tipster_name, sport, event,
            home_team, away_team, competition, market, market_type, direction,
            odds, reasoning, accuracy_pct, confidence, stats_cited, fetch_time
        """
        site_name = site_config["name"]
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build URLs
        urls = []
        if site_config.get("url_builder") == "zawodtyper":
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            urls = [self._build_zawodtyper_url(date_obj)]
        elif "urls" in site_config:
            urls = site_config["urls"]
        elif "url" in site_config:
            urls = [site_config["url"]]

        if not urls:
            return []

        all_picks = []
        parser = site_config.get("parser", "generic")
        wait_ms = site_config.get("wait_after_load", 3000)

        for url in urls:
            ctx = None
            try:
                ctx, page = self._load_page(url, wait_ms=wait_ms)

                # Route to appropriate DOM extractor
                if parser == "zawodtyper":
                    raw = self._evaluate_js(page, _JS_EXTRACT_ZAWODTYPER)
                elif parser == "pickswise":
                    raw = self._evaluate_js(page, _JS_EXTRACT_PICKSWISE)
                elif parser == "sportsgambler":
                    raw = self._evaluate_js(page, _JS_EXTRACT_SPORTSGAMBLER)
                else:
                    raw = self._evaluate_js(page, _JS_EXTRACT_GENERIC)

                if not raw:
                    logger.warning(f"[Tipster] {site_name}: DOM extraction returned empty for {url}")
                    # Try deep reasoning as fallback
                    raw = self._evaluate_js(page, _JS_EXTRACT_GENERIC)

                # Also extract deep reasoning sections
                reasoning_sections = self._evaluate_js(page, _JS_EXTRACT_DEEP_REASONING) or []

                # Convert raw DOM data to structured picks
                picks = self._convert_raw_to_picks(
                    raw or [], site_name, url, now_iso,
                    reasoning_sections, parser
                )
                all_picks.extend(picks)

                logger.info(f"[Tipster] {site_name}: extracted {len(picks)} picks from {url}")

            except APIError as e:
                logger.warning(f"[Tipster] {site_name}: {e}")
            except Exception as e:
                logger.error(f"[Tipster] {site_name}: unexpected error for {url}: {e}")
            finally:
                if ctx:
                    try:
                        ctx.close()
                    except Exception:
                        pass

        return all_picks

    def _convert_raw_to_picks(
        self,
        raw_data: list[dict],
        site_name: str,
        url: str,
        now_iso: str,
        reasoning_sections: list[dict],
        parser: str,
    ) -> list[dict]:
        """Convert raw DOM extraction data to structured tipster picks."""
        picks = []
        seen_events = set()

        # Build reasoning lookup by event context
        reasoning_lookup = {}
        for section in reasoning_sections:
            ctx = section.get("event_context", "").lower()
            if ctx:
                reasoning_lookup[ctx] = section

        for item in raw_data:
            home = (item.get("home") or "").strip()
            away = (item.get("away") or "").strip()

            if not home or not away or len(home) < 3 or len(away) < 3:
                continue
            if len(home) > 40 or len(away) > 40:
                continue

            # Dedup
            event_key = f"{home.lower()}|{away.lower()}"
            if event_key in seen_events:
                continue
            seen_events.add(event_key)

            # Detect sport
            full_text = item.get("full_text", "")
            sport = item.get("sport") or self._detect_sport(full_text, url)

            # Market classification
            market = item.get("market") or "N/A"
            market_type = self._classify_market(market, full_text)
            direction = self._extract_direction(market, full_text)

            # Enhance reasoning from deep extraction
            reasoning = item.get("reasoning") or ""
            event_lower = f"{home} vs {away}".lower()
            for ctx_key, section in reasoning_lookup.items():
                if home.lower() in ctx_key or away.lower() in ctx_key:
                    deep_text = section.get("text", "")
                    if len(deep_text) > len(reasoning):
                        reasoning = deep_text
                    break

            # Extract stats cited
            stats_cited = self._extract_stats_cited(reasoning + " " + full_text)

            odds = item.get("odds")
            accuracy = item.get("accuracy")
            tipster = item.get("tipster") or site_name

            picks.append({
                "source_site": site_name,
                "tipster_name": tipster,
                "sport": sport,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "competition": item.get("competition", ""),
                "market": market,
                "market_type": market_type,
                "direction": direction,
                "odds": odds,
                "reasoning": reasoning[:800],
                "accuracy_pct": accuracy,
                "confidence": "high" if accuracy and accuracy > 70 else ("medium" if accuracy and accuracy > 55 else "medium"),
                "stats_cited": stats_cited,
                "fetch_time": now_iso,
            })

        return picks

    def _detect_sport(self, text: str, url: str = "") -> str:
        """Detect sport from text content and URL."""
        combined = (text + " " + url).lower()
        sport_keywords = {
            "tennis": ["tennis", "tenis", "atp", "wta", "roland", "wimbledon", "grand slam", "challenger"],
            "basketball": ["basketball", "koszykówka", "nba", "euroleague", "ncaa", "fiba"],
            "volleyball": ["volleyball", "siatkówka", "plusliga", "superlega"],
            "hockey": ["hockey", "hokej", "nhl", "khl", "shl", "liiga"],
        }
        for sport, keywords in sport_keywords.items():
            for kw in keywords:
                if kw in combined:
                    return sport
        if "/soccer/" in url or "/football/" in url:
            return "football"
        if "/tennis/" in url:
            return "tennis"
        if "/nba/" in url or "/basketball/" in url:
            return "basketball"
        if "/nhl/" in url or "/hockey/" in url:
            return "hockey"
        return "football"

    def _classify_market(self, market_text: str, context: str = "") -> str:
        """Classify market as 'statistical' or 'outcome'."""
        market_lower = market_text.lower()
        outcome_kw = {"winner", "zwycięzca", "1x2", "ml", "moneyline", "draw", "btts", "both teams to score", "double chance"}
        stat_kw = {"corners", "corner", "fouls", "foul", "cards", "card", "shots", "games", "sets", "points",
                    "frames", "over", "under", "handicap", "totals", "total", "aces", "rebounds", "assists"}

        for kw in outcome_kw:
            if kw in market_lower:
                return "outcome"
        for kw in stat_kw:
            if kw in market_lower:
                return "statistical"
        return "outcome"

    def _extract_direction(self, market_text: str, context: str = "") -> str:
        """Extract direction from market text."""
        combined = (market_text + " " + context).lower()
        if any(w in combined for w in ["over", "powyżej"]):
            return "OVER"
        if any(w in combined for w in ["under", "poniżej"]):
            return "UNDER"
        if any(w in combined for w in ["btts", "both teams to score"]):
            return "BTTS"
        if any(w in combined for w in ["double chance"]):
            return "DC"
        if any(w in combined for w in [" win", "winner", "moneyline"]):
            return "WIN"
        if any(w in combined for w in ["draw", "remis"]):
            return "DRAW"
        return "OTHER"

    def _extract_stats_cited(self, text: str) -> list[str]:
        """Extract specific statistics cited in text."""
        stats = []
        patterns = [
            r'(\d+\.?\d*)\s*(?:corners?|ck)',
            r'(\d+\.?\d*)\s*(?:fouls?)',
            r'(\d+\.?\d*)\s*(?:cards?)',
            r'(\d+\.?\d*)\s*(?:shots?)',
            r'(\d+\.?\d*)\s*(?:games?)',
            r'(\d+\.?\d*)\s*(?:sets?)',
            r'(\d+\.?\d*)\s*(?:points?)',
            r'average\s*[:=]?\s*(\d+\.?\d*)',
            r'last\s*\d+\s*[:=]?\s*(\d+\.?\d*)',
        ]
        for pattern in patterns:
            for m in re.findall(pattern, text, re.IGNORECASE):
                stats.append(str(m))
        return stats[:10]

    @staticmethod
    def _build_zawodtyper_url(date: datetime) -> str:
        """Build ZawodTyper daily URL with Polish names."""
        MONTHS = {1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
                  5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
                  9: "wrzesnia", 10: "pazdziernika", 11: "listopada", 12: "grudnia"}
        WEEKDAYS = {0: "poniedzialek", 1: "wtorek", 2: "sroda", 3: "czwartek",
                    4: "piatek", 5: "sobota", 6: "niedziela"}
        return f"https://www.zawodtyper.pl/typy-dnia-{date.day}-{MONTHS[date.month]}-{WEEKDAYS[date.weekday()]}/"

