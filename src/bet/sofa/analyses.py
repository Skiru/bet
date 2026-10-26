"""The analysts' match sections, one store per day (`analyses.json`).

A day's reads are one-line reasons on the legs (`reads.json`); the analysis
behind them - the dossier read, the sample, the web context pass, the buy /
kill case - lives in the reports (`<d>_analiza_<sport>[_<i>][_r<n>].md`,
`<d>_weryfikacja*.md`), several dozen files a day after the C3 rounds
(2026-10-25: 50 files, 1.4 MB). Nobody could find the section behind a leg.

This module cuts every report into its match sections and keeps them by
match: `merge_reads.py` records each merged report, `build_analyses.py`
rebuilds the store from the files on disk. The HTML view shows a match's
sections folded under each of its legs, the PDF in an appendix, and
`read_set.py` points an analyst at the earlier section of a match it is
handed again (`prior_analysis`), so the context pass is not redone from
nothing. Display and process only: nothing here changes a confidence, a
gate or a verdict.

A section is a heading (`##` / `###` / `####`) naming one match: by the
`sofa:<event id>` token the event protocol puts in the heading (or on the
first lines below it), else by both team names of a match the caller knows.
It runs to the next heading of the same or a higher level.
"""

from __future__ import annotations

import datetime
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bet.sofa.atomic import write_atomic

