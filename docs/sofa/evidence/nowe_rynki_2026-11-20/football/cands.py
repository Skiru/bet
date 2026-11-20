"""Candidate selections as events on the score path (h1, a1, h2, a2) - shared by every step.
`parse(rec)` -> (cand, key, held) for one unmapped price record (board sides), or None.
held(h1, a1, h2, a2) -> True / False / None (None = refund, half DNB on a drawn half)."""
import re, sys
sys.path[:0] = ["src", "."]
from bet.sofa.market_mapper import fold

def _f(t):
    return " ".join(fold(t or "").split())

def side_of(name, rec):
    n = _f(name)
    a, b = _f(rec["side_a"]), _f(rec["side_b"])
    if a == b:
        return None
    return 0 if n == a else 1 if n == b else None

_WOB = re.compile(r"^(?P<t>.+) wygra obie polowy$")
_WAL = re.compile(r"^(?P<t>.+) wygra przynajmniej jedna polowe$")
_BTO = re.compile(r"^obie druzyny strzela gola & powyzej (?P<l>\d+\.5) gola$")
_HSEL = re.compile(r"^(?P<t>.+) \((?P<l>[+-]?\d+(?:\.\d+)?)\)$")
_HALF_H = re.compile(r"^(?P<h>[12])\.\s?polowa - handicap$")
_HALF_DNB = re.compile(r"^(?P<h>[12])\.\s?polowa - zaklad bez remisu$")
_E3 = re.compile(r"^(?P<t>.+) \((?P<x>\d+):(?P<y>\d+)\)$")

def parse(rec):
    """(cand, group_key_suffix, selection_label, held) or None."""
    mn, sel = _f(rec["marketName"]), _f(rec["name"])
    yes = sel == "tak"
    if sel not in ("tak", "nie") and not (_HSEL.match(sel) or _E3.match(sel) or sel):
        return None
    m = _WOB.match(mn)
    if m and sel in ("tak", "nie"):
        s = side_of(m.group("t"), rec)
        if s is None:
            return None
        def held(h1, a1, h2, a2, s=s, yes=yes):
            w = (h1 > a1 and h2 > a2) if s == 0 else (a1 > h1 and a2 > h2)
            return w if yes else not w
        return ("side_wins_both_halves", f"s{s}", f"{'1' if s == 0 else '2'}:{sel}", held)
    m = _WAL.match(mn)
    if m and sel in ("tak", "nie"):
        s = side_of(m.group("t"), rec)
        if s is None:
            return None
        def held(h1, a1, h2, a2, s=s, yes=yes):
            w = (h1 > a1 or h2 > a2) if s == 0 else (a1 > h1 or a2 > h2)
            return w if yes else not w
        return ("side_wins_a_half", f"s{s}", f"{'1' if s == 0 else '2'}:{sel}", held)
    if mn == "remis w obu polowach" and sel in ("tak", "nie"):
        def held(h1, a1, h2, a2, yes=yes):
            w = h1 == a1 and h2 == a2
            return w if yes else not w
        return ("draw_both_halves", "", sel, held)
    if mn == "gol w obu polowach" and sel in ("tak", "nie"):
        def held(h1, a1, h2, a2, yes=yes):
            w = h1 + a1 > 0 and h2 + a2 > 0
            return w if yes else not w
        return ("goal_both_halves", "", sel, held)
    m = _BTO.match(mn)
    if m and sel in ("tak", "nie"):
        L = float(m.group("l"))
        def held(h1, a1, h2, a2, L=L, yes=yes):
            w = (h1 + h2 > 0) and (a1 + a2 > 0) and (h1 + a1 + h2 + a2 > L)
            return w if yes else not w
        return ("btts_and_over", f"L{L:g}", f"L{L:g}:{sel}", held)
    m = _HALF_H.match(mn)
    if m:
        s = _HSEL.match(sel)
        if s is None:
            return None
        side = side_of(s.group("t"), rec)
        if side is None:
            return None
        L = float(s.group("l"))
        if L == int(L):
            return None
        half = int(m.group("h"))
        def held(h1, a1, h2, a2, side=side, L=L, half=half):
            h, a = (h1, a1) if half == 1 else (h2, a2)
            own, oth = (h, a) if side == 0 else (a, h)
            return own + L > oth
        # group: the 2-way pair shares |line| and the home team's sign (sbv = home's line)
        home_line = L if side == 0 else -L
        return (f"half{half}_handicap", f"H{home_line:+g}", f"{'1' if side == 0 else '2'}({L:+g})", held)
    m = _HALF_DNB.match(mn)
    if m:
        side = side_of(sel, rec)
        if side is None:
            return None
        half = int(m.group("h"))
        def held(h1, a1, h2, a2, side=side, half=half):
            h, a = (h1, a1) if half == 1 else (h2, a2)
            if h == a:
                return None
            return (h > a) if side == 0 else (a > h)
        return (f"half{half}_dnb", "", "1" if side == 0 else "2", held)
    if mn == "handicap":
        s = _HSEL.match(sel)
        if s is None:
            return None
        side = side_of(s.group("t"), rec)
        if side is None:
            return None
        L = float(s.group("l"))
        if L == int(L):
            return None
        def held(h1, a1, h2, a2, side=side, L=L):
            own, oth = (h1 + h2, a1 + a2) if side == 0 else (a1 + a2, h1 + h2)
            return own + L > oth
        home_line = L if side == 0 else -L
        return ("match_handicap_2way", f"H{home_line:+g}", f"{'1' if side == 0 else '2'}({L:+g})", held)
    if mn == "handicap 1x2":
        s = _E3.match(sel)
        if s is None:
            return None
        x, y = int(s.group("x")), int(s.group("y"))
        who = s.group("t")
        side = None if who == "remis" else side_of(who, rec)
        if who != "remis" and side is None:
            return None
        def held(h1, a1, h2, a2, side=side, x=x, y=y):
            d = (h1 + h2 + x) - (a1 + a2 + y)
            return d == 0 if side is None else (d > 0 if side == 0 else d < 0)
        return ("match_handicap_3way", f"E{x}:{y}", f"{'X' if side is None else side + 1}({x}:{y})", held)
    return None
