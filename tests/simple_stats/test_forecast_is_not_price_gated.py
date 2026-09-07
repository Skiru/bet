"""The forecast file after the operator's 2026-09-07 instruction.

Verbatim: *"decydujesz za mnie jeżeli chodzi o superbet, zamiast zająć się
głęboką analizą statystyk (...) KURS SIE ZMIENIA, JA TO OBSERWUJE LIVE A TY
NIE (...) gdybyś skupił się na głębokiej analizie i dawał mi która statystyka
z jakim kierunkiem i wartością ma największe prawdopodobieństwo to ja sobie
poradzę przy stawianiu."*

He was measurably right. The file as it stood ranked the day by ``p_central``,
kept only cards graded MEASURED or BIASED, dropped every rung at or above the
count-model clamp -- the highest probabilities on the board -- capped the
result at twelve rows, and printed a second table gated on ``price >= 1.30``.
Per fixture it showed ``best_rungs(4)``: the four rungs *nearest even money*,
which is the least confident end of every ladder.

These tests pin the four gates shut. Each one asserts a row that the old file
would have removed is present, which is the only form of this test that can
fail for the right reason.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bet.simple_stats.contracts import (
    EventDossierV1,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.forecast import Rung, build_cards

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs" / "2026-09-07"


def _row(**kw) -> StatsSheetRow:
    base = dict(
        event_id="e1",
        sport="football",
        market="shots_for",
        line=17.5,
        direction="UNDER",
        p_central=0.81,
        p_low=0.66,
        hits=9,
        sample_size=11,
        mean=14.0,
        median=14.0,
        sample_min=8.0,
        sample_max=21.0,
        dispersion=3.4,
        shrunk_mean=14.6,
        venue="home",
        team_name="Nantes",
        hit_rate=0.8182,
        cross_provider_agreement="AGREE",
        confidence="HIGH",
        data_quality="READY",
    )
    base.update(kw)
    return StatsSheetRow(**base)


def _sheet(rows: list[StatsSheetRow]) -> StatsSheetV1:
    return StatsSheetV1(
        run_id="t",
        date="2026-09-07",
        generated_at="2026-09-07T10:29:00+00:00",
        rows=rows,
    )


# --- the ranking is on the corrected probability, and only lowers -----------

def test_every_rung_carries_a_corrected_probability_at_or_below_the_claim():
    sheet = _sheet([_row(), _row(direction="OVER", p_central=0.19)])
    dossier = EventDossierV1(
        event_id="e1", sport="football", metrics={}, readiness="READY"
    )
    cards = build_cards(sheet, [dossier], min_sample=3)
    assert cards
    for card in cards:
        for rung in card.rungs:
            assert rung.p_honest is not None
            assert rung.p_honest <= rung.p_central + 1e-12
            assert (rung.claim_correction or 0.0) <= 0.0


def test_ranked_rungs_puts_the_most_likely_first_which_best_rungs_does_not():
    """The two orderings are opposites and both are wanted.

    ``best_rungs`` answers "where is this ladder informative", nearest even
    money first. ``ranked_rungs`` answers the operator's question -- which
    value, in which direction, is most likely -- and putting the wrong one at
    the top of the file was the substance of his complaint.
    """
    def _rung(line: float, p_central: float, p_honest: float, hits: int) -> Rung:
        return Rung(
            line=line,
            direction="OVER" if line < 2 else "UNDER",
            p_central=p_central,
            p_low=p_central - 0.12,
            hits=hits,
            sample_size=11,
            p_honest=p_honest,
        )

    card_rungs = [
        _rung(1.5, 0.52, 0.52, 6),
        _rung(4.5, 0.94, 0.90, 10),
        _rung(3.5, 0.80, 0.74, 9),
    ]
    from bet.simple_stats.forecast import ForecastCard

    card = ForecastCard(
        event_id="e1", sport="football", market="goals_total", subject=None,
        expected=2.4, spread=1.1, sample_mean=2.4, sample_median=2.0,
        sample_size=11, sample_min=0.0, sample_max=5.0, baseline=2.5,
        baseline_source="prior", weight=0.5, reliability=None,
        grade="UNMEASURED", grade_reason="", rungs=card_rungs,
    )
    assert [r.line for r in card.ranked_rungs()] == [4.5, 3.5, 1.5]
    assert [r.line for r in card.best_rungs(3)] == [1.5, 3.5, 4.5]


# --- props are in by default ------------------------------------------------

def test_player_props_are_built_unless_explicitly_dropped():
    """4,272 of 4,982 cards on a real slate. They were excluded because they
    price badly at Superbet, which is a fact about a price this file no longer
    decides anything about."""
    sheet = _sheet(
        [
            _row(),
            _row(
                market="player_total_shots",
                player_name="Mostafa Mohamed",
                player_id="9",
                team_name=None,
            ),
        ]
    )
    dossier = EventDossierV1(
        event_id="e1", sport="football", metrics={}, readiness="READY"
    )
    markets = {c.market for c in build_cards(sheet, [dossier], min_sample=3)}
    assert markets == {"shots_for", "player_total_shots"}
    dropped = {
        c.market
        for c in build_cards(sheet, [dossier], min_sample=3, include_players=False)
    }
    assert dropped == {"shots_for"}


# --- and now the rendered file, against the real day ------------------------


@pytest.fixture(scope="module")
def rendered() -> str:
    if not (RUN / "2026-09-07_event_dossiers_stats_sheet.json").exists():
        pytest.skip("runs/2026-09-07 not present")
    out = subprocess.run(
        [sys.executable, "scripts/simple/build_forecast.py", "--date", "2026-09-07"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr[-3000:]
    return (RUN / "2026-09-07_forecast.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def payload(rendered: str) -> dict:
    return json.loads((RUN / "2026-09-07_forecast.json").read_text(encoding="utf-8"))


def test_the_file_names_every_discovered_fixture_or_says_why_not(payload):
    """Three of 37 fixtures had no card on 2026-09-07 and the file said nothing.

    All three were right to be missing -- ``readiness: BLOCKED``, "kickoff
    already passed: cannot be backed pre-match" -- but silence and a correct
    refusal read identically on the page and only one of them is acceptable.
    """
    coverage = payload["coverage"]
    assert len(coverage) == payload["counts"]["events_discovered"]
    for entry in coverage:
        if entry["cards"]:
            continue
        assert entry["gaps"], entry
        assert entry["readiness"], entry


def test_a_fixture_without_cards_is_named_in_the_rendered_file(rendered, payload):
    missing = [c for c in payload["coverage"] if not c["cards"]]
    if not missing:
        pytest.skip("every fixture produced a card")
    assert "## Zasięg dnia" in rendered
    for entry in missing:
        assert entry["match"] in rendered, entry["match"]


def test_no_grade_is_filtered_out_of_the_ranking(rendered, payload):
    """OVERCONFIDENT and WORSE_THAN_AVERAGE cards used to be removed from the
    day's ranking entirely. They are shown now, with their grade and with the
    correction already subtracted -- which is the honest way to include them.
    """
    graded = payload["counts"]["by_grade"]
    for grade in ("PRZESADNIE PEWNY", "GORSZY OD ŚREDNIEJ"):
        assert grade in rendered, grade
    assert graded.get("OVERCONFIDENT", 0) > 0


def test_a_rung_at_the_arithmetic_ceiling_is_present_rather_than_deleted(payload):
    """It used to be filtered on ``p_central < 0.95``, i.e. exactly the highest
    probabilities on the board. Now the clamp rows are kept and sink on their
    own market's measured record if that record does not support them."""
    from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY

    clamped = [
        rung
        for card in payload["cards"]
        for rung in card["rungs"]
        if rung["p_central"] is not None
        and rung["p_central"] >= MAX_COUNT_MODEL_PROBABILITY
    ]
    assert clamped, "no clamped rungs on this slate to check"
    assert all(r["p_honest"] is not None for r in clamped)


