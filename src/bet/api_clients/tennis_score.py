"""One definition of "how many games was that match", shared by every tennis provider.

Tennis providers do not disagree about scores -- they disagree about what they
publish *instead* of a score, and the pipeline used to take whatever each one
offered and call the results the same metric.

* ``espn-tennis`` publishes per-set ``linescores``. Summing both sides' values
  is exactly the published score: measured 2026-09-02 against ESPN's own
  ``notes`` score line on **280 finished matches, 280 agreed**, tie-break sets
  included.
* ``tennis-abstract`` publishes ``games`` / ``ogames``, which are **service
  games**, and derived ``total_games`` from their sum. A tie-break game has no
  server, so it appears in neither count: the derived total is short by exactly
  one game per tie-break set. Measured on that provider's own cache, 6,753 rows
  with a parseable score: with no tie-break the sum agreed 4,476 times; with one
  tie-break it was one game short 1,821 times against 35 agreements; with two,
  two short 295 times; with three, three short 30 times.

That is a systematic, one-directional shift on ``total_games`` -- the metric
behind the Total Games market -- and it sat *inside* the 1.0 tolerance
``_cross_provider_agreement`` uses, so every one of those matches was certified
``AGREE``. Agreement between a correct provider and a provider that is
reliably one low is not corroboration; it is two rows that happen to be close.

So neither provider's own arithmetic is trusted for games or sets any more.
Both derive them here, from the set score each one already publishes, which is
the quantity the market actually settles on.

Retirements and walkovers are named rather than inferred. ``providers.py``
guesses at them with a minimum-games threshold (a completed singles match
cannot be shorter than 6-0 6-0), which is a reasonable guess and still only a
guess; both feeds *say* so in the score string, and a stated fact beats a
threshold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Tie-break points ("7-6 (7-3)"), seedings ("(15) Fabian Marozsan") and
# bracketed match tie-breaks ("[10-7]") all sit inside brackets and all contain
# digit pairs that are not set scores. Removing the bracketed spans first is
# what makes the remaining `\d+-\d+` search safe.
_BRACKETED = re.compile(r"[(\[][^)\]]*[)\]]")
_SET_PAIR = re.compile(r"(\d{1,2})-(\d{1,2})")

# ESPN states the score as a full sentence -- "A (GBR) bt B (ESP) 7-6 (7-3) 6-3"
# -- so the score proper begins after " bt ". Player names carry no digits, but
# splitting on the marker means the parser never has to rely on that.
_ESPN_RESULT_MARKER = re.compile(r"\bbt\b", re.IGNORECASE)

# What each feed writes when the match did not go the distance. tennis-abstract
# uses "ret" and "W/O" (and, on seven rows of a 78,750-row cache, the literal
# word "Walkover"); ESPN uses "ret" and "def".
#
# A regex with letter boundaries rather than a substring test, because the
# substring test read player names as retirements. ESPN states the score as a
# sentence -- "(9) Jiri Lehecka (CZE) bt Matteo Berrettini (ITA) 6-4 6-7 (3-7)
# 6-3" -- and ``"ret" in "berrettini"`` is True, so **every ESPN match against
# Berrettini was dropped as unfinished**, along with Cocciaretto's and Cretu's
# (3 of the 349 players in the local cache; Lehecka's 2026-09-04 dossier is
# where it surfaced). Boundaries are letter-based rather than ``\b`` so that
# "w/o" still matches -- the slash is not a word character, and ``\b`` around
# it behaves differently than around a letter.
_UNFINISHED_RE = re.compile(
    r"(?<![a-z])(?:ret|w/o|walkover|def|abn|disq)\.?(?![a-z])", re.IGNORECASE
)

# No professional set is won with fewer than six games, and no tie-break set
# passes 7-6, but sets *do* run long where no final-set tie-break is played --
# Isner-Mahut ended 70-68. The ceiling is a sanity bound on the regex, not a
# rule about tennis: it rejects a stray year or squad number that survived the
# bracket strip, and nothing a real match can produce.
_MAX_GAMES_IN_SET = 80


@dataclass(frozen=True)
class TennisScore:
    """A parsed set score.

    ``games`` and ``sets`` count what was actually played, so a retirement
    reports the games completed before it, not the games a full match would
    have had. ``completed`` is what says whether to use them: an abandoned
    match is exactly the shape that flatters an UNDER, and it is the caller,
    not this parser, that decides to drop it.
    """

    games: float
    sets: int
    completed: bool
    set_scores: tuple[tuple[int, int], ...]

    @property
    def tie_break_sets(self) -> int:
        """Sets decided 7-6. The size of the error this module exists to fix."""
        return sum(1 for a, b in self.set_scores if {a, b} == {6, 7})


def parse_tennis_score(raw: str | None) -> TennisScore | None:
    """Read a published set score. ``None`` when the string states no score.

    Handles both feeds' spellings without being told which one it was given:
    the ESPN sentence form, the tennis-abstract compact form ("7-6(2) 6-3"),
    and the empty/placeholder strings tennis-abstract uses for walkovers.
    """
    if raw is None:
        return None
    text = str(raw).replace("&nbsp;", " ").strip()
    if not text:
        return None

    # Names off first, *then* look for a retirement. Both halves of the fix
    # matter: the marker scan used to run on the whole sentence, so a surname
    # could be read as a result, and the boundaries in _UNFINISHED_RE keep that
    # from happening again on the feeds that state no " bt " at all.
    marker = _ESPN_RESULT_MARKER.search(text)
    if marker:
        text = text[marker.end():]

    completed = _UNFINISHED_RE.search(text) is None

    pairs: list[tuple[int, int]] = []
    for own, other in _SET_PAIR.findall(_BRACKETED.sub(" ", text)):
        a, b = int(own), int(other)
        if a > _MAX_GAMES_IN_SET or b > _MAX_GAMES_IN_SET:
            continue
        pairs.append((a, b))

    if not pairs:
        return None
    return TennisScore(
        games=float(sum(a + b for a, b in pairs)),
        sets=len(pairs),
        completed=completed,
        set_scores=tuple(pairs),
    )
