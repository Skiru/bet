"""A malformed config must leave a gate inert, never stop the run.

``analyze._load_json`` states the rule: "A config problem must degrade this
stage to the behaviour it had before the config existed, not empty the sheet."
Two of the three loaders that read through it broke that rule, and both were
found on 2026-09-02 by writing corrupted documents rather than by reading the
code:

* ``_load_market_priors`` called ``.items()`` on whatever ``"priors"`` held, so
  ``{"priors": "x"}`` raised AttributeError and aborted ANALYZE.
* ``tennis_match_format`` had its ``isinstance`` guard *inside* the
  comprehension, which evaluates ``formats.items()`` first and then tests a
  constant once per item -- so it had the same crash with none of the
  protection it appeared to have.

These matter on exactly one morning: the one where somebody edits a config
before the day's run. That is also the morning nobody wants to debug a stack
trace, which is why the degraded path is the contract and is tested here rather
than assumed.
"""
from __future__ import annotations

import pathlib
import statistics

import pytest

import bet.simple_stats.analyze as analyze
import bet.simple_stats.providers as providers

SAMPLE = [2.0, 4.0, 3.0, 2.0, 3.0]


@pytest.fixture
def corrupt(tmp_path, monkeypatch):
    """Point a config path at ``text`` for one test, caches cleared both ways.

    The attribute is looked up on whichever module owns the path. Two of these
    tables are read in ``providers.py`` -- the surface map and, since
    2026-09-03, the format map -- precisely so that ANALYZE and the ingest side
    cannot disagree about a tournament name; ``analyze.reset_scope_caches``
    already resets both caches, so the only thing that moved is where the
    constant lives.
    """

    def _write(attr: str, text: str) -> None:
        path = tmp_path / f"{attr}.json"
        path.write_text(text, encoding="utf-8")
        owner = analyze if hasattr(analyze, attr) else providers
        monkeypatch.setattr(owner, attr, path)
        analyze.reset_scope_caches()

    analyze.reset_scope_caches()
    yield _write
    analyze.reset_scope_caches()


# --- market priors ----------------------------------------------------------


@pytest.mark.parametrize(
    "document,why",
    [
        ("{ not json at all", "malformed"),
        ("[1, 2, 3]", "top level is not an object"),
        ("{}", "no priors key"),
        ('{"priors": "not a dict"}', "priors is a string"),
        ('{"priors": ["corners_for"]}', "priors is a list"),
        ('{"priors": {"corners_for": "not a dict"}}', "a block is a string"),
        ('{"priors": {"corners_for": {}}}', "a block has no mean"),
        ('{"priors": {"corners_for": {"mean": "4.7"}}}', "mean is a string"),
        ('{"priors": {"corners_for": {"mean": -1}}}', "mean is negative"),
        ('{"priors": {"corners_for": {"mean": true}}}', "mean is a bool"),
    ],
)
def test_a_broken_priors_file_leaves_the_sample_unshrunk(corrupt, document, why):
    """Not an exception, and not a zero: the raw sample mean, which is the
    behaviour this pipeline had before 2026-09-02."""
    corrupt("_MARKET_PRIORS_PATH", document)
    assert analyze.market_priors() == {}
    assert analyze.venue_market_priors() == {}
    assert analyze.shrunk_centre(SAMPLE, "corners_for") == pytest.approx(
        statistics.fmean(SAMPLE)
    )
    assert analyze.shrunk_centre(SAMPLE, "corners_for", "home") == pytest.approx(
        statistics.fmean(SAMPLE)
    )


def test_a_venue_prior_without_a_usable_pooled_one_is_refused(corrupt):
    """The incoherent state this prevents.

    With ``mean: 0`` failing validation and ``home: 5.2`` passing it, the home
    rows of that market shrank toward 5.2 (measured: centre 2.80 -> 4.40) while
    its away rows stayed on the raw mean, because they had no target and no
    fallback. Half a market priced one way and half the other is worse than
    either.
    """
    corrupt(
        "_MARKET_PRIORS_PATH",
        '{"priors": {"corners_for": {"mean": 0, "home": 5.2, "away": 4.2}}}',
    )
    assert analyze.venue_market_priors() == {}
    for venue in (None, "home", "away"):
        assert analyze.shrunk_centre(SAMPLE, "corners_for", venue) == pytest.approx(
            statistics.fmean(SAMPLE)
        )


