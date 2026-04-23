# Core Rules — NIGDY NIE ŁAMAĆ

## #1 STATYSTYKI SĄ PODSTAWĄ — BEZWZGLĘDNY PRIORYTET
- **TO JEST ZASADA NUMER JEDEN. NADRZĘDNA NAD WSZYSTKIMI INNYMI.**
- ZAWSZE bazuj na rynkach statystycznych: rzuty rożne, karty, faule, strzały, gemy (tenis), frame-y (snooker)
- NIGDY nie buduj portfolio z goli O/U, BTTS czy surowych wygranych (ML) jako głównych pozycji
- BTTS, O2.5, U2.5 = GOLE = to nie są "statystyki". To są rynki golowe. UNIKAĆ.
- Gole O/U, BTTS i ML to OSTATECZNY FALLBACK — tylko gdy ŻADEN rynek statystyczny nie jest dostępny i nie ma żadnych innych meczów ze statystykami
- Priorytet piłka: corners > cards > fouls > shots > team totals > BTTS > DC > goals O/U
- Priorytet tenis: game totals > set totals > games handicap > set handicap > ML
- Priorytet snooker: total frames > frame handicap > ML
- Priorytet hokej: totals > period totals > ML (z goalie + form)
- Priorytet koszykówka: totals > spreads > quarter totals > ML
- 22 kwietnia 3/3 AKO z cornerami wygrało — to POTWIERDZA metodologię

### ANTI-PATTERN (23 kwietnia — błąd):
- Agent wygenerował 5 picków: 2x BTTS No, 1x O2.5, 2x ML. ZERO rynków statystycznych.
- Wymówka "brak zakładek corners/cards na BetExplorer" to LENISTWO.
- Prawidłowe podejście: szukaj INNYCH meczów w ligach z rynkami statystycznymi (EPL, Bundesliga, Championship, Eredivisie, etc.)
- Użyj TotalCorner i SoccerStats do znalezienia meczów z ekstremalnym profilem cornerowym
- Jeśli dzisiejszy board nie ma rynków statystycznych → szukaj dalej w esporcie (map totals), snookerze (frame totals), tenisie (game totals), siatkówce (set totals)
- NIGDY więcej "BTTS No" jako "pewniaka". Corners Over/Under to pewniaki.

### KLUCZOWA ZASADA — AGENT SAM ROZKMINIWIA STATYSTYKI
- Agent MUSI sam wiedzieć, jakie rynki statystyczne są wartościowe w danej dyscyplinie.
- NIE CZEKAJ aż user powie Ci co obstawiać — TY jesteś analitykiem, TY szukasz edge'a.
- Każdy sport ma swoje nieefektywne rynki — agent je ZNA i AKTYWNIE SZUKA.
- Piłka: corners, cards, fouls, shots. Tenis: total games, set O/U. NBA: points, quarter totals. NHL: period totals, puck O/U. Siatkówka: sety, punkty. Snooker: framy. Esport: mapy, rundy. Darts: legi, 180ki.
- SKANUJESZ WSZYSTKIE SPORTY z config/betting_config.json — nie pomijasz żadnego.
- Jeśli nie ma danych z jednego źródła → idziesz do następnego. Internet ZAWSZE ma dane.
