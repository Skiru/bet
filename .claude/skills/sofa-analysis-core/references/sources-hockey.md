# Ice hockey - context checklist and sources

Checked 2026-10-26 (`docs/sofa/history/analitycy_2026-10-26/sources_measured_sports.md`).
Access: **OK** content read; **R** reachable, content unchecked; **B**
blocked (403 / 429 - snippets via a site-limited search only); **JS** empty
without JavaScript. Evidence: **E** measured, **E-** weak, **A** rules /
arithmetic, **F** folklore.

## Mandatory - every match, in this order

1. **Is it on** - postponement, a moved / neutral venue (league site, a
   second domain).
2. **Starting goalie** - NHL: DailyFaceoff's starting-goalie page (status
   Confirmed / Expected with a timestamp), Rotowire's lineups. Europe: no
   free pre-match source (Liiga: lineups through Veikkaus around noon on game
   day - one season seen; SHL: the line-up ~1 h before; KHL: none) - write
   `UNVERIFIED`.
3. **Back-to-back / travel** - dossier `rest_days` / `games_7d`; the goalie
   who played last night.
4. **Absences** of top-6 forwards, top-4 D, the PP1 quarterback - and for a
   **player prop**: is he dressed, which line, which PP unit.

## Checklist

| item | moves | evidence | carries |
|---|---|---|---|
| **Backup / call-up / emergency goalie** starting | opponent's team total ↑, match total ↑, favourite's handicap / winner ↓, opponent player points ↑ | E- (sv% .905 → .897 on 1 day's rest) | WATCH; NO_BET when a goalie-dependent line (UNDER, favourite -1.5) and the backup is confirmed on two domains |
| **Second night of a back-to-back** (same goalie both nights) | tired side's goals against ↑, shots ↓ | E- (mostly through the goalie) | WATCH on legs needing the tired side to defend / produce |
| **Travel west / long trips / KHL time zones** | away side ↓ | E (17,088 NHL games, 2013-20) | WATCH on the away side's output |
| **Top player out / scratched** | team total ↓; teammates' PP points shift | F (direction certain) | WATCH through the team's own line |
| **Line / PP unit change** for a prop's player | player points / SOG ↑ / ↓ | F | WATCH the prop; NO_BET if not dressed on two domains, else WATCH |
| **AHL call-up / assignment** | AHL team total ↓ when its best player is recalled | F | WATCH |
| **Late season: eliminated / clinched** | backup goalie starts, var ↑ | F | through the goalie only |
| **Outdoor game** | pace ↓ claimed, ice / wind | F | note |
| **Empty net / score effects** | late total ↑, favourite -1.5 ↑ | A | note (team-specific) |
| **International break / Olympic window** | European leagues pause; returning fatigue | F | note |

## Sources

| need | source | access | when |
|---|---|---|---|
| NHL starting goalies | dailyfaceoff.com/starting-goalies | OK | often confirmed the day before; updated live |
| NHL lines, PP units, injuries | dailyfaceoff.com/teams/<team>/line-combinations; rotowire.com/hockey/nhl-lineups.php | OK | game day |
| NHL morning skate, coach's words | team beat reporters on X | JS | ~10:30-11:30 local |
| AHL moves | search "<team> recalls" / "assigned to"; theahl.com | R | daily |
| Liiga | jatkoaika.com; liiga.fi (JS) | R | ~12:00 game day (Veikkaus) |
| SHL | shl.se; tv4.se goalie news | R | ~1 h before |
| DEL | penny-del.org, eishockeynews.de | R | |
| Czech / Slovak | hokej.cz; hockeyslovakia.sk | R | |
| Swiss / Austrian / Polish | nationalleague.ch, hockeyfans.ch; ice.hockey, hockeynews.at; phl.pl, hokej.net | R | |
| KHL | championat.com/hockey, sports.ru/hockey (RU); khl.ru is B / JS | R / B | |

**Blocked / unusable**: leftwinglock (goalie tool premium-only), nhl.com
injuries (error page), eliteprospects, puckpedia (B), capfriendly (closed).
