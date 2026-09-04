# ruff: noqa: E501, W291, W293

"""ESPN Hidden API client — free, no API key, no rate limits.

Provides per-game statistics for:
- Soccer (football): 28 stats per game across 36+ leagues
- Basketball (NBA/WNBA): 25 stats per game
- Hockey (NHL): 14 stats per game

Base URL: http://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/
"""

import json
import re
import threading
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TypeVar

import requests

from bet.integration.evidence import (
    EvidenceRef,
    load_evidence_object_bytes,
    persist_response_evidence,
    write_source_operation_bundle,
)

from .api_football import APIFixture, APIMatchStats
from .base_client import (
    APIError,
    APINotFoundError,
    BaseAPIClient,
    SourceOperationResult,
    SourceResultStatus,
)
from .rate_limiter import RateLimiter
from .tennis_score import parse_tennis_score

ESPN_PARSER_VERSION = "espn-client-rem002a-v1"
T = TypeVar("T")

# Re-export for backward compatibility
__all__ = [
    "SourceResultStatus",
    "SourceOperationResult",
    "ESPNClient",
    "APIFixture",
    "APIMatchStats",
    "ESPN_PARSER_VERSION",
    "COMPETITION_TO_ESPN_LEAGUE",
    "ESPN_FOOTBALL_LEAGUE_CODES",
    "ESPN_COUNTRY_CODE_PREFIXES",
    "espn_country_pin_words",
    "get_espn_league_for_competition",
]


def _retry_after_seconds(headers: dict[str, str] | None) -> float | None:
    if not headers:
        return None
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# ESPN uses "soccer" not "football"
ESPN_SPORT_MAP = {
    "football": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "tennis": "tennis",
    "volleyball": "volleyball",
}

ESPN_LEAGUES = {
    # Every code /teams-verified against ESPN on 2026-08-28 and kept only if it
    # returned a non-empty team directory. This list drives the discovery sweep
    # (scrapers/espn.py, stats/enrichment.py), which requests each league in
    # turn, so a dead code here is a guaranteed 404 on every sweep. 21 of the
    # 104 entries were dead: bul.1, conmebol.copa_america, cro.1, cze.1, egy.1,
    # fin.1, geo.1, hun.1, kaz.1, kor.1, mor.1, pol.1, qat.1, sau.1, ser.1,
    # svk.1, tun.1, uae.1, ukr.1, usa.w.1, uzb.1 -- cze.1, fin.1 and usa.w.1
    # answering 200 with zero teams rather than 404.
    #
    # ksa.1, usa.nwsl and conmebol.america replace the dead sau.1, usa.w.1 and
    # conmebol.copa_america: ESPN serves all three leagues, just under other
    # codes. eng.4 and eng.5 are added because the 2026-08-28 slate carried 11
    # English National League fixtures and this list could not see them.
    "football": [
        "eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "bra.1", "arg.1",
        "mex.1", "usa.1", "col.1", "por.1", "ned.1", "bel.1", "tur.1",
        "sco.1", "aut.1", "gre.1", "den.1", "nor.1", "swe.1", "sui.1",
        "aus.1", "jpn.1", "idn.1", "tha.1", "ven.1", "per.1", "bol.1",
        "par.1", "ecu.1", "uru.1", "eng.2", "eng.3", "esp.2", "ger.2",
        "ita.2", "fra.2", "ned.2", "uefa.champions", "uefa.europa", "uefa.europa.conf", "uefa.champions_qual",
        "uefa.europa_qual", "uefa.europa.conf_qual", "uefa.nations", "fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.afc",
        "fifa.worldq.concacaf", "fifa.worldq.caf", "uefa.euro", "concacaf.gold", "concacaf.nations.league", "concacaf.leagues.cup", "caf.nations",
        "caf.champions", "conmebol.libertadores", "conmebol.sudamericana", "conmebol.recopa", "afc.champions", "concacaf.champions", "eng.fa",
        "esp.copa_del_rey", "ger.dfb_pokal", "ita.coppa_italia", "fra.coupe_de_france", "ned.cup", "por.taca.portugal", "arg.copa",
        "bra.copa_do_brazil", "rou.1", "isr.1", "cyp.1", "rus.1", "rsa.1", "nga.1",
        "chn.1", "ind.1", "bra.2", "chi.1", "eng.w.1", "fra.w.1", "ksa.1",
        "usa.nwsl", "conmebol.america", "eng.4", "eng.5",
    ],
    "basketball": ["nba", "wnba"],
    "hockey": ["nhl"],
    "tennis": ["atp", "wta"],
    "volleyball": ["fivb.m", "fivb.w", "ncaa.w", "ncaa.m"],
}

# --- Competition name -> ESPN league code --------------------------------
#
# Resolution has exactly two rules, in this order, and nothing else:
#
#   1. An explicit tour marker ("ATP", "WTA") names the tennis tour.
#   2. The name is reduced to an order-free token signature and looked up in
#      the authored table below. Hit or miss. No third rule.
#
# There is no substring pass and no similarity score. The previous resolver
# fell back to "longest matching key wins", which quietly turned ~15 category
# keys ("premier league", "super league", "bundesliga", "serie a",
# "superliga", "la liga", "pro league", "primera division", ...) into
# catch-alls for their country. Measured against the 41 competition names in
# runs/2026-08-28, 8 of the 31 names it resolved got the wrong code, and 11 of
# 12 probed real unmapped leagues ("Nepal Premier League", "Malta Premier
# League", "Bhutan Super League", ...) came back with a confident wrong pin.
#
# Why a wrong pin is worse than no pin. A wrong *country* usually dies in
# resolve_team_id and surfaces as a data_gap blaming the team name, so the
# league bug never gets named. A wrong *division or gender inside the right
# country* does not die at all: women's and reserve sides carry the parent
# club's name, so ESPN answers with a real team and a real season -- just not
# the one that was asked for. Nothing raises, and that phantom second provider
# then feeds cross_provider_agreement, which is exactly what promotes a row
# from LEAN to CALL. Returning None costs one provider. A wrong pin corrupts
# the column the operator trusts most. See ProviderLeagueUnsupported in
# simple_stats/providers.py for the loud version of the same defect.
#
# Names are asserted from knowledge; codes are proved from provider data.
# Every code below was verified live on 2026-08-28 by requesting
# /apis/site/v2/sports/soccer/<code>/teams and requiring a non-empty team
# directory. That probe deleted 18 codes this table used to assert which ESPN
# does not serve at all:
#
#   sau.1 (404)     "saudi pro league"  -> the real code is ksa.1, and the
#                   2026-08-28 slate carried five Saudi fixtures
#   usa.w.1 (empty) "nwsl"              -> the real code is usa.nwsl
#   conmebol.copa_america (404)         -> the real code is conmebol.america
#   pol.1, ukr.1, egy.1, kor.1, cro.1, hun.1, bul.1, ser.1, svk.1, qat.1,
#   uae.1, tun.1, mor.1 (404), cze.1, fin.1 (200 with zero teams)
#
# ger.w.1 and por.2 were requested as fixes for "Frauen-Bundesliga" and "Liga
# Portugal 2" and are NOT here on purpose: both 404. ESPN has no German
# women's league and no Portuguese second tier, so those two names must stay
# unresolved. "Adding the missing code" is only a fix when the code exists.
#
# docs/PLAN_BOGATE_STATYSTYKI.md Faza 6 re-probed live on 2026-08-31 for the
# largest still-unresolved names on the 2026-08-31 slate
# (espn_competition_coverage's unresolved-by-fixtures list). Findings, so a
# future session does not re-probe the same names and reach for a table entry
# that cannot exist:
#   fin.1 (200, zero teams)  -> "Veikkausliiga" / "Veikkausliiga - Finland"
#                                (6+3 fixtures) have no ESPN code. Finland's
#                                whole soccer tree is absent from ESPN's own
#                                /v2/sports/soccer/leagues directory, not just
#                                this one code -- confirmed structural, not a
#                                missed spelling.
#   swe.2 (200, zero teams)  -> "Superettan - Sweden" (1 fixture), Sweden's
#                                second tier. Same pattern as por.2.
#   arg.4 (200, zero teams)  -> "Primera C" (6 fixtures). ESPN's own directory
#                                names this code "Argentine Primera C" -- it
#                                knows the league exists and still serves no
#                                team data for it.
#   isr.2 (200, zero teams)  -> "Liga Leumit" (3 fixtures), Israel's second
#                                tier.
#   aze.1 (200, zero teams)  -> "Azerbaijan Premier League" (2 fixtures).
#   geo.1, cro.1, bul.1 (200, zero teams) -- reconfirmed dead, matching the
#                                2026-08-28 list above ("Erovnuli Liga", "HNL",
#                                "Parva Liga").
# Every other unresolved name on that slate ("FAW Championship", "Second
# Division", "Professional League", ...) is either a generic label ESPN has no
# single code for (same doctrine as bare "Super League"/"Superliga" above) or
# a country/league this table has not yet probed live -- left alone rather
# than guessed.
#
# Nothing in this table was copied out of a fuzzy match. A table built from
# fuzzy output freezes the fuzzy matcher's mistakes as ground truth.

# Tokens that carry no competition identity, dropped before the signature is
# built. This is what lets "Nigeria Premier Football League" and "Nigerian
# Premier League" reduce to the same key without either one being a substring
# of the other.
_ESPN_NOISE_TOKENS = frozenset({"football", "soccer", "futbol", "fussball", "de", "the"})

# Applied token by token to both the authored keys and the incoming name, so
# the two sides cannot drift apart. Country adjectives fold onto the country
# noun because feeds alternate between them freely: the 2026-08-28 slate alone
# carried "Austrian Football Bundesliga", "Bundesliga - Germany",
# "Turkey Super League" and "Chinese Super League".
_ESPN_TOKEN_SYNONYMS = {
    # England
    "english": "england", "eng": "england",
    # Germany
    "german": "germany", "deutschland": "germany",
    # Spain
    "spanish": "spain", "espana": "spain", "espanola": "spain",
    # Italy
    "italian": "italy", "italia": "italy", "italiana": "italy",
    # France
    "french": "france",
    # Low Countries
    "dutch": "netherlands", "holland": "netherlands", "nederland": "netherlands",
    "belgian": "belgium", "belgique": "belgium",
    # Iberia
    "portuguese": "portugal", "portuguesa": "portugal",
    # Rest of Europe
    "turkish": "turkey", "turkiye": "turkey",
    "scottish": "scotland",
    "swiss": "switzerland", "suisse": "switzerland",
    "austrian": "austria", "osterreich": "austria",
    "greek": "greece", "hellenic": "greece",
    "danish": "denmark", "danmark": "denmark",
    "norwegian": "norway", "norge": "norway",
    "swedish": "sweden", "sverige": "sweden",
    "russian": "russia",
    "romanian": "romania", "romaniei": "romania",
    "cypriot": "cyprus",
    "israeli": "israel",
    "irish": "ireland",
    # South America
    "brazilian": "brazil", "brasil": "brazil",
    "argentine": "argentina", "argentinian": "argentina",
    "chilean": "chile",
    "colombian": "colombia",
    "ecuadorian": "ecuador",
    "peruvian": "peru",
    "uruguayan": "uruguay",
    "paraguayan": "paraguay",
    "bolivian": "bolivia",
    "venezuelan": "venezuela",
    # North America
    "mexican": "mexico",
    "american": "usa", "us": "usa",
    # Asia / Oceania / Africa
    "japanese": "japan",
    "australian": "australia",
    "chinese": "china",
    "indian": "india",
    "indonesian": "indonesia",
    "thai": "thailand",
    "nigerian": "nigeria",
    "african": "africa",
    # Division and gender markers. "ii"/"iii" are Roman division numbers; a
    # bare single digit is left alone because it already is one ("Liga 1",
    # "2. Bundesliga"). The gender fold is load-bearing: it is what makes
    # "Frauen-Bundesliga" fail to match "Bundesliga" instead of silently
    # answering with the men's league.
    "ii": "2", "iii": "3",
    "div": "division",
    "women": "women", "womens": "women", "woman": "women", "w": "women",
    "frauen": "women", "feminine": "women", "feminin": "women",
    "femenina": "women", "feminina": "women", "femminile": "women",
    "vrouwen": "women", "damer": "women",
}

# --- one country vocabulary, shared with the runtime gate ----------------
#
# Country noun -> the ESPN code prefix that country's leagues are filed under.
#
# This is the only place the resolver's vocabulary and the runtime pin gate's
# vocabulary meet, and it exists because they had already drifted. The resolver
# folds country adjectives onto the noun above so that "Austrian Football
# Bundesliga" and "Austria Bundesliga" are one key; _espn_pin_contradicted in
# simple_stats/providers.py needs the same words to read a country off a
# competition name and compare it with the country ESPN files the code under.
# Those were two hand-kept lists, and 24 words the resolver knew the gate did
# not -- "osterreich", "ecuadorian", "italiana", "danmark", "brasil" and the
# rest. That is not a wrong answer, it is worse: the gate's silence reads as a
# pass, so the safety net was thinnest exactly where the resolver was most
# permissive, and no test would have noticed them diverging further.
#
# espn_country_pin_words() composes _ESPN_TOKEN_SYNONYMS onto this map, so
# teaching the resolver a new spelling teaches the gate the same spelling in
# the same commit. A prefix absent from this map is not a bug by itself -- an
# unknown word contributes no evidence and the pin is left alone -- but every
# prefix the football table actually pins is listed, because silence is the
# expensive failure. test_the_gate_knows_every_country_the_table_pins holds
# that line.
ESPN_COUNTRY_CODE_PREFIXES = {
    # Europe
    "england": "eng", "spain": "esp", "germany": "ger", "italy": "ita",
    "france": "fra", "netherlands": "ned", "belgium": "bel",
    "portugal": "por", "turkey": "tur", "scotland": "sco",
    "switzerland": "sui", "austria": "aut", "greece": "gre",
    "denmark": "den", "norway": "nor", "sweden": "swe", "russia": "rus",
    "romania": "rou", "cyprus": "cyp", "israel": "isr",
    # pol.1, ukr.1 and irl.1 have no ESPN team directory, so the table pins
    # nothing to them. The words stay: the gate's job is to contradict a pin,
    # and a pin at one of these codes is exactly the kind that needs
    # contradicting if one is ever added back.
    "poland": "pol", "ukraine": "ukr", "ireland": "irl",
    # South America
    "brazil": "bra", "argentina": "arg", "chile": "chi", "colombia": "col",
    "ecuador": "ecu", "peru": "per", "uruguay": "uru", "paraguay": "par",
    "bolivia": "bol", "venezuela": "ven",
    # North and Central America. "costa" and "rica" both answer for crc so
    # that either half of the country name carries the evidence.
    "mexico": "mex", "usa": "usa", "costa": "crc", "rica": "crc",
    "guatemala": "gua", "honduras": "hon", "salvador": "slv",
    # Asia, Oceania, Africa. "arabia" is here alongside "saudi" because the
    # feed spells it both ways ("Saudi Pro League", "Saudi Arabia Pro
    # League"); "africa" answers rsa rather than caf because ESPN's only
    # African league directory is South Africa's.
    "japan": "jpn", "australia": "aus", "china": "chn", "india": "ind",
    "indonesia": "idn", "thailand": "tha", "saudi": "ksa", "arabia": "ksa",
    "nigeria": "nga", "africa": "rsa",
}


