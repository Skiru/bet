# CS2 - context checklist and sources

Checked 2026-10-26 (`docs/sofa/history/analitycy_2026-10-26/sources_measured_sports.md`).
Access and evidence legends as in `sources-hockey.md`.

## Mandatory - every match, in this order

1. **Is it on, which format** - postponement, forfeit; best-of (the series
   families assume the leg's `best_of`; none is never guessed as Bo3); LAN
   or online; the stage (elimination / already qualified).
2. **The five** - dossier `cs2.roster_latest` and
   `cs2.roster_new_vs_previous` (a new name = search it), then news: a stand-in, a benching, a visa problem, a new IGL. For a
   **player kills / deaths / assists / headshots** leg: is he in tonight's
   five?
3. **Map pool** - the map line's map against both teams' 90-day pool
   (dossier `cs2.map_pool_90d`); the Active Duty pool as of today.

**Removals**: the removal table of `.claude/agents/sofa-analyst-sport.md` - a dated `[WEB: domena, publ. <data>, fetched <czas>]` fact newer than the price or a real `DEFEKT:`; a schedule fact known before the price is a note.

## Checklist

| item | moves | evidence | carries |
|---|---|---|---|
| **Stand-in / missing player** | the team's map win / handicap ↓; a stand-in's kills cannot be read from the roster player's history; series total maps ↑ if it brings the sides closer | A (direction), size F | NO_BET on a player leg whose player is out on two domains, else WATCH; WATCH on winner / handicap / map legs, NO_BET when confirmed on two domains and the leg rests on the roster (a `lineup_unrated_rule` leg priced from the lineups) |
| **Roster change < 2-4 weeks** | var ↑, pool shrinks | F | note; a dated change since the price acts as a stand-in |
| **Map pool / veto** (a permaban, an opponent's pick) | map rounds and handicap depend on the map; the veto is known only shortly before | A | note; `DEFEKT: dossier cs2.map_pool_90d, <map> n=0 ...` only when neither side has played the map in 90 days |
| **Active Duty change** (Anubis for Train 2026-01-19; Cache for Overpass from Premier Season 5, press - verify on counter-strike.net) | thin history on the new map → var ↑ | A | `DEFEKT: dossier cs2.map_pool_90d, <map> ...` on a leg of a map new to Active Duty |
| **Best-of** other than the line assumes | series families wrong | A | NO_BET |
| **MR12 + overtime** (24 rounds regulation; OT in MR3, 4 of 6; OT money varies by event) | total rounds: a close map adds ≥ 4 rounds; an UNDER near 21.5-24.5 is OT-sensitive | A | note; the code counts OT rounds in a map's rounds |
| **LAN vs online; a first LAN; ping asymmetry** | the high-ping / LAN-debut side ↓ | E- (players ~30% better online than LAN in overtime - HSE) | note |
| **Visa / travel trouble, bootcamp jet lag** | as a stand-in | F | as a stand-in |
| **Stage stakes** (already through, last Swiss round, VRS-points chase) | already-qualified side ↓, var ↑ | F | note; WATCH only through a dated lineup consequence (a benching announced since the price) |
| **Patch shortly before** | var ↑ | F | note |
| **Schedule density** (two series a day) | var ↑ | F | note |
| **Tier-3 integrity** (ESIC sanctions, fixing history) | any leg | F | may carry a WATCH through the leg's variable (a sanctioned player out = the stand-in row) |

## Sources

| need | source | access | when |
|---|---|---|---|
| news, transfers, stand-ins | WebSearch limited to hltv.org (snippets carry the news); dust2.us (readable mirror), dust2.dk | HLTV B (403); dust2.us OK | continuous |
| rosters, transfers (machine-readable) | Liquipedia API: `https://liquipedia.net/counterstrike/api.php?action=parse&page=<Page>&format=json&prop=wikitext` with `Accept-Encoding: gzip` and a custom UA - **≤ 1 parse / 30 s**, CC BY-SA attribution | OK (HTML pages are 403) | continuous |
| matches by tournament | gosugamers.net/counterstrike/matches (no tier, no bo) | OK | |
| format, stage, Bo, OT rules | organiser sites: esl.com / pro.eslgaming.com, pgl.ro, blast.tv/cs | R | |
| Valve rankings / invitations | github.com/ValveSoftware/counter-strike_regional_standings | OK | periodic |
| map pool, patches | counter-strike.net/news | R | |

**Blocked / empty**: hltv.org match / stats pages (403 - the veto is not
fetchable), liquipedia HTML (403), bo3.gg (JS), faceit (B).
