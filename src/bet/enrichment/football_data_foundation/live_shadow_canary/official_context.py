import os
import re
import hashlib
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from html.parser import HTMLParser
from datetime import datetime, UTC

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.kernel.contracts import (
    SourceDescriptor,
    SourceRole,
    ProofLevel,
    FactType,
    ProviderIdentity,
    EvidenceFreshness,
    PayloadPolicy,
    EvidenceClaim,
    EvidenceClaimBatch,
)


class OfficialContextUnavailableError(Exception):
    """Raised when the official FIFA context cannot be retrieved or parsed."""
    pass


class FIFAHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.match_id = None
        self.home_team = None
        self.away_team = None
        self.kickoff_at = None
        self.venue = None
        self.city = None
        self.active_classes = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if "data-match-id" in attrs_dict:
            self.match_id = attrs_dict["data-match-id"]
        elif "id" in attrs_dict and tag in ("div", "section"):
            if attrs_dict.get("class") in ("match-card", "fixture-card", "match-detail-card"):
                self.match_id = attrs_dict["id"]
        cls = attrs_dict.get("class", "")
        self.active_classes = cls.split()

    def handle_data(self, data):
        data_stripped = data.strip()
        if not data_stripped or not self.active_classes:
            return

        if any(c in self.active_classes for c in ("team-home", "home", "home-team")):
            if not self.home_team:
                self.home_team = data_stripped
        elif any(c in self.active_classes for c in ("team-away", "away", "away-team")):
            if not self.away_team:
                self.away_team = data_stripped
        elif any(c in self.active_classes for c in ("match-date", "date", "kickoff", "kickoff-at")):
            if not self.kickoff_at:
                self.kickoff_at = data_stripped
        elif any(c in self.active_classes for c in ("match-venue", "venue", "stadium")):
            if not self.venue:
                self.venue = data_stripped
        elif any(c in self.active_classes for c in ("match-city", "city")):
            if not self.city:
                self.city = data_stripped

    def handle_endtag(self, tag):
        self.active_classes = []


