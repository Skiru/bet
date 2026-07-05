"""Deterministic HTML extractors for public tipster pages.

Design rules:
- false negatives are acceptable; false positives are not;
- source-specific extractors must preserve valuable context fields;
- no dynamic anti-bot bypass, login, premium or private API scraping;
- every extracted pick remains a source claim, never a bet decision.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .contracts import ExtractionResult, ExtractorVerdict, RawDocument, TipsterPick
from .html_tools import extract_json_ld_event_names, html_to_text, joined_context, link_candidates, text_blocks
from .market_parser import direction, extract_market_text, extract_odds, market_family, parse_line, stats_cited
from .normalization import clean_team_name, collapse_ws, is_garbage_team
from .source_registry import SOURCES
from .zawodtyper import extract_zawodtyper

PARSER_VERSION = "tipster_parser_v2.3_final_source_specific"

EVENT_PATTERNS = [
    re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+(?:vs?\.?|v\.?|@)\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
    re.compile(r"(?P<home>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55}?)\s+[–—-]\s+(?P<away>[A-ZÀ-Ž0-9][A-Za-zÀ-ž0-9.' &/-]{1,55})", re.U),
]

SPORT_HINTS = {
    "football": ("football", "soccer", "premier league", "la liga", "world cup", "btts", "goals"),
    "tennis": ("tennis", "atp", "wta", "wimbledon", "sets", "games", "aces"),
    "basketball": ("basketball", "nba", "euroleague", "points", "rebounds", "assists"),
    "hockey": ("hockey", "nhl", "puck", "goals", "shots on goal"),
    "volleyball": ("volleyball", "siatkówka", "sets", "points"),
}

GARBAGE_REASONING = re.compile(
    r"(cookie|privacy|terms|sign up|bonus|free bet|casino|telegram|download app|responsible gambling|18\+|read more|login|vip|bookmaker|best odds|promo code)",
    re.I,
)

AUTH_OR_COMMERCIAL_PATH = re.compile(r"/(?:go|r|redirect|out|odds|bookmaker|bonus|account|login|signup|join|vip|premium)(?:/|$)", re.I)


def detect_sport(text: str, url: str) -> str:
    low = f"{text} {url}".lower()
    for sport, hints in SPORT_HINTS.items():
        if any(h in low for h in hints):
            return sport
    return "football"


def reasoning_quality(text: str) -> float:
    text = collapse_ws(text)
    if len(text) < 40 or GARBAGE_REASONING.search(text):
        return 0.0
    signals = [
        "form", "average", "avg", "last", "recent", "scored", "conceded", "injury", "injuries", "lineup",
        "expected", "xg", "xga", "xa", "ppda", "odds movement", "tempo", "pressing", "weather",
        "expect", "value", "prediction", "pick", "over", "under", "goals", "corners",
        "cards", "shots", "forma", "średnio", "srednio", "ostatnie", "bram", "kart",
    ]
    return min(1.0, sum(1 for s in signals if s.lower() in text.lower()) / 6.0)


def valuable_signals(text: str) -> dict[str, list[str]]:
    """Extract pipeline-useful evidence buckets from source text."""
    buckets: dict[str, list[str]] = {}
    patterns: dict[str, list[str]] = {
        "team_news_injuries": [r"[^.]{0,80}\b(?:injur(?:y|ies|ed)|suspended|doubtful|missing|absent|kontuzj|zawiesz)[^.]{0,100}"],
        "lineups": [r"[^.]{0,80}\b(?:predicted lineup|probable lineup|starting xi|expected xi|lineups?|skład|sklad)[^.]{0,100}"],
        "advanced_metrics": [r"[^.]{0,80}\b(?:xg|xga|xa|ppda|pressing|chance quality|expected goals)[^.]{0,100}"],
        "form_trends": [r"[^.]{0,80}\b(?:last\s+\d+|recent form|unbeaten|winless|scored|conceded|clean sheets?|forma|ostatnie\s+\d+)[^.]{0,100}"],
        "odds_context": [r"[^.]{0,80}\b(?:odds movement|drift|shortened|price|coef|kurs|opening odds)[^.]{0,100}"],
        "weather_context": [r"[^.]{0,80}\b(?:weather|temperature|rain|wind|pitch|pogoda|wiatr|deszcz)[^.]{0,100}"],
    }
    for bucket, pats in patterns.items():
        values: list[str] = []
        for pat in pats:
            for m in re.finditer(pat, text, re.I):
                val = collapse_ws(m.group(0))[:220]
                if val and val not in values:
                    values.append(val)
        if values:
            buckets[bucket] = values[:5]
    return buckets


def _quality_verdict(picks: list[TipsterPick], warnings: list[str] | None = None) -> ExtractorVerdict:
    if not picks:
        return ExtractorVerdict.EMPTY
    if sum(p.extraction_quality for p in picks) / len(picks) < 0.45:
        if warnings is not None:
            warnings.append("average_extraction_quality_below_0_45")
        return ExtractorVerdict.LOW_QUALITY
    return ExtractorVerdict.OK


def _make_pick(source_id: str, url: str, context: str, home: str, away: str, *,
               market_override: str | None = None,
               family_override: str | None = None,
               direction_override: str | None = None,
               reasoning_prefix: str = "") -> TipsterPick | None:
    source = SOURCES[source_id]
    home = clean_team_name(home)
    away = clean_team_name(away)
    if is_garbage_team(home) or is_garbage_team(away) or home.lower() == away.lower():
        return None
    market = market_override or extract_market_text(context)
    fam = family_override or market_family(market + " " + context)
    dirn = direction_override or direction(market + " " + context)
    reasoning = collapse_ws((reasoning_prefix + " " + context).strip())[:1100]
    quality = reasoning_quality(reasoning)
    warnings: list[str] = []
    if market == "N/A":
        warnings.append("market_not_detected")
    if quality < 0.25:
        warnings.append("weak_or_empty_reasoning")
    signals = valuable_signals(context)
    base_quality = 0.33
    if market != "N/A":
        base_quality += 0.20
    if quality >= 0.25:
        base_quality += min(0.25, quality * 0.25)
    if signals:
        base_quality += min(0.17, len(signals) * 0.04)
    if stats_cited(context):
        base_quality += 0.05
    return TipsterPick(
        source_id=source_id,
        source_name=source.display_name,
        sport=detect_sport(context, url),
        event=f"{home} vs {away}",
        home_team=home,
        away_team=away,
        market=market,
        market_family=fam,  # type: ignore[arg-type]
        direction=dirn,  # type: ignore[arg-type]
        line=parse_line(market if market != "N/A" else context),
        odds_decimal=extract_odds(context),
        reasoning=reasoning if quality >= 0.25 else "",
        stats_cited=stats_cited(context),
        source_url=url,
        extraction_quality=round(min(0.96, base_quality), 2),
        warnings=warnings,
        valuable_signals=signals,
        source_record_type="source_claim_evidence",
    )


def _extract_events_from_text(source_id: str, url: str, text: str) -> list[TipsterPick]:
    seen: set[tuple[str, str, str, str]] = set()
    picks: list[TipsterPick] = []
    for pattern in EVENT_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 300)
            end = min(len(text), match.end() + 1050)
            context = collapse_ws(text[start:end])
            pick = _make_pick(source_id, url, context, match.group("home"), match.group("away"))
            if not pick:
                continue
            key = (pick.sport.lower(), pick.home_team.lower(), pick.away_team.lower(), pick.market.lower())
            if key in seen:
                continue
            seen.add(key)
            picks.append(pick)
    return picks


def _result(source_id: str, url: str, picks: list[TipsterPick], warnings: list[str] | None = None) -> ExtractionResult:
    warnings = warnings or []
    return ExtractionResult(
        source_id=source_id,
        url=url,
        verdict=_quality_verdict(picks, warnings),
        picks=picks,
        warnings=warnings,
        parser_version=PARSER_VERSION,
    )


def extract_generic_public_html(doc: RawDocument, source_id: str) -> ExtractionResult:
    text = html_to_text(doc.html)
    try:
        picks = _extract_events_from_text(source_id, doc.url, text)
        return _result(source_id, doc.url, picks)
    except Exception as exc:  # pragma: no cover - defensive fail-closed path
        return ExtractionResult(source_id=source_id, url=doc.url, verdict=ExtractorVerdict.PARSE_ERROR, picks=[], warnings=[str(exc)], parser_version=PARSER_VERSION)


def extract_sportsgambler(doc: RawDocument) -> ExtractionResult:
    """Sportsgambler article/card parser.

    Valuable output: market claim + analyst rationale + team news/injuries,
    predicted lineup, xG/xGA/xA/PPDA, form and odds-movement snippets.
    """
    blocks = text_blocks(doc.html)
    page_text = html_to_text(doc.html)
    picks: list[TipsterPick] = []
    seen: set[tuple[str, str, str]] = set()

    # Article/card text blocks keep rationale close to fixture headings.
    for i, block in enumerate(blocks):
        for pat in EVENT_PATTERNS:
            m = pat.search(block)
            if not m:
                continue
            context = joined_context(blocks[i:i + 8], window=8)
            pick = _make_pick("sportsgambler", doc.url, context, m.group("home"), m.group("away"))
            if not pick:
                continue
            key = (pick.home_team.lower(), pick.away_team.lower(), pick.market.lower())
            if key not in seen:
                seen.add(key)
                picks.append(pick)

    # JSON-LD SportsEvent can recover team names from article pages whose H1 is not "A vs B".
    for home, away in extract_json_ld_event_names(doc.html):
        context = page_text[:1600]
        pick = _make_pick("sportsgambler", doc.url, context, home, away)
        if pick and (pick.home_team.lower(), pick.away_team.lower(), pick.market.lower()) not in seen:
            seen.add((pick.home_team.lower(), pick.away_team.lower(), pick.market.lower()))
            picks.append(pick)

    # Fallback to generic full text.
    if not picks:
        picks = _extract_events_from_text("sportsgambler", doc.url, page_text)
    return _result("sportsgambler", doc.url, picks)


def extract_forebet_table(doc: RawDocument) -> ExtractionResult:
    """Forebet table parser.

    Valuable output: 1/X/2 probabilities, predicted result, correct score,
    average goals/weather/coef context where present. These are model signals,
    never final decisions.
    """
    text = html_to_text(doc.html)
    picks: list[TipsterPick] = []
    row_pat = re.compile(
        r"(?P<home>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,40})\s+(?P<away>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,40})\s+"
        r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{2}:\d{2})\s+"
        r"(?P<p1>\d{1,3})\s+(?P<px>\d{1,3})\s+(?P<p2>\d{1,3})\s+"
        r"(?P<pred>[12X])\s+(?P<compact_score>\d+\s*[-:]\s*\d+)\s+(?P<score>\d+\s*[-:]\s*\d+)"
        r"(?:\s+(?P<avg_goals>\d+(?:\.\d+)?))?",
        re.I,
    )
    for m in row_pat.finditer(text):
        home = clean_team_name(m.group("home"))
        away = clean_team_name(m.group("away"))
        if is_garbage_team(home) or is_garbage_team(away):
            continue
        pred = m.group("pred").upper()
        dirn = "HOME" if pred == "1" else "AWAY" if pred == "2" else "DRAW"
        probs = f"prob_1={m.group('p1')}%; prob_x={m.group('px')}%; prob_2={m.group('p2')}%"
        avg = m.group("avg_goals")
        reasoning = f"Forebet model row: {probs}; prediction={pred}; correct_score={m.group('score')}"
        if avg:
            reasoning += f"; avg_goals={avg}"
        pick = TipsterPick(
            source_id="forebet",
            source_name="Forebet",
            sport="football",
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            market=f"1X2 prediction {pred}; correct score {m.group('score')}",
            market_family="winner",
            direction=dirn,  # type: ignore[arg-type]
            reasoning=reasoning,
            stats_cited=[probs, f"correct_score={m.group('score')}"] + ([f"avg_goals={avg}"] if avg else []),
            published_at=f"{m.group('date')} {m.group('time')}",
            source_url=doc.url,
            extraction_quality=0.83,
            valuable_signals={"model_probabilities": [probs], "score_model": [f"correct_score={m.group('score')}"]},
            source_record_type="structured_model_row",
            pipeline_use=["s2_tipster_evidence", "s3_probability_cross_check", "s4_market_sanity_check"],
        )
        picks.append(pick)
    return _result("forebet", doc.url, picks)


def extract_predictz_table(doc: RawDocument) -> ExtractionResult:
    """PredictZ public table parser.

    Valuable output: page-market context, last-5 form tokens, odds shown on the
    page, predicted score when present.
    """
    text = html_to_text(doc.html)
    url_low = doc.url.lower()
    picks: list[TipsterPick] = []

    # Main match-winner / score table block.
    row_pat = re.compile(
        r"(?P<home>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,45})\s+(?P<form_home>(?:[WDL]\s+){2,8})"
        r"(?P<label>Home|Draw|Away|Over|Under|Yes|No)?\s*(?P<score>\d+[-:]\d+)?[^A-Z]{0,40}"
        r"(?P<away>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,45})\s+(?P<form_away>(?:[WDL]\s+){2,8}).{0,260}?"
        r"(?P=home)\s+v\s+(?P=away)",
        re.I,
    )
    for m in row_pat.finditer(text):
        home = clean_team_name(m.group("home"))
        away = clean_team_name(m.group("away"))
        if is_garbage_team(home) or is_garbage_team(away):
            continue
        label = (m.group("label") or "Home").title()
        score = m.group("score")
        market = "match winner"
        fam = "winner"
        dirn = "HOME" if label == "Home" else "AWAY" if label == "Away" else "DRAW" if label == "Draw" else "OTHER"
        if "both-teams-to-score" in url_low:
            market = f"BTTS {label}"
            fam = "btts"
            dirn = "BTTS_YES" if label.lower() == "yes" else "BTTS_NO" if label.lower() == "no" else "OTHER"
        elif "over-under" in url_low or "overunder" in url_low:
            market = f"{label} 2.5 goals"
            fam = "goals"
            dirn = "OVER" if label.lower() == "over" else "UNDER" if label.lower() == "under" else "OTHER"
        elif "correct-score" in url_low and score:
            market = f"correct score {score}"
            fam = "correct_score"
            dirn = "OTHER"
        elif score:
            market = f"match winner / correct score context {score}"
        context = collapse_ws(m.group(0))
        picks.append(TipsterPick(
            source_id="predictz",
            source_name="PredictZ",
            sport="football",
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            market=market,
            market_family=fam,  # type: ignore[arg-type]
            direction=dirn,  # type: ignore[arg-type]
            odds_decimal=extract_odds(context),
            reasoning=f"PredictZ public table block with page-market context, last-5 form tokens and displayed odds. {context[:500]}",
            stats_cited=([f"predicted_score={score}"] if score else []) + [
                f"home_last5={collapse_ws(m.group('form_home'))}",
                f"away_last5={collapse_ws(m.group('form_away'))}",
            ],
            source_url=doc.url,
            extraction_quality=0.76 if score else 0.68,
            valuable_signals={"form_trends": [f"home_last5={collapse_ws(m.group('form_home'))}", f"away_last5={collapse_ws(m.group('form_away'))}"]},
            source_record_type="table_market_context",
            pipeline_use=["s2_tipster_evidence", "s3_form_consensus_cross_check"],
        ))
    return _result("predictz", doc.url, picks)


def extract_windrawwin(doc: RawDocument) -> ExtractionResult:
    """WinDrawWin parser for prediction/stat rows.

    Valuable output: correct-score-driven inference: winner, BTTS and O/U 2.5
    are inferred from score rows when score is present, while stat pages expose
    BTTS/O-U/corners context for later market sanity checks.
    """
    text = html_to_text(doc.html)
    picks: list[TipsterPick] = []
    row_pat = re.compile(
        r"(?P<home>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,45})\s+(?:v|vs|-)\s+(?P<away>[A-ZÀ-Ž][A-Za-zÀ-ž .'-]{2,45}).{0,160}?"
        r"(?:correct\s+score\s+)?(?P<score>\d+\s*-\s*\d+).{0,160}?(?P<market>BTTS\s+(?:Yes|No)|Over\s+2\.5|Under\s+2\.5|Home\s+Win|Away\s+Win|Draw)?",
        re.I,
    )
    for m in row_pat.finditer(text):
        home = clean_team_name(m.group("home"))
        away = clean_team_name(m.group("away"))
        if is_garbage_team(home) or is_garbage_team(away):
            continue
        score = collapse_ws(m.group("score"))
        explicit_market = collapse_ws(m.group("market") or "")
        h_goals, a_goals = [int(x) for x in re.split(r"\s*[-:]\s*", score)]
        inferred = explicit_market or ("Home Win" if h_goals > a_goals else "Away Win" if a_goals > h_goals else "Draw")
        fam = market_family(inferred)
        if fam == "unknown":
            fam = "winner"
        dirn = direction(inferred)
        if dirn == "WIN":
            dirn = "HOME" if "Home" in inferred else "AWAY" if "Away" in inferred else "DRAW"
        picks.append(TipsterPick(
            source_id="windrawwin",
            source_name="WinDrawWin",
            sport="football",
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            market=f"{inferred}; correct score {score}",
            market_family=fam,  # type: ignore[arg-type]
            direction=dirn,  # type: ignore[arg-type]
            reasoning=f"WinDrawWin score-based row. Correct score={score}; inferred market={inferred}.",
            stats_cited=[f"correct_score={score}", f"inferred_market={inferred}"],
            source_url=doc.url,
            extraction_quality=0.74,
            valuable_signals={"score_model": [f"correct_score={score}"], "market_inference": [f"{inferred}"]},
            source_record_type="score_inferred_prediction",
            pipeline_use=["s2_tipster_evidence", "s3_consensus_cross_check", "s4_correct_score_inference_sanity"],
        ))
    if not picks:
        picks = _extract_events_from_text("windrawwin", doc.url, text)
    return _result("windrawwin", doc.url, picks)


def extract_feedinco(doc: RawDocument) -> ExtractionResult:
    """Feedinco parser with strict affiliate/noise filtering.

    Valuable output: broad multi-sport market index/detail claims, but only if
    explicit fixture+market context survives garbage filters.
    """
    text = html_to_text(doc.html)
    if re.search(r"\b(casino|bonus|free bet|bookmaker|login|vip|promo code)\b", text, re.I):
        return _result("feedinco", doc.url, [], warnings=["feedinco_affiliate_or_auth_noise_blocked"])
    picks = []
    for p in _extract_events_from_text("feedinco", doc.url, text):
        bad = any(token in (p.reasoning or "").lower() for token in ["casino", "bonus", "free bet", "bookmaker", "login", "vip"])
        if bad or p.market == "N/A":
            continue
        p.warnings.append("feedinco_high_affiliate_noise_source_shadow_only")
        p.pipeline_use = ["s2_tipster_evidence_shadow", "s3_noise_checked_cross_source_context"]
        picks.append(p)
    return _result("feedinco", doc.url, picks, warnings=["feedinco_shadow_only_high_noise"])


def extract_bettingclosed_index(doc: RawDocument) -> ExtractionResult:
    """BettingClosed index/detail guard.

    Its public index can be a count/loading page. We do not manufacture picks
    from competition counts; only detail pages with explicit fixture+market are
    allowed.
    """
    text = html_to_text(doc.html)
    low = text.lower()
    if "loading" in low or "vip" in low or "login" in low:
        return ExtractionResult("bettingclosed", doc.url, ExtractorVerdict.EMPTY, [], warnings=["index_or_js_loading_page_no_detail_pick_extraction"], parser_version=PARSER_VERSION)
    count_only = re.search(r"\b\d+\s+predictions?\b", low) and not any(p.search(text) for p in EVENT_PATTERNS)
    if count_only:
        return ExtractionResult("bettingclosed", doc.url, ExtractorVerdict.EMPTY, [], warnings=["competition_count_index_no_fixture_market_extraction"], parser_version=PARSER_VERSION)
    return extract_generic_public_html(doc, "bettingclosed")


def discover_public_detail_links(doc: RawDocument, source_id: str) -> list[str]:
    """Source-safe internal detail discovery for agent fetchers.

    This returns URLs only; the fetcher must still pass robots/ToS/rate gates.
    Commercial redirect/login/premium paths are excluded.
    """
    policy = SOURCES[source_id]
    urls: list[str] = []
    for link in link_candidates(doc.html, policy.base_url):
        if not link.url.startswith(policy.base_url):
            continue
        if AUTH_OR_COMMERCIAL_PATH.search(link.url):
            continue
        label = link.label.lower()
        if not any(tok in label or tok in link.url.lower() for tok in ["prediction", "tip", "preview", "football", "match", "betting-tips"]):
            continue
        if link.url not in urls:
            urls.append(link.url)
    return urls[: policy.max_pages_per_run]


def dispatch_extract(doc: RawDocument, source_id: str, review_data: dict[str, Any] | None = None) -> ExtractionResult:
    if source_id == "zawodtyper":
        return extract_zawodtyper(doc, review_data)
    if source_id == "sportsgambler":
        return extract_sportsgambler(doc)
    if source_id == "forebet":
        return extract_forebet_table(doc)
    if source_id == "predictz":
        specialised = extract_predictz_table(doc)
        if specialised.picks:
            return specialised
        return extract_generic_public_html(doc, "predictz")
    if source_id == "windrawwin":
        return extract_windrawwin(doc)
    if source_id == "feedinco":
        return extract_feedinco(doc)
    if source_id == "bettingclosed":
        return extract_bettingclosed_index(doc)
    return extract_generic_public_html(doc, source_id)


def make_raw(source_id: str, url: str, html: str) -> RawDocument:
    return RawDocument(
        source_id=source_id,
        url=url,
        fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        html=html,
        status_code=200,
        content_type="text/html",
    )
