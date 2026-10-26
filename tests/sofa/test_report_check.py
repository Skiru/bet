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
    "Dossier przeczytane.\n\n### Dewa - Persijap · sofa:1\n"
    "**Fakty zabójcze (przed siecią):** deszcz, rezerwowy skład\n"
    "Kontekst (web): nic istotnego."
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
    assert any(f.startswith("USUNIĘCIE BEZ FAKTU") and "WATCH" in f for f in found)
    sourced = dict(
        watch,
        reason="trener zwolniony [WEB: sport.pl, publ. 10-19, "
        "fetched 07:00Z] - niepotwierdzone",
    )
    assert not any(
        f.startswith(("ŹRÓDŁO", "USUNIĘCIE"))
        for f in findings(report([sourced], "dossier ok"))
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


def test_a_removal_needs_a_dated_fact_or_a_named_defect() -> None:
    """10-26 grading: 19 of 24 WATCHes rested on h2h, form, the table or a
    model-vs-sample gap - what the price and the code already carry."""
    def removal(reason: str) -> dict[str, object]:
        return dict(keep(1, reason), verdict="WATCH")

    streak = removal("Técnico bez gola w 4 ostatnich, h2h 0/4, luka model-próbka")
    defect = removal("DEFEKT: próbka z kortów otwartych, mecz w hali (02_fixtures)")
    fact = removal("bramkarz rezerwowy [WEB: nhl.com, publ. 10-26 15:00Z, fetched 16:00Z]")
    undated = removal("bramkarz rezerwowy [WEB: nhl.com, fetched 16:00Z]")
    def bad(r: dict[str, object]) -> bool:
        return any(f.startswith("USUNIĘCIE BEZ FAKTU")
                   for f in findings(report([r], GOOD_BODY)))
    assert bad(streak) and bad(undated)
    assert not bad(defect) and not bad(fact)


def test_undated_tags_missing_kill_facts_and_a_match_wide_keep() -> None:
    body = ("Dossier.\n\n### A - B · sofa:1\nKontekst (web): nic "
            "[WEB: bbc.com, fetched 08:00Z]\n\n### C - D · sofa:2\n"
            "[wcześniej: r1.md] Kontekst (web): delta, nic nowego\n")
    wide = dict(keep(1, DEEP), market=None)
    found = findings(report([wide, keep(2, DEEP)], body))
    assert any(f.startswith("TAG WEB BEZ DATY: 1 z ") for f in found)
    # the delta section of match 2 inherits its kill facts
    assert any(f.startswith("FAKTY ZABÓJCZE: mecze 1 ") for f in found)
    assert any(f.startswith("KEEP ZBIORCZY") for f in found)


def test_the_verdict_rules_bind_from_the_next_day_only() -> None:
    """Operator's go 2026-10-26: the sourced-removal and per-family KEEP
    rules change reads, so they bind reports of days from 2026-10-27 - a
    later round of the built 10-26 keeps the old rules; the hook and the CLI
    take the day from the file name."""
    from bet.sofa.report_check import report_day

    streak = dict(keep(1, "seria 0/4 w h2h, forma"), verdict="WATCH")
    wide = dict(keep(1, DEEP), market=None)
    text = report([streak, wide], GOOD_BODY)
    assert report_day("2026-10-26_analiza_football_r3.md") == "2026-10-26"
    assert report_day("x/2026-10-27_weryfikacja.md") == "2026-10-27"
    old = findings(text, "2026-10-26")
    new = findings(text, "2026-10-27")
    assert not any(f.startswith(("USUNIĘCIE", "KEEP ZBIORCZY")) for f in old)
    assert any(f.startswith("USUNIĘCIE") for f in new)
    assert any(f.startswith("KEEP ZBIORCZY") for f in new)
