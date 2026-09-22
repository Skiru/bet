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
    # F43. Superbet writes the half with and without the space after the dot,
    # and both forms appear on the same board, so both are keys — the same
    # reason the goal lines above are doubled.
    "1.polowa - liczba rzutow roznych": "corners_1h_total",
    "1. polowa - liczba rzutow roznych": "corners_1h_total",
    "2.polowa - liczba rzutow roznych": "corners_2h_total",
    "2. polowa - liczba rzutow roznych": "corners_2h_total",
    "1.polowa - liczba fauli": "fouls_1h_total",
    "1. polowa - liczba fauli": "fouls_1h_total",
    "1.polowa - liczba strzalow": "shots_1h_total",
    "1. polowa - liczba strzalow": "shots_1h_total",
    "1.polowa - liczba celnych strzalow": "shots_on_target_1h_total",
    "1. polowa - liczba celnych strzalow": "shots_on_target_1h_total",
    "liczba asow": "aces_total",
    "liczba podwojnych bledow": "double_faults_total",
    # F45. One quantity with one ladder, not an aces row plus a faults row.
    "liczba asow + podwojnych bledow": "serve_points_total",
    "1. set - liczba asow": "aces_set1_total",
    "1.set - liczba asow": "aces_set1_total",
    "2. set - liczba asow": "aces_set2_total",
    "2.set - liczba asow": "aces_set2_total",
    "1. set - liczba podwojnych bledow": "double_faults_set1_total",
    "1.set - liczba podwojnych bledow": "double_faults_set1_total",
    "2. set - liczba podwojnych bledow": "double_faults_set2_total",
    "2.set - liczba podwojnych bledow": "double_faults_set2_total",
    "1. set - liczba asow + podwojnych bledow": "serve_points_set1_total",
    "1.set - liczba asow + podwojnych bledow": "serve_points_set1_total",
    "2. set - liczba asow + podwojnych bledow": "serve_points_set2_total",
    "2.set - liczba asow + podwojnych bledow": "serve_points_set2_total",
    "liczba gemow": "games_total",
    "liczba setow": "sets_total",
    # `tiebreaks_total` was declared in metrics.py with a working extractor and
    # no way of being reached: the name was simply absent from this table, so
    # `metrics_from_offer` never requested the metric, SAMPLES never built it,
    # and the resulting hole read as a provider gap rather than a mapping one.
    # Superbet sends it in the ordinary ladder shape (specialBetValue carries
    # the line, selections say poniżej/powyżej, both sides quoted), 54 fixtures
    # on 2026-09-21. The yes/no sibling "czy bedzie tiebreak" has no line and
    # is deliberately NOT mapped — offer.py builds a rung from a direction.
    "liczba tiebreakow": "tiebreaks_total",
}

