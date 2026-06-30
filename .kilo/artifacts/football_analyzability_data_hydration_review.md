# Football Analyzability Data Hydration Review

This review performs a thorough root-cause audit of all 8 football candidates from the latest pre-S7 and S4 valuation/analyzability runs, detailing their identity resolution, local DB coverage, and hydration feasibility via API-Football / API-Sports.

---

## 1. Candidate Audits

### Candidate 1: football|Kazma|Al-Salmiya|2026-06-29
* **Candidate ID:** `football|Kazma|Al-Salmiya|2026-06-29`
* **Fixture ID / Event ID:** `232560`
* **Sport:** `football`
* **Competition:** `Kuwait - Premier League, Championship Group`
* **Participants:** `Kazma`, `Al-Salmiya`
* **Market Family:** `RESULT`
* **Market Type:** `ml`
* **Selection:** `Al-Salmiya`
* **Direction:** `None`
* **Line:** `None`
* **Team Identity Resolution Status:** Partial. `Al-Salmiya SC` resolved, but `Kazma` is unresolved or has 0 forms.
* **Provider Team IDs:** `Al-Salmiya SC` (ID: 45848). `Kazma` (No canonical ID).
* **Fixture IDs:** `232560`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** L10 match-by-match statistics for Kazma, `model_probability` is Null.
* **API-Football Hydration:** Possible. Kuwait Premier League is supported under League ID `289`.
* **Local DB/Cache Hydration:** Possible for Al-Salmiya (3 forms), but not possible for Kazma (0 forms).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `API_FOOTBALL_HYDRATION_POSSIBLE`

---

### Candidate 2: football|Melgar|CD Moquegua|2026-06-29
* **Candidate ID:** `football|Melgar|CD Moquegua|2026-06-29`
* **Fixture ID / Event ID:** `232558`
* **Sport:** `football`
* **Competition:** `Peru - Copa de la Liga, Group H`
* **Participants:** `Melgar`, `CD Moquegua`
* **Market Family:** `None` (reported as empty)
* **Market Type:** `Melgar Fouls O/U`
* **Selection:** `None`
* **Direction:** `None`
* **Line:** `10.0`
* **Team Identity Resolution Status:** Partial. `FBC Melgar` resolved, but `CD Moquegua` has minimal history.
* **Provider Team IDs:** `FBC Melgar` (ID: 11000). CD Moquegua (ID: 37186).
* **Fixture IDs:** `232558`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** `market_family`, L10 series, stat-semantics mapping for fouls.
* **API-Football Hydration:** Possible. Peru Primera Division / Copa de la Liga is supported under League ID `281`.
* **Local DB/Cache Hydration:** Melgar has 88 forms, CD Moquegua has 3 forms. Missing L10 matches.
* **Exact Blocker Category:** `MARKET_INPUT_MAPPING_MISSING`
* **Classification:** `STAT_SEMANTICS_MAPPING_MISSING`

---

### Candidate 3: football|B68 Toftir|Argir|2026-06-29
* **Candidate ID:** `football|B68 Toftir|Argir|2026-06-29`
* **Fixture ID / Event ID:** `232550`
* **Sport:** `football`
* **Competition:** `Faroe Islands - Premier League`
* **Participants:** `B68 Toftir`, `Argir`
* **Market Family:** `GOALS_TOTALS`
* **Market Type:** `goals_over/under`
* **Selection:** `None`
* **Direction:** `None`
* **Line:** `None`
* **Team Identity Resolution Status:** Partial. `B68 Toftir` (ID: 28478) and `AB Argir` (ID: 28701) are in DB, but B68 has 0 forms.
* **Provider Team IDs:** B68 Toftir (ID: 28478), AB Argir (ID: 28701).
* **Fixture IDs:** `232550`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** `line`, `direction`, L10 series for B68 Toftir.
* **API-Football Hydration:** Possible. Faroe Islands Premier League is supported under League ID `327`.
* **Local DB/Cache Hydration:** Not possible (B68 has 0 forms).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `API_FOOTBALL_HYDRATION_POSSIBLE`

---

### Candidate 4: football|HB Torshavn|Skala|2026-06-29
* **Candidate ID:** `football|HB Torshavn|Skala|2026-06-29`
* **Fixture ID / Event ID:** `232548`
* **Sport:** `football`
* **Competition:** `Faroe Islands - Premier League`
* **Participants:** `HB Torshavn`, `Skala`
* **Market Family:** `None`
* **Market Type:** `None`
* **Selection:** `None`
* **Direction:** `None`
* **Line:** `None`
* **Team Identity Resolution Status:** Partial. `HB Torshavn` (ID: 20944) and `Skala` (ID: 28700) are resolved, but Skala has 0 forms.
* **Provider Team IDs:** HB Torshavn (ID: 20944), Skala (ID: 28700).
* **Fixture IDs:** `232548`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** `market_family`, `line`, `direction`, L10 series.
* **API-Football Hydration:** Possible. Faroe Islands Premier League is supported under League ID `327`.
* **Local DB/Cache Hydration:** Skala has 0 forms. Not possible.
* **Exact Blocker Category:** `MARKET_INPUT_MAPPING_MISSING`
* **Classification:** `STAT_SEMANTICS_MAPPING_MISSING`

---

