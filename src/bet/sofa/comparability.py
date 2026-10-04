"""Is a past match comparable to the fixture? One answer for every reader.

2026-10-04, SC Farense - Chaves (goals_total UNDER 3.5 @1.29, lost 0-4 the
other way): the two ten-match samples held a pre-season tournament
("Torneio de Verao Povoa de Varzim", uniqueTournament 36573, not on the
friendly list), both legs of Farense's previous-season relegation play-off
and two cup ties against amateur sides - and every one of them entered as an
ordinary league match. The audit that followed found eight different
"does this match count" rules (samples, rating, cache replay, player model,
shadow sports, tennis, CS2), none of which read the round.

This module is where that question is answered:

* ``match_kind(event)`` - what kind of match a Sofascore event is:
  FRIENDLY (the reviewed id list in config/sofa_friendly_competitions.json,
  the football list keyed on the id because names are localised),
  KNOCKOUT (a cup round, a play-off, a qualifier: ``roundInfo.name`` /
  ``roundInfo.cupRoundType`` / a play-off stage name) or REGULAR (a league
  round). Measured on 959,985 cached finished football events: a league
  round carries no ``roundInfo.name`` (median share 0.08% over 1,023
  leagues, 98% of them at or below 20%), a cup round does ("Round 2",
  "Quarterfinals", "Final").
* ``is_friendly_event(event, sport)`` - the one exclusion every history
  reader applies. Football reads the id list; the other sports read their
  own ids from the same file plus the name markers below, because their
  friendlies are named consistently ("Club Friendly Games", "NHL Preseason",
  "Exhibition" as the tennis category).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from bet.sofa.config import config_path

FRIENDLIES_PATH = config_path("sofa_friendly_competitions.json")


class MatchKind(StrEnum):
    REGULAR = "REGULAR"
    KNOCKOUT = "KNOCKOUT"
    FRIENDLY = "FRIENDLY"


def _ids(entries: object) -> frozenset[int]:
    out: set[int] = set()
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("competition_id"), int):
            out.add(entry["competition_id"])
        elif isinstance(entry, int):
            out.add(entry)
    return frozenset(out)


def _load() -> tuple[frozenset[int], dict[str, frozenset[int]]]:
    """(football excluded ids, {sport: excluded ids}) from the config.

    A missing or malformed config degrades to "exclude nothing" rather than
    crashing; run_samples reports the size of the football set, so an empty
    filter is visible.
    """
    try:
        raw = json.loads(FRIENDLIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset(), {}
    if not isinstance(raw, dict):
        return frozenset(), {}
    other = raw.get("excluded_other_sports")
    by_sport = (
        {str(k): _ids(v) for k, v in other.items()} if isinstance(other, dict) else {}
    )
    return _ids(raw.get("excluded")), by_sport


FRIENDLY_COMPETITION_IDS, OTHER_SPORT_FRIENDLY_IDS = _load()

# Names that say "not a competitive match" in every language Sofascore uses
# for these sports. Applied to the sports other than football, where the
# names are consistent; football stays on its reviewed id list (852 is
# friendly-named and kept on purpose, see the config's `allowed`).
_NON_COMPETITIVE = re.compile(
    r"\b(friendl(y|ies)|pre-?season|exhibition|showmatch|show match|legends|"
    r"all-?star|summer league|testimonial)\b"
)
# Tennis files exhibitions and legends events under their own category.
_TENNIS_NON_COMPETITIVE_CATEGORIES = frozenset({"exhibition", "legends"})

# A stage of a league that is not a league round. "Relegation Round" and
# "Championship Round" are the regular split phases of a league (Scotland,
# Belgium, Austria) and are NOT here.
_PLAYOFF_STAGE = re.compile(
    r"(play-?offs?|relegation/promotion|promotion/relegation|baraj|barrage|"
    r"repechage|mata-mata|knockout|qualification|qualifying|eliminat)"
)


def fold(text: object) -> str:
    """Casefolded, accent-free text."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _tournament(event: Mapping[str, Any]) -> Mapping[str, Any]:
    t = event.get("tournament")
    return t if isinstance(t, Mapping) else {}


def _unique(event: Mapping[str, Any]) -> Mapping[str, Any]:
    u = _tournament(event).get("uniqueTournament")
    return u if isinstance(u, Mapping) else {}


def competition_id(event: Mapping[str, Any]) -> int | None:
    value = _unique(event).get("id")
    return int(value) if isinstance(value, int) else None