def build_official_worldcup_fixture_context(output_dir: Path) -> OfficialFixtureContext:
    url = os.getenv("FOOTBALL_ENRICHMENT_CANARY_OFFICIAL_MATCH_URL")
    if not url:
        url = "https://www.fifa.com/en/match-centre/match/17/285023/289273/400021491"

    allowed_prefixes = (
        "https://www.fifa.com/en/match-centre/match/",
        "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/",
    )
    if not any(url.startswith(prefix) for prefix in allowed_prefixes):
        raise OfficialContextUnavailableError(
            f"URL '{url}' does not start with an allowed official prefix."
        )

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        # Timeout <= 20 seconds, max bytes <= 2,000,000
        with urllib.request.urlopen(req, timeout=20.0) as response:
            raw_data = response.read(2000000)
    except Exception as e:
        raise OfficialContextUnavailableError(f"HTTP fetch failed for official FIFA context: {e}")

    html_hash = hashlib.sha256(raw_data).hexdigest()
    
    match_id = None
    home_team = None
    away_team = None
    kickoff_at = None
    venue = None
    city = None

    # 1. Parse using BeautifulSoup if available
    if _HAS_BS4:
        try:
            soup = BeautifulSoup(raw_data, "html.parser")
            card = soup.select_one(".match-detail-card, .match-card, .fixture-card, [data-match-id], .match")
            if card:
                match_id = card.get("data-match-id") or card.get("id")
                
                home_el = card.select_one(".team-home, .home, [data-home-team], .home-team")
                if home_el:
                    home_team = home_el.get_text(strip=True)
                    
                away_el = card.select_one(".team-away, .away, [data-away-team], .away-team")
                if away_el:
                    away_team = away_el.get_text(strip=True)
                    
                kickoff_el = card.select_one(".match-date, .date, .kickoff, .kickoff-at")
                if kickoff_el:
                    kickoff_at = kickoff_el.get_text(strip=True)
                    
                venue_el = card.select_one(".match-venue, .venue, .stadium")
                if venue_el:
                    venue = venue_el.get_text(strip=True)

                city_el = card.select_one(".match-city, .city")
                if city_el:
                    city = city_el.get_text(strip=True)
        except Exception:
            pass

        # Full document fallback search with BS4 if card selection was incomplete
        if not (home_team and away_team and kickoff_at):
            try:
                soup = BeautifulSoup(raw_data, "html.parser")
                home_el = soup.select_one(".team-home, .home, .home-team")
                if home_el:
                    home_team = home_el.get_text(strip=True)
                away_el = soup.select_one(".team-away, .away, .away-team")
                if away_el:
                    away_team = away_el.get_text(strip=True)
                kickoff_el = soup.select_one(".match-date, .date, .kickoff, .kickoff-at")
                if kickoff_el:
                    kickoff_at = kickoff_el.get_text(strip=True)
                venue_el = soup.select_one(".match-venue, .venue, .stadium")
                if venue_el:
                    venue = venue_el.get_text(strip=True)
                city_el = soup.select_one(".match-city, .city")
                if city_el:
                    city = city_el.get_text(strip=True)
            except Exception:
                pass

    # 2. Parse using standard library HTMLParser if metadata still missing or BS4 unavailable
    if not (home_team and away_team and kickoff_at):
        try:
            html_text = raw_data.decode("utf-8", errors="ignore")
            parser = FIFAHTMLParser()
            parser.feed(html_text)
            if parser.match_id and not match_id:
                match_id = parser.match_id
            if parser.home_team and not home_team:
                home_team = parser.home_team
            if parser.away_team and not away_team:
                away_team = parser.away_team
            if parser.kickoff_at and not kickoff_at:
                kickoff_at = parser.kickoff_at
            if parser.venue and not venue:
                venue = parser.venue
            if parser.city and not city:
                city = parser.city
        except Exception:
            pass

    # 3. Regex fallback
    if not (home_team and away_team and kickoff_at):
        try:
            html_text = raw_data.decode("utf-8", errors="ignore")
            if not home_team:
                m = re.search(r'class="[^"]*(?:team-home|home-team|home)[^"]*"[^>]*>([^<]+)', html_text)
                if m:
                    home_team = m.group(1).strip()
            if not away_team:
                m = re.search(r'class="[^"]*(?:team-away|away-team|away)[^"]*"[^>]*>([^<]+)', html_text)
                if m:
                    away_team = m.group(1).strip()
            if not kickoff_at:
                m = re.search(r'class="[^"]*(?:match-date|date|kickoff)[^"]*"[^>]*>([^<]+)', html_text)
                if m:
                    kickoff_at = m.group(1).strip()
            if not venue:
                m = re.search(r'class="[^"]*(?:match-venue|venue|stadium)[^"]*"[^>]*>([^<]+)', html_text)
                if m:
                    venue = m.group(1).strip()
            if not city:
                m = re.search(r'class="[^"]*(?:match-city|city)[^"]*"[^>]*>([^<]+)', html_text)
                if m:
                    city = m.group(1).strip()
        except Exception:
            pass

    # 4. Extract match_id from URL if not found in HTML
    if not match_id:
        match_id_match = re.search(r"/(\d+)$", url)
        if match_id_match:
            match_id = match_id_match.group(1)

    # Validate that we successfully extracted core context
    if not home_team or not away_team or not kickoff_at:
        raise OfficialContextUnavailableError(
            "Required official context metadata (home_team, away_team, kickoff_at) could not be extracted safely."
        )

    fixture_slug = f"worldcup2026-{home_team.lower()}-{away_team.lower()}"
    fixture_slug = fixture_slug.replace(" ", "-").replace("/", "-").replace("\\", "-")

    context = OfficialFixtureContext(
        fixture_slug=fixture_slug,
        competition_name="FIFA World Cup 2026",
        official_source_url=url,
        official_source_name="FIFA Official Website",
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        kickoff_at=kickoff_at,
        venue=venue,
        city=city,
        raw_payload_stored=False,
        selectable_for_production=False,
    )

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save sanitized context JSON (no raw HTML persisted!)
    sanitized_data = {
        "fixture_slug": context.fixture_slug,
        "competition_name": context.competition_name,
        "official_source_url": context.official_source_url,
        "official_source_name": context.official_source_name,
        "match_id": context.match_id,
        "home_team": context.home_team,
        "away_team": context.away_team,
        "kickoff_at": context.kickoff_at,
        "venue": context.venue,
        "city": context.city,
        "html_sha256": html_hash,
        "selectable_for_production": False,
    }
    
    with open(output_dir / "official_context_sanitized.json", "w", encoding="utf-8") as f:
        json.dump(sanitized_data, f, indent=2, sort_keys=True)

    return context


