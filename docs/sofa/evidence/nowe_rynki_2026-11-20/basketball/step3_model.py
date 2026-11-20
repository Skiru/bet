"""Steps 2-3: the installed player model's pre-game number for every active
milestone selection (N+ = OVER N-0.5 of the two-sided family SHADOW reads)
and the three marginals P(pts>=10), P(reb>=10), P(ast>=10) for every
double-double player, computed exactly as SHADOW computes a pre-game row
(player_model.forecast_records, pinned teams, the quote's own clock), then
graded from the stored box (shadow.build_player_box + the settle's name
matchers). Read-only DB (mode=ro), keyed queries only, one event at a time.

Output: out/scored.jsonl (one row per milestone selection or DD player).
"""
from __future__ import annotations

import gc
import json
import os
import resource
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet",
                "/Users/mkoziol/projects/bet/scripts/sofa"]

from bet.sofa import player_model, shadow  # noqa: E402
from bet.sofa.players import (  # noqa: E402
    match_player, match_player_by_surname, match_player_by_tokens)
from run_shadow import pinned_teams  # noqa: E402

S = os.path.join(os.path.dirname(__file__), "out")
DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
RUNS = "/Users/mkoziol/projects/bet/runs/sofa"
DAYS = ("2026-11-06", "2026-11-19")
CANON = {"player_points": 233565, "player_rebounds": 233567,
         "player_assists": 233566, "player_pts_reb_ast": 233569,
         "player_threes": 233568}
SPORT = shadow.SPORTS["basketball"]


def matched_stats(subject: str, box: shadow.PlayerBox):
    """The box entry the settle's player_value would read (same matchers)."""
    m = (match_player(subject, box.players)
         or match_player_by_tokens(subject, box.players)
         or match_player_by_surname(subject, box.players))
    if m is None:
        original = {shadow._bare_name(k): k for k in box.players}
        if len(original) == len(box.players):
            bare = {b: box.players[k] for b, k in original.items()}
            found = match_player_by_tokens(shadow._bare_name(subject), bare)
            m = original[found] if found is not None else None
    return None if m is None else box.players[m]