def test_the_price_never_removes_a_row(rendered, payload):
    """The gate that was the operator's actual complaint.

    Every ranked row must be reachable regardless of price, including rows the
    book posted no market for at all. Asserted by finding at least one row in
    the ranking whose price is missing and one whose price is below the old
    1.30 floor.
    """
    from bet.simple_stats.coupons import CERTAINTY_PRICE_FLOOR

    strongest: dict[tuple, dict] = {}
    for card in payload["cards"]:
        if not card["rungs"]:
            continue
        top = max(
            (r for r in card["rungs"] if r["p_honest"] is not None),
            key=lambda r: r["p_honest"],
            default=None,
        )
        if top is None:
            continue
        strongest[(card["event_id"], card["market"], card["subject"])] = top
    unpriced = [r for r in strongest.values() if r["superbet_price"] is None]
    cheap = [
        r
        for r in strongest.values()
        if r["superbet_price"] is not None
        and r["superbet_price"] < CERTAINTY_PRICE_FLOOR
    ]
    assert unpriced, "expected rows the book posts no market for"
    assert cheap, "expected rows priced under the old floor"
    # And the file must say the price is a column, not a gate.
    assert "Kurs jest kolumną" in rendered


def test_the_price_carries_its_own_age(rendered, payload):
    """Because he watches it change live and this process fetches it once."""
    assert payload["offer_generated_at"]
    assert payload["offer_generated_at"] in rendered


