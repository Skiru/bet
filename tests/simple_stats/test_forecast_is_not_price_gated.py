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


def test_the_file_accounts_for_every_card_it_leaves_out(rendered, payload):
    """A summary table excludes things; the objection was to not saying so.

    The first version of this note reported only cards whose entire ladder sat
    at the count model's clamp -- zero on a real board -- while the mechanism
    that actually removed 2,781 prop cards from the table went unmentioned.
    Every count in the note is derived from the day's own cards, and this test
    re-derives them independently.
    """
    import re

    from bet.simple_stats.analyze import MAX_COUNT_MODEL_PROBABILITY

    note = re.search(
        r"\*\*Poniżej progu:\*\* (\d+) kart drużynowych \(próg (\d+)%\) i "
        r"(\d+) kart zawodników \(próg (\d+)%\)",
        rendered,
    )
    assert note, "the exclusion note is missing"
    team_stated, team_floor, player_stated, player_floor = (
        int(note.group(1)), int(note.group(2)) / 100,
        int(note.group(3)), int(note.group(4)) / 100,
    )

    def below(is_player: bool, floor: float) -> int:
        count = 0
        for card in payload["cards"]:
            if card["market"].startswith("player_") is not is_player:
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
            if informative and max(informative) < floor:
                count += 1
        return count

    assert team_stated == below(False, team_floor)
    assert player_stated == below(True, player_floor)


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
