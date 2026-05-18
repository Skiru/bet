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
    const seen = new Set();
    
    // Strategy 1: Find elements with tipster/prediction-related classes or data attributes
    const selectors = [
        'article', '.prediction', '.tip', '.match', '.event', '.pick',
        '[class*="prediction"]', '[class*="match"]', '[class*="tip"]',
        '[class*="pick"]', '[class*="event"]', '[class*="fixture"]',
        '[class*="game"]', '[class*="card"]', '[class*="bet"]',
        '[data-match]', '[data-event]', '[data-fixture]',
        'li', 'tr', 'section > div', 'main div'
    ];
    
    const allElements = document.querySelectorAll(selectors.join(', '));
    
    for (const el of allElements) {
        const text = el.innerText || '';
        if (text.length < 15 || text.length > 8000) continue;
        
        // Look for "vs" or " - " patterns indicating a match
        // Support: "Team A vs Team B", "Team A - Team B", "Team A v Team B", "Team A @ Team B"
        const vsPatterns = [
            /([A-ZÀ-Ža-zà-ž0-9][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40}?)\\s+(?:vs?\\.?|VS\\.?)\\s+([A-ZÀ-Ža-zà-ž0-9][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40})/u,
            /([A-ZÀ-Ž][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40}?)\\s+[-–—]\\s+([A-ZÀ-Ž][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40})/u,
            /([A-ZÀ-Ž][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40}?)\\s+@\\s+([A-ZÀ-Ž][A-Za-zÀ-ž0-9.'\\/\\s-]{1,40})/u,
        ];
        
        let home = '', away = '';
        for (const pat of vsPatterns) {
            const m = text.match(pat);
            if (m) { home = m[1].trim(); away = m[2].trim(); break; }
        }
        if (!home || !away) continue;
        if (home.length < 2 || away.length < 2 || home.length > 45 || away.length > 45) continue;
        
        // Dedup by teams
        const key = (home + '|' + away).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        
        // Extract reasoning from nearby elements or text after team names
        let reasoning = '';
        const reasoningSelectors = '.reasoning, .analysis, .description, .content, .tip-content, .prediction-content, .expert-analysis, .comment, .text, p';
        const reasoningEl = el.querySelector(reasoningSelectors);
        if (reasoningEl) reasoning = (reasoningEl.innerText || '').trim();
        if (!reasoning) {
            const afterTeams = text.substring(text.indexOf(away) + away.length).trim();
            if (afterTeams.length > 10) reasoning = afterTeams;
        }
        
        // Extract odds (decimal format: 1.50 - 99.00)
        let odds = null;
        const oddsPatterns = [
            /@\\s*(\\d+\\.\\d+)/,
            /odds?\\s*[:=]?\\s*(\\d+\\.\\d+)/i,
            /kurs\\s*[:=]?\\s*(\\d+\\.\\d+)/i,
            /(\\d+\\.\\d{2})\\b/,
        ];
        for (const op of oddsPatterns) {
            const om = text.match(op);
            if (om) {
                const val = parseFloat(om[1]);
                if (val >= 1.01 && val <= 100) { odds = val; break; }
            }
        }
        
        // Extract market from text (extended patterns)
        let market = 'N/A';
        const marketPatterns = [
            /(?:corners?|ck|rzut[yó]w?\\s*ro[żz]n)/i,
            /(?:over|under|powyżej|poniżej)\\s*\\d+[.,]?\\d*/i,
            /(?:kart(?:ki|ek|ka)|cards?|yellow)/i,
            /(?:fouls?|faul[ei])/i,
            /btts|both\\s*teams?\\s*(?:to\\s*)?score/i,
            /(?:over|under)\\s*\\d+[.,]?\\d*\\s*(?:goals?|gol|bramk|corners?|cards?|fouls?|games?|gem|sets?|set|points?|punkt)/i,
            /double\\s*chance/i,
            /draw\\s*no\\s*bet/i,
            /(?:to\\s*win|winner|moneyline|zwycięzca|wygra)/i,
            /handicap\\s*[+-]?\\s*\\d+[.,]?\\d*/i,
            /total\\s*(?:over|under|o|u)/i,
        ];
        for (const pat of marketPatterns) {
            const m = text.match(pat);
            if (m) { market = m[0].trim(); break; }
        }
        
        // Extract accuracy/percentage
        let accuracy = null;
        const accMatch = text.match(/(\\d{1,3})\\s*%/);
        if (accMatch) {
            const val = parseInt(accMatch[1]);
            if (val > 0 && val <= 100) accuracy = val;
        }
        
        // Extract tipster name from child elements
        let tipster = '';
        const tipsterEl = el.querySelector('.tipster, .author, .expert, .username, .user, [class*="tipster"], [class*="author"], [class*="user"], [class*="expert"]');
        if (tipsterEl) tipster = (tipsterEl.innerText || '').trim();
        
        // Extract competition/league
        let competition = '';
        const compEl = el.querySelector('.league, .competition, .tournament, [class*="league"], [class*="competition"], [class*="tournament"], [class*="country"]');
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
    const seen = new Set();
    
    // Strategy 1: Find match-name elements (legacy structure)
    const matchIds = [];
    document.querySelectorAll('[id^="match-name"]').forEach(el => {
        const id = el.id.replace('match-name', '');
        if (id) matchIds.push(id);
    });
    
    for (const mid of matchIds) {
        const matchEl = document.querySelector('#match-name' + mid);
        const typeEl = document.querySelector('#type' + mid);
        if (!matchEl) continue;
        
        const searchDiv = matchEl.querySelector('.searched-in') || matchEl;
        const matchText = (searchDiv.innerText || searchDiv.textContent || '').trim();
        
        const typeDiv = typeEl ? (typeEl.querySelector('.searched-in') || typeEl) : null;
        const typeText = typeDiv ? (typeDiv.innerText || typeDiv.textContent || '').trim() : '';
        
        let home = '', away = '';
        const dashMatch = matchText.match(/(.+?)\\s*[-–—]\\s*(.+)/);
        const vsMatch = matchText.match(/(.+?)\\s+vs\\.?\\s+(.+)/i);
        if (dashMatch) { home = dashMatch[1].trim(); away = dashMatch[2].trim(); }
        else if (vsMatch) { home = vsMatch[1].trim(); away = vsMatch[2].trim(); }
        else continue;
        
        if (home.length < 3 || away.length < 3) continue;
        const key = (home + '|' + away).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        
        const parentBlock = matchEl.closest('.tip-block, .prediction-block, .row, article, section') || matchEl.parentElement;
        const blockText = parentBlock ? (parentBlock.innerText || '').trim() : '';
        
        let reasoning = '';
        if (parentBlock) {
            const reasoningEl = parentBlock.querySelector('.argument, .reasoning, .uzasadnienie, .description, p');
            if (reasoningEl) reasoning = (reasoningEl.innerText || '').trim();
        }
        
        let odds = null;
        const oddsMatch = blockText.match(/kurs\\s*[:=]?\\s*(\\d+\\.\\d+)|@\\s*(\\d+\\.\\d+)|(\\d+\\.\\d{2})\\b/i);
        if (oddsMatch) {
            const val = parseFloat(oddsMatch[1] || oddsMatch[2] || oddsMatch[3]);
            if (val >= 1.01 && val <= 100) odds = val;
        }
        
        let accuracy = null;
        const accMatch = blockText.match(/(\\d{1,3})\\s*%\\s*\\((\\d+)\\)/);
        if (accMatch) {
            const val = parseInt(accMatch[1]);
            if (val > 0 && val <= 100) accuracy = val;
        }
        
        let tipster = 'ZawodTyper';
        const tipsterMatch = blockText.match(/(?:Typer|Tipster|Autor):\\s*(\\S+)/i);
        if (tipsterMatch) tipster = tipsterMatch[1];
        
        // Build meaningful reasoning
        const reasonParts = [];
        if (accuracy) reasonParts.push('Tipster accuracy: ' + accuracy + '% (tracked)');
        if (typeText) reasonParts.push('Pick: ' + typeText);
        if (reasoning && reasoning.length > 20) reasonParts.push(reasoning);
        const finalReasoning = reasonParts.join(' | ') || blockText.substring(0, 400);
        
        results.push({
            home, away,
            market: typeText || 'N/A',
            reasoning: finalReasoning.substring(0, 800),
            odds, accuracy, tipster,
            competition: '',
            full_text: blockText.substring(0, 1500),
        });
    }
    
    // Strategy 2: New ZawodTyper structure — find pick blocks by content patterns
    // The site uses dynamic content with tipster accuracy badges and pick text
    if (results.length < 3) {
        // Look for elements containing "vs" or " - " with team-like content
        const allText = document.body.innerText || '';
        const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            // Match "Team A - Team B" pattern
            const matchPat = line.match(/^([A-Z\\u00C0-\\u024F][^\\n]{2,35})\\s*[-\\u2013\\u2014]\\s*([A-Z\\u00C0-\\u024F][^\\n]{2,35})$/);
            if (!matchPat) continue;
            
            let home = matchPat[1].trim();
            let away = matchPat[2].trim();
            
            // Skip if contains garbage
            if (home.length < 3 || away.length < 3 || home.length > 40 || away.length > 40) continue;
            const key = (home + '|' + away).toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            
            // Look at surrounding lines for pick details (next 5 lines)
            const context = lines.slice(Math.max(0, i-2), Math.min(lines.length, i+8)).join(' ');
            
            // Extract pick type (next meaningful line after match)
            let typeText = '';
            for (let j = i+1; j < Math.min(i+5, lines.length); j++) {
                const nextLine = lines[j];
                if (nextLine.match(/^[A-Z0-9]/) && nextLine.length > 3 && nextLine.length < 80 &&
                    !nextLine.match(/^\\d{1,2}[:.]\\d{2}/)) {
                    typeText = nextLine;
                    break;
                }
            }
            
            // Extract accuracy
            let accuracy = null;
            const accMatch = context.match(/(\\d{1,3})\\s*%\\s*\\((\\d+)\\)/);
            if (accMatch) accuracy = parseInt(accMatch[1]);
            
            // Build reasoning
            const reasonParts = [];
            if (accuracy) reasonParts.push('Tipster accuracy: ' + accuracy + '% (tracked)');
            if (typeText) reasonParts.push('Pick: ' + typeText);
            
            results.push({
                home, away,
                market: typeText || 'N/A',
                reasoning: reasonParts.join(' | ') || context.substring(0, 400),
                odds: null,
                accuracy,
                tipster: 'ZawodTyper',
                competition: '',
                full_text: context.substring(0, 1500),
            });
        }
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

# BetIdeas: extract match detail page URLs from rendered listing cards
_JS_EXTRACT_BETIDEAS = r"""() => {
    const results = [];
    const seen = new Set();
    
    // BetIdeas renders match cards via AJAX with fbbackend plugin
    // Each card has a link to the detail page with format: /league/team-vs-team-id
    const links = document.querySelectorAll('a[href*="-vs-"]');
    for (const link of links) {
        const href = link.href || link.getAttribute('href') || '';
        if (!href || !href.includes('-vs-')) continue;
        
        // Extract team names from link text or href
        const text = (link.innerText || '').trim();
        const hrefParts = href.split('/').filter(p => p);
        const slug = hrefParts[hrefParts.length - 1] || '';
        
        // Extract teams from slug: "team-a-vs-team-b-1234567"
        const vsMatch = slug.match(/^(.+?)-vs-(.+?)-(\d+)$/);
        if (!vsMatch) continue;
        
        let home = vsMatch[1].replace(/-/g, ' ').trim();
        let away = vsMatch[2].replace(/-/g, ' ').trim();
        
        // Capitalize words
        home = home.replace(/\\b\\w/g, c => c.toUpperCase());
        away = away.replace(/\\b\\w/g, c => c.toUpperCase());
        
        const key = (home + '|' + away).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        
        // Try to find odds from nearby elements
        let odds = null;
        const card = link.closest('[class*="card"], [class*="match"], [class*="fixture"], tr, li, article');
        if (card) {
            const oddsEl = card.querySelector('[class*="odd"], [class*="decimal"]');
            if (oddsEl) {
                const oddsText = oddsEl.innerText || '';
                const oddsMatch = oddsText.match(/(\\d+\\.\\d+)/);
                if (oddsMatch) odds = parseFloat(oddsMatch[1]);
            }
        }
        
        results.push({
            home: home,
            away: away,
            market: 'N/A',
            reasoning: '',
            odds: odds,
            accuracy: null,
            tipster: 'BetIdeas',
            competition: '',
            detail_url: href.startsWith('http') ? href : 'https://betideas.com' + href,
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
                # ZawodTyper: use XHR interception for structured data with analysis
                if parser == "zawodtyper":
                    picks = self._fetch_zawodtyper_via_xhr(url, now_iso)
                    if picks:
                        all_picks.extend(picks)
                        logger.info(f"[Tipster] {site_name}: XHR extracted {len(picks)} picks from {url}")
                        continue
                    # Fallback to DOM extraction if XHR capture failed
                    logger.warning(f"[Tipster] {site_name}: XHR capture empty, falling back to DOM extraction")

                ctx, page = self._load_page(url, wait_ms=wait_ms)

                # Route to appropriate DOM extractor
                if parser == "zawodtyper":
                    raw = self._evaluate_js(page, _JS_EXTRACT_ZAWODTYPER)
                elif parser == "pickswise":
                    raw = self._evaluate_js(page, _JS_EXTRACT_PICKSWISE)
                elif parser == "sportsgambler":
                    raw = self._evaluate_js(page, _JS_EXTRACT_SPORTSGAMBLER)
                elif parser == "betideas":
                    raw = self._evaluate_js(page, _JS_EXTRACT_BETIDEAS)
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

            # Validate reasoning quality — reject navigation/boilerplate garbage
            reasoning = self._clean_reasoning(reasoning, home, away)

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
                "detail_url": item.get("detail_url", ""),
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
        outcome_kw = {"winner", "zwycięzca", "1x2", "ml", "moneyline", "draw", "btts", "both teams to score", "double chance",
                      "remis", "wygra", "przegra", "dnb", "draw no bet"}
        stat_kw = {"corners", "corner", "fouls", "foul", "cards", "card", "shots", "games", "sets", "points",
                    "frames", "over", "under", "handicap", "totals", "total", "aces", "rebounds", "assists",
                    "rzuty rożne", "rzutów rożnych", "kartki", "kartek", "kartka", "żółte kartki",
                    "faule", "fauli", "strzały", "strzałów", "gole", "bramki", "bramek",
                    "sety", "setów", "gemy", "gemów", "punkty", "punktów",
                    "powyżej", "poniżej", "auty", "autów", "spalone", "spalonych",
                    "o/u", "ov", "un"}

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

    def _clean_reasoning(self, reasoning: str, home: str, away: str) -> str:
        """Validate and clean reasoning text — reject garbage, keep analysis.

        ZawodTyper and other sites produce navigation/UI text that's NOT analysis.
        Only keep reasoning that contains meaningful sports commentary.
        """
        if not reasoning:
            return ""

        # Strip common garbage patterns from ZawodTyper page navigation
        garbage_markers = [
            "BUKMACHER", "WYDARZENIE", "DYSCYPLINA", "TYP\n",
            "sign up", "claim now", "no deposit", "free bet",
            "bonus code", "gold coins", "subscribe",
            "cookie", "privacy policy", "view prediction",
            "serwis informacyjno", "społecznościowy",
        ]
        lower = reasoning.lower()
        for marker in garbage_markers:
            if marker.lower() in lower:
                return ""

        # If reasoning is mostly short lines (navigation), reject
        lines = [l.strip() for l in reasoning.split('\n') if l.strip()]
        if lines and len(lines) > 3:
            avg_line_len = sum(len(l) for l in lines) / len(lines)
            if avg_line_len < 15:  # Very short lines = navigation/UI elements
                return ""

        # Check for actual analytical content
        signal_words = {
            "win", "lose", "draw", "goal", "corner", "card",
            "form", "attack", "defend", "average", "scored", "possession",
            "expect", "predict", "back", "pick", "over", "under",
            "last", "recent", "match", "season", "injury", "lineup",
            # Polish
            "bramk", "gol", "wynik", "forma", "mecz", "kartek",
            "strzał", "średni", "sezon", "kontuzj", "atak", "obron",
            "wygr", "przegr", "trafność", "accuracy",
        }
        signal_count = sum(1 for w in signal_words if w in lower)

        # Also accept accuracy-formatted reasoning from ZawodTyper
        # e.g., "Tipster accuracy: 65% (tracked) | Pick: Under 2.5 seta"
        if "tipster accuracy:" in lower or "pick:" in lower:
            return reasoning[:800]

        if signal_count < 1:
            return ""

        return reasoning[:800]

    def _fetch_zawodtyper_via_xhr(self, url: str, now_iso: str) -> list[dict]:
        """Fetch ZawodTyper bets by intercepting the NP_ajax.php XHR response.

        ZawodTyper is a Vue.js SPA that loads bets via POST to NP_ajax.php.
        Instead of fragile DOM scraping, we intercept the structured JSON response
        which contains: match_name, content (analysis), rate (odds), discipline,
        type (pick), author_stats (accuracy), etc.
        """
        bets_data: list[dict] = []

        self._ensure_browser()
        ctx, page = self._new_page()

        def _capture_bets(response):
            if "NP_ajax.php" not in response.url:
                return
            if response.request.method != "POST":
                return
            try:
                body = response.json()
                if not isinstance(body, dict) or not body.get("success"):
                    return
                data = body.get("data")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    if "comment_id" in data[0] and "match_name" in data[0]:
                        bets_data.extend(data)
            except Exception:
                pass

        try:
            page.on("response", _capture_bets)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(6000)  # Wait for AJAX bets to load
            self._dismiss_cookies(page)

            # If first batch loaded, scroll to trigger more (lazy-loading)
            if bets_data:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
        except Exception as e:
            logger.warning(f"[Tipster] ZawodTyper XHR capture failed: {e}")
        finally:
            try:
                ctx.close()
            except Exception:
                pass

        if not bets_data:
            return []

        # Convert structured bet data to standard pick format
        picks = []
        seen_events: set[str] = set()
        _DISCIPLINE_MAP = {
            "piłka nożna": "football", "tenis": "tennis",
            "koszykówka": "basketball", "siatkówka": "volleyball",
            "hokej": "hockey", "piłka ręczna": "handball",
            "baseball": "baseball", "mma": "mma",
            "esport": "esport", "boks": "boxing",
        }

        for bet in bets_data:
            # Only process actual bets (not ads/bonuses)
            if bet.get("comment_type") != "bet":
                continue

            match_name = (bet.get("match_name") or "").strip()
            if not match_name:
                continue

            # Parse home - away
            parts = re.split(r'\s*[-–—]\s*', match_name, maxsplit=1)
            if len(parts) != 2:
                parts = re.split(r'\s+vs\.?\s+', match_name, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) != 2:
                continue

            home = parts[0].strip()
            away = parts[1].strip()
            if len(home) < 2 or len(away) < 2:
                continue

            event_key = f"{home.lower()}|{away.lower()}"
            if event_key in seen_events:
                # Keep the one with longer analysis (better reasoning)
                existing = next((p for p in picks if f"{p['home_team'].lower()}|{p['away_team'].lower()}" == event_key), None)
                if existing:
                    content = self._strip_html(bet.get("content") or "")
                    if len(content) > len(existing.get("reasoning") or ""):
                        existing["reasoning"] = content[:800]
                        # Update tipster if this one has better stats
                        author_stats = bet.get("author_stats") or {}
                        ratio_raw = author_stats.get("ratio")
                        if ratio_raw:
                            _ratio = float(ratio_raw)
                            if _ratio > 0:
                                existing["tipster_name"] = bet.get("author_name", "ZawodTyper")
                                existing["accuracy_pct"] = int(_ratio * 100)
                continue
            seen_events.add(event_key)

            # Extract analysis text (strip HTML tags)
            content = self._strip_html(bet.get("content") or "")

            # Accuracy from author_stats
            author_stats = bet.get("author_stats") or {}
            bet_count = int(author_stats.get("bet_count", 0) or 0)
            ratio_raw = author_stats.get("ratio")
            ratio = float(ratio_raw) if ratio_raw else 0.0
            accuracy = int(ratio * 100) if ratio > 0 and bet_count >= 3 else None

            # Odds
            rate = bet.get("rate")
            odds = float(rate) if rate is not None else None

            # Sport detection
            discipline = (bet.get("discipline") or "").lower().strip()
            sport = _DISCIPLINE_MAP.get(discipline, "football")

            # Market and type
            pick_type = (bet.get("type") or "").strip()
            market_type = self._classify_market(pick_type, content)
            direction = self._extract_direction(pick_type, content)

            # Build rich reasoning: accuracy + pick + analysis
            reasoning_parts = []
            if accuracy and bet_count >= 3:
                reasoning_parts.append(f"Tipster {bet.get('author_name', '')}: {accuracy}% ({bet_count} bets)")
            if content and len(content) > 30:
                reasoning_parts.append(content)
            reasoning = " | ".join(reasoning_parts) if reasoning_parts else ""

            # Confidence based on accuracy and bet count
            if accuracy and accuracy >= 65 and bet_count >= 10:
                confidence = "high"
            elif accuracy and accuracy >= 55 and bet_count >= 5:
                confidence = "medium"
            else:
                confidence = "low"

            picks.append({
                "source_site": "ZawodTyper",
                "tipster_name": bet.get("author_name", "ZawodTyper"),
                "sport": sport,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "competition": "",
                "market": pick_type or "N/A",
                "market_type": market_type,
                "direction": direction,
                "odds": odds,
                "reasoning": reasoning[:800],
                "accuracy_pct": accuracy,
                "confidence": confidence,
                "stats_cited": self._extract_stats_cited(content),
                "fetch_time": now_iso,
            })

        logger.info(f"[Tipster] ZawodTyper XHR: {len(picks)} picks from {len(bets_data)} bets")
        return picks

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML tags and decode entities from text."""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _build_zawodtyper_url(date: datetime) -> str:
        """Build ZawodTyper daily URL with Polish names."""
        MONTHS = {1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
                  5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
                  9: "wrzesnia", 10: "pazdziernika", 11: "listopada", 12: "grudnia"}
        WEEKDAYS = {0: "poniedzialek", 1: "wtorek", 2: "sroda", 3: "czwartek",
                    4: "piatek", 5: "sobota", 6: "niedziela"}
        return f"https://www.zawodtyper.pl/typy-dnia-{date.day}-{MONTHS[date.month]}-{WEEKDAYS[date.weekday()]}/"

