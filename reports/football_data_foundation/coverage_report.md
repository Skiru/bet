# Football Data Foundation Coverage

## Routing

- Removed the `sportdb` YAML alias workaround from `config/football_routing.yaml`.
- Preserved the existing additive routing shape: production routes remain `espn` and `football-data`; `sportdb` stays shadow-only.

## Connector Truthfulness

- Soccerdata connectors now expose documented `read_*` operations only.
- FBref now follows constructor-level `leagues` and `seasons`, with operation-level `stat_type` validation.
- Understat no longer references `read_match_shots`.
- WhoScored no longer references `read_player_ratings`.
- Sofascore no longer exposes `fetch_ratings` as a public operation.
- FiveThirtyEight remains represented but is demoted to `NOT_SUPPORTED` because the installed `soccerdata` build does not expose the class.

## Fail-Closed Local Parsers

- StatsBombOpenData, OpenFootball, and KaggleEuropeanSoccer only parse caller-provided fixture paths.
- Missing fixture paths return `NOT_FOUND` instead of inline success.
- Fixture-backed parses create deterministic atomic evidence identities.

## Status Demotions

- `FootballDataOrg` is `IMPLEMENTED_ACTIVE`, not certified.
- `FotMobProbe` and `SofaScoreRichProbe` are `NOT_SUPPORTED` without a safe client path.
- `StatsBombPy`, `ScraperFCSofascore`, `SoccerAction`, `Kloppy`, `Floodlight`, and `MplSoccer` are `NOT_SUPPORTED` when their optional dependencies are absent.

## Test Posture

- Unit coverage is deterministic and offline-only.
- Test fixtures live under `tests/fixtures/football_data_foundation/`.
- Network access is blocked during `tests/enrichment/football_data_foundation` execution.