def espn_country_pin_words() -> dict[str, str]:
    """Every country spelling the resolver understands -> its ESPN code prefix.

    Built rather than authored: the adjective folds in _ESPN_TOKEN_SYNONYMS are
    composed onto ESPN_COUNTRY_CODE_PREFIXES, so "osterreich" answers "aut"
    because the resolver already folds it to "austria". Synonym targets that
    are not countries ("women", "2", "division") drop out on their own.
    """
    words = dict(ESPN_COUNTRY_CODE_PREFIXES)
    for spelling, folded in _ESPN_TOKEN_SYNONYMS.items():
        prefix = ESPN_COUNTRY_CODE_PREFIXES.get(folded)
        if prefix is not None:
            words[spelling] = prefix
    return words


# An explicit tour marker is the only thing that resolves a tennis league.
#
# What this does NOT fix, checked rather than assumed: ESPN's tennis
# /scoreboard is not tour-scoped in content. Verified 2026-08-28, the atp and
# wta scoreboards return byte-identical competition sets, and Iga Swiatek's
# matches are present in both, so a mispinned tour never lost a player's
# history. The `dates` parameter returns the whole tournament window around
# that date rather than one day, which is why the 9-date scan in
# _get_athlete_recent_matches covers real history.
#
# What it does fix is identity precision. _resolve_athlete_id's first pass
# requires the search hit's league to equal self.league, and only falls through
# to a league-blind pass when it does not. With the tour pinned from the
# competition name, women's draws resolve on the strict pass; the table used to
# assert "atp" for every grand slam and masters event, which forced every WTA
# player onto the loose pass. Those unconditional "atp" entries are gone.
_ESPN_TENNIS_TOURS = frozenset({"atp", "wta"})

# A draw that names its gender pins the tour just as firmly as the word "WTA"
# does, and until 2026-08-28 nothing read it. Removing the table's blanket
# "atp" for grand slams stopped asserting the *wrong* tour but left the right
# one unstated, so every US Open fixture -- men's and women's, the largest
# tennis block of that slate -- resolved to None and fell to the default ATP
# client. Measured consequence in that run: 372 of 441 cached ESPN tennis
# resolutions came from the ATP scoreboard fallback, 23 more resolved across
# tours, and 50 ESPN athlete ids each answered to more than one queried name --
# 'eala, alexandra' and 'wolf, alexandra' sharing id 7759, 'geun jun kim' and
# 'kimberly birrell' sharing 2588. Qinwen Zheng's stats sheet carried Lorenzo
# Musetti's and Kei Nishikori's matches.
#
# The gender marker only counts alongside a tennis tier token, so football's
# "Women's Super League" cannot reach it -- that name is answered by the
# football table, which is consulted first.
_ESPN_TENNIS_TIER_TOKENS = frozenset({"atp", "wta", "itf", "challenger", "slam"})
_ESPN_TENNIS_GENDER_TOURS = {
    "men": "atp", "mens": "atp",
    "women": "wta", "womens": "wta", "ladies": "wta",
}

# Football competition name -> ESPN league code. Every code /teams-verified.
_ESPN_FOOTBALL_COMPETITIONS = {
    # --- England ---------------------------------------------------------
    # "EPL" is how the odds-api feed names the top flight, and without it the
    # best-corroborated league in the sheet resolved to None: measured
    # 2026-08-28, Crystal Palace - Manchester City came back SINGLE_SOURCE
    # with "no ESPN league code for competition 'EPL'".
    "Premier League": "eng.1",
    "EPL": "eng.1",
    "England Premier League": "eng.1",
    "Championship": "eng.2",
    "England Championship": "eng.2", "EFL Championship": "eng.2",
    "League One": "eng.3", "England League One": "eng.3",
    "EFL League One": "eng.3",
    "League Two": "eng.4", "England League Two": "eng.4",
    "EFL League Two": "eng.4",
    # The digit spellings, added 2026-09-01. Same two codes, already
    # /teams-verified; only the name was missing, and the name is what the
    # feeds actually emit. On that day's slate "League 1" was 7 fixtures and
    # "League 2" was 12 -- 19 of the 46 unresolved competition names, and the
    # largest resolvable block in the file. Every one came back
    # "no ESPN league code for competition 'League 1'", which left rows that
    # bzzoiro alone could serve stuck at SINGLE_SOURCE: Leicester City -
    # Plymouth Argyle reached the coupon uncorroborated for exactly this
    # reason, on a market (goals_for) espn-football is able to serve.
    #
    # Read off the fixtures, not off the name: the "League 1" block was
    # Bradford City, Bromley, Doncaster, Huddersfield, Leicester, Peterborough
    # and Wycombe, and the "League 2" block was Accrington, Exeter, Bristol
    # Rovers, Cheltenham, Chesterfield, Northampton, Crewe, Fleetwood,
    # Salford, Swindon, Rochdale and Tranmere. Both are unambiguously the
    # English third and fourth tiers, and neither collides with France's
    # "Ligue 1"/"Ligue 2", which this table keys separately.
    "League 1": "eng.3",
    "League 2": "eng.4",
    # 11 of the 80 fixtures on 2026-08-28 were "National League" -- the single
    # largest block in the slate -- and the old table left every one of them
    # unresolved. Confirmed as England's fifth tier from the fixtures
    # themselves (Wealdstone, Carlisle United, Tamworth, Woking, Gateshead);
    # eng.5 serves a 24-team directory.
    "National League": "eng.5",
    "England National League": "eng.5", "Vanarama National League": "eng.5",
    # Both spellings, because "fa cup" is on discover.py's generic-name list:
    # a provider that reports a country beside the league name (bzzoiro does,
    # and it is the only football discovery source since 2026-09-04) qualifies
    # it to "England FA Cup" before this table ever sees it. Same code, proved
    # once -- the alternative is a rename that resolves six leagues and
    # silently unresolves the five FA Cup fixtures on the 2026-09-04 slate.
    "FA Cup": "eng.fa", "England FA Cup": "eng.fa",
    "EFL Cup": "eng.league_cup", "Carabao Cup": "eng.league_cup",
    # 64 teams, probed 2026-09-02. The cup for the third and fourth tiers plus
    # Premier League under-21 sides, and it is not the FA Trophy (fifth tier
    # and below), which ESPN does not serve at all.
    "EFL Trophy": "eng.trophy",
    "WSL": "eng.w.1",
    "Women's Super League": "eng.w.1",
    "England Women's Super League": "eng.w.1",
    # --- Spain -----------------------------------------------------------
    "La Liga": "esp.1", "LaLiga": "esp.1", "Spain La Liga": "esp.1",
    "LaLiga EA Sports": "esp.1",
    "La Liga 2": "esp.2", "LaLiga 2": "esp.2", "Spain La Liga 2": "esp.2",
    "LaLiga Hypermotion": "esp.2",
    "Segunda Division": "esp.2",
    "Copa del Rey": "esp.copa_del_rey",
    "Supercopa de Espana": "esp.super_cup",
    "Liga F": "esp.w.1",
    # --- Germany ---------------------------------------------------------
    "Bundesliga": "ger.1", "Germany Bundesliga": "ger.1",
    # "Bundesliga 2 - Germany" and "Austrian Football Bundesliga" both used to
    # land on ger.1: the bare key "bundesliga" was the longest substring in
    # each. Both now need their own signature, and get one.
    "Bundesliga 2": "ger.2", "2. Bundesliga": "ger.2",
    "Germany Bundesliga 2": "ger.2",
    "DFB Pokal": "ger.dfb_pokal", "German Cup": "ger.dfb_pokal",
    "DFL Supercup": "ger.super_cup",
    # --- Italy -----------------------------------------------------------
    # Bare "Serie A"/"Serie B" are NOT here, same rule as "Super League" and
    # "Superliga" below. Brazil's top two flights carry the same names, and on
    # 2026-08-29 a bare "Serie A" fixture was Atletico-MG - Vitoria: Brazil,
    # resolved to ita.1, where "inter" contains-matches "internacional" and a
    # cross-country identity is one substring away. Italian fixtures arrive as
    # "Serie A - Italy" or gain their country in DISCOVER's qualification.
    "Italy Serie A": "ita.1",
    "Italy Serie B": "ita.2",
    "Coppa Italia": "ita.coppa_italia",
    "Supercoppa Italiana": "ita.super_cup",
    # --- France ----------------------------------------------------------
    # Bare "Ligue 1"/"Ligue 2" are NOT here: Algeria and Tunisia call their
    # top flights the same, and the 2026-08-28/29 slates carried eight bare
    # "Ligue 1" fixtures of which six were JS El Biar, US Biskra, US
    # Monastirienne and company -- not France.
    "France Ligue 1": "fra.1",
    "France Ligue 2": "fra.2",
    "Coupe de France": "fra.coupe_de_france",
    "Trophee des Champions": "fra.super_cup",
    "Premiere Ligue": "fra.w.1", "D1 Arkema": "fra.w.1",
    "Division 1 Feminine": "fra.w.1",
    # --- Netherlands -----------------------------------------------------
    "Eredivisie": "ned.1", "Netherlands Eredivisie": "ned.1",
    "Eerste Divisie": "ned.2", "Keuken Kampioen Divisie": "ned.2",
    "KNVB Beker": "ned.cup", "Dutch Cup": "ned.cup",
    "Johan Cruyff Shield": "ned.supercup",
    "Vrouwen Eredivisie": "ned.w.1",
    # --- Portugal --------------------------------------------------------
    # "Liga Portugal 2" is deliberately absent: por.2 404s, so Portugal's
    # second tier has no ESPN surface and must stay unresolved rather than
    # borrow por.1 the way it used to.
    "Primeira Liga": "por.1", "Liga Portugal": "por.1",
    "Liga Portugal Betclic": "por.1", "Portugal Primeira Liga": "por.1",
    "Taca de Portugal": "por.taca.portugal",
    # --- Belgium ---------------------------------------------------------
    # Bare "Pro League" is NOT here: Saudi Arabia, the UAE and Iran all name
    # their top flight that, and the recent slates' bare "Pro League" rows
    # were Abha, Al Wasl and Al Ain more often than Genk.
    "Jupiler Pro League": "bel.1",
    "Belgium Jupiler Pro League": "bel.1",
    "Belgium Pro League": "bel.1", "Belgium First Division": "bel.1",
    "Belgium First Division A": "bel.1",
    # --- Turkey ----------------------------------------------------------
    # tur.1's ESPN name is "Turkish Super Lig". Both the Turkish and the
    # English rendering appear in feeds, and "Turkey Super League" used to
    # resolve to sui.1 because "super league" was the longest substring.
    "Super Lig": "tur.1", "Turkey Super Lig": "tur.1",
    "Trendyol Super Lig": "tur.1", "Turkey Super League": "tur.1",
    # --- Rest of Europe --------------------------------------------------
    "Premiership": "sco.1", "Scotland Premiership": "sco.1",
    "Scotland Championship": "sco.2",
    "Scottish Cup": "sco.tennents",
    "Scottish League Cup": "sco.cis",
    # Bare "Super League" is NOT here. It is the name of the top flight in
    # Switzerland, Greece, China, India and Turkey among others, so the name on
    # its own does not carry the answer; only the qualified forms do.
    "Switzerland Super League": "sui.1",
    "Austria Bundesliga": "aut.1",
    "Greece Super League": "gre.1",
    # Bare "Superliga" is NOT here either. The 2026-08-28 slate proves why:
    # two fixtures came in as plain "Superliga" and resolved to den.1, but the
    # teams were Universitatea Cluj, Petrolul Ploiesti, Voluntari and Otelul
    # Galati -- Romania's Superliga, not Denmark's. Both countries call their
    # top flight that. Denmark's own fixture that day arrived correctly
    # qualified as "Denmark Superliga".
    "Denmark Superliga": "den.1",
    "Romania Superliga": "rou.1", "Liga 1 Romania": "rou.1",
    "Romania Liga 1": "rou.1",
    "Eliteserien": "nor.1",
    # "Allsvenskan - Sweden" is NOT a separate key here. It folds onto bare
    # "Allsvenskan" in config/competition_name_canonical_map.json (Faza 6)
    # before this table is ever consulted, because the two names reduce to
    # different token signatures ({allsvenskan} vs {allsvenskan, sweden}) and
    # would otherwise need two entries pointing at the same code.
    "Allsvenskan": "swe.1",
    # rus.1 serves a 16-team directory. "Premier League - Russia" used to
    # resolve to eng.1.
    "Russia Premier League": "rus.1", "Russian Premier Liga": "rus.1",
    "Cyprus First Division": "cyp.1",
    "Israel Premier League": "isr.1", "Ligat haAl": "isr.1",
    # --- South America ---------------------------------------------------
    "Brasileirao": "bra.1", "Brasileiro": "bra.1",
    "Brazil Serie A": "bra.1", "Campeonato Brasileiro": "bra.1",
    # "Brasileirao Serie B" used to resolve to bra.1: "brasileirao" is longer
    # than "serie b", so the division marker lost the longest-match contest.
    "Brasileirao Serie B": "bra.2", "Brazil Serie B": "bra.2",
    "Copa do Brasil": "bra.copa_do_brazil",
    "Liga Profesional": "arg.1", "Argentina Primera Division": "arg.1",
    "Argentina Liga Profesional": "arg.1", "Torneo Betano": "arg.1",
    "Primera Nacional": "arg.2", "Argentina Nacional B": "arg.2",
    "Copa Argentina": "arg.copa",
    "Chile Primera Division": "chi.1",
    "Primera A": "col.1", "Categoria Primera A": "col.1",
    "Colombia Primera A": "col.1",
    # 36 teams, probed 2026-09-02.
    "Copa Colombia": "col.copa",
    "LigaPro": "ecu.1", "Ecuador Serie A": "ecu.1",
    "Peru Liga 1": "per.1",
    "Liga AUF Uruguaya": "uru.1", "Uruguay Primera Division": "uru.1",
    "Paraguay Primera Division": "par.1",
    "Bolivia Primera Division": "bol.1",
    "Venezuela Primera Division": "ven.1",
    # Bare "Primera Division" is NOT here. Argentina, Chile, Uruguay,
    # Paraguay, Venezuela, Costa Rica and El Salvador all use it; it used to
    # resolve to uru.1 for all of them.
    # --- North and Central America ---------------------------------------
    # ESPN files the MLS postseason under usa.1 with the regular season, so
    # the playoff name resolves to the same code rather than to nothing.
    "MLS": "usa.1", "Major League Soccer": "usa.1", "MLS Cup": "usa.1",
    "US Open Cup": "usa.open",
    "USL Championship": "usa.usl.1",
    # A separate, lower division from the Championship above -- 17 teams,
    # probed 2026-09-02. Pinning it to usa.usl.1 would have been the
    # right-country-wrong-tier failure the division-marker gate exists for.
    "USL League One": "usa.usl.l1",
    "NWSL": "usa.nwsl",
    "Liga MX": "mex.1", "Mexico Liga MX": "mex.1",
    "Liga de Expansion MX": "mex.2",
    "Costa Rica Primera Division": "crc.1",
    "Guatemala Liga Nacional": "gua.1",
    "Honduras Liga Nacional": "hon.1",
    "El Salvador Primera Division": "slv.1",
    # --- Asia and Oceania ------------------------------------------------
    "J.League": "jpn.1", "J1 League": "jpn.1", "Japan J.League": "jpn.1",
    "Japan J1 League": "jpn.1",
    "A-League": "aus.1", "A-League Men": "aus.1",
    "Australia A-League Men": "aus.1",
    "A-League Women": "aus.w.1",
    "China Super League": "chn.1",
    "India Super League": "ind.1", "ISL": "ind.1",
    "Indonesia Super League": "idn.1", "Liga 1 Indonesia": "idn.1",
    "Thailand League 1": "tha.1", "Thai League": "tha.1",
    # Saudi Arabia's real code is ksa.1. sau.1, which this table asserted for
    # both Saudi spellings, 404s -- and 5 of the 80 fixtures on 2026-08-28
    # were Saudi Pro League, every one of them lost to a dead pin.
    "Saudi Pro League": "ksa.1", "Saudi Professional League": "ksa.1",
    "Saudi Arabia Pro League": "ksa.1", "Roshn Saudi League": "ksa.1",
    "Saudi King's Cup": "ksa.kings.cup",
    # --- Africa ----------------------------------------------------------
    "South Africa Premiership": "rsa.1", "PSL": "rsa.1",
    "Nigeria Premier League": "nga.1", "NPFL": "nga.1",
    "Nigeria NPFL": "nga.1", "Nigeria Professional League": "nga.1",
    # --- UEFA club and national ------------------------------------------
    "Champions League": "uefa.champions", "UCL": "uefa.champions",
    "UEFA Champions League": "uefa.champions",
    "Europa League": "uefa.europa", "UEL": "uefa.europa",
    "UEFA Europa League": "uefa.europa",
    "Conference League": "uefa.europa.conf",
    "UEFA Conference League": "uefa.europa.conf",
    "UEFA Europa Conference League": "uefa.europa.conf",
    "UEFA Super Cup": "uefa.super_cup",
    "Nations League": "uefa.nations", "UEFA Nations League": "uefa.nations",
    "Euro": "uefa.euro", "European Championship": "uefa.euro",
    "Women's Champions League": "uefa.wchampions",
    "UEFA Women's Champions League": "uefa.wchampions",
    "Women's Euro": "uefa.weuro", "UEFA Women's Euro": "uefa.weuro",
    "Women's Nations League": "uefa.w.nations",
    "UEFA Women's Nations League": "uefa.w.nations",
    # --- FIFA ------------------------------------------------------------
    "World Cup": "fifa.world", "FIFA World Cup": "fifa.world",
    "Women's World Cup": "fifa.wwc", "FIFA Women's World Cup": "fifa.wwc",
    "Club World Cup": "fifa.cwc", "FIFA Club World Cup": "fifa.cwc",
    "World Cup Qualifying UEFA": "fifa.worldq.uefa",
    "World Cup Qualifying CONMEBOL": "fifa.worldq.conmebol",
    "World Cup Qualifying AFC": "fifa.worldq.afc",
    "World Cup Qualifying CAF": "fifa.worldq.caf",
    "World Cup Qualifying CONCACAF": "fifa.worldq.concacaf",
    # "Club Friendlies" is NOT here, though club.friendly serves a 610-team
    # directory. A club.friendly-scoped client can only return friendlies, so
    # the L10 it produces is not comparable to a league L10, and the 2026-08-28
    # friendlies fixtures included reserve sides ("Leganes B") -- the exact
    # shape that resolves to a real-but-wrong team. Weak evidence dressed as a
    # second provider is what this table exists to prevent.
    # --- CONMEBOL / CONCACAF / AFC / CAF ---------------------------------
    "Copa Libertadores": "conmebol.libertadores",
    "Libertadores": "conmebol.libertadores",
    "Copa Sudamericana": "conmebol.sudamericana",
    "Sudamericana": "conmebol.sudamericana",
    "Recopa Sudamericana": "conmebol.recopa",
    "Copa America": "conmebol.america",
    "CONMEBOL Copa America": "conmebol.america",
    "CONMEBOL Libertadores": "conmebol.libertadores",
    "CONMEBOL Sudamericana": "conmebol.sudamericana",
    "Gold Cup": "concacaf.gold", "CONCACAF Gold Cup": "concacaf.gold",
    "CONCACAF Champions Cup": "concacaf.champions",
    "CONCACAF Nations League": "concacaf.nations.league",
    "Leagues Cup": "concacaf.leagues.cup",
    "AFC Champions League": "afc.champions",
    "AFC Champions League Elite": "afc.champions",
    "AFC Champions League Two": "afc.cup",
    "AFC Asian Cup": "afc.asian.cup",
    "CAF Champions League": "caf.champions",
    "CAF Confederation Cup": "caf.confed",
    "Africa Cup of Nations": "caf.nations", "AFCON": "caf.nations",
}

