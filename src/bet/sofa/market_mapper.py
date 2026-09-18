import re
import unicodedata

# Letters NFD cannot help with. Stripping diacritics by decomposing to NFD and
# dropping the combining marks works for ó ż ę ą ś ć ń ź — each is a letter plus
# a mark — but "ł" (U+0142) is a single indivisible code point with no
# decomposition, so it survived the fold untouched. Every Superbet market name
# containing "połowa", "strzałów" or "błędów" therefore missed its dictionary
# key, and eight mappings were unreachable: the half-time goal totals, shots,
# shots on target and double faults, match and per-side (F29).
_SINGLETONS = {
    "ł": "l",
    "đ": "d",
    "ø": "o",
    "ı": "i",
    "æ": "ae",
    "ß": "ss",
    "þ": "th",
}
_SINGLETON_TABLE = str.maketrans(_SINGLETONS)


def fold(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    # Before the decomposition, not after: the mapping is what NFD cannot do.
    text = text.translate(_SINGLETON_TABLE)
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


MATCH_MARKET_NAMES = {
    "liczba goli": "goals_total",
    "liczba rzutow roznych": "corners_total",
    "liczba kartek": "cards_points_total",
    "liczba celnych strzalow": "shots_on_target_total",
    "liczba strzalow": "shots_total",
    "liczba spalonych": "offsides_total",
    "liczba fauli": "fouls_total",
    "1.polowa - liczba goli": "goals_1h_total",
    "1. polowa - liczba goli": "goals_1h_total",
    "2.polowa - liczba goli": "goals_2h_total",
    "2. polowa - liczba goli": "goals_2h_total",
    "liczba asow": "aces_total",
    "liczba podwojnych bledow": "double_faults_total",
    "liczba gemow": "games_total",
    "liczba setow": "sets_total",
}

TEAM_MARKET_PATTERNS = [
    # Halves first, and they must stay first: the generic goals_for pattern
    # below backtracks happily into "1.polowa - <team> - liczba goli" and
    # reads the scope as the team name, which is how a half-time line got
    # priced off a whole-match sample (F29). goals_1h_for / goals_2h_for
    # already existed in FOOTBALL_METRICS and had no way of being reached.
    (re.compile(r"^1\.\s?polowa - (?P<team>.+?) - liczba goli$"), "goals_1h_for"),
    (re.compile(r"^2\.\s?polowa - (?P<team>.+?) - liczba goli$"), "goals_2h_for"),
    (re.compile(r"^(?P<team>.+?) - liczba rzutow roznych$"), "corners_for"),
    (re.compile(r"^(?P<team>.+?) - liczba kartek$"), "cards_points_for"),
    (re.compile(r"^(?P<team>.+?) - liczba goli$"), "goals_for"),
    (re.compile(r"^liczba celnych strzalow - (?P<team>.+?)$"), "shots_on_target_for"),
    (re.compile(r"^liczba strzalow (?P<team>.+?)$"), "shots_for"),
    (re.compile(r"^liczba fauli - (?P<team>.+?)$"), "fouls_for"),
    (re.compile(r"^spalone - (?P<team>.+?)$"), "offsides_for"),
    (re.compile(r"^(?P<team>.+?) liczba asow$"), "aces_for"),
    (re.compile(r"^(?P<team>.+?) liczba podwojnych bledow$"), "double_faults_for"),
    (re.compile(r"^(?P<team>.+?) - liczba gemow$"), "games_won_for"),
]


def get_mechanism_family(market: str) -> str:
    if market in (
        "goals_total",
        "goals_for",
        "goals_1h_total",
        "goals_1h_for",
        "goals_2h_total",
        "goals_2h_for",
        "xg_total",
        "xg_for",
    ):
        return "scoring"
    if market in (
        "shots_total",
        "shots_for",
        "shots_on_target_total",
        "shots_on_target_for",
        "corners_total",
        "corners_for",
        "offsides_total",
        "offsides_for",
        "blocked_shots_total",
    ):
        return "attacking"
    if market in (
        "cards_points_total",
        "cards_points_for",
        "fouls_total",
        "fouls_for",
    ):
        return "discipline"
    if market in ("games_total", "games_won_for", "sets_total", "tiebreaks_total"):
        return "tennis_length"
    if market in ("aces_total", "aces_for", "double_faults_total", "double_faults_for"):
        return "tennis_serve"
    return "other"


# A captured "team" that is really a market scope. Superbet prices half-time
# versions of markets we have no half-time metric for — "1. polowa - liczba
# kartek", "2. polowa - liczba rzutow roznych" — and the per-team patterns
# below match them happily, reading the scope as the name of a team. The row
# then carries a half-time price against a whole-match sample, which is F29's
# defect in a market family F29 did not reach.
#
# Returning None sends these to `unmapped_markets`, where they are visible as
# markets we do not price, instead of becoming a phantom per-team row that
# determine_side has to catch downstream.
_SUBJECT_IS_SCOPE = re.compile(r"^[12]\.\s?polowa\b")


def classify_market(market_name: str | None) -> tuple[str, str] | None:
    folded = fold(market_name)
    if not folded:
        return None
    if folded in MATCH_MARKET_NAMES:
        return (MATCH_MARKET_NAMES[folded], "")
    for pattern, market in TEAM_MARKET_PATTERNS:
        m = pattern.match(folded)
        if m:
            team = m.group("team")
            if _SUBJECT_IS_SCOPE.match(team):
                return None
            return (market, team)
    return None
