"""No live sofa agent or skill may tell an analyst to call a bzzoiro tool.

sofa reads Sofascore statistics and Superbet prices and nothing else, and the
agents' own descriptions say bzzoiro "must never be called". Until 2026-09-23
the football protocol still said to call `get_match_detail` for the status and
tag it `[BZZOIRO-MCP: ...]`, to read lineups with `get_match_lineups`, and to
weight game scripts off `compare_odds` - instructions the tool list could not
even satisfy. The word "bzzoiro" is allowed (the prohibitions name it); its
tool names and tags are not.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

LIVE = [
    *sorted((REPO / ".claude" / "agents").glob("sofa-*.md")),
    *sorted((REPO / ".claude" / "commands").glob("sofa-*.md")),
    # The Polish orchestration doc told the football analyst the same thing.
    *[p for p in sorted((REPO / "docs" / "sofa").glob("*.md"))],
    *[
        p
        for d in ("sofa-pipeline", "sofa-analysis-core", "football-analysis",
                  "tennis-analysis")
        for p in sorted((REPO / ".claude" / "skills" / d).rglob("*.md"))
    ],
]

FORBIDDEN = re.compile(
    r"get_match_detail|get_match_lineups|compare_odds|get_best_odds|"
    r"get_standings|get_team_fixtures|get_team_squad|get_match_h2h|"
    r"BZZOIRO-MCP|BZZOIRO-ODDS|mcp__bzzoiro"
)


def test_the_live_sofa_config_is_found():
    assert len(LIVE) >= 8, [p.name for p in LIVE]


def test_no_live_sofa_file_names_a_bzzoiro_tool():
    offenders = [
        f"{p.relative_to(REPO)}:{i}: {line.strip()[:80]}"
        for p in LIVE
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert not offenders, "\n".join(offenders)
