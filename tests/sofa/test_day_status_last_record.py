"""day_status.last_jsonl_record reads a record longer than its first window.

2026-10-21 11:33Z: the basketball snapshot's last line was 88 KB and the fixed
64 KB tail held no complete line, so day_status called the sport BROKEN ("no
readable record") on a healthy file.
"""

import json
from pathlib import Path

from scripts.sofa.day_status import last_jsonl_record


def _write(path: Path, records: list[dict[str, object]], torn: str = "") -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + torn,
                    encoding="utf-8")


def test_a_last_line_longer_than_the_window_is_read(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    big = {"fetched_at_utc": "2026-10-21T11:09:09Z", "pad": "x" * 90_000}
    _write(path, [{"fetched_at_utc": "2026-10-21T10:00:00Z"}, big])
    rec = last_jsonl_record(path, chunk=1 << 16)
    assert rec is not None and rec["fetched_at_utc"] == "2026-10-21T11:09:09Z"


def test_a_torn_last_line_falls_back_to_the_one_before(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    _write(path, [{"fetched_at_utc": "a"}, {"fetched_at_utc": "b"}],
           torn='{"fetched_at_utc": "c", "pad": "')
    rec = last_jsonl_record(path, chunk=16)
    assert rec is not None and rec["fetched_at_utc"] == "b"


def test_no_record_at_all(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    assert last_jsonl_record(path, chunk=4) is None