def _sport_slug(event: Mapping[str, Any]) -> str:
    category = _tournament(event).get("category")
    sport = category.get("sport") if isinstance(category, Mapping) else None
    return str(sport.get("slug") or "") if isinstance(sport, Mapping) else ""


def is_non_competitive_name(name: object) -> bool:
    """A tournament name that says friendly / pre-season / exhibition /
    show match / all-star / legends (the markers every sport but football
    reads; football is on its reviewed id list)."""
    folded = fold(name)
    return bool(folded and _NON_COMPETITIVE.search(folded))


def is_friendly_event(event: Mapping[str, Any], sport: str | None = None) -> bool:
    """A match no history reader may count: a friendly, a pre-season
    tournament, an exhibition.

    ``sport`` is the pipeline's sport name ("football", "tennis",
    "ice-hockey", "basketball", "volleyball", "esports"); None reads the
    event's own category slug.
    """
    sport = sport or _sport_slug(event)
    comp = competition_id(event)
    if sport == "football":
        return comp is not None and comp in FRIENDLY_COMPETITION_IDS
    if comp is not None and comp in OTHER_SPORT_FRIENDLY_IDS.get(sport, frozenset()):
        return True
    names = (_unique(event).get("name"), _tournament(event).get("name"))
    if any(is_non_competitive_name(n) for n in names):
        return True
    if sport == "tennis":
        category = _unique(event).get("category") or _tournament(event).get("category")
        if isinstance(category, Mapping):
            if fold(category.get("name")) in _TENNIS_NON_COMPETITIVE_CATEGORIES:
                return True
    return False


def is_knockout(event: Mapping[str, Any]) -> bool:
    """A cup round, a play-off or a qualifier - not a league round."""
    info = event.get("roundInfo")
    if isinstance(info, Mapping):
        if info.get("cupRoundType") is not None:
            return True
        if str(info.get("name") or "").strip():
            return True
    stage = fold(_tournament(event).get("name"))
    unique = fold(_unique(event).get("name"))
    suffix = stage[len(unique):] if unique and stage.startswith(unique) else stage
    return bool(suffix and _PLAYOFF_STAGE.search(suffix))


def match_kind(event: Mapping[str, Any], sport: str | None = None) -> MatchKind:
    if is_friendly_event(event, sport):
        return MatchKind.FRIENDLY
    if is_knockout(event):
        return MatchKind.KNOCKOUT
    return MatchKind.REGULAR


# --- Which past matches a goal sample holds (2026-10-04) ---------------------
#
# Measured on the cache (scripts/sofa/measure_sample_composition.py, every
# REGULAR league match 2025-08-01..2026-10-03, both sides' last ten matches
# read as SAMPLES reads them; data/analysis_2026-10-04_history/
# composition_all_v2.md). Taking only REGULAR matches of the fixture's own
# competition (falling back to the usual sample below SAME_COMPETITION_MIN)
# against the newest ten of every kind, Poisson log-loss per case, 95% from
# resampling matches, both event-id halves the same sign:
#
#     goals_for      -0.00555 [-0.00632; -0.00487]   676,815 cases
#     goals_1h_for   -0.00194 [-0.00262; -0.00123]
#     goals_2h_for   -0.00158 [-0.00228; -0.00088]
#     goals_total    -0.00070 [-0.00115; -0.00023]   316,637 matches
#
# and nowhere else: corners +0.00107 / +0.00191 (for), offsides_for +0.00193,
# shots_total +0.00114, fouls / cards / shots on target inside zero. A goal
# count carries the opponent's level (a cup tie against an amateur side, a
# relegation play-off); a corner or a foul count describes the side's own
# game and wants the newest matches. Restricting to the current season was
# worse for every metric (goals_for +0.00405) and is not done.
SAME_COMPETITION_METRICS: frozenset[str] = frozenset(
    {"goals_for", "goals_1h_for", "goals_2h_for", "goals_total"}
)
SAME_COMPETITION_MIN = 5


def pick_same_competition[T](
    newest_first: Sequence[T],
    competition: int,
    n: int,
    competition_of: Callable[[T], int | None],
    regular: Callable[[T], bool],
    minimum: int = SAME_COMPETITION_MIN,
) -> list[T] | None:
    """The newest ``n`` REGULAR matches of ``competition``, or None when there
    are fewer than ``minimum`` (the caller keeps its usual sample)."""
    chosen = [
        m for m in newest_first if competition_of(m) == competition and regular(m)
    ][:n]
    return chosen if len(chosen) >= minimum else None
