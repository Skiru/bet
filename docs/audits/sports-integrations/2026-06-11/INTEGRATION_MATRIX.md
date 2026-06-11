# Integration Matrix — Sports Integrations Portfolio Audit

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Schema Version:** 2.0  
**Generated:** 2026-06-11T09:45:00Z

---

## Integration Keys Inventory

### Football (soccer)

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `api-football::football::EVENT_AND_ENRICHMENT::default` | api-football | football | EVENT_AND_ENRICHMENT | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::football::EVENT_DISCOVERY::default` | odds-api-io | football | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `odds-api::football::EVENT_DISCOVERY::default` | odds-api | football | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | discovery/sources | ACTIVE_REACHABLE |
| `espn-football::football::ENRICHMENT_ONLY::default` | espn | football | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `flashscore-football::football::ENRICHMENT_ONLY::default` | flashscore | football | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `fbref::football::HISTORICAL_DATASET::default` | fbref | football | HISTORICAL_DATASET | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `understat::football::ENRICHMENT_ONLY::default` | understat | football | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `football-data-org::football::EVENT_DISCOVERY::default` | football-data-org | football | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `betclic::football::ODDS_ONLY::default` | betclic | football | ODDS_ONLY | default | BROWSER_AUTOMATION | SCRAPER_REGISTRY | ACTIVE_REACHABLE |

### Basketball

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `api-basketball::basketball::EVENT_AND_ENRICHMENT::default` | api-basketball | basketball | EVENT_AND_ENRICHMENT | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `nba-api::basketball::ENRICHMENT_ONLY::default` | nba-api | basketball | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `espn-basketball::basketball::ENRICHMENT_ONLY::default` | espn | basketball | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `flashscore-basketball::basketball::ENRICHMENT_ONLY::default` | flashscore | basketball | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `basketball-reference::basketball::HISTORICAL_DATASET::default` | basketball-reference | basketball | HISTORICAL_DATASET | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::basketball::EVENT_DISCOVERY::default` | odds-api-io | basketball | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### Volleyball

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default` | api-volleyball | volleyball | EVENT_AND_ENRICHMENT | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `espn-volleyball::volleyball::ENRICHMENT_ONLY::default` | espn | volleyball | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `flashscore-volleyball::volleyball::ENRICHMENT_ONLY::default` | flashscore | volleyball | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `volleybox::volleyball::HISTORICAL_DATASET::default` | volleybox | volleyball | HISTORICAL_DATASET | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::volleyball::EVENT_DISCOVERY::default` | odds-api-io | volleyball | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### Tennis

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `tennis-abstract::tennis::EVENT_AND_ENRICHMENT::default` | tennis-abstract | tennis | EVENT_AND_ENRICHMENT | default | STATIC_HTML | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `sackmann::tennis::HISTORICAL_DATASET::atp` | sackmann | tennis | HISTORICAL_DATASET | atp | LOCAL_OR_OPEN_DATASET | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `sackmann::tennis::HISTORICAL_DATASET::wta` | sackmann | tennis | HISTORICAL_DATASET | wta | LOCAL_OR_OPEN_DATASET | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `espn-tennis::tennis::ENRICHMENT_ONLY::default` | espn | tennis | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `flashscore-tennis::tennis::ENRICHMENT_ONLY::default` | flashscore | tennis | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::tennis::EVENT_DISCOVERY::default` | odds-api-io | tennis | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### Hockey

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `api-hockey::hockey::EVENT_AND_ENRICHMENT::default` | api-hockey | hockey | EVENT_AND_ENRICHMENT | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `nhl-api::hockey::ENRICHMENT_ONLY::default` | nhl-api | hockey | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `espn-hockey::hockey::ENRICHMENT_ONLY::default` | espn | hockey | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `flashscore-hockey::hockey::ENRICHMENT_ONLY::default` | flashscore | hockey | ENRICHMENT_ONLY | default | PUBLIC_XHR_OR_JSON | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `hockey-reference::hockey::HISTORICAL_DATASET::default` | hockey-reference | hockey | HISTORICAL_DATASET | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `moneypuck::hockey::ENRICHMENT_ONLY::default` | moneypuck | hockey | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `scrapernhl::hockey::ENRICHMENT_ONLY::default` | scrapernhl | hockey | ENRICHMENT_ONLY | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::hockey::EVENT_DISCOVERY::default` | odds-api-io | hockey | EVENT_DISCOVERY | default | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### CS2 (Counter-Strike 2)

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `hltv::cs2::EVENT_AND_ENRICHMENT::default` | hltv | cs2 | EVENT_AND_ENRICHMENT | default | BROWSER_AUTOMATION | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `bo3gg::cs2::EVENT_AND_ENRICHMENT::default` | bo3gg | cs2 | EVENT_AND_ENRICHMENT | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `gosugamers::cs2::EVENT_DISCOVERY::default` | gosugamers | cs2 | EVENT_DISCOVERY | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::cs2::EVENT_DISCOVERY::esports` | odds-api-io | cs2 | EVENT_DISCOVERY | esports | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### Dota 2

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `opendota::dota2::EVENT_AND_ENRICHMENT::default` | opendota | dota2 | EVENT_AND_ENRICHMENT | default | DOCUMENTED_PUBLIC_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |
| `gosugamers::dota2::EVENT_DISCOVERY::default` | gosugamers | dota2 | EVENT_DISCOVERY | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::dota2::EVENT_DISCOVERY::esports` | odds-api-io | dota2 | EVENT_DISCOVERY | esports | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

### Valorant

| integration_key | source | sport | role | variant | access_method | registration | reachability |
|---|---|---|---|---|---|---|---|
| `vlr::valorant::EVENT_AND_ENRICHMENT::default` | vlr | valorant | EVENT_AND_ENRICHMENT | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `bo3gg::valorant::EVENT_AND_ENRICHMENT::default` | bo3gg | valorant | EVENT_AND_ENRICHMENT | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `gosugamers::valorant::EVENT_DISCOVERY::default` | gosugamers | valorant | EVENT_DISCOVERY | default | STATIC_HTML | SCRAPER_REGISTRY | ACTIVE_REACHABLE |
| `odds-api-io::valorant::EVENT_DISCOVERY::esports` | odds-api-io | valorant | EVENT_DISCOVERY | esports | LICENSED_OR_OFFICIAL_API | CLIENT_REGISTRY | ACTIVE_REACHABLE |

---

## Summary Statistics

- **Total Sports Found:** 8 (football, basketball, volleyball, tennis, hockey, cs2, dota2, valorant)
- **Total Integration Keys:** 42
- **Sports NOT Found:** None (all 8 contract-specified sports present)

### By Role

| Role | Count |
|---|---|
| EVENT_AND_ENRICHMENT | 12 |
| EVENT_DISCOVERY | 10 |
| ENRICHMENT_ONLY | 12 |
| ODDS_ONLY | 1 |
| HISTORICAL_DATASET | 7 |

### By Access Method

| Access Method | Count |
|---|---|
| LICENSED_OR_OFFICIAL_API | 14 |
| DOCUMENTED_PUBLIC_API | 8 |
| STATIC_HTML | 12 |
| PUBLIC_XHR_OR_JSON | 5 |
| BROWSER_AUTOMATION | 2 |
| LOCAL_OR_OPEN_DATASET | 2 |

---

## Gate Results

*To be populated during P2-P4 phases*

---

## Final States

*To be populated during P5-P6 phases*
