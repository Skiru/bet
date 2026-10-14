"""Live probe (bridge): which Sofascore endpoints find the events SPORT_IDENTITY
missed on 2026-10-14. Read-only for the repo; raw payloads saved next to this file."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig

OUT = Path(__file__).parent / "probe"
OUT.mkdir(exist_ok=True)
API = "https://api.sofascore.com/api/v1/"
client = SofascoreClient(SofaConfig.from_env())


def get(path: str, tag: str):
    try:
        data = client._execute(API + path)
        status = "200"
    except Exception as e:  # noqa: BLE001
        data, status = None, f"ERR {type(e).__name__}: {e}"
    (OUT / f"{tag}.json").write_text(json.dumps(data, ensure_ascii=False))
    n = len((data or {}).get("events") or (data or {}).get("results") or []) if isinstance(data, dict) else 0
    print(f"{tag:45s} {status:40s} items={n}", flush=True)
    return data


mode = sys.argv[1]
if mode == "scheduled":
    for slug in ("volleyball", "basketball", "ice-hockey", "esports"):
        for day in ("2026-10-14",):
            get(f"sport/{slug}/scheduled-events/{day}", f"sched_{slug}_{day}")
elif mode == "search":
    for q, sport, tag in [
        ("THY", "volleyball", "s_thy"),
        ("Turk Hava Yollari", "volleyball", "s_turkhava"),
        ("Tryhoop Okayama", "basketball", "s_okayama"),
        ("Takamatsu", "basketball", "s_takamatsu"),
        ("Jordan", "volleyball", "s_jordan"),
        ("Binh Dien Long An", "volleyball", "s_binhdien"),
        ("Bilbao", "basketball", "s_bilbao"),
        ("Team Hooch", None, "s_hooch"),
    ]:
        path = "search/all?q=" + quote(q, safe="") + (f"&sport={sport}" if sport else "")
        get(path, tag)
    for q, tag in [("THY", "st_thy"), ("Okayama", "st_okayama")]:
        get("search/teams?q=" + quote(q, safe=""), tag)
elif mode == "team":
    # NO_GAME_WITHIN_1H: is the game on a later page / in 'last'?
    for tid, tag in [(203051, "oman"), (298548, "zokub"), (52459, "radnicki")]:
        get(f"team/{tid}/events/next/0", f"t_{tag}_next0")
        get(f"team/{tid}/events/next/1", f"t_{tag}_next1")
elif mode == "players":
    get("team/243989/players", "squad_thy")
    get("search/all?q=" + quote("Kreider", safe="") + "&sport=ice-hockey", "s_kreider")
elif mode == "extra":
    for path, tag in [(a, b) for a, b in [arg.split("=", 1)[::-1] for arg in sys.argv[2:]]]:
        get(path, tag)
print("done", datetime.now(timezone.utc).isoformat())
