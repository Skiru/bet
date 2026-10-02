"""Two Polish exonyms SETTLE could not grade on 2026-10-01 (82 gate).

'kenia' vs Sofascore's 'Kenya' scored 80.0 and 'macedonia polnocna u21' vs
'North Macedonia U21' 81.3. 'al wahda' vs 'Al-Wahda FC' (73.7) is a hyphen,
not an exonym, and is deliberately not aliased here.
"""

from __future__ import annotations

from bet.sofa.names import normalize_name
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, name_score
from scripts.sofa.run_settle import _subject_is_home


def test_the_exonyms_fold_to_sofascores_names() -> None:
    assert normalize_name("Kenia") == normalize_name("Kenya") == "kenya"
    assert normalize_name("Macedonia Północna U21") == normalize_name(
        "North Macedonia U21")
    assert normalize_name("Macedonia Północna") == "north macedonia"


def test_settle_finds_the_side() -> None:
    kenya = {"home_name": "Guinea", "away_name": "Kenya"}
    assert _subject_is_home("Kenia", kenya) is False
    macedonia = {"home_name": "North Macedonia U21", "away_name": "Montenegro U21"}
    assert _subject_is_home("Macedonia Północna U21", macedonia) is True
    assert name_score(normalize_name("Kenia"), normalize_name("Kenya")) >= (
        NAME_MATCH_THRESHOLD)


def test_a_name_that_only_resembles_the_key_is_untouched() -> None:
    assert normalize_name("Sofia Kenin") == "sofia kenin"
    assert normalize_name("Macedonia") == "macedonia"