def build_official_context_claim_batch(context: OfficialFixtureContext) -> EvidenceClaimBatch:
    is_safely_fetched = context.home_team is not None and context.away_team is not None
    proof_level = ProofLevel.REAL_LIVE_API_PROOF if is_safely_fetched else ProofLevel.SYNTHETIC_CONTRACT_PROOF

    source = SourceDescriptor(
        source_key="fifa-official-match-centre",
        display_name="FIFA Official Match Centre",
        role=SourceRole.CURRENT_REFERENCE,
        requires_credentials=False,
        supports_live=True,
        supports_historical=False,
        supports_reference=True,
        supports_replay=False,
        allowed_proof_levels=(
            ProofLevel.REAL_LIVE_API_PROOF,
            ProofLevel.SYNTHETIC_CONTRACT_PROOF,
            ProofLevel.NO_PROOF,
        ),
        forbidden_fact_types=(
            FactType.XG,
            FactType.SHOT,
            FactType.THREE_SIXTY_FRAME,
        ),
    )

    observed_at = datetime.now(UTC)

    claims = []

    # Claim 1: FIXTURE_IDENTITY
    identity = ProviderIdentity(
        source_key="fifa-official-match-centre",
        provider_fixture_id=context.match_id,
        normalized_home_name=context.home_team,
        normalized_away_name=context.away_team,
        identity_confidence=1.0,
    )

    claim_val_identity = {} if proof_level == ProofLevel.SYNTHETIC_CONTRACT_PROOF else {
        "home_team": context.home_team,
        "away_team": context.away_team,
        "competition_name": context.competition_name,
    }
    confidence = 0.0 if proof_level == ProofLevel.SYNTHETIC_CONTRACT_PROOF else 1.0

    freshness = EvidenceFreshness(
        observed_at=observed_at,
        is_current_truth_allowed=is_safely_fetched,
        freshness_reason="fifa official match centre context fetch",
    )

    payload_policy = PayloadPolicy(
        raw_payload_stored=False,
        raw_payload_git_allowed=False,
        sanitized_sample_allowed=True,
    )

    claims.append(
        EvidenceClaim(
            source=source,
            proof_level=proof_level,
            fact_type=FactType.FIXTURE_IDENTITY,
            identity=identity,
            freshness=freshness,
            payload_policy=payload_policy,
            claim_value=claim_val_identity,
            confidence=confidence,
        )
    )

    # Claim 2: REFERENCE_SCHEDULE (only if kickoff_at or venue/city is extracted)
    claim_val_sched = {}
    if proof_level != ProofLevel.SYNTHETIC_CONTRACT_PROOF:
        if context.kickoff_at:
            claim_val_sched["kickoff_at"] = context.kickoff_at
        if context.venue:
            claim_val_sched["venue"] = context.venue
        if context.city:
            claim_val_sched["city"] = context.city

    if proof_level == ProofLevel.SYNTHETIC_CONTRACT_PROOF:
        # We don't emit REFERENCE_SCHEDULE if synthetic contract proof since it can't carry values
        pass
    elif claim_val_sched:
        claims.append(
            EvidenceClaim(
                source=source,
                proof_level=proof_level,
                fact_type=FactType.REFERENCE_SCHEDULE,
                identity=identity,
                freshness=freshness,
                payload_policy=payload_policy,
                claim_value=claim_val_sched,
                confidence=confidence,
            )
        )

    batch_claims = tuple(claims)
    batch_id = EvidenceClaimBatch.deterministic_id(
        "fifa-official-match-centre", "football-foundation-pass2", batch_claims
    )

    return EvidenceClaimBatch(
        batch_id=batch_id,
        source_key="fifa-official-match-centre",
        adapter_name="FIFAOfficialMatchCentreAdapter",
        adapter_version="football-foundation-pass2",
        generated_at=observed_at,
        claims=batch_claims,
    )