# Non-football entries. These are NOT /teams-verified -- ESPN's volleyball
# surface was never probed -- so they are kept out of the football code set
# and out of the football provider's accept-list.
_ESPN_OTHER_COMPETITIONS = {
    "FIVB World Championship": "fivb.m",
    "FIVB Nations League": "fivb.m",
    "FIVB Men": "fivb.m",
    "FIVB Women": "fivb.w",
}

# Kept as a name -> code mapping for readability and for callers that import
# it; lookups go through _ESPN_SIGNATURE_TO_LEAGUE, derived below.
COMPETITION_TO_ESPN_LEAGUE = {
    **{k.lower(): v for k, v in _ESPN_FOOTBALL_COMPETITIONS.items()},
    **{k.lower(): v for k, v in _ESPN_OTHER_COMPETITIONS.items()},
}

# The set _provider_client is allowed to pin an ESPN football client to. A
# football request must never be handed "atp", and a tennis request must never
# be handed "eng.1"; without an explicit accept-list a single mistyped table
# entry crosses the sports silently.
ESPN_FOOTBALL_LEAGUE_CODES = frozenset(_ESPN_FOOTBALL_COMPETITIONS.values())


# League names that are one word in some feeds and two in others, folded to a
# single token so both spellings produce the same signature. Without this,
# "LaLiga EA Sports" and "La Liga - Spain" are unrelated keys, and "A-League"
# tokenises to {a, league} -- a one-letter token loose in the signature space.
_ESPN_PHRASE_ALIASES = (
    ("la liga", "laliga"),
    ("a league", "aleague"),
)