def test_the_price_appendix_comes_after_the_statistics(rendered):
    """Ordering is the whole argument: forecast first, price second."""
    assert rendered.index("Największe prawdopodobieństwa dnia") < rendered.index(
        "Dodatek: gdzie rynek jeszcze płacił rano"
    )


def test_every_fixture_with_cards_prints_a_ladder_with_its_values(rendered, payload):
    """"która statystyka z jakim kierunkiem i wartością" -- the value is the
    part that used to be missing, because only four rungs a card were shown and
    they were chosen for being uninformative."""
    assert "| wartość | kierunek | p (uczciwe) |" in rendered
    with_cards = [c for c in payload["coverage"] if c["cards"]]
    assert len(with_cards) >= 30
    for entry in with_cards:
        assert entry["match"] in rendered, entry["match"]


def test_a_team_card_below_the_table_floor_is_still_in_the_fixture_section(
    rendered, payload
):
    """The note claims exactly this, so it has to be true.

    An earlier wording claimed it of prop cards too, which is false -- those are
    in the JSON only, and the note now says so.
    """
    from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY

    weak = []
    for card in payload["cards"]:
        if card["market"].startswith("player_"):
            continue
        informative = [
            r["p_honest"]
            for r in card["rungs"]
            if r["p_honest"] is not None
            and not (
                r["p_central"] is not None
                and r["p_central"] >= MAX_COUNT_MODEL_PROBABILITY
            )
        ]
        if informative and max(informative) < 0.70:
            weak.append(card)
    assert weak, "no team card below the floor on this slate"
    # The fixture sections start after the two ranked tables.
    sections = rendered.split("## Karty po meczach")[1]
    for card in weak[:25]:
        label = card["market_label"]
        if card["subject"]:
            label = f"{label} · {card['subject']}"
        assert f"**{label}**" in sections, label


# --- the prop table is split by side, because the sides are not comparable ---


def test_ranked_rungs_can_be_narrowed_to_one_side():
    from bet.simple_stats.forecast import ForecastCard

    rungs = [
        Rung(line=0.5, direction="OVER", p_central=0.90, p_low=0.7,
             hits=5, sample_size=5, p_honest=0.90),
        Rung(line=2.5, direction="UNDER", p_central=0.95, p_low=0.8,
             hits=5, sample_size=5, p_honest=0.95),
    ]
    card = ForecastCard(
        event_id="e1", sport="football", market="player_fouls", subject="X",
        expected=0.4, spread=0.5, sample_mean=0.4, sample_median=0.0,
        sample_size=5, sample_min=0.0, sample_max=1.0, baseline=None,
        baseline_source="none", weight=0.3, reliability=None,
        grade="MEASURED", grade_reason="", rungs=rungs,
    )
    # Unnarrowed, the UNDER wins -- which is the whole problem.
    assert card.ranked_rungs(1)[0].direction == "UNDER"
    assert [r.direction for r in card.ranked_rungs(direction="OVER")] == ["OVER"]
    assert [r.line for r in card.ranked_rungs(direction="UNDER")] == [2.5]


def test_superbet_really_does_post_football_props_on_one_side_only(payload):
    """The measured fact the whole split rests on.

    If Superbet ever starts posting prop UNDERs, the asymmetric floor stops
    being justified and this test is where that shows up -- not in a paragraph
    somebody has to remember to reread.
    """
    import collections

    priced = collections.Counter(
        rung["direction"]
        for card in payload["cards"]
        if card["market"].startswith("player_")
        for rung in card["rungs"]
        if rung["superbet_price"] is not None
    )
    assert priced["OVER"] > 1000, priced
    assert priced["UNDER"] == 0, priced


def test_the_file_has_a_separate_over_table_and_it_comes_first(rendered):
    over = rendered.index("### Rynki zawodników — POWYŻEJ")
    under = rendered.index("### Rynki zawodników — PONIŻEJ")
    team = rendered.index("### Rynki meczowe i drużynowe")
    assert team < over < under, (team, over, under)


def test_each_prop_table_holds_only_its_own_side(rendered):
    """Asserted on the rendered rows, not on the code that produced them."""
    over_block = rendered.split("### Rynki zawodników — POWYŻEJ")[1].split(
        "### Rynki zawodników — PONIŻEJ"
    )[0]
    under_block = rendered.split("### Rynki zawodników — PONIŻEJ")[1].split(
        "## Karty po meczach"
    )[0]
    for block, wanted, unwanted in (
        (over_block, "OVER", "UNDER"),
        (under_block, "UNDER", "OVER"),
    ):
        rows = [line for line in block.split("\n") if line.startswith("| **")]
        assert rows, wanted
        for row in rows:
            direction = row.split("|")[7].strip().strip("*")
            assert direction.endswith(wanted), row
            assert not direction.endswith(unwanted), row


