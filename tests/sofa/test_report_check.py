"""bet.sofa.report_check and the PostToolUse hook that runs it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from bet.sofa.report_check import findings
from scripts.sofa import check_analyst_report

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "check_analyst_report.py"


def report(reads: list[dict[str, object]], body: str) -> str:
    return f"# Analiza\n\n{body}\n\n```json reads\n{json.dumps(reads)}\n```\n"


def keep(eid: int, reason: str) -> dict[str, object]:
    return {
        "sofascore_event_id": eid,
        "market": "corners_total",
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "verdict": "KEEP",
        "author": "analyst",
        "reason": reason,
    }


DEEP = (
    "rożne: Dewa 10.2 / Persijap 9.1 śr., 15/18 > 7.5; tabela 2. vs 18.; "
    "pogoda bez opadów [WEB: bmkg.go.id, publ. 10-20, fetched 06:20Z]"
)
GOOD_BODY = (
    "Dossier przeczytane.\n\n### Dewa - Persijap\nKontekst (web): nic istotnego."
)


def test_a_deep_report_is_clean() -> None:
    assert findings(report([keep(1, DEEP)], GOOD_BODY)) == []


def test_a_bare_count_keep_and_a_missing_context_pass_are_findings() -> None:
    found = findings(report([keep(1, "15/18"), keep(2, DEEP)], GOOD_BODY))
    assert any(f.startswith("KEEP BEZ UZASADNIENIA") and "15/18" in f for f in found)
    assert any(f.startswith("KONTEKST: 2 meczów") for f in found)


def test_no_dossier_mention_and_an_unsourced_context_removal() -> None:
    watch = dict(
        keep(1, "trener zwolniony wczoraj, szatnia podzielona"),
        verdict="WATCH",
        context="MORALE",
    )
    found = findings(report([watch], "### Mecz\nKontekst (web): plotki."))
    assert any(f.startswith("DOSSIER") for f in found)
    assert any(f.startswith("ŹRÓDŁO") and "MORALE" in f for f in found)
    sourced = dict(
        watch,
        reason="trener zwolniony [WEB: sport.pl, publ. 10-19, "
        "fetched 07:00Z] - niepotwierdzone",
    )
    assert not any(
        f.startswith("ŹRÓDŁO") for f in findings(report([sourced], "dossier ok"))
    )


def test_cli_exit_codes(tmp_path: Path) -> None:
    good, bad = tmp_path / "a_analiza_x.md", tmp_path / "b_analiza_x.md"
    good.write_text(report([keep(1, DEEP)], GOOD_BODY))
    bad.write_text(report([keep(1, "15/18")], GOOD_BODY))
    assert check_analyst_report.main(["--report", str(good)]) == 0
    assert check_analyst_report.main(["--report", str(good), "--report", str(bad)]) == 1
    assert check_analyst_report.main(["--report", str(tmp_path / "none.md")]) == 2


def run_hook(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env={"CLAUDE_PROJECT_DIR": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


def test_hook_sends_findings_back_on_a_shallow_report(tmp_path: Path) -> None:
    path = tmp_path / "2026-10-20_analiza_football_kupon_1200_1.md"
    path.write_text(report([keep(1, "15/18")], GOOD_BODY))
    command = f"cat > {path} <<'MD'\n...\nMD"
    done = run_hook(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp_path)}
    )
    assert done.returncode == 2 and "KEEP BEZ UZASADNIENIA" in done.stderr
    path.write_text(report([keep(1, DEEP)], GOOD_BODY))
    assert (
        run_hook({"tool_name": "Bash", "tool_input": {"command": command}}).returncode
        == 0
    )


def test_hook_ignores_other_commands_and_tools() -> None:
    assert (
        run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}).returncode == 0
    )
    assert run_hook({"tool_name": "Read", "tool_input": {}}).returncode == 0
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 0