### Candidate 5: football|Brazil|Japan|2026-06-29
* **Candidate ID:** `football|Brazil|Japan|2026-06-29`
* **Fixture ID / Event ID:** `232546`
* **Sport:** `football`
* **Competition:** `International - FIFA World Cup`
* **Participants:** `Brazil`, `Japan`
* **Market Family:** `SHOTS`
* **Market Type:** `Japan Shots O/U`
* **Selection:** `UNDER`
* **Direction:** `UNDER`
* **Line:** `24.0`
* **Team Identity Resolution Status:** High. Both teams resolved and have forms.
* **Provider Team IDs:** Brazil (ID: 1263), Japan (ID: 5067).
* **Fixture IDs:** `232546`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** `direction` inside prefilter validation, raw L10 match statistics.
* **API-Football Hydration:** Possible. World Cup is supported under League ID `1`.
* **Local DB/Cache Hydration:** Possible (Brazil 68, Japan 65 forms).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `TEAM_IDENTITY_READY`

---

### Candidate 6: football|Germany|Paraguay|2026-06-29
* **Candidate ID:** `football|Germany|Paraguay|2026-06-29`
* **Fixture ID / Event ID:** `232567`
* **Sport:** `football`
* **Competition:** `International - FIFA World Cup`
* **Participants:** `Germany`, `Paraguay`
* **Market Family:** `SHOTS`
* **Market Type:** `Germany Shots O/U`
* **Selection:** `UNDER`
* **Direction:** `UNDER`
* **Line:** `24.0`
* **Team Identity Resolution Status:** High. Both teams resolved and have forms.
* **Provider Team IDs:** Germany (ID: 10716), Paraguay (ID: 12055).
* **Fixture IDs:** `232567`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** `direction` validation in prefilter, raw L10 match statistics.
* **API-Football Hydration:** Possible. World Cup is supported under League ID `1`.
* **Local DB/Cache Hydration:** Possible (Germany 78, Paraguay 8 forms).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `TEAM_IDENTITY_READY`

---

### Candidate 7: football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29
* **Candidate ID:** `football|Deportivo Garcilaso|Deportivo Binacional|2026-06-29`
* **Fixture ID / Event ID:** `232566`
* **Sport:** `football`
* **Competition:** `Peru - Copa de la Liga, Group F`
* **Participants:** `Deportivo Garcilaso`, `Deportivo Binacional`
* **Market Family:** `GOALS_TOTALS`
* **Market Type:** `Goals Total O/U`
* **Selection:** `None`
* **Direction:** `None`
* **Line:** `3.0`
* **Team Identity Resolution Status:** High. Both teams resolved.
* **Provider Team IDs:** Deportivo Garcilaso (ID: 259), Deportivo Binacional (ID: 25247).
* **Fixture IDs:** `232566`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** L10 match-by-match stats, line/direction mapping in prefilter.
* **API-Football Hydration:** Possible. Peru Primera Division / Copa de la Liga is supported under League ID `281`.
* **Local DB/Cache Hydration:** Partial (Garcilaso has 5, Binacional has 2).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `TEAM_IDENTITY_READY`

---

### Candidate 8: football|Vikingur|Runavik|2026-06-29
* **Candidate ID:** `football|Vikingur|Runavik|2026-06-29`
* **Fixture ID / Event ID:** `232549`
* **Sport:** `football`
* **Competition:** `Faroe Islands - Premier League`
* **Participants:** `Vikingur`, `Runavik`
* **Market Family:** `GOALS_TOTALS`
* **Market Type:** `Goals Total O/U`
* **Selection:** `UNDER`
* **Direction:** `UNDER`
* **Line:** `2.0`
* **Team Identity Resolution Status:** High. Both resolved.
* **Provider Team IDs:** Vikingur Gota (ID: 248), NSI Runavik (ID: 247).
* **Fixture IDs:** `232549`
* **Stats Seed Path:** `/private/tmp/full_analytical_session_smoke_a/data/2026-06-29_s3_deep_stats.json`
* **L10 Source Path:** None on disk.
* **Exact Missing Fields:** Raw L10 match statistics.
* **API-Football Hydration:** Possible. Faroe Islands Premier League is supported under League ID `327`.
* **Local DB/Cache Hydration:** Partial (Vikingur has 2, Runavik has 4).
* **Exact Blocker Category:** `L10_CACHE_MISSING`
* **Classification:** `TEAM_IDENTITY_READY`

---

## 2. Summary Classification Matrix

| Blocker Category | Count | Classification | Recovery / Action Plan |
|---|---|---|---|
| `TEAM_IDENTITY_READY` | 5 | Ready to Hydrate | Run targeted S2.5/S2.9 hydration scripts. |
| `TEAM_IDENTITY_MISSING` | 0 | - | N/A |
| `L10_CACHE_MISSING` | 6 | API_FOOTBALL_HYDRATION_POSSIBLE | Trigger targeted endpoint query to build caches. |
| `STAT_SEMANTICS_MAPPING_MISSING` | 2 | STAT_SEMANTICS_MAPPING_MISSING | Refine the regex key mapping for split averages. |
| `DATA_TRULY_UNAVAILABLE` | 0 | - | N/A |
| `ANALYZABLE_AFTER_HYDRATION` | 8 | Potentially Analyzable | Ensure S3 validation passes with length >= 5. |
