# Football - context checklist and sources

Checked 2026-10-26 (`docs/sofa/history/analitycy_2026-10-26/sources_football_tennis.md`).
Access: **OK** static HTML; **JS** content needs JavaScript (a fetch sees
little); **CF** Cloudflare / bot wall (do not retry); **PAY** paywall.
Evidence: **E+** measured, **E~** mixed / small, **F** folklore. "Carries" =
the most it may carry (`context-pass.md` decides the rest).

## Mandatory - every match, in this order

1. **Is it on, where, when** - dossier `header` (venue, both clocks) vs
   `fixture_status.json`; a postponement, a moved venue, a pitch inspection
   (local press, the club's channel).
2. **Who plays** - dossier `lineups` (predicted / confirmed, missing /
   doubtful); then one search for fresh absences since the price (injury,
   illness, suspension), the club's language first. Every **prop** leg: is
   the player expected to start, in his usual role / position?
3. **Second leg / knockout / dead rubber** - from the dossier; on the web only
   when it changes the lineup (a coach naming reserves).
4. **Card / foul legs** - the referee: dossier vs the federation's
   appointment (a **change** is the only new information; the rate is in the
   model).
5. **Outdoor conditions** - only when the forecast is extreme.

Everything else below only when the dossier or the legs raise it. The
market drivers (possession, crosses, box touches, blocked shots, the
opponent's concession, the league rate) are read from the dossier's `style`
block, never searched (`market-drivers.md`).

## Checklist

| item | moves | evidence | carries |
|---|---|---|---|
| **Confirmed XI** contradicting a prop (not starting, a different position) | the prop's premise (Superbet voids a non-starter; a role change is the real risk) | mechanical | NO_BET with the XI on two domains (official + one), else WATCH |
| **Rotated / weakened XI** (cup priority, congestion, decided tie) | the weakened side's shots / SOT / corners / goals ↓, the opponent's ↑ | E~ (our 10-23 measurement: the real XI added nothing on team counts) | WATCH through the side's own count, with the names |
| **Key absence since the price** (striker, CB, GK) | side's goals / shots ↓ (striker), opponent's goals ↑ (CB / GK) | E~ (ratings absorb part) | WATCH; NO_BET only on two domains and when it breaks the leg's premise |
| **Suspension risk** (a player on the card threshold) | cards ↓ / tactical fifth yellow | F | note |
| **Referee change** vs the dossier | cards, card points, fouls, penalties | E+ (referees differ, stable - Dawson et al. 2007) | WATCH on card / foul legs (the model's rate was the named referee's; a new name is a changed input - no outside rate is quoted; the named referee's shrunk rate is in the centre since 2026-10-21, `referee_rule`) |
| **Fan ban / closed doors / away-fan ban** | away yellows ↑ with a crowd (~+⅓ card), so closed doors lower away cards | E+ (Bryson et al. 2021; Reade et al.) | WATCH on away-card legs |
| **Heat** (very hot kickoff) | passes, counter-attack shots ↓ | M (UCL, Bundesliga studies) | WATCH on shot / SOT OVER only when extreme |
| **Rain / wind / snow** | unmeasured on goals, corners, shots | F | note; a postponement risk is a fact (refund) |
| **Artificial turf** (Norway yes, Sweden no; Eredivisie banned it from 2025-26) | home advantage ↑ (Norway) | E~ | note (in the samples already) |
| **Altitude** (La Paz, Quito, Bogotá, Cusco, Toluca, Mexico City) | home goal difference ↑ ~0.5 per 1,000 m | E~ (McSharry 2007; confounded) | WATCH on the away side's output only with a > ~2,000 m gap |
| **Congestion / midweek Europe** | rotation ↑; result effect mixed | E~ | through the XI only |
| **New manager** | bounce = regression to the mean; odds may under-price the team in games 1-4 | E+ / M | may carry a WATCH on a leg **against** that team, through its variable; no reason for a leg on it |
| **Derby** | no effect on goals / results; fouls ↑ in one EPL sample | E+ null / W | note; never a reason for goals |
| **Title / relegation / dead rubber** | effort, rotation | F / priced | through the XI only |
| **Second leg, aggregate** | the team ahead protects (its shots ↓, opponent's ↑); a late chase raises cards (game state: Buraimo et al.) | F / E+ (game state) | WATCH through the side's count when the aggregate is lopsided |
| **Dressing room / unpaid wages / crisis** (lower leagues) | collapse, walk-out, forfeit (refund) | F | note; WATCH only with a lineup consequence |
| **Women / youth / reserve** | lineups rarely published; reserves change with the first team's needs | F | `UNVERIFIED` is the honest answer |

Card thresholds (one-match ban): Premier League 5 in the first 19 games (10
by 32); Ligue 1 any 5 (from 2025-26); LaLiga, Serie A, Bundesliga, MLS 5
(secondary sources); UEFA 3rd, 5th, 7th, reset after the QF. Ekstraklasa,
Süper Lig, Brasileirão, Argentina, Nordics: not verified - check the
federation's disciplinary page.

## Sources

| need | source | access | when |
|---|---|---|---|
| confirmed XI | the club's X / site / app; rotowire.com/soccer/lineups.php (EPL static; UCL, L1, LaLiga, SA, BL, MLS, Liga MX listed) | X: JS; rotowire OK | EPL from 75' before KO; EFL / UEFA ~60-75' (unverified); lower leagues often only at KO |
| predicted XI | sportsgambler.com/lineups/football/ (~60 competitions incl. AR, BR, TR, Nordics, J1, K1, CSL, RU - **not Poland**); sportsmole.co.uk/football/preview/ (EN, ES, FR, PT, TR leagues) | OK | 1-3 days before |
| injuries / suspensions | transfermarkt (`.../verletztespieler/wettbewerb/<ID>`, `.../sperrenausfaelle/wettbewerb/<ID>` - "Risk of suspension"; .pl / .co.uk mirrors); sportsgambler.com/injuries/football/<league>/ | OK to curl, WebFetch may be blocked | daily |
| referee appointment | England premierleague.com news (PGMOL); Italy aia-figc.it/designazioni/; Germany dfb.de/bundesliga/schiedsrichter; Brazil cbf.com.br/a-cbf/arbitragem/escala-de-arbitragem; Poland meczyki.pl "obsada sędziowska" (pzpn.pl pages 404); Spain marca.com (rfef.es CF); Turkey fanatik.com.tr / tff.org; Argentina ole.com.ar | OK unless noted | 2-5 days before |
| weather | open-meteo JSON (coordinates from the dossier); yr.no (Scandinavia), meteoblue, wetteronline, weather.gov | OK | 0-48 h |
| venue, surface, capacity | stadiumdb.com, footballgroundguide.com; Wikipedia venue lists (Eliteserien surface column) | OK | static |
| local press | PL sport.pl, przegladsportowy.pl, weszlo.com, meczyki.pl, 90minut.pl / laczynaspilka.pl (lower leagues); ES marca.com; IT gazzetta.it; TR fanatik.com.tr, mackolik.com; BR ge.globo.com; AR ole.com.ar, promiedos.com.ar; EN bbc.com/sport | OK | daily |
| fixtures / dates | flashscore.com (dates static, lineups JS), soccerway.com, soccerbase.com | OK | |

**Blocked - do not fetch** (use a site-limited search for snippets if
needed): sofascore (the bridge has it), whoscored, fbref, footystats,
football-lineups, besoccer, zerozero / ogol, forebet, kicker, lequipe,
premierinjuries, rfef.es, 11v11 (CF); worldfootball.net (PAY); fotmob (JS);
physioroom (gone).
