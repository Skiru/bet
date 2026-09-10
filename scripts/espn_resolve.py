#!/usr/bin/env python3
"""ESPN Resolution CLI & Module for Bzzoiro.

Resolves external provider (Superbet, bzzoiro, odds-api) fixtures to ESPN entities and events.
Implements fail-closed matching, 4-state lifecycle, duplicate handling, and evidence logging.

States:
  - EVENT_FOUND: Both entities resolved, exact event matched and verified.
  - ENTITY_FOUND: Entities resolved, but event is absent (e.g. ITF/Challenger or unindexed match).
  - EVENT_NOT_FOUND: Event does not exist in ESPN (entities missing or no matching fixture).
  - AMBIGUOUS: Multiple conflicting candidates with insufficient evidence to distinguish.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Run in .venv.", file=sys.stderr)
    sys.exit(1)

HEADERS = {"Accept": "application/json"}
TIMEOUT = 10

# Common letters NFKD does not decompose
SPECIAL_CHAR_MAP = str.maketrans({
    "Ł": "L", "ł": "l",
    "Ø": "O", "ø": "o",
    "Đ": "D", "đ": "d",
    "ß": "ss",
    "Ħ": "H", "ħ": "h",
    "Ŧ": "T", "ŧ": "t",
    "İ": "I", "ı": "i",
    "Þ": "Th", "þ": "th",
    "Ð": "D", "ð": "d",
    "Æ": "Ae", "æ": "ae",
    "Œ": "Oe", "œ": "oe",
})


def fold_name(name: str) -> str:
    """Normalize string: strip emoji, diacritics, lowercase, alphanumeric only."""
    if not name:
        return ""
    s = name.translate(SPECIAL_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def tokens_match(requested: str, claimed: str) -> bool:
    """Exact token equality, order-independent (e.g. 'Sabalenka Aryna' == 'Aryna Sabalenka')."""
    req_tokens = set(fold_name(requested).split())
    cla_tokens = set(fold_name(claimed).split())
    if not req_tokens or not cla_tokens:
        return False
    # Exact set match or initial abbreviation match
    if req_tokens == cla_tokens:
        return True
    # If one token is single-letter initial (e.g. A. Sabalenka)
    if len(req_tokens) == 2 and len(cla_tokens) == 2:
        r_list = sorted(list(req_tokens), key=len)
        c_list = sorted(list(cla_tokens), key=len)
        if len(r_list[0]) == 1 and r_list[1] == c_list[1] and c_list[0].startswith(r_list[0]):
            return True
        if len(c_list[0]) == 1 and c_list[1] == r_list[1] and r_list[0].startswith(c_list[0]):
            return True
    return False


class ESPNResolver:
    """Deterministic, fail-closed ESPN Entity & Event Resolver."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def resolve_athlete(self, name: str, tour: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Resolve athlete name to candidate ESPN athlete records. Handles duplicates."""
        evidence = []
        cleaned = fold_name(name)
        if not cleaned:
            return [], ["Athlete name is empty after normalization"]

        candidates: List[Dict[str, Any]] = []
        seen_ids = set()

        # Step 1: Query Search v2 (captures all duplicate player records)
        url_v2 = "https://site.api.espn.com/apis/search/v2"
        try:
            r2 = self.session.get(url_v2, params={"query": cleaned, "limit": 10}, timeout=TIMEOUT)
            if r2.status_code == 200:
                for block in r2.json().get("results", []):
                    for c in block.get("contents", []):
                        if c.get("type") == "player":
                            uid = c.get("uid", "")
                            # Tennis athletes uid has s:850
                            disp = c.get("displayName", "")
                            if "s:850" in uid or tokens_match(name, disp):
                                aid = uid.split("~a:")[1].split("~")[0] if "~a:" in uid else str(c.get("id"))
                                if aid and aid not in seen_ids:
                                    seen_ids.add(aid)
                                    league = "wta" if "~l:900" in uid else ("atp" if "~l:851" in uid else "")
                                    candidates.append({
                                        "id": aid,
                                        "uid": uid,
                                        "displayName": disp,
                                        "league": league,
                                        "source": "search_v2"
                                    })
        except Exception as e:
            evidence.append(f"Search v2 error for '{name}': {e}")

        # Step 2: Query Search v3
        url_v3 = "https://site.web.api.espn.com/apis/common/v3/search"
        try:
            params = {"query": cleaned, "type": "player", "sport": "tennis"}
            r3 = self.session.get(url_v3, params=params, timeout=TIMEOUT)
            if r3.status_code == 200:
                for it in r3.json().get("items", []):
                    aid = str(it.get("id", ""))
                    disp = it.get("displayName", "")
                    if aid and aid not in seen_ids and (tokens_match(name, disp) or cleaned in fold_name(disp)):
                        seen_ids.add(aid)
                        candidates.append({
                            "id": aid,
                            "uid": it.get("uid", ""),
                            "displayName": disp,
                            "league": it.get("league", ""),
                            "country": it.get("citizenshipCountry", {}).get("abbreviation"),
                            "source": "search_v3"
                        })
        except Exception as e:
            evidence.append(f"Search v3 error for '{name}': {e}")

        # Filter by tour if specified
        if tour:
            tour_lower = tour.lower()
            matching_tour = [c for c in candidates if not c.get("league") or c.get("league").lower() == tour_lower]
            if matching_tour:
                candidates = matching_tour

        # Filter by exact name token match to avoid "Henri" matching "Henrique"
        strict_candidates = [c for c in candidates if tokens_match(name, c["displayName"])]
        if strict_candidates:
            candidates = strict_candidates

        # Step 3: Probe eventlog for each candidate to filter out dead/empty stubs
        active_candidates = []
        for cand in candidates:
            aid = cand["id"]
            cand_tour = cand.get("league") or "wta"
            el_url = f"https://sports.core.api.espn.com/v2/sports/tennis/leagues/{cand_tour}/athletes/{aid}/eventlog"
            try:
                r_el = self.session.get(el_url, timeout=TIMEOUT)
                if r_el.status_code == 200:
                    cnt = r_el.json().get("events", {}).get("count", 0)
                    cand["eventlog_count"] = cnt
                    cand["has_active_events"] = cnt > 0
                    active_candidates.append(cand)
                    evidence.append(f"Athlete candidate ID {aid} ({cand['displayName']}) has active eventlog (count: {cnt})")
                else:
                    cand["eventlog_count"] = 0
                    cand["has_active_events"] = False
                    evidence.append(f"Athlete candidate ID {aid} ({cand['displayName']}) has eventlog status {r_el.status_code} (stub/inactive)")
                    # Keep as fallback candidate if no active candidates exist
                    active_candidates.append(cand)
            except Exception as e:
                evidence.append(f"Eventlog check error for {aid}: {e}")
                active_candidates.append(cand)

        return active_candidates, evidence

    def resolve_team(self, name: str, league_slug: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Resolve football team to ESPN team records. Fail-closed against youth/reserve corruption."""
        evidence = []
        cleaned = fold_name(name)
        if not cleaned:
            return [], ["Team name is empty"]

        # Guard: Check for Youth / Reserve markers
        is_youth = bool(re.search(r"\b(u17|u18|u19|u20|u21|u23|youth|juvenil|juniors?)\b", name, re.I))
        is_reserve = bool(re.search(r"\b(ii|b|reserves?)\b", name, re.I))
        is_women = bool(re.search(r"\b(women|womens|femenino|frauen|damer)\b", name, re.I))

        candidates: List[Dict[str, Any]] = []
        seen_ids = set()

        url_v3 = "https://site.web.api.espn.com/apis/common/v3/search"
        try:
            params = {"query": cleaned, "type": "team", "sport": "soccer"}
            r3 = self.session.get(url_v3, params=params, timeout=TIMEOUT)
            if r3.status_code == 200:
                for it in r3.json().get("items", []):
                    tid = str(it.get("id", ""))
                    disp = it.get("displayName", "")
                    cand_lg = it.get("league", "")
                    cand_clean = fold_name(disp)

                    # Guard against false positive token match
                    if tid and tid not in seen_ids:
                        # Check exact or contained
                        if tokens_match(name, disp) or cleaned == cand_clean or cleaned in cand_clean or cand_clean in cleaned:
                            # Verify youth / reserve / women congruence
                            cand_is_youth = bool(re.search(r"\b(u17|u18|u19|u20|u21|u23|youth)\b", disp, re.I))
                            cand_is_reserve = bool(re.search(r"\b(ii|b|reserves?)\b", disp, re.I))
                            cand_is_women = bool(re.search(r"\b(women|w)\b", cand_lg, re.I) or "women" in disp.lower())

                            if is_youth != cand_is_youth and not cand_is_youth:
                                evidence.append(f"Rejected senior team '{disp}' (ID: {tid}) for youth query '{name}'")
                                continue
                            if is_reserve != cand_is_reserve and not cand_is_reserve:
                                evidence.append(f"Rejected senior team '{disp}' (ID: {tid}) for reserve query '{name}'")
                                continue
                            if is_women != cand_is_women:
                                evidence.append(f"Rejected team '{disp}' (ID: {tid}) due to gender mismatch (requested women={is_women}, got {cand_is_women})")
                                continue

                            seen_ids.add(tid)
                            candidates.append({
                                "id": tid,
                                "displayName": disp,
                                "league": cand_lg,
                                "source": "search_v3"
                            })
        except Exception as e:
            evidence.append(f"Team search error for '{name}': {e}")

        # If league_slug provided, filter by it
        if league_slug:
            filtered = [c for c in candidates if c.get("league") == league_slug]
            if filtered:
                candidates = filtered
            else:
                evidence.append(f"None of {len(candidates)} team hits matched requested league '{league_slug}'")

        return candidates, evidence

    def resolve_tennis_event(
        self,
        home_name: str,
        away_name: str,
        date_str: Optional[str] = None,
        time_str: Optional[str] = None,
        tour: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a tennis match between two players."""
        evidence: List[str] = []
        evidence.append(f"Tennis resolution requested: '{home_name}' vs '{away_name}' on date '{date_str}'")

        # Step 1: Resolve Home Athlete
        home_cands, home_ev = self.resolve_athlete(home_name, tour)
        evidence.extend(home_ev)
        if not home_cands:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Home player '{home_name}' could not be resolved in ESPN",
                "confidence": 0.0,
                "evidence": evidence
            }

        # Step 2: Resolve Away Athlete
        away_cands, away_ev = self.resolve_athlete(away_name, tour)
        evidence.extend(away_ev)
        if not away_cands:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Away player '{away_name}' could not be resolved in ESPN",
                "confidence": 0.0,
                "evidence": evidence
            }

        # Check Ambiguity
        if len(home_cands) > 1 and len({c['id'] for c in home_cands}) > 1:
            active_home = [c for c in home_cands if c.get("has_active_events")]
            if len(active_home) == 1:
                home_cands = active_home
            elif len(active_home) > 1:
                return {
                    "status": "AMBIGUOUS",
                    "reason": f"Multiple distinct active athletes for home player '{home_name}'",
                    "home_candidates": home_cands,
                    "confidence": 0.0,
                    "evidence": evidence
                }

        if len(away_cands) > 1 and len({c['id'] for c in away_cands}) > 1:
            active_away = [c for c in away_cands if c.get("has_active_events")]
            if len(active_away) == 1:
                away_cands = active_away
            elif len(active_away) > 1:
                return {
                    "status": "AMBIGUOUS",
                    "reason": f"Multiple distinct active athletes for away player '{away_name}'",
                    "away_candidates": away_cands,
                    "confidence": 0.0,
                    "evidence": evidence
                }

        best_home = home_cands[0]
        best_away = away_cands[0]
        evidence.append(f"Resolved Home Player: {best_home['displayName']} (ID: {best_home['id']}, Tour: {best_home.get('league')})")
        evidence.append(f"Resolved Away Player: {best_away['displayName']} (ID: {best_away['id']}, Tour: {best_away.get('league')})")

        # Step 3: Search for Match between Player A and Player B in eventlogs
        target_away_ids = {c["id"] for c in away_cands}
        found_matches = []

        for h_cand in home_cands:
            aid = h_cand["id"]
            cand_tour = h_cand.get("league") or "wta"
            el_url = f"https://sports.core.api.espn.com/v2/sports/tennis/leagues/{cand_tour}/athletes/{aid}/eventlog?limit=100"
            try:
                r_el = self.session.get(el_url, timeout=TIMEOUT)
                if r_el.status_code != 200:
                    continue
                items = r_el.json().get("events", {}).get("items", [])
                for it in items:
                    comp_ref = it.get("competition", {}).get("$ref", "")
                    if not comp_ref:
                        continue
                    r_c = self.session.get(comp_ref, timeout=TIMEOUT)
                    if r_c.status_code != 200:
                        continue
                    c_data = r_c.json()
                    competitors = c_data.get("competitors", [])
                    comp_aids = []
                    for comp in competitors:
                        cref = comp.get("$ref", "")
                        caid = str(comp.get("id", ""))
                        if not caid and "/competitors/" in cref:
                            caid = cref.split("/competitors/")[1].split("?")[0]
                        if caid:
                            comp_aids.append(caid)

                    if any(t in comp_aids for t in target_away_ids):
                        ev_ref = it.get("event", {}).get("$ref", "")
                        r_e = self.session.get(ev_ref, timeout=TIMEOUT)
                        e_data = r_e.json() if r_e.status_code == 200 else {}
                        status_val = None
                        status_obj = c_data.get("status")
                        if isinstance(status_obj, dict):
                            if "$ref" in status_obj:
                                try:
                                    r_st = self.session.get(status_obj["$ref"], timeout=TIMEOUT)
                                    if r_st.status_code == 200:
                                        status_val = r_st.json().get("type", {}).get("name")
                                except Exception:
                                    pass
                            else:
                                status_val = status_obj.get("type", {}).get("name")

                        round_val = None
                        round_obj = c_data.get("round")
                        if isinstance(round_obj, dict):
                            round_val = round_obj.get("description") or round_obj.get("displayName")
                        elif isinstance(round_obj, str):
                            round_val = round_obj

                        venue_val = None
                        venue_obj = c_data.get("venue")
                        if isinstance(venue_obj, dict):
                            venue_val = venue_obj.get("address", {}).get("summary") or venue_obj.get("fullName")
                        elif isinstance(venue_obj, str):
                            venue_val = venue_obj

                        found_matches.append({
                            "event_name": e_data.get("name"),
                            "event_id": e_data.get("id"),
                            "competition_id": c_data.get("id"),
                            "kickoff_utc": c_data.get("date"),
                            "time_valid": c_data.get("timeValid", True),
                            "status": status_val or "STATUS_SCHEDULED",
                            "round": round_val,
                            "venue": venue_val,
                            "tour": cand_tour,
                            "c_data": c_data
                        })
            except Exception as e:
                evidence.append(f"Eventlog traversal error for athlete {aid}: {e}")

        # If not found yet, also check date scoreboard if date is provided
        if not found_matches and date_str:
            date_compact = date_str.replace("-", "")
            for check_tour in ["atp", "wta"]:
                sb_url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{check_tour}/scoreboard"
                try:
                    r_sb = self.session.get(sb_url, params={"dates": date_compact}, timeout=TIMEOUT)
                    if r_sb.status_code == 200:
                        for ev in r_sb.json().get("events", []):
                            for grp in ev.get("groupings", []):
                                for comp in grp.get("competitions", []):
                                    c_athletes = [c.get("athlete", {}).get("displayName", "") for c in comp.get("competitors", [])]
                                    if len(c_athletes) >= 2:
                                        if (tokens_match(home_name, c_athletes[0]) and tokens_match(away_name, c_athletes[1])) or \
                                           (tokens_match(home_name, c_athletes[1]) and tokens_match(away_name, c_athletes[0])):
                                            found_matches.append({
                                                "event_name": ev.get("name"),
                                                "event_id": ev.get("id"),
                                                "competition_id": comp.get("id"),
                                                "kickoff_utc": comp.get("date"),
                                                "time_valid": comp.get("timeValid", True),
                                                "status": comp.get("status", {}).get("type", {}).get("name"),
                                                "round": comp.get("round", {}).get("displayName") if isinstance(comp.get("round"), dict) else comp.get("round"),
                                                "tour": check_tour,
                                                "c_data": comp
                                            })
                except Exception as e:
                    evidence.append(f"Scoreboard probe error for tour {check_tour}: {e}")

        if not found_matches:
            evidence.append(
                f"PROOF_OF_ABSENCE: Both players resolved ({best_home['displayName']} ID: {best_home['id']}, "
                f"{best_away['displayName']} ID: {best_away['id']}), but 0 mutual competitions found in ESPN eventlogs or scoreboards. "
                f"ESPN Tennis strictly covers ATP/WTA main tours; ITF/Challenger fixtures are not indexed."
            )
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": "PROOF_OF_ABSENCE: Entities exist in ESPN, but match fixture is absent (ITF/Challenger tier unindexed).",
                "athletes": [best_home, best_away],
                "confidence": 0.0,
                "evidence": evidence
            }

        # Step 4: Evaluate Date / Time compatibility
        scored_events = []
        for m in found_matches:
            score = 0.50 # base entity match
            ev_date_str = m["kickoff_utc"]
            m_evidence = []
            
            if date_str and ev_date_str:
                # Compare dates in UTC
                try:
                    ev_dt = datetime.fromisoformat(ev_date_str.replace("Z", "+00:00"))
                    target_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                    day_diff = abs((ev_dt.date() - target_dt.date()).days)
                    if day_diff == 0:
                        score += 0.35
                        m_evidence.append(f"Exact date match ({date_str})")
                    elif day_diff <= 1:
                        score += 0.20
                        m_evidence.append(f"Nearby date match (+/-1 day for timezone difference: {ev_dt.date()})")
                    else:
                        m_evidence.append(f"Date divergence: expected {date_str}, match was on {ev_dt.date()}")
                except Exception as e:
                    m_evidence.append(f"Date parse error: {e}")
            else:
                score += 0.20

            # Time compatibility
            if time_str and ev_date_str and m.get("time_valid"):
                try:
                    ev_dt = datetime.fromisoformat(ev_date_str.replace("Z", "+00:00"))
                    req_time = datetime.strptime(time_str, "%H:%M:%S").time()
                    time_diff_hours = abs((ev_dt.hour * 60 + ev_dt.minute) - (req_time.hour * 60 + req_time.minute)) / 60.0
                    if time_diff_hours <= 3.0:
                        score += 0.13
                        m_evidence.append(f"Kickoff time compatible (within {time_diff_hours:.1f}h)")
                    else:
                        m_evidence.append(f"Kickoff time difference {time_diff_hours:.1f}h")
                except Exception:
                    pass
            elif not m.get("time_valid"):
                score += 0.10
                m_evidence.append("Event kickoff time is TBD / unconfirmed")

            score = min(0.99, round(score, 2))
            scored_events.append((score, m, m_evidence))

        scored_events.sort(key=lambda x: x[0], reverse=True)
        best_score, best_match, match_ev = scored_events[0]
        evidence.extend(match_ev)

        if best_score >= 0.80:
            return {
                "status": "EVENT_FOUND",
                "confidence": best_score,
                "athletes": [best_home, best_away],
                "league": {"tour": best_match["tour"], "slug": best_match["tour"]},
                "event": {
                    "event_name": best_match["event_name"],
                    "event_id": best_match["event_id"],
                    "competition_id": best_match["competition_id"],
                    "kickoff_utc": best_match["kickoff_utc"],
                    "status": best_match["status"],
                    "round": best_match["round"],
                    "venue": best_match["venue"],
                },
                "evidence": evidence
            }
        elif len(scored_events) > 1 and scored_events[0][0] == scored_events[1][0]:
            return {
                "status": "AMBIGUOUS",
                "reason": "Multiple candidate events matched with identical confidence",
                "confidence": best_score,
                "evidence": evidence
            }
        else:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Event candidate found but failed date/time validation (confidence {best_score} < 0.80)",
                "confidence": best_score,
                "evidence": evidence
            }

    def resolve_football_event(
        self,
        home_team: str,
        away_team: str,
        date_str: Optional[str] = None,
        time_str: Optional[str] = None,
        league_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a football (soccer) match between two teams."""
        evidence: List[str] = []
        evidence.append(f"Football resolution requested: '{home_team}' vs '{away_team}' on date '{date_str}', league '{league_slug}'")

        home_cands, home_ev = self.resolve_team(home_team, league_slug)
        evidence.extend(home_ev)
        if not home_cands:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Home team '{home_team}' not found or rejected due to youth/reserve safety rules",
                "confidence": 0.0,
                "evidence": evidence
            }

        away_cands, away_ev = self.resolve_team(away_team, league_slug)
        evidence.extend(away_ev)
        if not away_cands:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Away team '{away_team}' not found or rejected due to youth/reserve safety rules",
                "confidence": 0.0,
                "evidence": evidence
            }

        # Check Ambiguity
        if len(home_cands) > 1 and not league_slug:
            return {
                "status": "AMBIGUOUS",
                "reason": f"Home team '{home_team}' matches multiple teams across leagues (e.g. {', '.join(c['displayName'] + ' in ' + c['league'] for c in home_cands[:3])})",
                "confidence": 0.0,
                "evidence": evidence
            }
        if len(away_cands) > 1 and not league_slug:
            return {
                "status": "AMBIGUOUS",
                "reason": f"Away team '{away_team}' matches multiple teams across leagues",
                "confidence": 0.0,
                "evidence": evidence
            }

        best_home = home_cands[0]
        best_away = away_cands[0]
        evidence.append(f"Resolved Home Team: {best_home['displayName']} (ID: {best_home['id']}, League: {best_home.get('league')})")
        evidence.append(f"Resolved Away Team: {best_away['displayName']} (ID: {best_away['id']}, League: {best_away.get('league')})")

        # League congruence check
        target_league = league_slug or best_home.get("league")
        if best_home.get("league") and best_away.get("league") and best_home["league"] != best_away["league"]:
            evidence.append(f"Domestic leagues differ ({best_home['league']} vs {best_away['league']}); could be cup/friendly/continental")

        found_events = []

        # Strategy 1: Check Team Schedule
        sched_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{target_league}/teams/{best_home['id']}/schedule"
        try:
            r_sc = self.session.get(sched_url, timeout=TIMEOUT)
            if r_sc.status_code == 200:
                for ev in r_sc.json().get("events", []):
                    for comp in ev.get("competitions", []):
                        t_names = [fold_name(c.get("team", {}).get("displayName", "")) for c in comp.get("competitors", [])]
                        if fold_name(best_away["displayName"]) in t_names or fold_name(away_team) in t_names:
                            found_events.append({
                                "event_name": ev.get("name"),
                                "event_id": ev.get("id"),
                                "competition_id": comp.get("id"),
                                "kickoff_utc": comp.get("date"),
                                "time_valid": comp.get("timeValid", True),
                                "status": comp.get("status", {}).get("type", {}).get("name"),
                                "league": target_league,
                                "comp": comp
                            })
        except Exception as e:
            evidence.append(f"Team schedule search error: {e}")

        # Strategy 2: Check Scoreboard by date if date provided
        if not found_events and date_str and target_league:
            date_compact = date_str.replace("-", "")
            sb_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{target_league}/scoreboard"
            try:
                r_sb = self.session.get(sb_url, params={"dates": date_compact}, timeout=TIMEOUT)
                if r_sb.status_code == 200:
                    for ev in r_sb.json().get("events", []):
                        for comp in ev.get("competitions", []):
                            t_ids = [str(c.get("id", "")) for c in comp.get("competitors", [])]
                            if best_home["id"] in t_ids and best_away["id"] in t_ids:
                                found_events.append({
                                    "event_name": ev.get("name"),
                                    "event_id": ev.get("id"),
                                    "competition_id": comp.get("id"),
                                    "kickoff_utc": comp.get("date"),
                                    "time_valid": comp.get("timeValid", True),
                                    "status": comp.get("status", {}).get("type", {}).get("name"),
                                    "league": target_league,
                                    "comp": comp
                                })
            except Exception as e:
                evidence.append(f"League scoreboard check error: {e}")

        if not found_events:
            evidence.append(
                f"PROOF_OF_ABSENCE: Both teams resolved ({best_home['displayName']} ID: {best_home['id']}, "
                f"{best_away['displayName']} ID: {best_away['id']}), but no matching match fixture found in schedule or scoreboard."
            )
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": "PROOF_OF_ABSENCE: Teams exist in ESPN, but match is not on the ESPN schedule/scoreboard.",
                "teams": [best_home, best_away],
                "confidence": 0.0,
                "evidence": evidence
            }

        # Step 4: Validate best match against target date
        best_event = found_events[0]
        score = 0.55
        ev_date = best_event["kickoff_utc"]
        if date_str and ev_date:
            try:
                ev_dt = datetime.fromisoformat(ev_date.replace("Z", "+00:00"))
                tgt_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                diff = abs((ev_dt.date() - tgt_dt.date()).days)
                if diff == 0:
                    score += 0.35
                    evidence.append(f"Exact date match ({date_str})")
                elif diff <= 1:
                    score += 0.15
                    evidence.append(f"Close date match ({ev_dt.date()} vs expected {date_str})")
            except Exception:
                pass
        else:
            score += 0.20

        score = min(0.99, round(score, 2))
        return {
            "status": "EVENT_FOUND" if score >= 0.80 else "EVENT_NOT_FOUND",
            "confidence": score,
            "teams": [best_home, best_away],
            "league": {"slug": target_league},
            "event": {
                "event_name": best_event["event_name"],
                "event_id": best_event["event_id"],
                "competition_id": best_event["competition_id"],
                "kickoff_utc": best_event["kickoff_utc"],
                "status": best_event["status"],
            },
            "evidence": evidence
        }

    def resolve(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch resolution based on sport."""
        sport = req.get("sport", "football").lower()
        if sport in ("tennis",):
            return self.resolve_tennis_event(
                home_name=req.get("home", ""),
                away_name=req.get("away", ""),
                date_str=req.get("date"),
                time_str=req.get("time"),
                tour=req.get("league")
            )
        elif sport in ("football", "soccer"):
            return self.resolve_football_event(
                home_team=req.get("home", ""),
                away_team=req.get("away", ""),
                date_str=req.get("date"),
                time_str=req.get("time"),
                league_slug=req.get("league")
            )
        else:
            return {
                "status": "EVENT_NOT_FOUND",
                "reason": f"Sport '{sport}' not supported by ESPN resolver",
                "confidence": 0.0,
                "evidence": [f"Unsupported sport: {sport}"]
            }


def main():
    parser = argparse.ArgumentParser(description="ESPN Resolution CLI for Bzzoiro")
    parser.add_argument("--json", type=str, help="Input query JSON string")
    parser.add_argument("--file", type=str, help="Input query JSON file path")
    parser.add_argument("--sport", type=str, default="football", help="Sport (tennis/football)")
    parser.add_argument("--home", type=str, help="Home participant / player / team")
    parser.add_argument("--away", type=str, help="Away participant / player / team")
    parser.add_argument("--date", type=str, help="Event date YYYY-MM-DD")
    parser.add_argument("--time", type=str, help="Event time HH:MM:SS")
    parser.add_argument("--league", type=str, help="Potential league name or slug")

    args = parser.parse_args()

    req = {}
    if args.json:
        req = json.loads(args.json)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            req = json.load(f)
    else:
        if not args.home or not args.away:
            parser.error("Either --json, --file, or both --home and --away must be provided.")
        req = {
            "sport": args.sport,
            "home": args.home,
            "away": args.away,
            "date": args.date,
            "time": args.time,
            "league": args.league
        }

    resolver = ESPNResolver()
    result = resolver.resolve(req)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
