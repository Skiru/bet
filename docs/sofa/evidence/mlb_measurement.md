# MLB Measurement — NOT MEASURED

**Status:** NOT_MEASURED (attempted 2026-09-17T22:31:57.418934+00:00)

**Reason:** Every one of 50 Sofascore requests failed; no fixture was resolved or probed.

No recall figure, no statistics-coverage finding and no conclusion about baseball may be quoted from this file. Re-run
`python -m scripts.sofa.measure_mlb --date <YYYY-MM-DD>` from a host that can reach Sofascore, and this file will be overwritten with the measured numbers plus the raw payloads in `mlb_measurement_raw.json`.

Baseball remains out of `sofa` (`Sport = Literal["football", "tennis"]`) because it was never measured, not because it was measured and rejected.
