# Team Identity Resolution Contract

## 1. Objective
Define a robust, verifiable contract and implementation for resolving raw team names (possibly variants or aliases) to canonical names and unique provider IDs for football.

---

## 2. TeamIdentityResult Fields

| Field Name | Type | Description |
|---|---|---|
| `raw_team_name` | `str` | The input team name exactly as scraped or parsed from the odds source. |
| `sport` | `str` | The sport category (e.g. `football`). |
| `competition` | `str \| None` | The associated competition or league name context. |
| `country_or_context` | `str \| None` | Country of origin or structural region/context. |
| `provider` | `str \| None` | Target provider identity (e.g. `api-football`). |
| `provider_team_id` | `str \| None` | The provider's unique ID for the resolved team. |
| `canonical_name` | `str \| None` | The official, resolved canonical team name. |
| `aliases` | `list[str]` | A list of alternative names or aliases for the resolved team. |
| `confidence` | `str` | Confidence level of the match: `HIGH`, `MEDIUM`, or `MINIMAL`. |
| `source` | `str` | Matching algorithm/source used (e.g. `seed_exact`, `seed_alias`, `seed_normalized`, `db_resolve`). |
| `resolved` | `bool` | `True` if resolution was successful; `False` otherwise. |
| `failure_reason` | `str \| None` | Explains why resolution failed. If unresolved, must emit `TEAM_IDENTITY_NOT_RESOLVED`. |

---

## 3. Resolution Rules
1. **Exact Name Match First:** Check if `raw_team_name` matches a canonical name in seed dictionary or database.
2. **Alias Table / Normalization Second:** Check if `raw_team_name` matches any alias (case-insensitive) or normalized string (diacritics stripped, common suffix like `FC` or `CD` removed).
3. **Provider Search Third:** If configured, search provider API.
4. **No fuzzy match above threshold** without recording a lower confidence.
5. **Do Not Drop Candidates:** If a name is unresolved, do not silently drop the candidate. Set `resolved = False` and `failure_reason = "TEAM_IDENTITY_NOT_RESOLVED"`.

---

## 4. Target Smoke Cases & Seed Map

All target smoke cases are seeded with high confidence:
* **Brazil:** `api-football:1`, aliases `["Seleção", "Brasil", "Brazil national football team", "bra"]`
* **Japan:** `api-football:2`, aliases `["Samurai Blue", "Nippon", "Japan national football team", "jpn"]`
* **Germany:** `api-football:3`, aliases `["Die Mannschaft", "Deutschland", "Germany national football team", "ger"]`
* **Paraguay:** `api-football:4`, aliases `["La Albirroja", "Paraguay national football team", "par"]`
* **Melgar:** `api-football:5`, aliases `["FBC Melgar", "Melgar Arequipa"]`
* **CD Moquegua:** `api-football:6`, aliases `["Moquegua", "Club Deportivo Moquegua"]`
* **Kazma:** `api-football:7`, aliases `["Kazma SC", "Kazma Sporting Club"]`
* **Al-Salmiya:** `api-football:8`, aliases `["Al Salmiya", "Al-Salmiya SC"]`
* **Deportivo Garcilaso:** `api-football:9`, aliases `["Garcilaso", "Deportivo Garcilaso Cusco"]`
* **Deportivo Binacional:** `api-football:10`, aliases `["Binacional", "Escuela Municipal Deportivo Binacional"]`
* **B68 Toftir:** `api-football:11`, aliases `["B68", "Toftir"]`
* **Argir:** `api-football:12`, aliases `["AB Argir", "Argir Boltfelag"]`
* **HB Torshavn:** `api-football:13`, aliases `["HB", "Torshavn"]`
* **Skala:** `api-football:14`, aliases `["Skala IF", "Skala Boltfelag"]`
* **Vikingur:** `api-football:15`, aliases `["Vikingur Gota", "Vikingur Fano"]`
* **Runavik:** `api-football:16`, aliases `["NSI Runavik", "Runavik NSI"]`
