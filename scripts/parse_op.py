import re, sys, html as htmlmod

raw = open(sys.argv[1]).read()

# Sport keyword patterns for league headers (Polish and English)
SPORT_KW = [
    "nożna", "Football", "Tenis", "Tennis", "Koszykówka", "Basketball",
    "Hokej", "Hockey", "Siatkówka", "Volleyball", "Baseball",
    "Piłka ręczna", "Handball", "Esports", "Snooker", "Darts",
    "Tenis stołowy", "Table Tennis", "MMA", "Sztuki walki",
]

# Find positions of eventRow blocks
p = [m.start() for m in re.finditer(r'class="eventRow', raw)]
tag_re = re.compile(r"<[^>]+>")

lg = co = ""
evts = []
for i in range(len(p)):
    end = p[i+1] if i+1 < len(p) else p[i] + 2000
    b = raw[p[i]:min(p[i]+2000, end)]
    text = tag_re.sub("|", b)
    parts = [x.strip() for x in text.split("|") if x.strip()]
    
    is_header = any(kw in " ".join(parts[:6]) for kw in SPORT_KW)
    if is_header:
        for j, part in enumerate(parts):
            if any(kw in part for kw in SPORT_KW):
                co = parts[j+1] if j+1 < len(parts) else co
                lg = parts[j+2] if j+2 < len(parts) else lg
                break
    else:
        tm = h = a = ""
        for part in parts:
            if re.match(r"^\d{2}:\d{2}$", part):
                tm = part
            elif tm and not h and len(part) > 1:
                h = htmlmod.unescape(part)
            elif h and not a and len(part) > 1:
                a = htmlmod.unescape(part)
                break
        if h and a:
            evts.append((tm, co, lg, h, a))

print(len(evts), "matches")
prev = ""
for t, c, l, h, a in evts:
    lb = c + "/" + l
    if lb != prev:
        print("\n=== " + lb + " ===")
        prev = lb
    print("  " + t + "  " + h + " vs " + a)
