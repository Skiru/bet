"""The day's KUPON pdf + html copied to the operator's iCloud Drive - a copy
for reading on the phone, never a source: nothing in the pipeline reads it.

    <iCloud Drive>/Kupony/<DD.MM.YYYY>/KUPON_<d>.pdf, KUPON_<d>.html

(operator 2026-10-25: the folder layout he had kept by hand since 10-21).
`build_coupon_pdf.py` calls `sync_day` after every render of the day's own
coupon - a print, every rebuild, a results render - and
`build_coupon_html.py` after the page alone, so the copy is always the newest
render: each file is copied beside its target and swapped in with
`os.replace` (a reader never sees half a PDF), with the local file's mtime.

Only the real day is copied: a render under another runs directory (a scratch
rebuild, a test) never reaches iCloud - a scratch rebuild once overwrote the
real coupon (2026-09-23). `SOFA_ICLOUD_KUPONY_DIR` names the destination
root explicitly (any runs directory; empty = off). A machine without iCloud
Drive is SKIPPED, not a failure.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
REAL_RUNS_DIR = _REPO / "runs" / "sofa"
ICLOUD_DRIVE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
FOLDER = "Kupony"
ENV = "SOFA_ICLOUD_KUPONY_DIR"

OK, SKIPPED, FAILED = "OK", "SKIPPED", "FAILED"


@dataclass(frozen=True)
class SyncResult:
    status: str
    detail: str
    copied: tuple[str, ...] = ()

    def as_json(self) -> dict[str, object]:
        return {"status": self.status, "detail": self.detail,
                "copied": list(self.copied)}


def coupon_files(date: str) -> tuple[str, str]:
    return f"KUPON_{date}.pdf", f"KUPON_{date}.html"


def day_folder(date: str) -> str:
    """2026-10-25 -> 25.10.2026, the operator's own folder names."""
    return datetime.date.fromisoformat(date).strftime("%d.%m.%Y")


def destination_root(runs_dir: str | Path) -> tuple[Path | None, str]:
    """(root, why) - root None means do not copy, `why` says why."""
    explicit = os.environ.get(ENV)
    if explicit is not None:
        if not explicit.strip():
            return None, f"{ENV} empty (off)"
        return Path(explicit).expanduser(), f"{ENV}"
    if Path(runs_dir).resolve() != REAL_RUNS_DIR.resolve():
        return None, f"runs dir {runs_dir} is not the real {REAL_RUNS_DIR}"
    if not ICLOUD_DRIVE.is_dir():
        return None, f"no iCloud Drive at {ICLOUD_DRIVE}"
    return ICLOUD_DRIVE / FOLDER, "iCloud Drive"


def sync_day(runs_dir: str | Path, date: str) -> SyncResult:
    """Copy the day's KUPON pdf / html (those that exist) over the iCloud
    copy. Never raises: a failure is FAILED with the reason."""
    root, why = destination_root(runs_dir)
    if root is None:
        return SyncResult(SKIPPED, why)
    run = Path(runs_dir) / date
    sources = [run / name for name in coupon_files(date) if (run / name).exists()]
    if not sources:
        return SyncResult(SKIPPED, f"no KUPON_{date}.pdf / .html in {run}")
    dest = root / day_folder(date)
    copied: list[str] = []
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for src in sources:
            tmp = dest / f".{src.name}.partial"
            shutil.copy2(src, tmp)
            os.replace(tmp, dest / src.name)
            copied.append(src.name)
    except OSError as exc:
        return SyncResult(FAILED, f"{dest}: {type(exc).__name__}: {exc}",
                          tuple(copied))
    return SyncResult(OK, str(dest), tuple(copied))


def _md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - a content check, not security
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def differences(runs_dir: str | Path, date: str) -> tuple[Path | None, list[str]]:
    """(the day's iCloud folder or None when not copied here, the files whose
    iCloud copy is missing or differs from the local render)."""
    root, _ = destination_root(runs_dir)
    if root is None:
        return None, []
    run = Path(runs_dir) / date
    dest = root / day_folder(date)
    out: list[str] = []
    for name in coupon_files(date):
        local, remote = run / name, dest / name
        if not local.exists():
            continue
        if not remote.exists():
            # an evicted file ("Optimise Mac Storage") is a placeholder here
            evicted = (dest / f".{name}.icloud").exists()
            out.append(f"{name} {'evicted, not compared' if evicted else 'missing'}")
        elif (remote.stat().st_size != local.stat().st_size
              or _md5(remote) != _md5(local)):
            out.append(f"{name} differs")
    return dest, out
