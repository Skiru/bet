"""Women's and reserve sides reach Sofascore's search (2026-09-28).

190 of 228 women's fixtures on the 2026-09-23..28 boards failed RESOLVE. Two
causes, both measured that day:

- the search was sent our own cache key, "(w)"/"(r)" included, and Sofascore
  returns nothing for "chicago red stars (w)" or "ca penarol (r)" - live, six of
  six empty, each found without the marker;
- the gender gate read only competition-name markers, which have no word for
  "NWSL", "WE-League" or "Liga F": 4,919 cached women's events read as men's.

Without the marker the search ranks the men's club first ("rio ave" -> Rio Ave,
Rio Ave U23, Rio Ave FC U19, then the women's Rio Ave FC), so the three
candidates are filtered on Sofascore's own `gender` before they are counted.
"""

from datetime import UTC, datetime

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver, search_query, sofascore_gender

KICKOFF = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


def _team(id_: int, name: str, gender: str) -> dict:
    return {"id": id_, "name": name, "gender": gender, "sport": {"slug": "football"}}


class _Client:
    """Sofascore as measured: nothing for a marked query, men's club first."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, q: str):
        self.queries.append(q)
        if "(" in q:
            return {"results": []}
        return {
            "results": [
                {"type": "team", "entity": _team(3036, "Rio Ave", "M")},
                {"type": "team", "entity": _team(292852, "Rio Ave U23", "M")},
                {"type": "team", "entity": _team(78123, "Rio Ave FC U19", "M")},
                {"type": "team", "entity": _team(900, "Rio Ave FC", "F")},
            ]
        }

    def entity_events(self, entity_id: int, kind: str, page: int):
        if entity_id != 900 or page > 0:
            return {"events": [], "hasNextPage": False}
        return {
            "events": [
                {
                    "id": 5001,
                    "startTimestamp": int(KICKOFF.timestamp()),
                    # A women's league whose name carries no women's marker.
                    "tournament": {"name": "Liga BPI", "slug": "liga-bpi"},
                    "homeTeam": {"name": "Valadares Gaia", "gender": "F"},
                    "awayTeam": {"name": "Rio Ave FC", "gender": "F"},
                }
            ],
            "hasNextPage": False,
        }


def test_search_query_drops_our_squad_markers() -> None:
    assert search_query("chicago red stars (w)") == "chicago red stars"
    assert search_query("ca penarol (r)") == "ca penarol"
    assert search_query("rio ave") == "rio ave"


def test_gender_comes_from_the_teams_before_the_competition_name() -> None:
    nwsl = {
        "tournament": {"name": "NWSL", "slug": "nwsl"},
        "homeTeam": {"name": "NJ/NY Gotham FC", "gender": "F"},
        "awayTeam": {"name": "Chicago Stars FC", "gender": "F"},
    }
    assert sofascore_gender(nwsl) == "W"
    # No gender field at all: the competition-name fallback still applies.
    legacy = {"tournament": {"name": "Liga F Women"}, "homeTeam": {}, "awayTeam": {}}
    assert sofascore_gender(legacy) == "W"


def test_womens_side_resolves_past_the_mens_candidates(tmp_path) -> None:
    config = SofaConfig(db_path=str(tmp_path / "t.db"))
    migrate(config.db_path)
    client = _Client()
    resolver = SofaResolver(config, client, SofaCache(config))  # type: ignore[arg-type]

    entity_id, event, ambiguous = resolver.resolve_entity(
        "football",
        "Rio Ave (K)",
        KICKOFF,
        "Valadares Gaia (K)",
        board_side_a="Valadares Gaia (K)",
        board_side_b="Rio Ave (K)",
    )

    assert client.queries == ["rio ave"]
    assert (entity_id, ambiguous) == (900, False)
    assert event is not None and event["id"] == 5001
    # The cache key keeps the marker: the men's Rio Ave never shares it.
    assert normalize_name("Rio Ave (K)") == "rio ave (w)"
