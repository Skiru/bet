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
    # No dash. Superbet sends "Adrian Andreev liczba gemow", not
    # "Adrian Andreev - liczba gemow", so the dashed pattern matched nothing
    # and games_won_for — a declared metric with a working extractor — was
    # unreachable for the life of the pipeline. 139 priced markets a day went
    # to unmapped_markets over one character (F38).
    (re.compile(r"^(?P<team>.+?) liczba gemow$"), "games_won_for"),
]


def get_mechanism_family(market: str) -> str:
    # A derived market is the same mechanism as the metric it is derived from.
    # "both_over_corners" and "corners_for" are one fact about one match said
    # two ways, and MAX_PER_MECHANISM_FAMILY_PER_FIXTURE exists precisely so
    # that fact reaches a coupon once. Leaving derived markets to fall through
    # to "other" would let a corners row and a both-teams-corners row share a
    # fixture as though they were independent evidence.
    base = derived_base(market)
    if base is not None:
        return get_mechanism_family(
            DERIVED_BASE_TO_SIDE_METRIC.get(base, f"{base}_for")
        )

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
# Tennis has its own scopes, and the no-dash games pattern above walks
# straight into them: "1. set - Adrian Andreev liczba gemow" captures the
# team as "1. set - Adrian Andreev", which is a *set* line priced against a
# whole-match sample — F29's defect in the sport F29 never touched. 268 such
# markets were quoted on 2026-09-18, twice as many as the whole-match version
# the pattern was added for.
#
# A subject carrying "&" or ";" is a combination market ("Mecz & liczba
# gemow", and the whole Bet Builder catalogue), not a participant.
_SUBJECT_IS_SCOPE = re.compile(
    r"^(?:[12]\.\s?polowa\b|\d+\.?\s?set\b|x\.?\s?set\b)"
)
_SUBJECT_IS_COMBINATION = re.compile(r"[&;]")


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
            if _SUBJECT_IS_COMBINATION.search(team):
                return None
            return (market, team)
    return None


# ---------------------------------------------------------------------------
# Derived markets — the ones that are about BOTH sides at once
# ---------------------------------------------------------------------------
#
# Everything above maps a Superbet market to a single number: a total, or one
# side's own count. These map to a *pair* of numbers, and they are priced in
# derived.py against the joint distribution built by joint.py.
#
# They were all landing in `unmapped_markets` — 42,426 market names went
# unread on 2026-09-18 — and they are not exotic: "Obie drużyny strzelą" is
# among the most heavily quoted markets on the board, and it is exactly
# "każda z drużyn powyżej 0.5 gola" under a different name.

# Superbet's name for the quantity -> our metric base.
_DERIVED_METRIC_NAMES = {
    "rzutow roznych": "corners",
    "rz.roznych": "corners",
    "kartek": "cards_points",
    "celnych strzalow": "shots_on_target",
    "strzalow": "shots",
    "fauli": "fouls",
    "spalonych": "offsides",
    "goli": "goals",
    "gola": "goals",
    "gemow": "games",
}

# "Każda z drużyn powyżej X rzutów rożnych" -> both_over_corners.
_BOTH_OVER = re.compile(r"^kazda z druzyn powyzej x (?P<metric>.+)$")

# "Obie drużyny strzelą" is the same market at line 0.5, and
# "Obie drużyny strzelą powyżej 1.5 gola" is its ladder.
_BTTS_PLAIN = re.compile(r"^obie druzyny strzela$")
_BTTS_LINE = re.compile(r"^obie druzyny strzela powyzej (?P<line>[\d.]+) gola$")

# "Najwięcej kartek", and the corner version Superbet calls a head-to-head.
_MOST = re.compile(r"^najwiecej (?P<metric>.+)$")
_MOST_H2H = re.compile(r"^liczba (?P<metric>.+) - h2h$")

# "Rzuty rożne handicap", "Liczba kartek - handicap", "Handicap gemy".
_HANDICAP_PATTERNS = [
    (re.compile(r"^rzuty rozne handicap$"), "corners"),
    (re.compile(r"^liczba (?P<metric>.+) - handicap$"), None),
    (re.compile(r"^handicap gemy$"), "games"),
]

# The selection side of a both-teams market. Superbet is not consistent about
# which order it puts them in: corners and cards say "Powyżej 3.5 - tak",
# fouls says "Tak - 8.5".
_YES = ("tak",)
_NO = ("nie",)

