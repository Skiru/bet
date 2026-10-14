"""Read-only: Superbet team name -> Sofascore id coverage across all sport_fixtures.json days.

Uses the real sport_identity.TeamResolver (sofa_entity verified + exact name index /
cs2_series index) on a read-only connection with now_ts = now. Listing caches read
directly from sofa_entity_events / sofa_listed_event (SofaCache() is NOT used: its
constructor runs migrate(), a write).
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from bet.sofa import cs2
from bet.sofa.names import normalize_name
from bet.sofa.sport_identity import SPORTS, TeamResolver

OUT = "docs/sofa/evidence/identity_coverage_2026-10-14/"
conn = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
NOW = int(time.time())
res = TeamResolver(conn, NOW)

# ---- 1. load + dedupe
recs: dict[str, dict] = {}
files = sorted(glob.glob("runs/sofa/*/sport_fixtures.json"))
days = []
for f in files:
    d = json.load(open(f))
    days.append(d["date"])
    for r in d["fixtures"]:
        r = dict(r, _file_date=d["date"], _created=d.get("created_at_utc"))
        key = r["superbet_event_id"]
        old = recs.get(key)
        if old is None or (r["_file_date"], r["_created"] or "") >= (old["_file_date"], old["_created"] or ""):
            recs[key] = r
print("files", len(files), days[0], "..", days[-1], "| missing days:",
      [x for x in (datetime.fromisoformat(days[0]) + timedelta(i) for i in range(
          (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(days[0])).days + 1))
       if x.strftime("%Y-%m-%d") not in days])


def key_of(sport, name):
    return cs2.esports_name(name) if sport == "cs2" else normalize_name(name)


def excluded(r):
    return r["status"] == "DUPLICATE_SUPERBET_TEAM" or "1x1" in (r.get("tournament") or "").lower()


def kick_day(r):
    return r["kickoff_utc"][:10]


SPORTS4 = ["hockey", "basketball", "volleyball", "cs2"]
by_sport = defaultdict(list)
for r in recs.values():
    by_sport[r["sport"]].append(r)

# id cache
_rid: dict = {}


def rid(sport, name):
    k = (sport, name)
    if k not in _rid:
        _rid[k] = res.team_id(sport, name)
    return _rid[k]


def side_ids(r):
    if r["status"] != "IDENTIFIED" or r.get("home_is_team1") is None:
        return None
    h, a = r.get("home_id"), r.get("away_id")
    return (h, a) if r["home_is_team1"] else (a, h)


def initials(name):
    s = unicodedata.normalize("NFKD", name.replace("ı", "i").replace("ł", "l")).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", s) if w]
    return "".join(w[0] for w in words).upper()


def acronym(name):
    s = re.sub(r"\([^)]*\)", " ", name).strip()
    s = re.sub(r"\s+", " ", s)
    return s if re.fullmatch(r"[A-Z]{2,5}", s) else None


def listing_candidates(team_id, kickoff, slug):
    """Events with team_id within 1 h of kickoff: sofa_entity_events next (latest only) + sofa_listed_event."""
    out = {}
    row = conn.execute("SELECT events_json FROM sofa_entity_events WHERE sofascore_entity_id=? AND kind='next' AND page=0",
                       (team_id,)).fetchone()
    src = set()
    if row:
        for e in json.loads(row[0]).get("events") or []:
            out[e.get("id")] = e
            src.add("entity_events")
    ts = int(kickoff.timestamp())
    for (txt,) in conn.execute("SELECT event_json FROM sofa_listed_event WHERE sport=? AND start_ts BETWEEN ? AND ?",
                               (slug, ts - 3600, ts + 3600)):
        e = json.loads(txt)
        if team_id in ((e.get("homeTeam") or {}).get("id"), (e.get("awayTeam") or {}).get("id")):
            out[e.get("id")] = e
            src.add("listed_event")
    keep = []
    for e in out.values():
        st = e.get("startTimestamp")
        if isinstance(st, int) and abs(st - ts) <= 3600 and team_id in (
                (e.get("homeTeam") or {}).get("id"), (e.get("awayTeam") or {}).get("id")):
            keep.append(e)
    return keep, (bool(row))


report = {}
top_never = []
for sport in SPORTS4:
    rs = by_sport[sport]
    slug = "esports" if sport == "cs2" else SPORTS[sport].sofascore_slug
    excl = [r for r in rs if excluded(r)]
    main = [r for r in rs if not excluded(r)]
    st = Counter(r["status"] for r in main)
    reasons = Counter(r.get("reason") for r in main if r["status"] != "IDENTIFIED")
    kdays = sorted({kick_day(r) for r in rs})
    print(f"\n===== {sport}: kickoff days {kdays[0]}..{kdays[-1]} ({len(kdays)}), events {len(rs)}, excluded(dup/1x1) {len(excl)} "
          f"{Counter(r['status'] for r in excl)}")
    print(" main events", len(main), dict(st))
    print(" not-identified reasons", dict(reasons.most_common()))

    # 2. names
    names = defaultdict(lambda: {"events": [], "tours": Counter()})
    for r in main:
        for nm in (r["team1"], r["team2"]):
            names[nm]["events"].append(r)
            names[nm]["tours"][r.get("tournament")] += 1
    keys = defaultdict(set)
    for nm in names:
        keys[key_of(sport, nm)].add(nm)
    unresolved = {nm for nm in names if rid(sport, nm) is None}
    unres_keys = {key_of(sport, nm) for nm in unresolved}
    print(f" distinct names exact {len(names)}, normalised {len(keys)}; unresolved now: exact {len(unresolved)}, keys {len(unres_keys)}")

    # 3. learning
    learned = defaultdict(set)   # key -> ids
    wrong_resolve = []
    for r in main:
        ids = side_ids(r)
        if not ids:
            continue
        for nm, sid in zip((r["team1"], r["team2"]), ids):
            if sid is None:
                continue
            cur = rid(sport, nm)
            if cur is None:
                learned[key_of(sport, nm)].add(sid)
            elif cur != sid:
                wrong_resolve.append((nm, cur, sid, r["superbet_event_id"]))
    learn_keys = set(learned)
    conflicts = {k: v for k, v in learned.items() if len(v) > 1}
    learn_names = {nm for nm in unresolved if key_of(sport, nm) in learn_keys}
    print(f" learnable: keys {len(learn_keys)}, exact names {len(learn_names)}; conflicts (key->2+ ids) {len(conflicts)}")
    for k, v in list(conflicts.items())[:10]:
        print("   CONFLICT", k, sorted(v))
    print(f" resolver id != identified side id: {len(wrong_resolve)} sides ({len({w[0] for w in wrong_resolve})} names)")
    for w in wrong_resolve[:8]:
        print("   MISRESOLVE", w)

    # events
    notid = [r for r in main if r["status"] != "IDENTIFIED"]
    aff = {nm for nm in unresolved if any(r["status"] != "IDENTIFIED" for r in names[nm]["events"])}
    print(f" unresolved names present in >=1 NOT_IDENTIFIED event: {len(aff)} (learnable among them {len(aff & learn_names)})")
    # causal learning: only from identified events with an earlier kickoff day
    first_learn = {}
    for r in sorted(main, key=lambda x: x["kickoff_utc"]):
        ids = side_ids(r)
        if not ids:
            continue
        for nm, sid in zip((r["team1"], r["team2"]), ids):
            if sid is not None and rid(sport, nm) is None:
                first_learn.setdefault(key_of(sport, nm), kick_day(r))
    causal = Counter(); causal_day = Counter(); by_reason = Counter()
    for r in notid:
        for nm in (r["team1"], r["team2"]):
            k = key_of(sport, nm)
            if rid(sport, nm) is None and k in first_learn:
                by_reason[r.get("reason")] += 1
                if first_learn[k] < kick_day(r):
                    causal["causal"] += 1; causal_day[kick_day(r)] += 1
                break
    print(f" (a) events by reason {dict(by_reason)}; causal (learned on an earlier kickoff day) {causal['causal']}, "
          f"last7 {sum(causal_day[d] for d in sorted({kick_day(x) for x in rs})[-7:])}")

    def sides_state(r):
        out = []
        for nm in (r["team1"], r["team2"]):
            if rid(sport, nm) is not None:
                out.append("res")
            elif key_of(sport, nm) in learn_keys and len(learned[key_of(sport, nm)]) == 1:
                out.append("learn")
            else:
                out.append("none")
        return out

    # 4. never identified + acronym
    never = unresolved - learn_names
    never_keys = {key_of(sport, n) for n in never}
    acr_results = {}
    for nm in never:
        a = acronym(nm)
        if not a:
            continue
        hits = misses = nocand = nolisting = 0
        examples = []
        for r in names[nm]["events"]:
            other = r["team2"] if r["team1"] == nm else r["team1"]
            oid = rid(sport, other)
            if oid is None:
                ok = learned.get(key_of(sport, other))
                oid = next(iter(ok)) if ok and len(ok) == 1 else None
            if oid is None:
                nolisting += 1
                continue
            ko = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
            cands, had_row = listing_candidates(oid, ko, slug)
            if not cands:
                nocand += 1
                continue
            m = False
            for e in cands:
                for sd in ("homeTeam", "awayTeam"):
                    t = e.get(sd) or {}
                    if t.get("id") != oid and initials(t.get("name") or "") == a:
                        m = True
                        examples.append((t.get("name"), t.get("id")))
            if m:
                hits += 1
            else:
                misses += 1
                examples.append(("MISS:" + "|".join(f"{(e.get('homeTeam') or {}).get('name')}-{(e.get('awayTeam') or {}).get('name')}" for e in cands), None))
        acr_results[nm] = dict(acr=a, hits=hits, misses=misses, nocand=nocand, other_unresolved=nolisting, ex=examples[:2])
    acr_ok_names = {nm for nm, v in acr_results.items() if v["hits"] > 0 and v["misses"] == 0}
    print(f" never-identified: exact {len(never)}, keys {len(never_keys)}; acronym-like {len(acr_results)}; "
          f"acronym hypothesis confirmed (hit, no miss) {len(acr_ok_names)}")
    for nm, v in sorted(acr_results.items(), key=lambda x: -len(names[x[0]]['events'])):
        print("   ACR", nm, v)

    lst = sorted(never, key=lambda n: -len(names[n]["events"]))
    for nm in lst[:30]:
        top_never.append((len(names[nm]["events"]), sport, nm, names[nm]["tours"].most_common(1)[0][0],
                          acr_results.get(nm, {}).get("acr")))

    # 5. impact
    def recov(r, with_acr):
        ss = sides_state(r)
        if with_acr:
            ss = ["learn" if (s == "none" and nm in acr_ok_names) else s for s, nm in zip(ss, (r["team1"], r["team2"]))]
        return ss
    cats = Counter()
    per_day_a = Counter()
    per_day_b = Counter()
    per_day_n = Counter()
    for r in notid:
        if r.get("reason") == "BRIDGE_ABORTED":
            cats["bridge_aborted"] += 1
        ss = sides_state(r)
        per_day_n[kick_day(r)] += 1
        if "none" not in ss and "learn" not in ss:
            cats["both_resolve_now_already"] += 1
        if "learn" in ss:
            cats["a_learnable_side"] += 1
            per_day_a[kick_day(r)] += 1
            if r.get("reason") == "TEAM_UNRESOLVED":
                cats["a_learnable_side_and_TEAM_UNRESOLVED"] += 1
        sb = recov(r, True)
        if "learn" in sb:
            cats["b_learn_or_acronym_side"] += 1
            per_day_b[kick_day(r)] += 1
        if "none" in ss and "learn" not in ss:
            cats["has_unresolved_unlearnable_side_only"] += 1
    nd = len(kdays)
    last7 = kdays[-7:]
    print(" impact over NOT_IDENTIFIED", len(notid), dict(cats))
    print(f"  per day (all {nd} kickoff days): notid {len(notid)/nd:.1f}, (a) {sum(per_day_a.values())/nd:.1f}, (b) {sum(per_day_b.values())/nd:.1f}")
    print(f"  last 7 days {last7[0]}..{last7[-1]}: notid {sum(per_day_n[d] for d in last7)/7:.1f}, "
          f"(a) {sum(per_day_a[d] for d in last7)/7:.1f}, (b) {sum(per_day_b[d] for d in last7)/7:.1f}")
    print("  by day notid/(a)/(b):", {d: (per_day_n[d], per_day_a[d], per_day_b[d]) for d in kdays})

print("\n===== TOP 30 never-identified names (all sports, by event count)")
for row in sorted(top_never, key=lambda x: -x[0])[:30]:
    print("  ", row)
