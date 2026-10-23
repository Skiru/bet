"""Review R2 #6: find_friendly_competitions.reviewed_ids reads the friendlies
file's `excluded_from_sample_conflict_cut` too (the ids added for
epochs.SAMPLE_CONFLICT_CUT_FROM_UTC), so they are not proposed again."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.sofa.find_friendly_competitions import reviewed_ids


def test_every_decided_list_counts_as_reviewed(tmp_path: Path) -> None:
    path = tmp_path / "friendlies.json"
    path.write_text(json.dumps({
        "excluded": [{"competition_id": 1}],
        "allowed": [{"competition_id": 2}],
        "excluded_from_sample_conflict_cut": [{"competition_id": 38292},
                                              {"competition_id": 38659}],
    }))
    assert reviewed_ids(path) == {1, 2, 38292, 38659}


def test_the_installed_file_holds_the_conflict_cut_ids() -> None:
    assert {38292, 38659} <= reviewed_ids()