STORE = "analyses.json"
VERSION = 1
# The token a match heading carries (event protocol): "sofa:15275920".
EVENT_TOKEN = re.compile(r"sofa:(\d+)")
_HEADING = re.compile(r"^(#{2,4})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
# The token may sit on the first lines under the heading instead - on a line
# of its own ("`sofa:123`", "**Sofascore:** sofa:123"), never a token cited
# in a sentence ("8 nóg z meczu SC Bern - Lugano, sofa:1634...").
TOKEN_LOOKAHEAD_LINES = 3
TOKEN_LINE = re.compile(r"^[\s*_`>\-]*(?:[\w ]{0,20}:\**\s*)?`?sofa:(\d+)`?\W*$", re.I)
# A report's own headings, never a match's section whatever they cite.
NOT_A_MATCH = re.compile(
    r"^\W*(nag[łl][oó]wek|zdj[eę]te|czego zabrak[łl]o|nie podano|punkt decyzji"
    r"|podsumowanie|ekspozycja|vetoes|reads)\b", re.I)
_FENCE = re.compile(r"^[ \t]*```.*?(?:^[ \t]*```[^\n]*$|\Z)", re.M | re.S)
WEB_TAG = re.compile(r"\[WEB:", re.I)
CONTEXT_HEAD = re.compile(r"kontekst\s*\(web\)", re.I)
# A delta section (a re-read citing the earlier one) is not a full pass.
DELTA_MARK = re.compile(r"\[wcze[sś]niej:", re.I)
# A section kept whole up to this size; a longer one is cut (a report that
# pasted an artifact into a match section).
MAX_SECTION_CHARS = 30_000
# A word of a side's name that counts in the loose match (not "fc", "de").
MIN_WORD = 4
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-"})


def fold(text: str) -> str:
    """Casefolded, accents stripped, dashes one '-', spaces one."""
    norm = unicodedata.normalize("NFKD", text.translate(_DASHES))
    plain = "".join(c for c in norm if not unicodedata.combining(c))
    return " ".join(plain.casefold().split())


def sides(match: str) -> tuple[str, str] | None:
    """('home', 'away') of "Home - Away" folded; None when not two sides."""
    folded = fold(match)
    for sep in (" - ", " vs ", " v "):
        if sep in folded:
            home, away = folded.split(sep, 1)
            if home.strip() and away.strip():
                return home.strip(), away.strip()
    return None


def author_of(path: Path) -> str:
    """The verifier writes `<d>_weryfikacja*.md`; every other report is an
    analyst's."""
    return "verifier" if "weryfikacja" in path.name else "analyst"


def _words(side: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", side) if len(w) >= MIN_WORD}


def _event_by_name(heading: str, names: Mapping[int, tuple[str, str]],
                   hint: set[int]) -> int | None:
    """The one known match both of whose sides the heading names; failing
    that, among the matches the report itself read (`hint`), the one match
    each of whose sides shares a word with the heading ("Olympiacos - PS
    Kalamata" for "Olympiacos FC - Kalamata")."""
    folded = fold(heading)
    hits = [eid for eid, (home, away) in names.items()
            if home in folded and away in folded]
    if len(hits) == 1:
        return hits[0]
    # one side a substring of another match's side ("Ajax" / "Jong Ajax"):
    # the longest names win when they are one match
    if hits:
        best = max(len(names[e][0]) + len(names[e][1]) for e in hits)
        top = [e for e in hits if len(names[e][0]) + len(names[e][1]) == best]
        return top[0] if len(top) == 1 else None
    words = set(re.findall(r"[a-z0-9]+", folded))
    loose = [eid for eid in hint if eid in names
             and _words(names[eid][0]) & words and _words(names[eid][1]) & words]
    return loose[0] if len(loose) == 1 else None


def read_event_ids(text: str) -> set[int]:
    """The matches the report's ```json reads / vetoes arrays name."""
    out: set[int] = set()
    for body in re.findall(r"```json[^\n]*\n(.*?)```", text, re.S):
        try:
            data = json.loads(body)
        except ValueError:
            continue
        if isinstance(data, list):
            out |= {int(e["sofascore_event_id"]) for e in data
                    if isinstance(e, dict)
                    and isinstance(e.get("sofascore_event_id"), int)}
    return out


def split_sections(text: str, matches: Mapping[int, str] | None = None
                   ) -> list[dict[str, Any]]:
    """Every match section of one report: event id, heading, markdown (the
    heading included), its `[WEB:` tag count, whether it has a context
    pass and whether it is a delta pass over an earlier section. A heading
    that names no match is not a section, nor is a report's own heading
    (Nagłówek, Zdjęte, Czego zabrakło, NIE PODANO ...) whatever it cites;
    a heading inside a ``` fence is no heading. The fenced JSON blocks never
    sit inside a section."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    names = {int(e): pair for e, m in (matches or {}).items()
             if (pair := sides(m))}
    hint = read_event_ids(text)
    fenced = [(f.start(), f.end()) for f in _FENCE.finditer(text)]
    heads = [h for h in _HEADING.finditer(text)
             if not any(a <= h.start() < b for a, b in fenced)]
    out: list[dict[str, Any]] = []
    for i, h in enumerate(heads):
        level = len(h.group(1))
        end = len(text)
        for nxt in heads[i + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        body = text[h.start():end]
        fence = body.find("```json")
        if fence >= 0:
            body = body[:fence]
        if NOT_A_MATCH.match(h.group(2)):
            continue
        # a sub-heading of a section already taken (a level-3 "Kontekst"
        # inside a level-2 match) is part of it, never a second section -
        # whatever match it cites, unless its own heading names one by token
        token = EVENT_TOKEN.search(h.group(2))
        if out and out[-1]["_end"] >= end and token is None:
            continue
        if token is None:
            # a token line right under this heading, never a nested heading's
            for line in body.split("\n")[1:TOKEN_LOOKAHEAD_LINES + 1]:
                if line.lstrip().startswith("#"):
                    break
                token = TOKEN_LINE.match(line) or token
                if token:
                    break
        eid = int(token.group(1)) if token else _event_by_name(h.group(2), names, hint)
        if eid is None:
            continue
        if out and out[-1]["_end"] >= end and out[-1]["event_id"] == eid:
            continue
        body = body.rstrip()
        if len(body) > MAX_SECTION_CHARS:
            body = body[:MAX_SECTION_CHARS].rstrip() + "\n\n… (sekcja ucięta)"
        out.append({
            "event_id": eid,
            "heading": EVENT_TOKEN.sub("", h.group(2)).strip(" ·-—|"),
            "markdown": body,
            "web_tags": len(WEB_TAG.findall(body)),
            "context_pass": bool(CONTEXT_HEAD.search(body)),
            "delta": bool(DELTA_MARK.search(body)),
            "_end": end,
        })
    for s in out:
        del s["_end"]
    return out


def load(run: Path) -> dict[str, Any]:
    """The day's store; an empty one when absent or unreadable (display
    only - a broken store never stops a render)."""
    path = run / STORE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": VERSION, "events": {}}
    if not isinstance(doc, dict) or not isinstance(doc.get("events"), dict):
        return {"version": VERSION, "events": {}}
    # a hand-edited store: only lists of sections survive
    doc["events"] = {
        str(k): [e for e in v if isinstance(e, dict)]
        for k, v in doc["events"].items() if isinstance(v, list)}
    return doc


def add_report(store: dict[str, Any], report: Path, author: str, at_utc: str,
               matches: Mapping[int, str] | None = None) -> int:
    """Record one report's sections (newest first per match); a report
    recorded again replaces its own earlier sections. Returns the count."""
    text = report.read_text(encoding="utf-8")
    events: dict[str, list[dict[str, Any]]] = store.setdefault("events", {})
    name = report.name
    for entries in events.values():
        entries[:] = [e for e in entries if e.get("report") != name]
    found = split_sections(text, matches)
    fresh: dict[str, list[dict[str, Any]]] = {}
    for s in found:
        entry = {"author": author, "report": name, "recorded_at_utc": at_utc, **s}
        del entry["event_id"]
        fresh.setdefault(str(s["event_id"]), []).append(entry)
    # newest report first; one report's sections of a match in its own order
    for key, entries in fresh.items():
        events[key] = entries + events.get(key, [])
    for key in [k for k, v in events.items() if not v]:
        del events[key]
    return len(found)


def save(run: Path, store: Mapping[str, Any]) -> Path:
    path = run / STORE
    write_atomic(path, json.dumps({**store, "version": VERSION}, ensure_ascii=False,
                                  indent=1) + "\n")
    return path


def match_names(doc: Mapping[str, Any]) -> dict[int, str]:
    """{event id: "Home - Away"} of every leg of an 11_coupon.json (singles,
    removed_by_reads, builders) - the names a heading without a token is
    matched against."""
    out: dict[int, str] = {}
    for src in ("singles", "removed_by_reads", "builders"):
        for leg in doc.get(src) or []:
            eid, match = leg.get("sofascore_event_id"), leg.get("match")
            if eid is not None and match:
                out.setdefault(int(eid), str(match))
    return out


def coupon_match_names(run: Path) -> dict[int, str]:
    """match_names of the day's 11_coupon.json (one full parse); {} when the
    artifact is absent or unreadable."""
    path = run / "11_coupon.json"
    if not path.exists():
        return {}
    try:
        return match_names(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def report_files(run: Path, day: str) -> list[Path]:
    """The day's analyst and verifier reports, oldest first (by mtime, then
    name) - the order they were merged in."""
    # a chat slip's reports (`_kupon_`) never reach the coupon's store
    files = [p for p in (*run.glob(f"{day}_analiza_*.md"),
                         *run.glob(f"{day}_weryfikacja*.md"))
             if "_kupon_" not in p.name]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))


def rebuild(run: Path, day: str, matches: Mapping[int, str] | None = None
            ) -> tuple[dict[str, Any], int]:
    """The store from every report on disk (the day before analyses.json,
    or after a hand edit). Returns (store, sections)."""
    store: dict[str, Any] = {"version": VERSION, "events": {}}
    names = coupon_match_names(run) if matches is None else matches
    n = 0
    for path in report_files(run, day):
        at = _mtime_utc(path)
        n += add_report(store, path, author_of(path), at, names)
    return store, n


def _mtime_utc(path: Path) -> str:
    return datetime.datetime.fromtimestamp(
        path.stat().st_mtime, datetime.UTC).isoformat(timespec="seconds")


def latest(store: Mapping[str, Any], event_id: Any,
           author: str | None = None) -> dict[str, Any] | None:
    """The newest section of a match (by one author when given)."""
    for entry in (store.get("events") or {}).get(str(event_id)) or []:
        if author is None or entry.get("author") == author:
            return dict(entry)
    return None


def full_pass(store: Mapping[str, Any], event_id: Any) -> dict[str, Any] | None:
    """The analysts' last full context pass on a match: the newest analyst
    section with a context pass that searched (a web source, or a check named
    UNVERIFIED - an ITF match, a volleyball six) and no delta mark."""
    for entry in (store.get("events") or {}).get(str(event_id)) or []:
        if (entry.get("author") == "analyst" and entry.get("context_pass")
                and not entry.get("delta")
                and (entry.get("web_tags")
                     or "UNVERIFIED" in str(entry.get("markdown") or ""))):
            return dict(entry)
    return None


def full_pass_at(store: Mapping[str, Any], event_id: Any) -> str | None:
    """When full_pass was recorded (None: never)."""
    entry = full_pass(store, event_id)
    return str(entry.get("recorded_at_utc") or "") or None if entry else None


def for_events(store: Mapping[str, Any], event_ids: Iterable[Any]
               ) -> dict[str, list[dict[str, Any]]]:
    """The store narrowed to these matches (the view inlines only them)."""
    events = store.get("events") or {}
    return {str(e): list(events[str(e)]) for e in event_ids if str(e) in events}