# "Brentford (-1.5)" — the handicap that applies to *this* selection. The
# market's specialBetValue carries one signed value for the pair, so reading
# the line from there gives both sides the same handicap and prices the away
# side's row against the home side's line.
_HANDICAP_SELECTION = re.compile(r"^(?P<team>.+?)\s*\((?P<line>[+-]?[\d.]+)\)\s*$")

# Draw selections, across the several ways Superbet writes them.
_DRAW_TOKENS = {"remis", "x"}

DERIVED_DRAW_SUBJECT = "__draw__"


def _derived_metric(raw: str) -> str | None:
    cleaned = raw.strip()
    if cleaned in _DERIVED_METRIC_NAMES:
        return _DERIVED_METRIC_NAMES[cleaned]
    # "celnych strzalow" must beat "strzalow"; longest key first.
    for key in sorted(_DERIVED_METRIC_NAMES, key=len, reverse=True):
        if cleaned.endswith(key):
            return _DERIVED_METRIC_NAMES[key]
    return None


def _yes_no(selection: str) -> str | None:
    tokens = [t.strip() for t in re.split(r"[-–]", selection)]
    for token in tokens:
        if token in _YES:
            return "OVER"
        if token in _NO:
            return "UNDER"
    return None


def classify_derived_market(
    market_name: str | None,
    selection_name: str | None,
    special_bet_value: str | None,
) -> tuple[str, str, float, str] | None:
    """Map one Superbet selection to (market, subject, line, direction).

    Returns None for anything this module does not price, which keeps it in
    `unmapped_markets` where it stays visible.

    ``direction`` reuses OVER/UNDER because that is what the rest of the
    pipeline speaks. For a both-teams market OVER is "tak". For a comparative
    or handicap market there is no over and no under — every selection is its
    own proposition — so they are all OVER and the subject says which one.
    """
    folded = fold(market_name)
    selection = fold(selection_name)
    if not folded or not selection:
        return None

    match = _BOTH_OVER.match(folded)
    if match:
        metric = _derived_metric(match.group("metric"))
        direction = _yes_no(selection)
        if metric is None or direction is None or special_bet_value is None:
            return None
        try:
            line = float(special_bet_value)
        except (TypeError, ValueError):
            return None
        return (f"both_over_{metric}", "", line, direction)

    if _BTTS_PLAIN.match(folded):
        direction = _yes_no(selection)
        if direction is None:
            return None
        return ("both_over_goals", "", 0.5, direction)

    match = _BTTS_LINE.match(folded)
    if match:
        direction = _yes_no(selection)
        if direction is None:
            return None
        return ("both_over_goals", "", float(match.group("line")), direction)

    match = _MOST.match(folded) or _MOST_H2H.match(folded)
    if match:
        metric = _derived_metric(match.group("metric"))
        if metric is None:
            return None
        subject = DERIVED_DRAW_SUBJECT if selection in _DRAW_TOKENS else selection
        if _SUBJECT_IS_COMBINATION.search(subject):
            return None
        return (f"most_{metric}", subject, 0.0, "OVER")

    for pattern, fixed_metric in _HANDICAP_PATTERNS:
        hm = pattern.match(folded)
        if not hm:
            continue
        metric = fixed_metric
        if metric is None:
            metric = _derived_metric(hm.groupdict().get("metric") or "")
        if metric is None:
            return None
        sel = _HANDICAP_SELECTION.match(selection)
        if not sel:
            return None
        try:
            line = float(sel.group("line"))
        except (TypeError, ValueError):
            return None
        team = sel.group("team").strip()
        if not team or _SUBJECT_IS_COMBINATION.search(team):
            return None
        return (f"handicap_{metric}", team, line, "OVER")

    return None


# Metric bases that carry a `_for` sample per side, which is what derived.py
# needs to build a joint. A derived market on a base not listed here has no
# way to be priced and must stay unmapped.
DERIVED_BASE_TO_SIDE_METRIC = {
    "corners": "corners_for",
    "cards_points": "cards_points_for",
    "shots": "shots_for",
    "shots_on_target": "shots_on_target_for",
    "fouls": "fouls_for",
    "offsides": "offsides_for",
    "goals": "goals_for",
    "games": "games_won_for",
}


def derived_base(market: str) -> str | None:
    for prefix in ("both_over_", "most_", "handicap_"):
        if market.startswith(prefix):
            return market[len(prefix) :]
    return None


def is_derived(market: str) -> bool:
    return derived_base(market) is not None