def test_a_broken_venue_value_still_leaves_the_pooled_prior_working(corrupt):
    """The other direction, and it is not symmetric: the pooled prior is the
    fallback for every row, so a bad ``home`` value costs only the venue
    refinement."""
    corrupt(
        "_MARKET_PRIORS_PATH",
        '{"priors": {"corners_for": {"mean": 4.738, "home": "5.2", "away": -3}}}',
    )
    assert analyze.market_priors() == {"corners_for": 4.738}
    assert analyze.venue_market_priors() == {}
    pooled = analyze.shrunk_centre(SAMPLE, "corners_for")
    assert pooled == pytest.approx(analyze.shrunk_centre(SAMPLE, "corners_for", "home"))
    assert pooled != pytest.approx(statistics.fmean(SAMPLE))


def test_underscore_keys_are_documentation_and_not_markets(corrupt):
    """``config/market_priors.json`` carries its own reasoning under ``_why``,
    ``_limits`` and friends. Those live beside ``priors`` today, but a key
    starting with an underscore is skipped inside it too, so moving one in
    cannot invent a market."""
    corrupt(
        "_MARKET_PRIORS_PATH",
        '{"priors": {"_why": {"mean": 4.7}, "corners_for": {"mean": 4.738}}}',
    )
    assert analyze.market_priors() == {"corners_for": 4.738}


# --- tennis format ----------------------------------------------------------


@pytest.mark.parametrize(
    "document",
    [
        "{ not json",
        '{"formats": "nope"}',
        '{"formats": ["ATP US Open"]}',
        '{"formats": 5}',
        "{}",
    ],
)
def test_a_broken_tennis_format_file_leaves_the_gate_inert(corrupt, document):
    """None, not BO3. Guessing best-of-three from a name is how the sheet came
    to price a men's Grand Slam off a best-of-three sample in the first place,
    and a crash here would take the whole football slate down with it."""
    corrupt("_TENNIS_FORMAT_MAP_PATH", document)
    assert analyze.tennis_match_format("ATP US Open") is None
    assert analyze.tennis_match_format(None) is None


# --- tennis tournamentId table (step 2, source consolidation) ---------------


@pytest.mark.parametrize(
    "document",
    [
        "{ not json",
        '{"tournaments": "nope"}',
        '{"tournaments": ["189"]}',
        '{"tournaments": {"189": "Hard"}}',
        '{"tournaments": {"189": {"surface": "hardcourt", "level": "SLAM"}}}',
        "{}",
    ],
)
def test_a_broken_tennis_tournament_file_leaves_the_lookup_inert(corrupt, document):
    """Same contract as the name-keyed tables: a corrupted or unrecognised
    entry must read as unknown, never as a guessed surface or draw class that
    could silently delete real observations."""
    corrupt("_TENNIS_TOURNAMENT_MAP_PATH", document)
    assert providers.tennis_tournament_by_id("189") is None
    assert providers.tennis_tournament_by_id(None) is None


def test_the_real_configs_on_disk_load(tmp_path):
    """A guard against shipping a config the loaders silently reject. Both
    files are pinned data this pipeline prices from, and "degrades quietly" is
    the right behaviour for a corrupted one and the wrong outcome to discover
    in production."""
    analyze.reset_scope_caches()
    try:
        assert pathlib.Path(analyze._MARKET_PRIORS_PATH).exists()
        priors = analyze.market_priors()
        by_venue = analyze.venue_market_priors()
        assert len(priors) > 40, len(priors)
        assert len(by_venue) == 26, len(by_venue)
        # Every venue prior has the pooled one the loader now insists on.
        for market, _venue in by_venue:
            assert market in priors
        assert analyze.tennis_match_format("ATP US Open") == "BO5"
        assert pathlib.Path(providers._TENNIS_TOURNAMENT_MAP_PATH).exists()
        assert providers.tennis_tournament_by_id("189") == {
            "surface": "Hard", "level": "GRAND_SLAM",
        }
    finally:
        analyze.reset_scope_caches()