def _espn_name_signature(name: str) -> frozenset[str]:
    """Reduce a competition name to the order-free token set used for lookup.

    Order-free on purpose: feeds render the same league as "Super League -
    China", "Chinese Super League" and "China Super League", and a signature
    makes those one key instead of three substring hazards.
    """
    folded = unicodedata.normalize("NFKD", name.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    # A possessive is not a token. Squashing punctuation first turns "Women's"
    # into "women s", and that stray "s" is a token the same league written
    # without the apostrophe does not have -- so "UEFA Women's Champions
    # League" (pinned, signature {uefa, women, champions, league, s}) and the
    # feed's "UEFA Champions League Women" ({uefa, women, champions, league})
    # were two different keys for one competition. Nine fixtures on 2026-09-02
    # lost ESPN over one letter.
    folded = re.sub(r"['’]s\b", "", folded)
    spaced = " " + re.sub(r"[^a-z0-9]+", " ", folded).strip() + " "
    for phrase, atom in _ESPN_PHRASE_ALIASES:
        spaced = spaced.replace(f" {phrase} ", f" {atom} ")
    tokens: set[str] = set()
    for raw in spaced.split():
        # Season markers: "2025", "2025/26", "24-25". A *single* digit is a
        # division number ("Liga 1", "2. Bundesliga") and is always kept.
        if raw.isdigit() and len(raw) >= 2:
            continue
        token = _ESPN_TOKEN_SYNONYMS.get(raw, raw)
        if token in _ESPN_NOISE_TOKENS:
            continue
        tokens.add(token)
    return frozenset(tokens)


def _build_espn_signature_index() -> dict[frozenset[str], str]:
    """Index the authored table by signature, refusing to hide a collision.

    Two authored names that reduce to the same signature but different codes
    mean the signature cannot decide between them, and silently keeping one is
    how a table starts guessing. Raise instead: it is a table bug, and it
    surfaces at import, in the first test that runs.
    """
    index: dict[frozenset[str], str] = {}
    for name, code in {**_ESPN_FOOTBALL_COMPETITIONS, **_ESPN_OTHER_COMPETITIONS}.items():
        signature = _espn_name_signature(name)
        if not signature:
            raise ValueError(f"competition name reduces to an empty signature: {name!r}")
        existing = index.get(signature)
        if existing is not None and existing != code:
            raise ValueError(
                f"ambiguous ESPN competition signature {sorted(signature)}: "
                f"{name!r} wants {code!r} but the same signature already maps "
                f"to {existing!r}"
            )
        index[signature] = code
    return index


_ESPN_SIGNATURE_TO_LEAGUE = _build_espn_signature_index()

# --- Stat Mappings: ESPN name → normalized key ---

SOCCER_STAT_MAP = {
    "wonCorners": "corners",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "possessionPct": "possession",
    "offsides": "offsides",
    "saves": "saves",
    "totalPasses": "total_passes",
    "accuratePasses": "accurate_passes",
    "passPct": "pass_accuracy",
    "totalCrosses": "crosses",
    "accurateCrosses": "accurate_crosses",
    "totalLongBalls": "long_balls",
    "accurateLongBalls": "accurate_long_balls",
    "blockedShots": "blocked_shots",
    "effectiveTackles": "tackles_won",
    "totalTackles": "tackles",
    "tacklePct": "tackle_accuracy",
    "interceptions": "interceptions",
    "effectiveClearance": "clearances",
    "totalClearance": "total_clearances",
    "penaltyKickGoals": "penalty_goals",
    "penaltyKickShots": "penalty_attempts",
    "shotPct": "shot_accuracy",
    "crossPct": "cross_accuracy",
    "longballPct": "long_ball_accuracy",
}

NBA_STAT_MAP = {
    "totalRebounds": "rebounds",
    "offensiveRebounds": "offensive_rebounds",
    "defensiveRebounds": "defensive_rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "fouls": "fouls",
    "technicalFouls": "technical_fouls",
    "flagrantFouls": "flagrant_fouls",
    "turnoverPoints": "turnover_points",
    "fastBreakPoints": "fast_break_points",
    "pointsInPaint": "points_in_paint",
    "largestLead": "largest_lead",
    "fieldGoalPct": "fg_pct",
    "threePointFieldGoalPct": "three_pct",
    "freeThrowPct": "ft_pct",
}

NHL_STAT_MAP = {
    "blockedShots": "blocks",
    "hits": "hits",
    "takeaways": "takeaways",
    "shotsTotal": "shots",
    "powerPlayGoals": "powerplay_goals",
    "powerPlayOpportunities": "power_play_opportunities",
    "powerPlayPct": "power_play_pct",
    "shortHandedGoals": "shorthanded_goals",
    "faceoffsWon": "faceoffs_won",
    "faceoffPercent": "faceoff_pct",
    "giveaways": "giveaways",
    "penalties": "penalties",
    "penaltyMinutes": "pim",
    "shootoutGoals": "shootout_goals",
}

VOLLEYBALL_STAT_MAP = {
    "kills": "kills",
    "aces": "aces",
    "blocks": "blocks",
    "digs": "digs",
    "assists": "assists",
    "errors": "errors",
    "hittingPercentage": "hitting_pct",
    "serviceAces": "service_aces",
    "attackErrors": "attack_errors",
    "blockSolos": "block_solos",
    "blockAssists": "block_assists",
    "points": "points",
    "totalAttacks": "total_attacks",
}

# Sport → stat map lookup
_SPORT_STAT_MAPS = {
    "football": SOCCER_STAT_MAP,
    "basketball": NBA_STAT_MAP,
    "hockey": NHL_STAT_MAP,
    "volleyball": VOLLEYBALL_STAT_MAP,
}


# A scoreboard is per *date*, not per player: one Cincinnati payload answers
# for everybody in the draw. Memoising it for the life of the process turns the
# athlete scan from "N requests per player" into "one request per date for the
# whole slate", which is what makes a hole-free scan affordable at all. Keyed by
# (sport, league, date) because those are what change the payload; bounded by
# the scan window, so it holds tens of entries, not thousands.
_SCOREBOARD_MEMO: dict[tuple[str, str, str], dict] = {}
_SCOREBOARD_MEMO_LOCK = threading.Lock()

# How far back the athlete scan looks, and how it steps.
#
# ONE window, used by every tennis path. It used to be two: the athlete scan
# read 60 consecutive days while the per-fixture stats lookup read 45 days
# sampled every third day. The 2026-08-28 fix that replaced sampling with a
# contiguous scan was applied to the first function and not the second, so a
# match the scan had already found could not have its stats read -- silently,
# because an empty result is not an error. Measured on the cache 2026-09-02: of
# 1,843 fixtures ESPN had listed for the slate's players, 348 never got stats,
# and 346 of those 348 were simply older than 45 days.
#
# The stride is not the sampling that was removed in August, and the difference
# is a property of the endpoint rather than a judgement about tennis. **A
# tennis scoreboard date returns the whole draw of every tournament running
# that day, not that day's matches**: probed 2026-09-02, `dates=20260902`
# returned 625 competitions dated 2026-08-24 to 2026-09-13, and `dates=20260210`
# returned a February tournament's full draw the same way. So a date inside a
# tournament yields all of it, and the only thing a stride can miss is a
# tournament no sampled date falls inside.
#
# Measured against ground truth -- 365 consecutive days of the ATP scoreboard,
# 6,546 unique finished singles matches:
#
#   365 daily          365 requests   6,546 matches
#   14 daily + every 4th 102 requests   6,546 matches, none missing
#   60 daily (previous)  60 requests   1,737 matches (26.5%)
#
# The shortest run of consecutive days on which any of the year's 62 events was
# visible was five (Next Gen ATP Finals), so a stride of four clears the
# shortest real tournament with a day to spare, while a stride of seven would
# not. The most recent fortnight is walked day by day regardless: an event
# still in progress has had fewer days to become visible, and recent form is
# the part of the sample it would hurt most to thin.
#
# What it bought, on the 108 slate players resolvable from the ESPN id cache:
# mean history per player 9.58 -> 41.44 matches, players reaching a full L10
# 59/108 -> 104/108, players with no history at all 1 -> 0.
_TENNIS_SCAN_DAYS = 365
_TENNIS_SCAN_CONTIGUOUS_DAYS = 14
_TENNIS_SCAN_STRIDE = 4


def _tennis_scan_offsets() -> list[int]:
    """Day offsets the tennis scan walks, most recent first."""
    contiguous = list(range(min(_TENNIS_SCAN_CONTIGUOUS_DAYS, _TENNIS_SCAN_DAYS)))
    strided = list(range(_TENNIS_SCAN_CONTIGUOUS_DAYS, _TENNIS_SCAN_DAYS, _TENNIS_SCAN_STRIDE))
    return contiguous + strided


_TENNIS_TOUR_BY_SLUG = {"mens-singles": "ATP", "womens-singles": "WTA"}

# How many of a player's own rows an H2H search reads. Larger than the ten an
# L10 needs, because a meeting between two specific players is rare inside one
# scan window and the rows are already in hand; it costs nothing but a longer
# slice of the same memoised scan.
_TENNIS_SCAN_MEETING_ROWS = 40


def _get_stat_map(sport: str) -> dict[str, str]:
    """Return the appropriate stat map for a sport."""
    return _SPORT_STAT_MAPS.get(sport, {})


def _parse_espn_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_competitor_team_id(competitor: dict) -> str:
    team = competitor.get("team", {})
    return str(competitor.get("id") or team.get("id") or "").strip()


def _extract_competitor_team_name(competitor: dict) -> str:
    team = competitor.get("team", {})
    return str(team.get("displayName", "")).strip()


def _extract_two_sided_competitors(competitors: list[dict]) -> dict[str, tuple[str, str]] | None:
    sides: dict[str, tuple[str, str]] = {}
    for index, competitor in enumerate(competitors):
        side = competitor.get("homeAway")
        if side not in ("home", "away"):
            if index == 0:
                side = "home"
            elif index == 1:
                side = "away"
            else:
                continue
        participant_id = _extract_competitor_team_id(competitor)
        participant_name = _extract_competitor_team_name(competitor)
        if not participant_id or not participant_name:
            continue
        sides[side] = (participant_id, participant_name)
    if "home" not in sides or "away" not in sides:
        return None
    return {"home": sides["home"], "away": sides["away"]}


def _extract_explicit_two_sided_competitors(competitors: list[dict]) -> dict[str, tuple[str, str]] | None:
    sides: dict[str, tuple[str, str]] = {}
    for competitor in competitors:
        side = competitor.get("homeAway")
        if side not in ("home", "away"):
            return None
        if side in sides:
            return None
        participant_id = _extract_competitor_team_id(competitor)
        participant_name = _extract_competitor_team_name(competitor)
        if not participant_id or not participant_name:
            return None
        sides[side] = (participant_id, participant_name)
    if "home" not in sides or "away" not in sides:
        return None
    if sides["home"][0] == sides["away"][0]:
        return None
    return {"home": sides["home"], "away": sides["away"]}


def _is_game_finished(event: dict) -> bool:
    """Determine if an ESPN event is finished.

    ESPN status.type.name can be empty for completed games.
    Use date + score presence as reliable indicator.
    """
    # Check explicit status first
    status = event.get("status", {})
    if isinstance(status, dict):
        type_info = status.get("type", {})
        if isinstance(type_info, dict):
            state = type_info.get("state", "")
            name = type_info.get("name", "")
            if state == "post" or name in (
                "STATUS_FULL_TIME", "STATUS_FINAL",
            ):
                return True

    # Fallback: date in past + score exists
    event_date_str = event.get("date", "")
    if not event_date_str:
        return False

    try:
        game_date = datetime.fromisoformat(
            event_date_str.rstrip("Z")
        ).replace(tzinfo=UTC)
        is_past = game_date < datetime.now(UTC)
    except (ValueError, TypeError):
        return False

    if not is_past:
        return False

    # Check for scores in competitions
    competitions = event.get("competitions", [])
    if not competitions:
        return False
    competitors = competitions[0].get("competitors", [])
    has_score = any(c.get("score") is not None for c in competitors)
    return has_score


def _tennis_tour_of(grouping: dict, comp: dict) -> str:
    """ATP or WTA for one match, read off the draw it was played in.

    Not off ``self.league``. Probed live 2026-09-02: the ATP scoreboard and the
    WTA scoreboard return the *same* events, each carrying both a "Men's
    Singles" and a "Women's Singles" grouping, so the tour in the URL says
    nothing about the tour of any individual match. The draw does, twice over
    -- ``competition.type.slug`` and the grouping's own slug -- and they agree.
    """
    for slug in (
        comp.get("type", {}).get("slug", ""),
        grouping.get("grouping", {}).get("slug", ""),
    ):
        tour = _TENNIS_TOUR_BY_SLUG.get(str(slug).strip().lower())
        if tour:
            return tour
    return ""


def _parse_tennis_competition(event: dict, grouping: dict, comp: dict) -> dict | None:
    """One finished singles match, with everything the scoreboard states about it.

    This is the whole tennis payload in one place, and it is built once. The
    scan used to keep four fields per match (id, date, two display names) and
    then re-fetch up to twenty scoreboards *per fixture* to read the set scores
    it had already had in hand -- while the tournament, the season, the round,
    the format and the published score line went in the bin every time.

    What is kept and why:

    * ``competition_provider_id`` / ``season`` -- ESPN's ``tournamentId`` and
      season year. Every ESPN tennis observation used to reach ANALYZE with
      ``competition_id=None, season_id=None``, which is precisely what
      ``scope_values`` needs to drop a stale season or an out-of-scope event,
      so nothing could ever be scoped out of an ESPN sample.
    * ``competition_name`` -- the tour prefixed to ESPN's event name, spelled
      the way DISCOVER spells a competition ("ATP US Open"), so one table maps
      both to a surface.
    * ``score`` -- the published set score from ``notes``. It is what
      ``tennis_score.parse_tennis_score`` reads to tell a retirement from a
      completed match; a threshold on games cannot, because a retirement at
      7-6 6-7 1-0 is twenty-seven games long.
    * ``best_of`` -- ``format.regulation.periods``, stated by the provider.
    * ``round`` -- qualifying rounds are in the same draw as the main one.

    Returns None for anything that is not a two-player singles match that has
    finished.
    """
    if "double" in str(grouping.get("grouping", {}).get("displayName", "")).lower():
        return None
    # STATUS_FINAL, not state == "post". "post" is every match that has stopped
    # happening, and ESPN says which kind: over a year of ATP scoreboards it
    # returned 6,327 STATUS_FINAL, 174 STATUS_RETIRED, 37 STATUS_WALKOVER and 8
    # STATUS_SUSPENDED. A retirement carries a real, short score line and is
    # exactly the shape that flatters an UNDER; a walkover carries no
    # linescores at all and used to arrive here as a match in which both
    # players won zero games. The provider states the distinction, so it is
    # read rather than inferred from a threshold on games.
    if comp.get("status", {}).get("type", {}).get("name") != "STATUS_FINAL":
        return None
    competitors = comp.get("competitors", [])
    if len(competitors) != 2:
        return None

    # Ordered by ESPN's own ``homeAway``, not by position. Position is not the
    # order: across all 6,546 finished singles matches in a year of ATP
    # scoreboards, ``homeAway`` read ("away", "home") -- every single row --
    # so indexing by list position labelled every ESPN tennis observation
    # backwards. Totals survived that (a sum does not care), a per-side figure
    # such as ``ranking`` did not.
    ordered = sorted(
        competitors,
        key=lambda c: 0 if str(c.get("homeAway", "")).lower() == "home" else 1,
    )

    names: list[str] = []
    ids: list[str] = []
    stats: dict[str, dict[str, float]] = {}
    linescore_games = 0.0
    linescore_sets = 0
    for index, competitor in enumerate(ordered):
        side = "home" if index == 0 else "away"
        athlete = competitor.get("athlete", {}) or {}
        names.append(str(athlete.get("displayName", "")))
        ids.append(str(competitor.get("id", "")))

        linescores = competitor.get("linescores", []) or []
        games_won = float(sum(int(ls.get("value", 0) or 0) for ls in linescores))
        sets_won = float(sum(1 for ls in linescores if ls.get("winner", False)))
        linescore_games += games_won
        linescore_sets = max(linescore_sets, len(linescores))

        stats.setdefault("sets_won", {})[side] = sets_won
        stats.setdefault("games_won", {})[side] = games_won
        stats.setdefault("total_sets", {})[side] = float(len(linescores))
        rank = competitor.get("curatedRank", {}).get("current", 0)
        try:
            if rank and rank != "NR":
                stats.setdefault("ranking", {})[side] = float(rank)
        except (ValueError, TypeError):
            pass

    if not names[0] or not names[1] or not ids[0] or not ids[1]:
        return None

    notes = comp.get("notes") or []
    score_text = ""
    for note in notes:
        text = str(note.get("text", "")).strip()
        if text:
            score_text = text
            break
    parsed = parse_tennis_score(score_text)

    # The provider stating the same match twice is the one disagreement this
    # module can adjudicate, so it does: the per-set linescores and the
    # published score line are two transcriptions of one result, and a match
    # where they differ is not a match to price off. Measured 2026-09-02 on 310
    # finished matches, they agreed on 309; the one exception was a retirement,
    # which is dropped on its own account below.
    if parsed is not None and parsed.completed and parsed.games != linescore_games:
        return None

    tour = _tennis_tour_of(grouping, comp)
    event_name = str(event.get("name", "")).strip()
    season = event.get("season", {})
    # Never falls back to ``event.get("id")``: that is the id of this one
    # match, not of the tournament, so it is a different number per round and
    # per year -- a fixture whose provider omitted ``tournamentId`` must read
    # as "tournament unknown", not silently acquire a fake, unstable one that
    # config/tennis_tournament_map.json could never sensibly pin.
    tournament_id = comp.get("tournamentId")

    # ``format.regulation.periods`` is deliberately NOT read as the match
    # format, though it is the obvious candidate and the name invites it. It is
    # a constant of the scoreboard being queried, not a fact about the match:
    # probed 2026-09-02, the ATP scoreboard reported periods=5 for every
    # competition it served -- including the US Open *women's* singles and
    # mixed doubles, and including Monte-Carlo, where a men's final is
    # best-of-three -- while the WTA scoreboard reported 3 for everything,
    # including men's singles at combined events. Best-of-five is decided by
    # ``config/tennis_match_format.json`` and by the sample, and a confidently
    # wrong pin from here would override both.

    return {
        "id": str(comp.get("id", "")),
        "date": comp.get("date", comp.get("startDate", "")),
        "home_team": names[0],
        "away_team": names[1],
        "home_participant_id": ids[0],
        "away_participant_id": ids[1],
        "competition_provider_id": str(tournament_id) if tournament_id else "",
        "competition_name": f"{tour} {event_name}".strip() if event_name else "",
        "season": str(season.get("year", "")) if isinstance(season, dict) else "",
        "tour": tour,
        "round": str(comp.get("round", {}).get("displayName", "")),
        "score": score_text,
        "completed": bool(parsed.completed) if parsed is not None else True,
        "stats": stats,
    }


def _iter_tennis_competitions(payload: dict):
    """Every (event, grouping, competition) triple in one day's scoreboard."""
    for event in payload.get("events", []):
        for grouping in event.get("groupings", []):
            for comp in grouping.get("competitions", []):
                yield event, grouping, comp


class ESPNClient(BaseAPIClient):
    """ESPN Hidden API client — free, unlimited requests.

    Supports soccer (36+ leagues), basketball (NBA/WNBA),
    hockey (NHL), tennis, and volleyball.
    """

    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

    def __init__(self, sport: str = "football", league: str = "eng.1", rate_limiter: RateLimiter | None = None):
        """Initialize ESPN client for a specific sport and league.

        Args:
            sport: Our sport name (football/basketball/hockey/tennis/volleyball)
            league: ESPN league code (eng.1, nba, nhl, mlb, etc.)
            rate_limiter: RateLimiter instance (not used for ESPN but required by base)
        """
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        self.sport = sport
        self.league = league
        self._espn_sport = ESPN_SPORT_MAP.get(sport, sport)

        base_url = f"{self.ESPN_BASE}/{self._espn_sport}/{league}"
        super().__init__(
            api_name=f"espn-{sport}",
            base_url=base_url,
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str:
        """ESPN needs no API key — return sentinel so is_available() returns True."""
        return "espn-no-key"

    def _build_headers(self) -> dict:
        """No API key header needed for ESPN."""
        return {"Accept": "application/json"}

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 0) -> dict:
        """Make ESPN request — skip rate limiter, still handle retries/errors."""
        from bet.integration.telemetry_wrapper import wrap_request

        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = wrap_request(
                    provider=self.api_name,
                    request_fn=requests.get,
                    url=url,
                    params=params,
                    headers=self._build_headers(),
                    timeout=self.TIMEOUT,
                    scope_id=endpoint,
                )

                if result.error and result.error.retryable:
                    raise requests.exceptions.RequestException(result.error.message)

                # Reconstruct a response-like object from TransportResult
                response = type("_Response", (), {
                    "status_code": result.status_code,
                    "text": result.body.decode("utf-8", errors="replace"),
                    "headers": result.headers,
                })()

                if response.status_code == 404:
                    raise APINotFoundError(
                        f"[{self.api_name}] Not found: {endpoint}",
                        status_code=404,
                    )
                if response.status_code >= 400:
                    raise APIError(
                        f"[{self.api_name}] HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                return json.loads(response.text)

            except APINotFoundError:
                raise
            except APIError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    import time
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        raise APIError(
            f"[{self.api_name}] Failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    def _load_cached_payload_result(self, cache_key: str, ttl_hours: int) -> SourceOperationResult[dict] | None:
        cached = self._check_cache(cache_key, ttl_hours=ttl_hours)
        if not cached or not isinstance(cached, dict):
            return None
        payload = cached.get("payload")
        evidence_entries = cached.get("evidence_refs")
        if not isinstance(payload, dict) or not isinstance(evidence_entries, list):
            return None
        refs = [EvidenceRef.from_dict(entry) for entry in evidence_entries]
        try:
            for ref in refs:
                load_evidence_object_bytes(ref.object_sha256)
        except (FileNotFoundError, ValueError):
            return None
        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            http_status=200,
            evidence_refs=refs,
        )

    def _save_cached_payload_result(self, cache_key: str, payload: dict, evidence_refs: list[EvidenceRef]) -> None:
        self._save_cache(
            cache_key,
            {
                "payload": payload,
                "evidence_refs": [ref.to_dict() for ref in evidence_refs],
            },
        )

    def _request_payload_result(
        self,
        *,
        endpoint: str,
        params: dict | None,
        operation: str,
        cache_key: str | None,
        ttl_hours: int,
        source_event_id: str | None = None,
    ) -> SourceOperationResult[dict]:
        from bet.integration.telemetry_wrapper import wrap_request

        if cache_key:
            cached = self._load_cached_payload_result(cache_key, ttl_hours)
            if cached is not None:
                return cached

        url = f"{self.base_url}{endpoint}"
        last_error_code = "transport_error"
        last_retryable = False
        for attempt in range(1, self.MAX_RETRIES + 1):
            result = wrap_request(
                provider=self.api_name,
                request_fn=requests.get,
                url=url,
                params=params,
                headers=self._build_headers(),
                timeout=self.TIMEOUT,
                scope_id=endpoint,
            )
            evidence_refs: list[EvidenceRef] = []
            if result.status_code is not None:
                evidence_refs.append(
                    persist_response_evidence(
                        operation=operation,
                        url=url,
                        params=params,
                        response=result,
                        source_event_id=source_event_id,
                    )
                )
            if result.error and result.error.retryable and attempt < self.MAX_RETRIES:
                import time

                time.sleep(self.BACKOFF_BASE * (2 ** (attempt - 1)))
                last_error_code = result.error.type or "transport_error"
                last_retryable = True
                continue
            if result.error and result.status_code is None:
                return SourceOperationResult(
                    status=SourceResultStatus.TRANSPORT_ERROR,
                    http_status=None,
                    retryable=bool(result.error.retryable),
                    error_code=result.error.type or "transport_error",
                    evidence_refs=evidence_refs,
                )

            status_code = result.status_code or 0
            retry_after = _retry_after_seconds(result.headers)
            if status_code == 401:
                return SourceOperationResult(SourceResultStatus.AUTHENTICATION_ERROR, http_status=401, error_code="http_401", evidence_refs=evidence_refs)
            if status_code == 403:
                return SourceOperationResult(SourceResultStatus.BLOCKED, http_status=403, error_code="http_403", evidence_refs=evidence_refs)
            if status_code == 404:
                return SourceOperationResult(SourceResultStatus.NOT_FOUND, http_status=404, error_code="http_404", evidence_refs=evidence_refs)
            if status_code == 429:
                return SourceOperationResult(
                    SourceResultStatus.RATE_LIMITED,
                    http_status=429,
                    retryable=True,
                    error_code="http_429",
                    retry_after_seconds=retry_after,
                    evidence_refs=evidence_refs,
                )
            if status_code >= 500:
                return SourceOperationResult(
                    SourceResultStatus.UPSTREAM_ERROR,
                    http_status=status_code,
                    retryable=True,
                    error_code=f"http_{status_code}",
                    evidence_refs=evidence_refs,
                )
            if status_code >= 400:
                return SourceOperationResult(
                    SourceResultStatus.UPSTREAM_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code=f"http_{status_code}",
                    evidence_refs=evidence_refs,
                )
            try:
                payload = json.loads(result.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return SourceOperationResult(
                    SourceResultStatus.PARSE_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code="json_decode_error",
                    evidence_refs=evidence_refs,
                )
            if not isinstance(payload, dict):
                return SourceOperationResult(
                    SourceResultStatus.SCHEMA_ERROR,
                    http_status=status_code,
                    retryable=False,
                    error_code="payload_not_object",
                    evidence_refs=evidence_refs,
                )
            if cache_key:
                self._save_cached_payload_result(cache_key, payload, evidence_refs)
            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=payload,
                http_status=status_code,
                evidence_refs=evidence_refs,
            )

        return SourceOperationResult(
            SourceResultStatus.TRANSPORT_ERROR,
            retryable=last_retryable,
            error_code=last_error_code,
        )

    def get_event_fixture_result(self, date: str, event_id: str) -> SourceOperationResult[APIFixture]:
        date_compact = date.replace("-", "")
        payload_result = self._request_payload_result(
            endpoint="/scoreboard",
            params={"dates": date_compact},
            operation="scoreboard",
            cache_key=f"espn/{self.sport}/{self.league}/fixtures/{date}",
            ttl_hours=6,
            source_event_id=event_id,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )
        events = payload_result.value.get("events")
        if not isinstance(events, list):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="scoreboard_events_missing",
                evidence_refs=payload_result.evidence_refs,
            )
        for event in events:
            if str(event.get("id", "")).strip() != str(event_id).strip():
                continue
            competitions = event.get("competitions", [])
            if not competitions:
                return SourceOperationResult(
                    SourceResultStatus.SCHEMA_ERROR,
                    http_status=payload_result.http_status,
                    error_code="event_competitions_missing",
                    evidence_refs=payload_result.evidence_refs,
                )
            sides = _extract_explicit_two_sided_competitors(competitions[0].get("competitors", []))
            if not sides:
                return SourceOperationResult(
                    SourceResultStatus.SCHEMA_ERROR,
                    http_status=payload_result.http_status,
                    error_code="event_explicit_sides_missing",
                    evidence_refs=payload_result.evidence_refs,
                )
            status = event.get("status", {})
            status_name = "scheduled"
            if isinstance(status, dict):
                type_info = status.get("type", {})
                if isinstance(type_info, dict):
                    status_name = type_info.get("name", "scheduled")
            season = event.get("season", {})
            season_type = season.get("type", {})
            league_info = competitions[0].get("league", {})
            if isinstance(league_info, dict) and league_info.get("name"):
                comp_name = league_info.get("name", self.league)
            elif isinstance(season_type, dict):
                comp_name = season_type.get("name", self.league)
            else:
                comp_name = season.get("slug", self.league)
            home_id, home_name = sides["home"]
            away_id, away_name = sides["away"]
            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=APIFixture(
                    external_id=str(event_id).strip(),
                    source=self.api_name,
                    sport=self.sport,
                    competition_name=comp_name,
                    home_team_name=home_name,
                    away_team_name=away_name,
                    kickoff=event.get("date", ""),
                    status=status_name,
                    home_participant_id=home_id,
                    away_participant_id=away_id,
                ),
                http_status=payload_result.http_status,
                evidence_refs=payload_result.evidence_refs,
            )
        return SourceOperationResult(
            SourceResultStatus.NOT_FOUND,
            http_status=payload_result.http_status,
            error_code="event_not_present_on_scoreboard",
            evidence_refs=payload_result.evidence_refs,
        )

    def get_fixtures_result(self, date: str) -> SourceOperationResult[list[APIFixture]]:
        date_compact = date.replace("-", "")
        payload_result = self._request_payload_result(
            endpoint="/scoreboard",
            params={"dates": date_compact},
            operation="scoreboard",
            cache_key=f"espn/{self.sport}/{self.league}/fixtures/{date}",
            ttl_hours=6,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )

        data = payload_result.value
        events = data.get("events")
        if not isinstance(events, list):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="scoreboard_events_missing",
                evidence_refs=payload_result.evidence_refs,
            )

        if self.sport == "tennis":
            fixtures = self._get_individual_sport_fixtures(data, date)
            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=fixtures,
                http_status=payload_result.http_status,
                evidence_refs=payload_result.evidence_refs,
            )

        fixtures = []
        for event in events:
            event_id = str(event.get("id", "")).strip()
            if not event_id:
                continue
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            sides = _extract_two_sided_competitors(competitors)
            if not sides:
                continue
            home_id, home_name = sides["home"]
            away_id, away_name = sides["away"]
            status = event.get("status", {})
            status_name = "scheduled"
            if isinstance(status, dict):
                type_info = status.get("type", {})
                if isinstance(type_info, dict):
                    status_name = type_info.get("name", "scheduled")
            season = event.get("season", {})
            season_type = season.get("type", {})
            league_info = comp.get("league", {})
            if isinstance(league_info, dict) and league_info.get("name"):
                comp_name = league_info.get("name", self.league)
            elif isinstance(season_type, dict):
                comp_name = season_type.get("name", self.league)
            else:
                comp_name = season.get("slug", self.league)
            fixtures.append(
                APIFixture(
                    external_id=event_id,
                    source=self.api_name,
                    sport=self.sport,
                    competition_name=comp_name,
                    home_team_name=home_name,
                    away_team_name=away_name,
                    kickoff=event.get("date", ""),
                    status=status_name,
                    home_participant_id=home_id,
                    away_participant_id=away_id,
                )
            )

        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value=fixtures,
            http_status=payload_result.http_status,
            evidence_refs=payload_result.evidence_refs,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """Get fixtures for a date (YYYY-MM-DD) via /scoreboard endpoint."""
        return self.get_fixtures_result(date).value or []

    def _get_individual_sport_fixtures(self, data: dict, date: str) -> list[APIFixture]:
        """Parse fixtures for individual sports (tennis).

        Tennis: events are tournaments, groupings contain singles/doubles,
                competitions are individual matches.
        """
        fixtures = []
        for event in data.get("events", []):
            event_name = event.get("name", "")

            # Tennis: matches are in groupings→competitions
            for grouping in event.get("groupings", []):
                group_name = grouping.get("grouping", {}).get("displayName", "")
                # Only singles matches (skip doubles for betting)
                if "double" in group_name.lower():
                    continue
                for comp in grouping.get("competitions", []):
                    fixture = self._parse_individual_competition(
                        comp, f"{event_name} - {group_name}"
                    )
                    if fixture:
                            fixtures.append(fixture)
        return fixtures

    def _parse_individual_competition(
        self, comp: dict, competition_name: str
    ) -> APIFixture | None:
        """Parse a single competition (match/fight) for individual sports."""
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        # Individual sports use athlete, not team
        names = []
        for c in competitors:
            athlete = c.get("athlete", {})
            name = athlete.get("displayName", "")
            if not name:
                name = c.get("team", {}).get("displayName", "")
            names.append(name)

        if len(names) < 2 or not names[0] or not names[1]:
            return None

        status = comp.get("status", {})
        status_name = "scheduled"
        if isinstance(status, dict):
            type_info = status.get("type", {})
            if isinstance(type_info, dict):
                status_name = type_info.get("name", "scheduled")

        return APIFixture(
            external_id=str(comp.get("id", "")),
            source=self.api_name,
            sport=self.sport,
            competition_name=competition_name,
            home_team_name=names[0],
            away_team_name=names[1],
            kickoff=comp.get("date", comp.get("startDate", "")),
            status=status_name,
        )

    def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
        return self.get_fixture_stats_result(fixture_id).value or []

    def get_fixture_stats_result(self, fixture_id: str) -> SourceOperationResult[list[APIMatchStats]]:
        if self.sport == "tennis":
            return SourceOperationResult(SourceResultStatus.SUCCESS, value=self._get_tennis_match_stats(fixture_id))
        if self.sport not in _SPORT_STAT_MAPS:
            return SourceOperationResult(SourceResultStatus.NOT_SUPPORTED, error_code="sport_not_supported")

        payload_result = self._request_payload_result(
            endpoint="/summary",
            params={"event": fixture_id},
            operation="summary",
            cache_key=f"espn/{self.sport}/{self.league}/fixture_stats/{fixture_id}",
            ttl_hours=168,
            source_event_id=fixture_id,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )

        data = payload_result.value
        boxscore = data.get("boxscore")
        if not isinstance(boxscore, dict):
            status = data.get("header", {}).get("competitions", [{}])[0].get("status", {})
            state = status.get("type", {}).get("state") if isinstance(status, dict) else None
            if state in {"pre", "in"}:
                return SourceOperationResult(
                    SourceResultStatus.NOT_PUBLISHED_YET,
                    http_status=payload_result.http_status,
                    error_code="summary_not_published_yet",
                    evidence_refs=payload_result.evidence_refs,
                )
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="summary_boxscore_missing",
                evidence_refs=payload_result.evidence_refs,
            )
        teams_data = boxscore.get("teams")
        if not isinstance(teams_data, list):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="summary_teams_missing",
                evidence_refs=payload_result.evidence_refs,
            )
        if len(teams_data) < 2:
            return SourceOperationResult(
                SourceResultStatus.SUCCESS,
                value=[],
                http_status=payload_result.http_status,
                evidence_refs=payload_result.evidence_refs,
            )

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        participant_ids: dict[str, str] = {}
        for i, team_data in enumerate(teams_data):
            team_info = team_data.get("team", {})
            team_name = team_info.get("displayName", "")
            participant_id = str(team_data.get("id") or team_info.get("id") or "").strip()
            home_away = team_data.get("homeAway", "")
            if home_away == "home":
                side = "home"
            elif home_away == "away":
                side = "away"
            else:
                side = "home" if i == 0 else "away"
            teams[side] = team_name
            participant_ids[side] = participant_id
            self._parse_flat_stats(team_data.get("statistics", []), side, stats)

        score_key = None
        if self.sport in ("football", "hockey"):
            score_key = "goals"
        elif self.sport == "basketball":
            score_key = "points"

        if score_key:
            header = data.get("header", {})
            header_comps = header.get("competitions", [])
            if header_comps:
                for comp in header_comps[0].get("competitors", []):
                    ha = comp.get("homeAway", "")
                    score_val = comp.get("score", "")
                    if ha in ("home", "away") and score_val:
                        try:
                            stats.setdefault(score_key, {})[ha] = float(score_val)
                        except (ValueError, TypeError):
                            pass

        if (
            not teams.get("home")
            or not teams.get("away")
            or not participant_ids.get("home")
            or not participant_ids.get("away")
        ):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="summary_participants_incomplete",
                evidence_refs=payload_result.evidence_refs,
            )

        result = [APIMatchStats(
            external_id=fixture_id,
            source=self.api_name,
            sport=self.sport,
            home_team_name=teams["home"],
            away_team_name=teams["away"],
            stats=stats,
            home_participant_id=participant_ids["home"],
            away_participant_id=participant_ids["away"],
        )]
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value=result,
            http_status=payload_result.http_status,
            evidence_refs=payload_result.evidence_refs,
        )

    def _parse_flat_stats(
        self, team_stats_raw: list, side: str, stats: dict[str, dict[str, float]]
    ) -> None:
        """Parse flat statistics list (soccer, NBA, NHL)."""
        stat_map = _get_stat_map(self.sport)

        for stat_entry in team_stats_raw:
            espn_name = stat_entry.get("name", "")
            display_value = stat_entry.get("displayValue")

            normalized_key = stat_map.get(espn_name)
            if not normalized_key:
                continue

            if display_value is None:
                continue

            if isinstance(display_value, str):
                cleaned = display_value.replace("%", "").strip()
                if not cleaned:
                    continue
            else:
                cleaned = str(display_value).strip()
                if not cleaned:
                    continue

            try:
                value = float(cleaned)
            except (ValueError, TypeError):
                continue

            if normalized_key not in stats:
                stats[normalized_key] = {}
            stats[normalized_key][side] = value

    # Row shape v3: v2 rows carried four fields and no metadata, so a cache
    # written before this change would keep feeding ANALYZE observations with
    # no competition, no season, no surface and a games figure that had never
    # been checked against the published score. Versioning the key retires them
    # rather than waiting twelve hours for each one.
    _TENNIS_FIXTURES_KEY = "athlete_fixtures_v3"
    _TENNIS_STATS_KEY = "fixture_stats_v2"

    def _tennis_stats_cache_key(self, fixture_id: str) -> str:
        return f"espn/{self.sport}/{self.league}/{self._TENNIS_STATS_KEY}/{fixture_id}"

    def _get_tennis_match_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """One tennis match's stats, normally without a request.

        The athlete scan writes this cache for every match it parses, so by the
        time the enrichment loop asks for a fixture's stats the answer is
        already on disk. The scan below is the fallback for a fixture that
        arrived from somewhere else, and it uses the same memoised, hole-free
        window as the scan itself -- it used to use a different, shorter,
        sampled one, which is how 346 fixtures came to be found and then never
        read.

        A miss is cached too. It used to not be, so each of those 346 fixtures
        re-spent its whole scan on every run, for ever, to conclude nothing.
        """
        cache_key = self._tennis_stats_cache_key(fixture_id)
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached is not None:
            stats = cached.get("stats", [])
            if stats:
                return [APIMatchStats(**ms) for ms in stats]
            # A miss is kept for a day, a hit for a week. The scan window moves
            # with the calendar and a result ESPN had not published when we
            # asked may be there tomorrow, so a negative that lasted as long as
            # a positive would be its own kind of stale.
            if self._check_cache(cache_key, ttl_hours=24) is not None:
                return []

        from datetime import timedelta

        today = datetime.now(UTC).date()
        for offset in _tennis_scan_offsets():
            date_str = (today - timedelta(days=offset)).strftime("%Y%m%d")
            payload = self._scoreboard_for_date(date_str)
            if payload is None:
                continue
            for event, grouping, comp in _iter_tennis_competitions(payload):
                if str(comp.get("id", "")) != str(fixture_id):
                    continue
                row = _parse_tennis_competition(event, grouping, comp)
                if row is None:
                    break
                return self._store_tennis_stats(row)

        self._save_cache(cache_key, {"stats": []})
        return []

    def _store_tennis_stats(self, row: dict) -> list[APIMatchStats]:
        """Turn a parsed competition into APIMatchStats and cache it under its id.

        ``stats`` carries the scoreboard's per-side counts plus the flat
        metadata fields ``providers.py`` reads off a stats dict (``surface`` is
        the established one). ``_combined_from_dict_stats`` only ever looks at
        aliased keys whose value is a two-sided dict, so the flat entries pass
        through it untouched and reach the consumer that wants them.
        """
        stats = dict(row.get("stats") or {})
        stats["score"] = row.get("score", "")
        stats["completed"] = row.get("completed", True)
        stats["round"] = row.get("round", "")

        result = [
            APIMatchStats(
                external_id=str(row.get("id", "")),
                source=self.api_name,
                sport=self.sport,
                home_team_name=row.get("home_team", ""),
                away_team_name=row.get("away_team", ""),
                stats=stats,
            )
        ]
        self._save_cache(
            self._tennis_stats_cache_key(str(row.get("id", ""))),
            {"stats": [asdict(ms) for ms in result]},
        )
        return result

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H data — uses team schedule filtered by opponent."""
        if self.sport == "tennis":
            return self._get_athlete_h2h(team1_id, team2_id, last_n)
        cache_key = f"espn/{self.sport}/{self.league}/h2h/{team1_id}_{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("games", [])

        try:
            data = self._request(f"/teams/{team1_id}/schedule")
        except Exception:
            return []

        events = data.get("events", [])
        h2h_games = []
        for event in events:
            if not _is_game_finished(event):
                continue
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            competitors = competitions[0].get("competitors", [])
            # Check if team2 is in this game
            opponent_match = any(
                str(c.get("id", "")) == str(team2_id)
                or str(c.get("team", {}).get("id", "")) == str(team2_id)
                for c in competitors
            )
            if opponent_match:
                h2h_games.append({
                    "id": event.get("id"),
                    "date": event.get("date", ""),
                    "competitors": competitors,
                })

        h2h_games.sort(key=lambda g: g.get("date", ""), reverse=True)
        result = h2h_games[:last_n]

        self._save_cache(cache_key, {"games": result})
        return result

    def _get_athlete_h2h(self, athlete_id: str, opponent_id: str, last_n: int = 10) -> list[dict]:
        """Meetings between two players, taken from the scan that already ran.

        The generic path sent tennis to ``/teams/{id}/schedule``, an endpoint
        ESPN publishes for clubs and not for players. It answered nothing, and
        on the 2026-09-02 slate that produced a ``no h2h meetings`` data_gap on
        36 of 38 fixtures -- a sentence that reads like a fact about the two
        players and was really a fact about the URL.

        This says what ESPN can actually support: meetings inside the scan
        window, found in the rows already fetched and memoised for each
        player's own history, at no additional request. Outside that window it
        returns nothing and means it -- ``tennis-abstract`` carries the full
        career and is the provider for a deep H2H.
        """
        meetings = [
            row
            for row in self._get_athlete_recent_matches(athlete_id, last_n=_TENNIS_SCAN_MEETING_ROWS)
            if str(opponent_id)
            in (str(row.get("home_participant_id")), str(row.get("away_participant_id")))
        ]
        meetings.sort(key=lambda m: m.get("date", ""), reverse=True)
        return meetings[:last_n]

    def get_h2h_result(
        self,
        team1_id: str,
        team2_id: str,
        *,
        analysis_cutoff_at: str | None = None,
        exclude_event_ids: set[str] | None = None,
        last_n: int = 10,
    ) -> SourceOperationResult[dict]:
        """Get typed H2H history with exact cutoff/exclusion and retained evidence."""
        excluded_ids = {
            str(event_id).strip()
            for event_id in (exclude_event_ids or set())
            if str(event_id).strip()
        }
        cache_key = (
            f"espn/{self.sport}/{self.league}/h2h/{team1_id}_{team2_id}/"
            f"{analysis_cutoff_at or 'none'}/{','.join(sorted(excluded_ids)) or 'none'}/{last_n}"
        )
        cutoff_dt = _parse_espn_datetime(analysis_cutoff_at) if analysis_cutoff_at else None
        payload_result = self._request_payload_result(
            endpoint=f"/teams/{team1_id}/schedule",
            params=None,
            operation="h2h_team_schedule",
            cache_key=cache_key,
            ttl_hours=12,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )

        events = payload_result.value.get("events")
        if not isinstance(events, list):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="schedule_events_missing",
                evidence_refs=payload_result.evidence_refs,
            )

        requested_ids = {str(team1_id).strip(), str(team2_id).strip()}
        meetings: list[dict] = []
        for event in events:
            event_id = str(event.get("id", "")).strip()
            if not event_id or event_id in excluded_ids:
                continue
            event_date = str(event.get("date", "")).strip()
            event_dt = _parse_espn_datetime(event_date)
            if event_dt is None:
                continue
            if cutoff_dt is not None and not event_dt < cutoff_dt:
                continue
            if not _is_game_finished(event):
                continue

            competitions = event.get("competitions", [])
            if not competitions:
                continue
            competitors = competitions[0].get("competitors", [])
            sides = (
                _extract_explicit_two_sided_competitors(competitors)
                if self.sport == "football"
                else _extract_two_sided_competitors(competitors)
            )
            if not sides:
                continue
            home_id, home_name = sides["home"]
            away_id, away_name = sides["away"]
            if {home_id, away_id} != requested_ids:
                continue

            home_score = ""
            away_score = ""
            for competitor in competitors:
                score = str(competitor.get("score", "") or "")
                if competitor.get("homeAway") == "home":
                    home_score = score
                elif competitor.get("homeAway") == "away":
                    away_score = score
            meetings.append(
                {
                    "event_id": event_id,
                    "date": event_date,
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_participant_id": home_id,
                    "away_participant_id": away_id,
                    "score": f"{home_score}-{away_score}" if home_score or away_score else "",
                }
            )

        meetings.sort(key=lambda item: item["date"], reverse=True)
        selected = meetings[:last_n]
        bundle_id = ""
        if payload_result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_h2h",
                    request_identity=payload_result.evidence_refs[0].request_identity,
                    parser_version=ESPN_PARSER_VERSION,
                    source_event_refs=[event["event_id"] for event in selected],
                    evidence_refs=payload_result.evidence_refs,
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=payload_result.http_status,
                    error_code="bundle_manifest_failed",
                    evidence_refs=payload_result.evidence_refs,
                )

        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value={
                "team1_id": str(team1_id),
                "team2_id": str(team2_id),
                "meetings": selected,
                "meeting_count": len(selected),
            },
            http_status=payload_result.http_status,
            evidence_refs=payload_result.evidence_refs,
            bundle_id=bundle_id,
            parser_diagnostics={
                "raw_count": len(events),
                "accepted_count": len(selected),
                "excluded_event_count": len(excluded_ids),
            },
        )

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve team name to ESPN team ID via /teams endpoint.

        Uses case-insensitive fuzzy matching. Results cached for 7 days.
        For individual sports (tennis/MMA), searches scoreboard for athlete IDs.
        """
        cache_key = f"espn/{self.sport}/{self.league}/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")

        # For individual sports, search scoreboard for athlete IDs
        if self.sport == "tennis":
            return self._resolve_athlete_id(team_name)

        try:
            data = self._request("/teams")
        except Exception:
            return None

        # ESPN returns teams in .sports[].leagues[].teams[] or .teams[]
        teams_list = []
        sports = data.get("sports", [])
        if sports:
            for sport_data in sports:
                for league_data in sport_data.get("leagues", []):
                    for team_entry in league_data.get("teams", []):
                        t = team_entry.get("team", team_entry)
                        teams_list.append(t)
        else:
            # Direct teams array
            for team_entry in data.get("teams", []):
                t = team_entry.get("team", team_entry)
                teams_list.append(t)

        # Fail-closed matching: exact/abbr first, then constrained contains/location.
        name_lower = _fold_espn_participant_name(team_name)
        if not name_lower:
            return None
        exact_matches = []
        abbreviation_matches = []
        contains_matches = []
        location_matches = []

        for t in teams_list:
            display = _fold_espn_participant_name(t.get("displayName", ""))
            short = _fold_espn_participant_name(t.get("shortDisplayName", ""))
            abbr = _fold_espn_participant_name(t.get("abbreviation", ""))
            location = _fold_espn_participant_name(t.get("location", ""))

            if display == name_lower or short == name_lower:
                exact_matches.append(t)
                continue
            if abbr == name_lower:
                abbreviation_matches.append(t)
                continue
            if len(name_lower) >= 4 and (
                name_lower in display
                or display in name_lower
                or name_lower in short
                or short in name_lower
            ):
                contains_matches.append(t)
                continue
            if len(name_lower) >= 4 and (name_lower in location or location in name_lower):
                location_matches.append(t)

        for bucket in (
            exact_matches,
            abbreviation_matches,
            contains_matches,
            location_matches,
        ):
            if not bucket:
                continue
            ids = {
                str(match.get("id", "")).strip()
                for match in bucket
                if str(match.get("id", "")).strip()
            }
            if len(ids) != 1:
                return None
            tid = ids.pop()
            self._save_cache(cache_key, {"team_id": tid})
            return tid

        return None

    def _resolve_athlete_id(self, athlete_name: str) -> str | None:
        """Resolve athlete name to ESPN ID via search API, then scoreboard fallback.

        Uses ESPN's web search API (site.web.api.espn.com/apis/common/v3/search)
        which works regardless of whether the player is active on today's scoreboard.
        Falls back to scoreboard scanning if search fails.
        """
        cache_key = f"espn/{self.sport}/{self.league}/athlete_search/{athlete_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")

        name_lower = _fold_espn_participant_name(athlete_name)
        if not name_lower:
            return None

        # Method 1: ESPN Web Search API (works for ALL players, not just today's matches)
        try:
            from urllib.parse import quote
            search_url = (
                f"https://site.web.api.espn.com/apis/common/v3/search"
                f"?query={quote(athlete_name)}&type=player&sport={self.sport}&limit=10"
            )
            resp = requests.get(search_url, headers=self._build_headers(), timeout=10)
            if resp.status_code == 200:
                search_data = resp.json()
                items = search_data.get("items", [])
                for item in items:
                    item_sport = item.get("sport", "").lower()
                    item_league = item.get("league", "").lower()
                    # Match by name AND league (atp/wta). The name test is
                    # identity_matches, not a substring test: "henri" is a
                    # substring of "henrique", and on 2026-08-28 that is how one
                    # ESPN id came to answer for 'squire, henri', 'rocha,
                    # henrique' and 'lazarte, gonzalo enrique' alike.
                    if (
                        _espn_athlete_name_matches(athlete_name, item.get("displayName", ""))
                        and item_sport == self.sport
                        and item_league == self.league
                    ):
                        aid = item.get("id", "")
                        if aid:
                            self._save_cache(cache_key, {"team_id": aid, "league": item_league})
                            return aid
                # Second pass, for hits whose league ESPN leaves blank. It does
                # NOT drop the tour check: a hit that *states* the other tour is
                # a crossing, and accepting it is what filed 23 of the
                # 2026-08-28 slate's players under the wrong tour's id. Name
                # equality is required here too, so an unlabelled hit still has
                # to be the same person by name before it is believed.
                candidates = [
                    item for item in items
                    if _espn_athlete_name_matches(athlete_name, item.get("displayName", ""))
                    and item.get("sport", "").lower() == self.sport
                    and not item.get("league", "").strip()
                    and item.get("id")
                ]
                distinct_ids = {str(item["id"]) for item in candidates}
                if len(distinct_ids) == 1:
                    aid = str(candidates[0]["id"])
                    self._save_cache(cache_key, {"team_id": aid, "league": ""})
                    return aid
                if len(distinct_ids) > 1:
                    names = ", ".join(
                        sorted({item.get("displayName", "") for item in candidates})
                    )
                    print(
                        f"[{self.api_name}] '{athlete_name}' matches more than one "
                        f"ESPN athlete ({names}); refusing to guess"
                    )
                    return None
        except Exception as e:
            print(f"[{self.api_name}] ESPN search API failed for '{athlete_name}': {e}")

        # Method 2: Scoreboard fallback (only finds players active today)
        try:
            data = self._request("/scoreboard")
        except Exception:
            return None

        athletes = []
        for event in data.get("events", []):
            for grouping in event.get("groupings", []):
                for comp in grouping.get("competitions", []):
                    for c in comp.get("competitors", []):
                        ath = c.get("athlete", {})
                        if ath:
                            athletes.append({"id": str(c.get("id", "")), **ath})

        # Name equality only. The rules that used to live here -- "the query
        # contains the display name", "the query's last token appears in the
        # display name" -- are surname and forename substring tests, and they
        # cannot fail: on 2026-08-28 this pass answered 372 of 441 resolutions
        # and returned an id for the literal string "TBD". Fifty ESPN ids ended
        # up serving more than one queried player through it.
        matches = [
            a for a in athletes
            if a.get("id")
            and (
                _espn_athlete_name_matches(athlete_name, a.get("displayName", ""))
                or _espn_athlete_name_matches(athlete_name, a.get("fullName", ""))
            )
        ]
        distinct_ids = {str(a["id"]) for a in matches}
        if len(distinct_ids) == 1:
            aid = str(matches[0]["id"])
            self._save_cache(cache_key, {"team_id": aid, "league": self.league})
            return aid
        if len(distinct_ids) > 1:
            names = ", ".join(sorted({a.get("displayName", "") for a in matches}))
            print(
                f"[{self.api_name}] '{athlete_name}' matches more than one athlete "
                f"on the {self.league} scoreboard ({names}); refusing to guess"
            )
        return None

    def get_team_last_fixtures(
        self,
        team_id: str,
        last_n: int = 10,
        analysis_cutoff_at: str | None = None,
        exclude_event_ids: set[str] | None = None,
    ) -> list[dict]:
        return self.get_team_last_fixtures_result(
            team_id,
            last_n=last_n,
            analysis_cutoff_at=analysis_cutoff_at,
            exclude_event_ids=exclude_event_ids,
        ).value or []

    def get_team_last_fixtures_result(
        self,
        team_id: str,
        last_n: int = 10,
        analysis_cutoff_at: str | None = None,
        exclude_event_ids: set[str] | None = None,
    ) -> SourceOperationResult[list[dict]]:
        """Get last N completed fixtures for a team via /teams/{id}/schedule."""
        excluded_ids = {
            str(event_id).strip() for event_id in (exclude_event_ids or set()) if str(event_id).strip()
        }
        cache_key = (
            f"espn/{self.sport}/{self.league}/team_fixtures/{team_id}/"
            f"{analysis_cutoff_at or 'none'}/{','.join(sorted(excluded_ids)) or 'none'}/{last_n}"
        )
        cutoff_dt = _parse_espn_datetime(analysis_cutoff_at) if analysis_cutoff_at else None

        # Individual sports: scan scoreboard for athlete matches
        if self.sport == "tennis":
            return SourceOperationResult(SourceResultStatus.SUCCESS, value=self._get_athlete_recent_matches(team_id, last_n))

        payload_result = self._request_payload_result(
            endpoint=f"/teams/{team_id}/schedule",
            params=None,
            operation="team_schedule",
            cache_key=cache_key,
            ttl_hours=12,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )

        events = payload_result.value.get("events")
        if not isinstance(events, list):
            return SourceOperationResult(
                SourceResultStatus.SCHEMA_ERROR,
                http_status=payload_result.http_status,
                error_code="schedule_events_missing",
                evidence_refs=payload_result.evidence_refs,
            )
        finished = []
        for event in events:
            event_id = str(event.get("id", "")).strip()
            if not event_id or event_id in excluded_ids:
                continue

            event_date = str(event.get("date", "")).strip()
            event_dt = _parse_espn_datetime(event_date)
            if event_dt is None:
                continue
            if cutoff_dt is not None and not event_dt < cutoff_dt:
                continue

            if not _is_game_finished(event):
                continue

            competitions = event.get("competitions", [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get("competitors", [])
            sides = _extract_explicit_two_sided_competitors(competitors) if self.sport == "football" else _extract_two_sided_competitors(competitors)
            if not sides:
                continue
            home_id, home_name = sides["home"]
            away_id, away_name = sides["away"]
            home_score = ""
            away_score = ""
            for c in competitors:
                c_score = c.get("score", "0")
                if c.get("homeAway") == "home":
                    home_score = str(c_score)
                elif c.get("homeAway") == "away":
                    away_score = str(c_score)

            finished.append({
                "id": event_id,
                "date": event_date,
                "home_team": home_name,
                "away_team": away_name,
                "score": f"{home_score}-{away_score}" if home_score or away_score else "",
                "home_participant_id": home_id,
                "away_participant_id": away_id,
            })

        # Sort by date descending (most recent first)
        finished.sort(key=lambda f: f.get("date", ""), reverse=True)
        result = finished[:last_n]
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value=result,
            http_status=payload_result.http_status,
            evidence_refs=payload_result.evidence_refs,
        )

    def get_injuries(self) -> list[dict]:
        """Get injury reports for the league."""
        cache_key = f"espn/{self.sport}/{self.league}/injuries"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return cached.get("injuries", [])

        try:
            data = self._request("/injuries")
        except Exception:
            return []

        injuries = []
        for team_data in data.get("injuries", data.get("teams", [])):
            team_name = ""
            if isinstance(team_data, dict):
                team_name = team_data.get("team", {}).get("displayName", "")
                for injury in team_data.get("injuries", []):
                    injuries.append({
                        "team": team_name,
                        "player": injury.get("athlete", {}).get("displayName", ""),
                        "status": injury.get("status", ""),
                        "type": injury.get("type", {}).get("description", ""),
                    })

        self._save_cache(cache_key, {"injuries": injuries})
        return injuries

    def get_team_roster(self, team_id: str) -> list[dict]:
        """Get full team roster with player details.

        Returns list of players: {name, id, position, jersey, age, height, weight, status}
        """
        cache_key = f"espn/{self.sport}/{self.league}/roster/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached.get("roster", [])

        try:
            data = self._request(f"/teams/{team_id}/roster")
        except Exception:
            return []

        roster = []
        # ESPN roster can be in athletes[] directly or grouped by position
        athletes = data.get("athletes", [])
        for group in athletes:
            # Group might be a position group dict or direct athlete
            items = group.get("items", [group]) if isinstance(group, dict) else [group]
            for item in items:
                if not isinstance(item, dict):
                    continue
                roster.append({
                    "id": str(item.get("id", "")),
                    "name": item.get("displayName", item.get("fullName", "")),
                    "position": item.get("position", {}).get("abbreviation", "") if isinstance(item.get("position"), dict) else str(item.get("position", "")),
                    "jersey": item.get("jersey", ""),
                    "age": item.get("age", None),
                    "height": item.get("displayHeight", ""),
                    "weight": item.get("displayWeight", ""),
                    "status": item.get("status", {}).get("type", "") if isinstance(item.get("status"), dict) else "active",
                })

        self._save_cache(cache_key, {"roster": roster})
        return roster

    def get_depth_chart(self, team_id: str) -> dict:
        """Get team depth chart (positional hierarchy).

        Returns dict mapping position → list of players in order (starter first).
        """
        cache_key = f"espn/{self.sport}/{self.league}/depthchart/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached.get("depthchart", {})

        try:
            data = self._request(f"/teams/{team_id}/depthcharts")
        except Exception:
            return {}

        depth = {}
        items = data.get("items", [])
        for item in items:
            positions = item.get("positions", {})
            for pos_key, pos_data in positions.items():
                if isinstance(pos_data, dict):
                    athletes = pos_data.get("athletes", [])
                    depth[pos_key] = [
                        {
                            "id": str(a.get("id", "")),
                            "name": a.get("displayName", ""),
                            "rank": a.get("rank", i + 1),
                        }
                        for i, a in enumerate(athletes)
                    ]

        self._save_cache(cache_key, {"depthchart": depth})
        return depth

    def get_team_transactions(self, team_id: str, limit: int = 25) -> list[dict]:
        """Get recent team transactions (trades, signings, waivers).

        Returns list of: {date, type, description, player}
        """
        cache_key = f"espn/{self.sport}/{self.league}/transactions/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("transactions", [])

        try:
            data = self._request(f"/teams/{team_id}/transactions", params={"limit": str(limit)})
        except Exception:
            return []

        transactions = []
        items = data.get("items", data.get("transactions", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            transactions.append({
                "date": item.get("date", ""),
                "type": item.get("type", {}).get("text", "") if isinstance(item.get("type"), dict) else str(item.get("type", "")),
                "description": item.get("text", item.get("description", "")),
                "player": item.get("athlete", {}).get("displayName", "") if isinstance(item.get("athlete"), dict) else "",
            })

        self._save_cache(cache_key, {"transactions": transactions})
        return transactions

    def _get_athlete_recent_matches(self, athlete_id: str, last_n: int = 10) -> list[dict]:
        """This athlete's last ``last_n`` finished matches, with their stats.

        ESPN exposes tennis only through the daily scoreboard, so finding a
        player's history means walking dates. Two properties make that
        affordable and make it correct:

        * **Consecutive days, not a sample.** A tournament run is a block of
          consecutive days, so a three-day hole does not lose precision, it
          loses players: on 2026-08-28 the nine sampled dates landed either
          side of every one of Carlos Alcaraz's matches and he came back with
          an empty history ESPN had all along.
        * **The scoreboard is per date, not per player**, so it is memoised for
          the life of the process and one Cincinnati payload answers for
          everybody in the draw.

        Every match is parsed in full here and its stats cached under its own
        id, so the enrichment loop's later ``get_fixture_stats`` calls cost
        nothing. That replaces a second, shorter, sampled scan that re-fetched
        up to twenty scoreboards per fixture to read set scores this pass had
        already parsed.
        """
        cache_key = f"espn/{self.sport}/{self.league}/{self._TENNIS_FIXTURES_KEY}/{athlete_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and len(cached.get("fixtures", [])) >= last_n:
            # Sliced, not returned whole. The H2H search below asks this same
            # function for a deeper slice of the same player and writes the
            # longer list back under the same key, so an unsliced return would
            # hand the next L10 caller forty observations where it asked for
            # ten -- four times the sample, from one call order.
            return cached.get("fixtures", [])[:last_n]

        from datetime import timedelta

        matches: list[dict] = []
        seen_ids: set[str] = set()
        today = datetime.now(UTC).date()

        for offset in _tennis_scan_offsets():
            if len(matches) >= last_n:
                break
            date_str = (today - timedelta(days=offset)).strftime("%Y%m%d")
            payload = self._scoreboard_for_date(date_str)
            if payload is None:
                continue

            for event, grouping, comp in _iter_tennis_competitions(payload):
                comp_id = str(comp.get("id", ""))
                if comp_id in seen_ids:
                    continue
                if not any(
                    str(c.get("id", "")) == str(athlete_id)
                    for c in comp.get("competitors", [])
                ):
                    continue
                row = _parse_tennis_competition(event, grouping, comp)
                if row is None:
                    continue
                seen_ids.add(comp_id)
                self._store_tennis_stats(row)
                matches.append(row)

        matches.sort(key=lambda m: m.get("date", ""), reverse=True)
        result = matches[:last_n]
        self._save_cache(cache_key, {"fixtures": result})
        return result

    def _scoreboard_for_date(self, date_str: str) -> dict | None:
        """One day's scoreboard, fetched at most once per process.

        Returns None when the day cannot be fetched. A failed day is memoised
        as well: a date ESPN will not serve is not going to start serving it
        because a second player asked, and retrying it once per player is how a
        slate of twenty players turns one bad day into twenty stalled requests.
        """
        key = (self.sport, self.league, date_str)
        with _SCOREBOARD_MEMO_LOCK:
            if key in _SCOREBOARD_MEMO:
                return _SCOREBOARD_MEMO[key]
        try:
            data = self._request("/scoreboard", params={"dates": date_str})
        except Exception:  # noqa: BLE001 - a missing day is a gap, never fatal
            data = None
        with _SCOREBOARD_MEMO_LOCK:
            _SCOREBOARD_MEMO[key] = data
        return data

    def get_standings(self) -> list[dict]:
        """Get league standings/table."""
        cache_key = f"espn/{self.sport}/{self.league}/standings"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("standings", [])

        try:
            # v2 standings API works for ALL sports (soccer, basketball, hockey, etc.)
            url = f"https://site.api.espn.com/apis/v2/sports/{self._espn_sport}/{self.league}/standings"
            response = requests.get(url, headers=self._build_headers(), timeout=self.TIMEOUT)
            data = response.json()
        except Exception:
            return []

        standings = []
        for child in data.get("children", data.get("standings", [])):
            if isinstance(child, dict):
                entries = child.get("standings", {}).get("entries", [])
                if not entries:
                    entries = child.get("entries", [])
                for entry in entries:
                    team = entry.get("team", {})
                    stats_list = entry.get("stats", [])
                    stat_dict = {}
                    for s in stats_list:
                        stat_dict[s.get("name", "")] = s.get("value", s.get("displayValue", ""))
                    standings.append({
                        "team_id": str(team.get("id", "")),
                        "team_name": team.get("displayName", ""),
                        "rank": stat_dict.get("rank", ""),
                        "wins": stat_dict.get("wins", ""),
                        "losses": stat_dict.get("losses", ""),
                        "draws": stat_dict.get("ties", stat_dict.get("draws", "")),
                        "points": stat_dict.get("points", ""),
                        "gamesPlayed": stat_dict.get("gamesPlayed", ""),
                    })

        self._save_cache(cache_key, {"standings": standings})
        return standings

    def get_standings_result(self) -> SourceOperationResult[list[dict]]:
        """Get league standings with typed result for capability router.

        Returns SourceOperationResult with:
        - status: SUCCESS, NOT_FOUND, etc.
        - value: list of standings dicts
        - evidence_refs: list of evidence references
        """
        cache_key = f"espn/{self.sport}/{self.league}/standings"
        payload_result = self._request_payload_result(
            endpoint="/standings",
            params=None,
            operation="standings",
            cache_key=cache_key,
            ttl_hours=12,
        )
        if payload_result.status is not SourceResultStatus.SUCCESS or payload_result.value is None:
            return SourceOperationResult(
                status=payload_result.status,
                http_status=payload_result.http_status,
                retryable=payload_result.retryable,
                error_code=payload_result.error_code,
                retry_after_seconds=payload_result.retry_after_seconds,
                evidence_refs=payload_result.evidence_refs,
            )

        data = payload_result.value
        standings = []
        raw_children = data.get("children", data.get("standings", []))
        for child in raw_children:
            if not isinstance(child, dict):
                continue
            entries = child.get("standings", {}).get("entries", [])
            if not entries:
                entries = child.get("entries", [])
            for entry in entries:
                team = entry.get("team", {})
                stats_list = entry.get("stats", [])
                stat_dict = {}
                for stat in stats_list:
                    stat_dict[stat.get("name", "")] = stat.get(
                        "value", stat.get("displayValue", "")
                    )
                standings.append(
                    {
                        "team_id": str(team.get("id", "")),
                        "team_name": team.get("displayName", ""),
                        "rank": stat_dict.get("rank", ""),
                        "wins": stat_dict.get("wins", ""),
                        "losses": stat_dict.get("losses", ""),
                        "draws": stat_dict.get("ties", stat_dict.get("draws", "")),
                        "points": stat_dict.get("points", ""),
                        "gamesPlayed": stat_dict.get("gamesPlayed", ""),
                    }
                )

        if not standings:
            return SourceOperationResult(
                SourceResultStatus.NOT_FOUND,
                http_status=payload_result.http_status,
                error_code="standings_empty",
                evidence_refs=payload_result.evidence_refs,
            )

        bundle_id = ""
        if payload_result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_standings",
                    request_identity=payload_result.evidence_refs[0].request_identity,
                    parser_version=ESPN_PARSER_VERSION,
                    source_event_refs=[],
                    evidence_refs=payload_result.evidence_refs,
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=payload_result.http_status,
                    error_code="bundle_manifest_failed",
                    evidence_refs=payload_result.evidence_refs,
                )

        self._save_cache(cache_key, {"standings": standings})
        return SourceOperationResult(
            SourceResultStatus.SUCCESS,
            value=standings,
            bundle_id=bundle_id,
            evidence_refs=payload_result.evidence_refs,
            http_status=payload_result.http_status,
            parser_diagnostics={
                "raw_child_count": len(raw_children) if isinstance(raw_children, list) else 0,
                "accepted_count": len(standings),
            },
        )

    @staticmethod
    def extract_odds_from_event(event: dict) -> dict | None:
        """Extract DraftKings odds from an ESPN scoreboard event.

        Returns dict with moneyline, total, spread in American odds format.
        Returns None if no odds available.
        """
        competitions = event.get("competitions", [])
        if not competitions:
            return None

        odds_list = competitions[0].get("odds", [])
        if not odds_list:
            return None

        # Find DraftKings odds (usually first/only)
        odds_data = None
        for o in odds_list:
            if o is not None:
                odds_data = o
                break

        if not odds_data:
            return None

        result = {"provider": "DraftKings", "source": "espn"}

        # Moneyline
        ml = odds_data.get("moneyline", {})
        if ml:
            result["moneyline"] = {
                "home": ml.get("home", {}).get("close", {}).get("odds", ""),
                "away": ml.get("away", {}).get("close", {}).get("odds", ""),
                "draw": ml.get("draw", {}).get("close", {}).get("odds", ""),
            }
            result["moneyline_open"] = {
                "home": ml.get("home", {}).get("open", {}).get("odds", ""),
                "away": ml.get("away", {}).get("open", {}).get("odds", ""),
                "draw": ml.get("draw", {}).get("open", {}).get("odds", ""),
            }

        # Totals (over/under)
        total = odds_data.get("total", {})
        if total:
            result["total"] = {
                "line": odds_data.get("overUnder", ""),
                "over_odds": total.get("over", {}).get("close", {}).get("odds", ""),
                "under_odds": total.get("under", {}).get("close", {}).get("odds", ""),
            }

        # Spread / Point Spread
        spread = odds_data.get("pointSpread", {})
        if spread:
            result["spread"] = {
                "home_line": spread.get("home", {}).get("close", {}).get("line", ""),
                "home_odds": spread.get("home", {}).get("close", {}).get("odds", ""),
                "away_line": spread.get("away", {}).get("close", {}).get("line", ""),
                "away_odds": spread.get("away", {}).get("close", {}).get("odds", ""),
            }

        return result

    @staticmethod
    def extract_form_and_records(event: dict) -> dict:
        """Extract team form strings and records from scoreboard event."""
        result = {}
        competitions = event.get("competitions", [])
        if not competitions:
            return result

        for comp in competitions[0].get("competitors", []):
            side = comp.get("homeAway", "")
            team = comp.get("team", {})
            team_name = team.get("displayName", "")
            form = comp.get("form", "")
            records = comp.get("records", [])

            record_summary = ""
            for r in records:
                if r.get("type") == "total":
                    record_summary = r.get("summary", "")
                    break

            if team_name:
                result[side] = {
                    "team": team_name,
                    "form": form,
                    "record": record_summary,
                }

        return result

    def get_cross_competition_schedule(
        self, team_id: str, future_only: bool = False
    ) -> list[dict]:
        """Get all-competition schedule for a team (soccer only).

        Uses soccer/all/teams/{id}/schedule endpoint.
        Returns matches across ALL competitions (league + cups + continental).
        """
        if self.sport != "football":
            return []

        cache_key = f"espn/{self.sport}/all/cross_schedule/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("events", [])

        params = {}
        if future_only:
            params["fixture"] = "true"

        try:
            url = f"{self.ESPN_BASE}/soccer/all/teams/{team_id}/schedule"
            response = requests.get(
                url, params=params, headers=self._build_headers(), timeout=self.TIMEOUT
            )
            if response.status_code >= 400:
                return []
            data = response.json()
        except Exception:
            return []

        events = []
        for event in data.get("events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            home_name = ""
            away_name = ""
            score = ""
            for c in competitors:
                t = c.get("team", {})
                if c.get("homeAway") == "home":
                    home_name = t.get("displayName", "")
                    score = str(c.get("score", ""))
                else:
                    away_name = t.get("displayName", "")
                    score = f"{score}-{c.get('score', '')}"

            events.append({
                "id": event.get("id"),
                "date": event.get("date", ""),
                "name": event.get("name", ""),
                "home_team": home_name,
                "away_team": away_name,
                "score": score,
                "league": event.get("league", {}).get("abbreviation", ""),
            })

        self._save_cache(cache_key, {"events": events})
        return events

    def get_coaches(self, season_year: int | None = None) -> list[dict]:
        """Get coaching staff for the league/season.

        URL: https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/coaches

        Returns list of: {id, name, team, record, experience_years}
        Note: Only works for US sports (NBA, NHL). Soccer returns HTTP 500.
        """
        import time as _time

        year = season_year or datetime.now().year
        cache_key = f"espn/{self.sport}/{self.league}/seasons/{year}/coaches"
        try:
            cached = self._check_cache(cache_key, ttl_hours=24)
            if cached is not None:
                return cached.get("coaches", [])
        except (ValueError, OSError):
            pass

        url = f"https://sports.core.api.espn.com/v2/sports/{self._espn_sport}/leagues/{self.league}/seasons/{year}/coaches"
        data = self._core_request(url)
        if not data:
            return []

        coaches = []
        failed = 0
        for item in data.get("items", []):
            coach_url = item.get("$ref", "")
            if not coach_url:
                continue
            coach_url = coach_url.replace("http://", "https://")
            coach_data = self._core_request(coach_url)
            if coach_data:
                coaches.append({
                    "id": coach_data.get("id"),
                    "name": f"{coach_data.get('firstName', '')} {coach_data.get('lastName', '')}".strip(),
                    "experience_years": coach_data.get("experience", 0),
                })
            else:
                failed += 1
            _time.sleep(0.1)  # avoid hammering ESPN

        if failed == 0:
            self._save_cache(cache_key, {"coaches": coaches})
        return coaches

    def get_coach_record(self, coach_id: str | int, record_type: int = 0) -> dict:
        """Get coaching record by type.

        URL: https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/coaches/{coachId}/record/{type}
        record_type: 0=Total, 1=Home, 2=Away (numeric IDs)

        Returns: {name, summary, win_pct, stats: {...}}
        """
        coach_id = str(coach_id)
        cache_key = f"espn/{self.sport}/{self.league}/coaches/{coach_id}/record/{record_type}"
        try:
            cached = self._check_cache(cache_key, ttl_hours=24)
            if cached is not None:
                return cached.get("record", {})
        except (ValueError, OSError):
            pass

        url = f"https://sports.core.api.espn.com/v2/sports/{self._espn_sport}/leagues/{self.league}/coaches/{coach_id}/record/{record_type}"
        data = self._core_request(url)
        if not data:
            return {}

        # Parse stats array into dict
        stats_dict = {}
        for stat in data.get("stats", []):
            name = stat.get("name", "")
            if name:
                stats_dict[name] = stat.get("value", stat.get("displayValue", ""))

        record = {
            "name": data.get("name", ""),
            "summary": data.get("summary", ""),
            "win_pct": data.get("value", 0.0),
            "stats": stats_dict,
        }

        self._save_cache(cache_key, {"record": record})
        return record

    def get_play_by_play(self, event_id: str, limit: int = 300) -> list[dict]:
        """Get play-by-play data for a match.

        URL: https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{event_id}/competitions/{event_id}/plays?limit={limit}

        For soccer: goals, cards, corners, substitutions with timestamps
        For basketball: shots, rebounds, assists with quarter/time
        For hockey: goals, penalties, shots with period/time

        Returns list of: {id, type, text, clock, period, team, athlete}
        """
        cache_key = f"espn/{self.sport}/{self.league}/events/{event_id}/plays"
        try:
            cached = self._check_cache(cache_key, ttl_hours=168)
            if cached is not None:
                return cached.get("plays", [])
        except (ValueError, OSError):
            pass

        url = f"https://sports.core.api.espn.com/v2/sports/{self._espn_sport}/leagues/{self.league}/events/{event_id}/competitions/{event_id}/plays"
        try:
            response = requests.get(url, params={"limit": limit}, headers=self._build_headers(), timeout=self.TIMEOUT)
            if response.status_code >= 400:
                return []
            data = response.json()
        except requests.exceptions.RequestException:
            return []

        plays = []
        for item in data.get("items", []):
            plays.append({
                "id": item.get("id"),
                "type": item.get("type", {}).get("text", ""),
                "text": item.get("text", ""),
                "clock": item.get("clock", {}).get("displayValue", ""),
                "period": item.get("period", {}).get("number", 0),
                "team": item.get("team", {}).get("$ref", ""),
                "athlete": item.get("participants", [{}])[0].get("athlete", {}).get("$ref", "") if item.get("participants") else "",
            })

        self._save_cache(cache_key, {"plays": plays})
        return plays

    def get_cdn_game_package(self, game_id: str) -> dict:
        """Get full game package via CDN (boxscore + plays + odds + matchup in one call).

        URL: https://cdn.espn.com/core/{sport}/game?xhr=1&gameId={game_id}

        For soccer, also needs &league={league} parameter.
        Returns: dict with 'gamepackageJSON' containing boxscore, plays, odds, matchup data.
        Note: CDN endpoint may be unreliable (redirects/HTML). Falls back gracefully.
        """
        cache_key = f"espn/cdn/{self.sport}/{self.league}/game/{game_id}"
        try:
            cached = self._check_cache(cache_key, ttl_hours=6)
            if cached is not None:
                return cached.get("package", {})
        except (ValueError, OSError):
            pass

        # CDN uses league slug (nba, nhl) not sport slug (basketball, hockey)
        cdn_sport = self.league if self.sport != "football" else self._espn_sport
        url = f"https://cdn.espn.com/core/{cdn_sport}/game"
        params = {"xhr": "1", "gameId": game_id}
        if self._espn_sport == "soccer":
            params["league"] = self.league

        try:
            response = requests.get(
                url, params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Referer": "https://www.espn.com/",
                },
                timeout=self.TIMEOUT,
                allow_redirects=True,
            )
            if response.status_code >= 400:
                return {}
            # CDN may return HTML instead of JSON — check content type
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type and "javascript" not in content_type:
                return {}
            data = response.json()
        except (requests.exceptions.RequestException, ValueError):
            return {}

        self._save_cache(cache_key, {"package": data})
        return data

    def _core_request(self, url: str) -> dict:
        """Make a request to a full URL (Core API) with retry and backoff.

        Unlike self._request() which prepends base_url, this accepts a complete URL.
        Used for sports.core.api.espn.com endpoints and $ref resolution.
        """
        import time as _time

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=self._build_headers(), timeout=self.TIMEOUT)
                if response.status_code == 404:
                    return {}
                if response.status_code >= 400:
                    if attempt < self.MAX_RETRIES:
                        _time.sleep(self.BACKOFF_BASE * (2 ** (attempt - 1)))
                        continue
                    return {}
                return response.json()
            except requests.exceptions.RequestException:
                if attempt < self.MAX_RETRIES:
                    _time.sleep(self.BACKOFF_BASE * (2 ** (attempt - 1)))
        return {}


# Latin letters Unicode gives no NFKD decomposition, mapped to the ASCII form
# ESPN's own feeds use. Keyed on the casefolded character, since the fold
# casefolds first -- ``ß`` and ``İ`` are already handled there (``ß`` casefolds
# to ``ss``, ``İ`` to ``i`` plus a combining dot the fold strips) and are listed
# only so a reader does not have to rediscover why they are missing.
_NO_NFKD_DECOMPOSITION = str.maketrans(
    {
        # Nordic. ESPN writes Bodo/Glimt, Brondby, Tromso.
        "ø": "o",
        "æ": "ae",
        # Icelandic/Faroese.
        "þ": "th",
        "ð": "d",
        # Polish. ESPN has no pol.1 team directory today, but the same names
        # reach the tennis routes, which this fold also serves.
        "ł": "l",
        # Croatian, Serbian-Latin, Vietnamese.
        "đ": "d",
        # Turkish dotless i: Sivasspor, Karagümrük, Basaksehir all carry it in
        # the endonym and none of them in ESPN's spelling.
        "ı": "i",
        # French/Latin ligature.
        "œ": "oe",
    }
)


def _fold_espn_participant_name(name: str) -> str:
    """Case-, accent- and separator-insensitive form of a team or player name.

    Both sides of every name comparison go through this, because the feed and
    ESPN disagree on all three routinely. Measured against the 2026-08-28 slate
    with the leagues correctly pinned, bare ``.lower()`` matching lost:

      Al-Hilal / Al-Nassr / Al-Riyadh / Al-Fayha / Al-Khaleej / Al-Taawoun
                              ESPN writes these with a space, not a hyphen --
                              five Saudi fixtures, no team resolved
      Paris Saint Germain     ESPN writes "Paris Saint-Germain"
      VfL Osnabrück           ESPN writes "VfL Osnabruck"
      Gençlerbirliği          ESPN writes "Genclerbirligi"
      Anna Bondár             ESPN writes "Anna Bondar" -- ESPN's own search
                              returns the right player for the accented query
                              and the comparison then threw the answer away

    Every one of those surfaced as "could not resolve team identity for
    '<name>'", i.e. as a fuzzy-matching problem with the name, which is the
    same misdirection a wrong league pin produces.

    ``_NO_NFKD_DECOMPOSITION`` is applied before the normalisation because NFKD
    does not touch those letters and the strip below then turned each one into
    a **space**. That is worse than leaving an accent on: it splits one token
    into two, so the name stops matching even a correct spelling of itself.
    Measured on the 2026-09-04 slate, ``Bodø/Glimt`` folded to ``bod glimt``
    while ESPN's own directory spells it ``Bodo/Glimt`` -> ``bodo glimt``, and
    Fredrikstad - Bodø/Glimt came back "could not resolve team identity" with
    12 metrics on one side and 0 on the other. ESPN's spelling *is* what a
    correct fold produces, which is what makes this a fold bug rather than an
    alias question.

    These are letters, not accented vowels -- Unicode defines no decomposition
    for them on purpose -- so each needs the transliteration its own language
    uses. ``å``, ``ö``, ``ü``, ``ş``, ``ğ``, ``ç`` and the Polish acutes are
    absent from the table because they *do* decompose and already fold
    correctly; adding them would be a second, disagreeing copy of NFKD.
    """
    folded = unicodedata.normalize("NFKD", name.casefold().translate(_NO_NFKD_DECOMPOSITION))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def _espn_athlete_name_matches(requested: str, claimed: str) -> bool:
    """Is ESPN's ``claimed`` athlete name the player we asked for?

    Delegates to tennis_abstract.identity_matches so both tennis providers
    judge identity by one rule: ASCII-folded token *equality*, order-free
    ("Qinwen Zheng" / ESPN's "Zheng Qinwen"), plus the forename-initial rule.

    Deliberately not a substring or similarity test. Every crossing measured on
    the 2026-08-28 slate came from one: 'henri' inside 'henrique',
    'alexandra' shared by Eala and Wolf, 'anna' shared by Kalinskaya and
    Grigoreva. A name test that accepts a shared forename is not a name test.
    """
    if not requested or not claimed:
        return False
    from bet.api_clients.tennis_abstract import identity_matches

    return identity_matches(requested, claimed)


def get_espn_league_for_competition(competition_name: str) -> str | None:
    """Resolve a competition name to an ESPN league code, or None.

    None is a valid, common and *safe* answer. Callers must treat it as "ESPN
    cannot cover this competition" and drop the provider, never as "try the
    default league": see ProviderLeagueUnsupported in simple_stats/providers.py
    for what the default-league fallback used to cost.
    """
    if not competition_name:
        return None

    signature = _espn_name_signature(competition_name)
    if not signature:
        return None

    # An explicit tour marker outranks the table, because it is the one piece
    # of tennis information the feed states outright. Both markers at once
    # ("ATP/WTA Mixed") names no single tour, so it resolves to nothing.
    tours = signature & _ESPN_TENNIS_TOURS
    if len(tours) == 1:
        return next(iter(tours))
    if tours:
        return None

    authored = _ESPN_SIGNATURE_TO_LEAGUE.get(signature)
    if authored is not None:
        return authored

    # Last: a gendered tennis draw. Checked after the authored table so that
    # "Women's Super League" is answered as football before the word "women"
    # can be read as a tour, and gated on a tennis tier token so that only a
    # name already saying "grand slam" / "challenger" / "ITF" is eligible.
    # A draw that names neither tour nor gender ("Kingston 2, Jamaica
    # (challenger)") stays None on purpose: None drops the provider, and
    # dropping it costs one source where guessing costs another player's
    # history filed under this one's name.
    if signature & _ESPN_TENNIS_TIER_TOKENS:
        genders = {_ESPN_TENNIS_GENDER_TOURS[t] for t in signature if t in _ESPN_TENNIS_GENDER_TOURS}
        if len(genders) == 1:
            return next(iter(genders))

    return None