TEAM_MARKET_PATTERNS = [
    # Halves first, and they must stay first: the generic goals_for pattern
    # below backtracks happily into "1.polowa - <team> - liczba goli" and
    # reads the scope as the team name, which is how a half-time line got
    # priced off a whole-match sample (F29). goals_1h_for / goals_2h_for
    # already existed in FOOTBALL_METRICS and had no way of being reached.
    (re.compile(r"^1\.\s?polowa - (?P<team>.+?) - liczba goli$"), "goals_1h_for"),
    (re.compile(r"^2\.\s?polowa - (?P<team>.+?) - liczba goli$"), "goals_2h_for"),
    # F43. No dash before the metric on these — Superbet sends
    # "1. polowa - Brentford liczba rzutow roznych". Same one-character trap
    # that hid games_won_for for the life of the pipeline (F38), so the
    # pattern is written against the strings the board actually carries.
    (
        re.compile(r"^1\.\s?polowa - (?P<team>.+?) liczba rzutow roznych$"),
        "corners_1h_for",
    ),
    (
        re.compile(r"^2\.\s?polowa - (?P<team>.+?) liczba rzutow roznych$"),
        "corners_2h_for",
    ),
    (re.compile(r"^1\.\s?polowa - (?P<team>.+?) liczba fauli$"), "fouls_1h_for"),
    (re.compile(r"^1\.\s?polowa - (?P<team>.+?) liczba strzalow$"), "shots_1h_for"),
    (
        re.compile(r"^1\.\s?polowa - (?P<team>.+?) liczba celnych strzalow$"),
        "shots_on_target_1h_for",
    ),
    (re.compile(r"^(?P<team>.+?) - liczba rzutow roznych$"), "corners_for"),
    (re.compile(r"^(?P<team>.+?) - liczba kartek$"), "cards_points_for"),
    (re.compile(r"^(?P<team>.+?) - liczba goli$"), "goals_for"),
    (re.compile(r"^liczba celnych strzalow - (?P<team>.+?)$"), "shots_on_target_for"),
    (re.compile(r"^liczba strzalow (?P<team>.+?)$"), "shots_for"),
    (re.compile(r"^liczba fauli - (?P<team>.+?)$"), "fouls_for"),
    (re.compile(r"^spalone - (?P<team>.+?)$"), "offsides_for"),
    # F45. Set-scoped serve markets, before the generic ones below — the
    # unscoped pattern happily reads "1. set - Ben Shelton" as the player.
    # Superbet uses a dash before "liczba podwojnych bledow" and none before
    # "liczba asow", on the same screen, so both shapes are written out.
    (
        re.compile(
            r"^1\.\s?set - (?P<team>.+?) -? ?liczba asow \+ podwojnych bledow$"
        ),
        "serve_points_set1_for",
    ),
    (
        re.compile(
            r"^2\.\s?set - (?P<team>.+?) -? ?liczba asow \+ podwojnych bledow$"
        ),
        "serve_points_set2_for",
    ),
    (
        re.compile(r"^1\.\s?set - (?P<team>.+?) -? ?liczba asow$"),
        "aces_set1_for",
    ),
    (
        re.compile(r"^2\.\s?set - (?P<team>.+?) -? ?liczba asow$"),
        "aces_set2_for",
    ),
    (
        re.compile(r"^1\.\s?set - (?P<team>.+?) -? ?liczba podwojnych bledow$"),
        "double_faults_set1_for",
    ),
    (
        re.compile(r"^2\.\s?set - (?P<team>.+?) -? ?liczba podwojnych bledow$"),
        "double_faults_set2_for",
    ),
    (
        re.compile(r"^(?P<team>.+?) -? ?liczba asow \+ podwojnych bledow$"),
        "serve_points_for",
    ),
    (re.compile(r"^(?P<team>.+?) liczba asow$"), "aces_for"),
    (re.compile(r"^(?P<team>.+?) liczba podwojnych bledow$"), "double_faults_for"),
    (re.compile(r"^(?P<team>.+?) - liczba podwojnych bledow$"), "double_faults_for"),
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
        return get_mechanism_family(derived_side_metric(base))

    # F43. A half is a scope, not a mechanism: the corners of the first half
    # and the corners of the match are one fact about one match, so they share
    # a family and MAX_PER_MECHANISM_FAMILY_PER_FIXTURE gives the slot to
    # whichever expresses the claim better. Falling through to "other" would
    # have let both onto a coupon as independent evidence — the failure the
    # derived-market branch above exists to prevent.
    # F43/F45. A half and a set are *scopes*, not mechanisms: first-set aces
    # and match aces are one fact about one match, so they share a family and
    # MAX_PER_MECHANISM_FAMILY_PER_FIXTURE gives the slot to one of them.
    # Falling through to "other" would put both on a coupon as independent
    # evidence — the failure the derived branch above exists to prevent.
    scope_stripped = market
    for scope in ("_1h_", "_2h_", "_set1_", "_set2_"):
        scope_stripped = scope_stripped.replace(scope, "_")
    for suffix in ("_1h", "_2h", "_set1", "_set2"):
        if scope_stripped.endswith(suffix):
            scope_stripped = scope_stripped[: -len(suffix)]
    if scope_stripped != market:
        return get_mechanism_family(scope_stripped)

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
    if market in (
        "aces_total",
        "aces_for",
        "double_faults_total",
        "double_faults_for",
        # F45. Aces + double faults is the same mechanism said a third way:
        # what happened on serve. It must not win a second slot on a fixture
        # that already has an aces or a faults row.
        "serve_points_total",
        "serve_points_for",
    ):
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

# Phrases that describe the *shape of the question*, not a competitor. The
# team patterns are deliberately loose — "<player> liczba gemow" has no dash,
# because Superbet sends none (F38) — and that looseness reads the words
# "nieparzysta/parzysta" as a player name: `classify_market` returned
# ("games_won_for", "nieparzysta/parzysta") for all 96 tennis fixtures
# carrying that market on 2026-09-21. Nothing downstream would have caught it
# on merit; the only reason no phantom rung was built is that Superbet sends
# no specialBetValue for odd/even, so offer.py diverted it to "(no line)".
# A market that gains a line later would have become a rung priced off a
# sample belonging to neither player, so the guard is here and not there.
_SUBJECT_IS_PROPOSITION = re.compile(r"^(?:nieparzysta|parzysta)\b|/parzysta\b")


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
            if _SUBJECT_IS_PROPOSITION.search(team):
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
    # F45. Longest-key-first matching in _derived_metric means
    # "asow + podwojnych bledow" beats both "asow" and "podwojnych bledow".
    "asow + podwojnych bledow": "serve_points",
    "asow serwisowych": "aces",
    "asow": "aces",
    "podwojnych bledow": "double_faults",
}