def main() -> None:
    cand = [json.loads(x) for x in open(f"{S}/candidates.jsonl")]
    cand = [c for c in cand if DAYS[0] <= (c["shadow_day"] or "") <= DAYS[1]
            and c["status"] == "active" and c["price"] > 1.0
            and not c.get("family", "").startswith("?")
            and c["kind"] in ("milestone", "double_double")]
    events = json.load(open(f"{S}/events.json"))
    by_ev: dict[str, list] = defaultdict(list)
    for c in cand:
        by_ev[c["superbet_event_id"]].append(c)
    conn = sqlite3.connect(DB, uri=True, timeout=60)
    out = open(f"{S}/scored.jsonl", "w")
    stats = Counter()
    for i, (eid, sels) in enumerate(sorted(by_ev.items())):
        ev = events[eid]
        day = ev["shadow_day"]
        pinned = pinned_teams(RUNS, "basketball", day)
        clock = max(s["fetched_at_utc"] for s in sels)
        now_ts = int(datetime.fromisoformat(clock.replace("Z", "+00:00")).timestamp())
        lines = []
        for s in sels:
            if s["kind"] == "milestone":
                lines.append({"market_id": CANON[s["family"]], "family": s["family"],
                              "period": 0, "subject": s["subject"],
                              "line": s["N"] - 0.5, "side": "OVER", "odds": s["price"]})
        dd_players = sorted({s["subject"] for s in sels if s["kind"] == "double_double"})
        for subj in dd_players:
            for fam in ("player_points", "player_rebounds", "player_assists"):
                lines.append({"market_id": CANON[fam], "family": fam, "period": 0,
                              "subject": subj, "line": 9.5, "side": "OVER", "odds": 2.0})
        # dedupe identical lines (a DD marginal may equal a 10+ milestone)
        seen = set()
        uniq = []
        for ln in lines:
            k = (ln["market_id"], ln["subject"], ln["line"])
            if k not in seen:
                seen.add(k)
                uniq.append(ln)
        rec = {"superbet_event_id": eid, "kickoff_utc": ev["kickoff_utc"],
               "team1": ev["team1"], "team2": ev["team2"],
               "fetched_at_utc": clock, "lines": uniq}
        rows = player_model.forecast_records(
            conn, "basketball", "basketball", [rec], clock, set(), now_ts, {}, pinned)
        mp = {(r["market_id"], r["subject"], r["line"]): r for r in rows}
        # box
        box = None
        sid = ev.get("sofascore_event_id")
        if sid and ev.get("state") == "SETTLED":
            lr = conn.execute("SELECT lineups_json FROM sofa_event_stats WHERE sofascore_event_id=?", (sid,)).fetchone()
            dr = conn.execute("SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id=?", (sid,)).fetchone()
            if lr and lr[0] and dr:
                det = json.loads(dr[0])
                det = det.get("event", det)
                box = shadow.build_player_box(json.loads(lr[0]), det, SPORT)
        box_state = "none" if box is None else ("ok" if box.ok else box.reason)
        stats[box_state] += 1
        for s in sels:
            row = {k: s[k] for k in ("superbet_event_id", "market_id", "kind", "subject",
                                     "price", "first_price", "fetched_at_utc", "tournament")}
            row["shadow_day"] = day
            row["box"] = box_state
            st = matched_stats(s["subject"], box) if box is not None and box.ok else None
            if s["kind"] == "milestone":
                row.update(family=s["family"], N=s["N"])
                m = mp.get((CANON[s["family"]], s["subject"], s["N"] - 0.5))
                row["model_p"] = m and m.get("model_p")
                row["model_n"] = m and m.get("model_n")
                row["model_reason"] = m.get("model_reason") if m else "NO_ROW"
                row["model_mean"] = m and m.get("model_mean")
                row["teams_resolved"] = m and m.get("teams_resolved")
                if box is not None and box.ok:
                    if st is None:
                        row["outcome"] = "UNMATCHED"
                    else:
                        spec = shadow.PLAYER_MARKETS["basketball"][CANON[s["family"]]]
                        v = shadow.player_stat_value(st, spec)
                        row["actual"] = v if isinstance(v, float) else None
                        row["outcome"] = v if isinstance(v, str) else ("WIN" if v >= s["N"] else "LOSS")
            else:
                row.update(side=s["side"], family="double_double")
                ps = {}
                for fam in ("player_points", "player_rebounds", "player_assists"):
                    m = mp.get((CANON[fam], s["subject"], 9.5))
                    ps[fam] = m and m.get("model_p")
                    row[f"p10_{fam}"] = ps[fam]
                    row[f"n_{fam}"] = m and m.get("model_n")
                    row[f"reason_{fam}"] = m and m.get("model_reason")
                if box is not None and box.ok:
                    if st is None:
                        row["outcome"] = "UNMATCHED"
                    elif not shadow.has_played(st):
                        row["outcome"] = "DNP"
                    else:
                        vals = {k: st.get(k) for k in ("points", "rebounds", "assists", "steals", "blocks")}
                        row["box_vals"] = vals
                        if any(not isinstance(v, int | float) for v in vals.values()):
                            row["outcome"] = "NO_STAT"
                        else:
                            dd = sum(1 for v in vals.values() if v >= 10) >= 2
                            hit = dd if s["side"] == "Tak" else not dd
                            row["outcome"] = "WIN" if hit else "LOSS"
                            row["dd"] = dd
                            row["dd_pra_only"] = sum(1 for k in ("points", "rebounds", "assists") if vals[k] >= 10) >= 2
            out.write(json.dumps(row) + "\n")
        del rows, mp, box
        if i % 20 == 0:
            gc.collect()
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
            print(i, len(by_ev), eid, ev.get("tournament"), "rss GB %.2f" % rss, flush=True)
    out.close()
    print("box states:", dict(stats))


if __name__ == "__main__":
    main()
