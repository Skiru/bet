import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_surface_stats(filepath, player):
    with open(filepath) as f:
        html = f.read()
    tag_re = re.compile(r'<[^>]+>')
    text = tag_re.sub('\n', html)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print('=== {} ==='.format(player))

    wl_re = re.compile(r'^(\d+)/(\d+)$')
    found_singles = False

    for i, line in enumerate(lines):
        if line == 'Summary:':
            ctx = lines[max(0, i - 8):i + 8]
            is_mixed = any('mixed' in c.lower() for c in ctx)
            if is_mixed:
                continue

            surfaces = ['Clay', 'Hard', 'Indoors', 'Grass', 'Not set']
            wl = []
            for c in ctx:
                m = wl_re.match(c)
                if m:
                    wl.append((int(m.group(1)), int(m.group(2))))

            if wl and not found_singles:
                for j, s in enumerate(surfaces):
                    if j < len(wl):
                        w, l = wl[j]
                        total = w + l
                        pct = round(100 * w / total) if total > 0 else 0
                        print('  {}: {}W-{}L ({}%)'.format(s, w, l, pct))
                found_singles = True

    for i, line in enumerate(lines):
        if line == '2026':
            ctx2026 = lines[i:i + 20]
            wl26 = []
            for c in ctx2026:
                m = wl_re.match(c)
                if m:
                    wl26.append((int(m.group(1)), int(m.group(2))))
            if wl26:
                print('  2026 season:')
                surf26 = ['Clay', 'Hard', 'Indoors', 'Grass']
                for j, s in enumerate(surf26):
                    if j < len(wl26):
                        w, l = wl26[j]
                        print('    {}: {}W-{}L'.format(s, w, l))
            break
    print()


players = [
    ('betting/data/tennisexplorer_struff.html', 'STRUFF'),
    ('betting/data/tennisexplorer_michelsen.html', 'MICHELSEN'),
    ('betting/data/tennisexplorer_tauson.html', 'TAUSON'),
    ('betting/data/tennisexplorer_siniakova.html', 'SINIAKOVA'),
]

for rel, name in players:
    get_surface_stats(os.path.join(BASE, rel), name)