def test_the_over_side_uses_the_team_floor_and_the_under_side_the_prop_floor(
    rendered,
):
    """The asymmetry, pinned with its reason.

    The higher prop floor exists for volume, and the volume is entirely on the
    UNDER side: measured at n>=5, 294 OVER rows against 937 UNDER at a 0.70
    floor. Applying the raised floor to both sides is what buried the only side
    the book actually prices.
    """
    import re

    over = re.search(r"POWYŻEJ — (\d+) pozycji \(próg (\d+)%, n ≥ (\d+)\)", rendered)
    under = re.search(r"PONIŻEJ — (\d+) pozycji \(próg (\d+)%, n ≥ (\d+)\)", rendered)
    team = re.search(r"drużynowe — (\d+) pozycji", rendered)
    assert over and under and team
    assert over.group(2) == "70"
    assert under.group(2) == "85"
    assert over.group(3) == under.group(3) == "5"
    # And the split actually surfaced the postable side: more OVER rows than the
    # 40 the single combined ranking managed.
    assert int(over.group(1)) > 200, over.group(1)


def test_the_small_sample_floor_keeps_three_match_props_out_of_the_tables(
    rendered, payload
):
    """n=3 with 3/3 is arithmetic, not knowledge of the player, and those rows
    sorted to the top of the file before this floor existed."""
    thin = [
        c
        for c in payload["cards"]
        if c["market"].startswith("player_") and c["sample"]["size"] < 5
    ]
    assert thin, "no thin prop cards on this slate"
    blocks = rendered.split("### Rynki zawodników — POWYŻEJ")[1].split(
        "## Karty po meczach"
    )[0]
    rows = [line for line in blocks.split("\n") if line.startswith("| **")]
    # Non-empty, or the loop below asserts nothing. An earlier version of this
    # test split the block on "---" and matched the table's own separator row,
    # so it passed on zero rows.
    assert len(rows) > 200, len(rows)
    for row in rows:
        raw = row.split("|")[9].strip()          # the "Surowo" cell, hits/n
        assert int(raw.split("/")[1]) >= 5, row
    # But they are still in the JSON, every one of them.
    assert all(c["rungs"] for c in thin)


def test_the_over_paragraph_derives_its_offer_counts(rendered, payload):
    """It quoted a literal 4,690 for one day's board in a file rebuilt daily --
    the same stale-figure failure this file has been corrected for twice."""
    import collections
    import re

    priced = collections.Counter(
        rung["direction"]
        for card in payload["cards"]
        if card["market"].startswith("player_")
        for rung in card["rungs"]
        if rung["superbet_price"] is not None
    )
    stated = re.search(
        r"wycenił (\d+) szczebli propowych POWYŻEJ i (\d+) PONIŻEJ", rendered
    )
    assert stated, "the derived sentence is missing"
    assert int(stated.group(1)) == priced["OVER"]
    assert int(stated.group(2)) == priced["UNDER"]


def test_the_exclusion_note_counts_all_three_tables_independently(
    rendered, payload
):
    import re

    from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY

    note = re.search(
        r"\*\*Poniżej progu:\*\* (\d+) kart drużynowych \(próg (\d+)%\), "
        r"(\d+) propowych POWYŻEJ \(próg (\d+)%\) i (\d+) propowych PONIŻEJ "
        r"\(próg (\d+)%\)",
        rendered,
    )
    assert note, "the three-way exclusion note is missing"

    def below(is_player: bool, floor: float, direction: str | None) -> int:
        count = 0
        for card in payload["cards"]:
            if card["market"].startswith("player_") is not is_player:
                continue
            if is_player and card["sample"]["size"] < 5:
                continue
            informative = [
                r["p_honest"]
                for r in card["rungs"]
                if r["p_honest"] is not None
                and (direction is None or r["direction"] == direction)
                and not (
                    r["p_central"] is not None
                    and r["p_central"] >= MAX_COUNT_MODEL_PROBABILITY
                )
            ]
            if informative and max(informative) < floor:
                count += 1
        return count

    assert int(note.group(1)) == below(False, int(note.group(2)) / 100, None)
    assert int(note.group(3)) == below(True, int(note.group(4)) / 100, "OVER")
    assert int(note.group(5)) == below(True, int(note.group(6)) / 100, "UNDER")