# "Każda z drużyn powyżej X rzutów rożnych" -> both_over_corners.
_BOTH_OVER = re.compile(r"^kazda z druzyn powyzej x (?P<metric>.+)$")

# "Obie drużyny strzelą" is the same market at line 0.5, and
# "Obie drużyny strzelą powyżej 1.5 gola" is its ladder.
_BTTS_PLAIN = re.compile(r"^obie druzyny strzela$")
_BTTS_LINE = re.compile(r"^obie druzyny strzela powyzej (?P<line>[\d.]+) gola$")

# "Najwięcej kartek", and the corner version Superbet calls a head-to-head.
_MOST = re.compile(r"^najwiecej (?P<metric>.+)$")
# F45. Superbet also scopes the who-takes-more question to a set or a half:
# "1. set - najwiecej asow", "1. polowa - najwiecej rzutow roznych". The scope
# is captured so it can be carried onto the metric name, because
# "most aces in set 1" and "most aces in the match" are different questions
# with different samples.
_MOST_SCOPED = re.compile(
    r"^(?P<scope>[12])\.\s?(?P<unit>set|polowa) - najwiecej (?P<metric>.+)$"
)
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


def _scope_metric(side_metric: str, scope: str) -> str | None:
    """`aces_for` + `set1` -> `aces_set1`, if that metric actually exists.

    Returns None when the scoped metric is not declared, so a scoped market we
    cannot sample stays in unmapped_markets and is visible there, rather than
    becoming a row with no sample behind it.
    """
    from bet.sofa.metrics import FOOTBALL_METRICS, TENNIS_METRICS

    if not side_metric.endswith("_for"):
        return None
    stem = side_metric[: -len("_for")]
    candidate = f"{stem}_{scope}"
    if f"{candidate}_for" in TENNIS_METRICS or f"{candidate}_for" in FOOTBALL_METRICS:
        return candidate
    return None


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

    scoped = _MOST_SCOPED.match(folded)
    if scoped:
        metric = _derived_metric(scoped.group("metric"))
        if metric is None:
            return None
        side_metric = derived_side_metric(metric)
        n = scoped.group("scope")
        # The declared names are `aces_set1_for` and `corners_1h_for`: the
        # scope sits after the stem in both, but tennis writes "set1" and
        # football writes "1h".
        scope = f"set{n}" if scoped.group("unit") == "set" else f"{n}h"
        scoped_metric = _scope_metric(side_metric, scope)
        if scoped_metric is None:
            return None
        subject = DERIVED_DRAW_SUBJECT if selection in _DRAW_TOKENS else selection
        if _SUBJECT_IS_COMBINATION.search(subject):
            return None
        return (f"most_{scoped_metric}", subject, 0.0, "OVER")

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


# Bases whose per-side sample is NOT simply `<base>_for` — `games` is measured
# as `games_won_for`. Everything else follows the regular rule, so read this
# table through `derived_side_metric`, never with a bare `.get(base)`.
DERIVED_BASE_TO_SIDE_METRIC = {
    "corners": "corners_for",
    "cards_points": "cards_points_for",
    "shots": "shots_for",
    "shots_on_target": "shots_on_target_for",
    "fouls": "fouls_for",
    "offsides": "offsides_for",
    "goals": "goals_for",
    "games": "games_won_for",
    "aces": "aces_for",
    "double_faults": "double_faults_for",
    "serve_points": "serve_points_for",
}


def derived_side_metric(base: str) -> str:
    """The per-side metric a derived market's base is built from.

    The regular rule is `<base>_for`; the table above holds only the bases
    that break it. Reading the table with a bare `.get(base)` silently
    excludes every *scoped* base — `corners_1h`, `aces_set1`, `serve_points_set2` —
    because none of them is listed, and the scoped bases are exactly the ones
    `_scope_metric` has already proved to be declared before it will emit the
    market at all.

    That contradiction was live: the mapper created 78 scoped `most_*` rungs
    on 2026-09-21, `derived.price_derived_rungs` dropped all of them as
    "no None sample", and `run_settle` — which already used the fallback —
    would have settled them. 75 of the 78 had the per-side sample sitting in
    `03_samples.json`. One helper, so the two halves cannot drift again.
    """
    return DERIVED_BASE_TO_SIDE_METRIC.get(base, f"{base}_for")


def derived_base(market: str) -> str | None:
    for prefix in ("both_over_", "most_", "handicap_"):
        if market.startswith(prefix):
            return market[len(prefix) :]
    return None


def is_derived(market: str) -> bool:
    return derived_base(market) is not None
