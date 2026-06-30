# Live Session Sport Provider Coverage Matrix

| sport | raw_discovery | merged_discovery | future_or_live | stale_filtered | competition | participants | markets | odds | lines | status | blocker |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| football | 99 | 82 | 64 | 0 | 64 | 64 | 39 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| volleyball | 5 | 5 | 5 | 0 | 5 | 5 | 0 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| basketball | 22 | 17 | 15 | 0 | 15 | 15 | 10 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| tennis | 157 | 157 | 157 | 0 | 157 | 157 | 117 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| hockey | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | PROVIDER_UNAVAILABLE | discovery returned zero fixtures |
| cs2 | 15 | 15 | 15 | 0 | 15 | 15 | 0 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| dota2 | 5 | 5 | 5 | 0 | 5 | 5 | 1 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |
| valorant | 5 | 5 | 5 | 0 | 5 | 5 | 2 | 0 | 0 | NO_MARKETS_OR_ODDS | no odds/market data reached market matrix |

## football
- provider_counts: `{'odds-api-io': 51, 'api-football': 48, 'espn': 0, 'odds-api': 0, 'football-data': 0}`
- provider_errors: `['odds-api/football: auth failed (401) — key expired or credits exhausted']`

## volleyball
- provider_counts: `{'odds-api-io': 4, 'api-volleyball': 1}`
- provider_errors: `[]`

## basketball
- provider_counts: `{'odds-api-io': 10, 'api-basketball': 12, 'odds-api': 0}`
- provider_errors: `[]`

## tennis
- provider_counts: `{'odds-api-io': 157, 'odds-api': 0}`
- provider_errors: `[]`

## hockey
- provider_counts: `{'odds-api-io': 0, 'api-hockey': 0, 'odds-api': 0}`
- provider_errors: `[]`

## cs2
- provider_counts: `{'odds-api-io': 15}`
- provider_errors: `[]`

## dota2
- provider_counts: `{'odds-api-io': 5}`
- provider_errors: `[]`

## valorant
- provider_counts: `{'odds-api-io': 5}`
- provider_errors: `[]`
