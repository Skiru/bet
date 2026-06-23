import ast
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .contracts import NetworkProbeResult

REQUIRED_PROVIDERS = {"sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"}
RAW_LIKE_FACT_TYPES = {"match_event", "lineup", "match_statistic"}
SUMMARY_FACT_TYPES = {"match_event_summary", "lineup_summary", "statistics_summary", "odds_reference"}

def check_reviewability() -> List[str]:
    failed_review = []
    src_dir = Path(__file__).parent
    if not src_dir.exists():
        return [f"SOURCE_DIR_MISSING:{src_dir}"]
        
    for py_file in src_dir.glob("*.py"):
        try:
            content_bytes = py_file.read_bytes()
            content_str = content_bytes.decode("utf-8")
        except Exception as e:
            failed_review.append(f"READ_FAIL:{py_file.name}:{e}")
            continue
            
        if b"\r" in content_bytes:
            failed_review.append(f"CR_LINE_ENDINGS_FOUND:{py_file.name}")
            
        try:
            ast.parse(content_str)
        except Exception as e:
            failed_review.append(f"AST_PARSE_FAIL:{py_file.name}:{e}")
            
        lines = content_str.split("\n")
        if py_file.name != "__init__.py":
            if len(lines) < 40:
                failed_review.append(f"FILE_TOO_SHORT:{py_file.name}:{len(lines)}")
                
        for idx, line in enumerate(lines, 1):
            if len(line) > 300 and ";" in line:
                failed_review.append(f"COLLAPSED_SEMICOLONS:{py_file.name}:line_{idx}")
                
        target_f1 = "from" + " future import annotations"
        target_f2 = "from" + " __future__ import annotations"
        if target_f1 in content_str or target_f2 in content_str:
            failed_review.append(f"FUTURE_ANNOTATIONS_FOUND:{py_file.name}")
            
        for idx, line in enumerate(lines, 1):
            if "#" in line:
                comment = line.split("#", 1)[1].lower()
                if "line ending" in comment or "lf only" in comment or "line-ending" in comment:
                    failed_review.append(f"LINE_ENDING_PROOF_COMMENT_FOUND:{py_file.name}:line_{idx}")
                    
    return failed_review

def walk_json_structural(data: Any, is_espn: bool = False, path: List[str] = None) -> List[str]:
    if path is None:
        path = []
    failures = []
    
    FORBIDDEN_FIELD_NAMES = {
        "raw_payload", "raw_headers", "authorization", "x-api-key",
        "x-rapidapi-key", "cookie", "set-cookie", "token", "api_key",
        "password", "secret", "bearer"
    }
    ESPN_FORBIDDEN_KEYS = {"story", "article", "media", "body"}
    FORBIDDEN_TEXT_VALUES = {
        "betting decision", "recommendation", "stake", "edge", "tip", "pick",
        "secret", "bearer", "token", "password", "raw_payload", "raw_headers",
        "authorization", "x-api-key", "x-rapidapi-key", "api_key"
    }

    if isinstance(data, dict):
        for k, v in data.items():
            k_lower = k.lower()
            if k_lower in FORBIDDEN_FIELD_NAMES:
                failures.append(f"FORBIDDEN_FIELD_NAME:{'.'.join(path + [k])}")
            if is_espn and k_lower in ESPN_FORBIDDEN_KEYS:
                failures.append(f"ESPN_RAW_FIELD_PRESENT:{'.'.join(path + [k])}")
            
            failures.extend(walk_json_structural(v, is_espn=is_espn, path=path + [k]))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            failures.extend(walk_json_structural(item, is_espn=is_espn, path=path + [str(idx)]))
    elif isinstance(data, str):
        val_lower = data.lower()
        for token in FORBIDDEN_TEXT_VALUES:
            if token in val_lower:
                if token == "tip" and "tippeligaen" in val_lower:
                    continue
                if token == "pick" and ("pick up" in val_lower or "picking up" in val_lower):
                    continue
                failures.append(f"FORBIDDEN_TEXT_VALUE:{'.'.join(path)}:{token}")
    return failures

def check_sqlite_contents(sqlite_path: Path) -> Dict[str, Any]:
    errors = []
    required_tables = {"snapshot_metadata", "provider_ids", "facts", "conflicts"}
    
    if not sqlite_path.exists():
        errors.append("SQLITE_FILE_MISSING")
        return {
            "table_check": "FAIL",
            "row_count_check": "FAIL",
            "errors": errors,
        }
    if sqlite_path.stat().st_size == 0:
        errors.append("SQLITE_FILE_EMPTY")
        return {
            "table_check": "FAIL",
            "row_count_check": "FAIL",
            "errors": errors,
        }
        
    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()
        
        # 1. Table check
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        missing_tables = required_tables - existing_tables
        if missing_tables:
            errors.append(f"SQLITE_MISSING_TABLES:{','.join(sorted(missing_tables))}")
            table_check = "FAIL"
        else:
            table_check = "PASS"
            
        # 2. Row count check
        row_count_check = "PASS"
        if table_check == "PASS":
            # snapshot_metadata
            cursor.execute("SELECT COUNT(*) FROM snapshot_metadata")
            if cursor.fetchone()[0] == 0:
                errors.append("SQLITE_EMPTY_snapshot_metadata")
                row_count_check = "FAIL"
                
            # provider_ids
            cursor.execute("SELECT COUNT(*) FROM provider_ids")
            if cursor.fetchone()[0] == 0:
                errors.append("SQLITE_EMPTY_provider_ids")
                row_count_check = "FAIL"
                
            # facts
            cursor.execute("SELECT COUNT(*) FROM facts")
            if cursor.fetchone()[0] == 0:
                errors.append("SQLITE_EMPTY_facts")
                row_count_check = "FAIL"
            else:
                # SQLite table facts must have at least one row per provider
                cursor.execute("SELECT DISTINCT source FROM facts")
                present_providers = {row[0] for row in cursor.fetchall()}
                missing_providers = REQUIRED_PROVIDERS - present_providers
                if missing_providers:
                    errors.append(f"SQLITE_FACTS_MISSING_PROVIDERS:{','.join(sorted(missing_providers))}")
                    row_count_check = "FAIL"
                
                # Check for zero rows per provider
                for provider in REQUIRED_PROVIDERS:
                    cursor.execute("SELECT COUNT(*) FROM facts WHERE source=?", (provider,))
                    if cursor.fetchone()[0] == 0:
                        errors.append(f"SQLITE_FACTS_EMPTY_FOR_PROVIDER:{provider}")
                        row_count_check = "FAIL"
                        
        # 3. Structural forbidden content check on SQLite schema and data
        FORBIDDEN_FIELDS = {
            "raw_payload", "raw_headers", "authorization", "x-api-key",
            "x-rapidapi-key", "cookie", "set-cookie", "token", "api_key",
            "password", "secret", "bearer"
        }
        ESPN_FORBIDDEN_KEYS = {"story", "article", "media", "body"}
        FORBIDDEN_TEXT_VALUES = {
            "betting decision", "recommendation", "stake", "edge", "tip", "pick",
            "secret", "bearer", "token", "password", "raw_payload", "raw_headers",
            "authorization", "x-api-key", "x-rapidapi-key", "api_key"
        }
        
        for table in existing_tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            for col in columns:
                if col.lower() in FORBIDDEN_FIELDS:
                    errors.append(f"SQLITE_FORBIDDEN_COLUMN_NAME:{table}.{col}")
                    
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            for r_idx, row in enumerate(rows):
                row_dict = dict(zip(columns, row))
                
                is_espn_row = False
                if table == "facts" and "source" in row_dict and row_dict["source"] == "espn-baseline":
                    is_espn_row = True
                    
                for col_name, val in row_dict.items():
                    if val is None:
                        continue
                    val_str = str(val)
                    val_str_lower = val_str.lower()
                    
                    try:
                        parsed_json = json.loads(val_str)
                        if isinstance(parsed_json, (dict, list)):
                            json_errs = walk_json_structural(parsed_json, is_espn=is_espn_row)
                            for je in json_errs:
                                errors.append(f"SQLITE_JSON_ERROR:{table}[{col_name}]:{je}")
                            continue
                    except ValueError:
                        pass
                        
                    for token in FORBIDDEN_TEXT_VALUES:
                        if token in val_str_lower:
                            if token == "tip" and "tippeligaen" in val_str_lower:
                                continue
                            if token == "pick" and ("pick up" in val_str_lower or "picking up" in val_str_lower):
                                continue
                            errors.append(f"SQLITE_FORBIDDEN_TEXT_VALUE:{table}[{col_name}]:{token}")
                    if is_espn_row:
                        for token in ESPN_FORBIDDEN_KEYS:
                            if token in val_str_lower:
                                errors.append(f"SQLITE_ESPN_FORBIDDEN_KEY:{table}[{col_name}]:{token}")
                                
        conn.close()
    except Exception as e:
        errors.append(f"SQLITE_INSPECTION_FAILED:{e}")
        table_check = "FAIL"
        row_count_check = "FAIL"
        
    return {
        "table_check": table_check,
        "row_count_check": row_count_check,
        "errors": errors,
    }

def verify_shadow_bundle(
    snapshot_path: Path,
    sqlite_path: Path,
    diagnostics_path: Path,
    fact_counts_path: Path,
    network_probe: Optional[NetworkProbeResult] = None,
    expected_fixture_slug: str = "worldcup2026-norway-senegal",
) -> Dict[str, Any]:
    failed: List[str] = []
    
    # Check if snapshot file exists
    if not snapshot_path.exists():
        failed.append("SNAPSHOT_FILE_MISSING")
        return {"verdict": "FAIL", "failed_requirements": ["SNAPSHOT_FILE_MISSING"]}

    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    
    # 1. Structural Walk on JSON Snapshot
    json_errors = walk_json_structural(snapshot_data, is_espn=False)
    for fact in snapshot_data.get("facts", []):
        if fact.get("source") == "espn-baseline":
            val = fact.get("value")
            espn_errors = walk_json_structural(val, is_espn=True)
            for ee in espn_errors:
                # Prefix with path
                json_errors.append(f"ESPN_RAW_FIELD_PRESENT:{ee}")
    failed.extend(json_errors)
    
    # 2. General metadata validation
    shadow_status = snapshot_data.get("shadow_status")
    if shadow_status == "PRODUCTION_READY":
        failed.append("STATUS_IS_PRODUCTION_READY")
    elif shadow_status != "SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW":
        failed.append("STATUS_IS_NOT_SHADOW_ENRICHMENT_READY_FOR_MANUAL_REVIEW")

    if snapshot_data.get("production_selectable") is not False:
        failed.append("PRODUCTION_SELECTABLE_IS_TRUE")

    if snapshot_data.get("manual_authorization_required") is not True:
        failed.append("MANUAL_AUTHORIZATION_REQUIRED_IS_FALSE")

    provider_ids = snapshot_data.get("provider_ids") or {}
    present_providers = set(provider_ids.keys())
    missing_ids = REQUIRED_PROVIDERS - present_providers
    if missing_ids:
        failed.append("MISSING_REQUIRED_PROVIDER_IDS:" + ",".join(sorted(missing_ids)))

    score = snapshot_data.get("score") or {}
    if score != {"home": 3, "away": 2} and score != {"away": 2, "home": 3}:
        failed.append("SCORE_NOT_NORWAY_3_2_SENEGAL")

    conflicts = snapshot_data.get("conflicts") or []
    if conflicts:
        failed.append("CONFLICTS_ARE_PRESENT")

    facts = snapshot_data.get("facts") or []
    for fact in facts:
        if not fact.get("source_file") or not fact.get("body_sha256"):
            failed.append("FACT_MISSING_PROVENANCE")
            break

    has_score_fact_for_score = False
    for fact in facts:
        if fact.get("fact_type") == "score" and fact.get("key") == "full_time_score":
            val = fact.get("value")
            if isinstance(val, dict) and val.get("home") == 3 and val.get("away") == 2:
                has_score_fact_for_score = True
                break
    if not has_score_fact_for_score:
        failed.append("HARDCODED_FALLBACK_USED_WITHOUT_SUPPORTING_FACTS")

    for fact in facts:
        if fact.get("source") == "espn-baseline":
            if fact.get("source_role") != "unofficial_shadow_cross_check":
                failed.append("ESPN_INCORRECT_ROLE")

    for fact in facts:
        if fact.get("fact_type") in RAW_LIKE_FACT_TYPES:
            failed.append(f"RAW_LIKE_FACT_TYPE_PRESENT:{fact.get('fact_type')}")

    for fact in facts:
        val_json = json.dumps(fact.get("value"), sort_keys=True)
        if len(val_json) > 12000:
            failed.append(f"FACT_VALUE_TOO_LARGE:{fact.get('source')}")

    if "reports/football_data_foundation/source_bound_shadow" not in str(sqlite_path):
        failed.append("SQLITE_ARTIFACT_OUTSIDE_ALLOWED_PATH")

    contributing_providers = set(f.get("source") for f in facts)
    if len(contributing_providers & REQUIRED_PROVIDERS) < 5:
        failed.append("FEWER_THAN_FIVE_PROVIDERS_CONTRIBUTE_FACTS")

    # SportDB check: check only for specific betting words
    for fact in facts:
        if fact.get("source") == "sportdb" and fact.get("fact_type") == "odds_reference":
            val_str = str(fact.get("value")).lower()
            if any(dec in val_str for dec in ["tip", "pick", "recommendation", "betting decision"]):
                failed.append("SPORTDB_ODDS_CLASSIFIED_AS_BETTING_DECISION")

    source_priority = snapshot_data.get("source_priority")
    expected_priority = ["api-football", "sportdb", "highlightly", "football-data-org", "espn-baseline"]
    if source_priority != expected_priority:
        failed.append("SOURCE_PRIORITY_MISSING_OR_NON_DETERMINISTIC")

    sportdb_facts = [f for f in facts if f.get("source") == "sportdb"]
    sportdb_non_mapping = [f for f in sportdb_facts if f.get("fact_type") != "provider_mapping"]
    if not sportdb_non_mapping:
        failed.append("SPORTDB_ONLY_CONTRIBUTES_MAPPING_FACTS")

    hl_facts = [f for f in facts if f.get("source") == "highlightly"]
    hl_non_mapping = [f for f in hl_facts if f.get("fact_type") != "provider_mapping"]
    if not hl_non_mapping:
        failed.append("HIGHLIGHTLY_ONLY_CONTRIBUTES_MAPPING_FACTS")

    api_facts = [f for f in facts if f.get("source") == "api-football"]
    api_detailed = [f for f in api_facts if f.get("fact_type") in SUMMARY_FACT_TYPES]
    if not api_detailed:
        failed.append("API_FOOTBALL_CONTRIBUTES_NO_DETAILED_FACTS")

    fdo_facts = [f for f in facts if f.get("source") == "football-data-org"]
    fdo_score_status_ref = [f for f in fdo_facts if f.get("fact_type") in {"score", "match_status", "competition"}]
    if not fdo_score_status_ref:
        failed.append("FOOTBALL_DATA_ORG_CONTRIBUTES_NO_STATUS_SCORE_REFERENCE_FACTS")

    for prov in ["api-football", "sportdb", "highlightly"]:
        prov_facts = [f for f in facts if f.get("source") == prov]
        has_summary = any(f.get("fact_type") in SUMMARY_FACT_TYPES for f in prov_facts)
        if not has_summary:
            failed.append(f"MISSING_SUMMARY_FACT_TYPE_FOR_{prov.upper()}")

    # 3. SQLite checks
    sqlite_res = check_sqlite_contents(sqlite_path)
    sqlite_table_check = sqlite_res["table_check"]
    sqlite_row_count_check = sqlite_res["row_count_check"]
    failed.extend(sqlite_res["errors"])

    # 4. Network Probe Check
    if network_probe is None:
        network_probe_check = "FAIL"
        failed.append("NETWORK_PROBE_NOT_EXECUTED")
    elif not network_probe.runner_executed_under_socket_block:
        network_probe_check = "FAIL"
        failed.append("NETWORK_PROBE_NOT_EXECUTED")
    elif network_probe.network_attempts_detected > 0:
        network_probe_check = "FAIL"
        failed.append("LIVE_NETWORK_USED")
    else:
        network_probe_check = "PASS"

    # 5. Fixture Slug Source Check
    snapshot_slug = snapshot_data.get("fixture_slug")
    if snapshot_slug and snapshot_slug == expected_fixture_slug:
        fixture_slug_source_check = "PASS"
    else:
        fixture_slug_source_check = "FAIL"
        failed.append(f"FIXTURE_SLUG_MISMATCH:{snapshot_slug} vs {expected_fixture_slug}")

    # 6. Committed Test Artifact Check
    test_artifact_dir = Path("/Users/mkoziol/projects/bet-multisport-enrichment-v1/reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal_test")
    if test_artifact_dir.exists():
        committed_test_artifact_check = "FAIL"
        failed.append("COMMITTED_TEST_ARTIFACT_PRESENT")
    else:
        committed_test_artifact_check = "PASS"

    # 7. Reviewability check
    review_errs = check_reviewability()
    failed.extend(review_errs)
    reviewability_check_status = "FAIL" if any("LINE" in f or "CR_" in f or "AST" in f or "SHORT" in f or "PROOF" in f or "FUTURE" in f or "SEMICOLONS" in f for f in failed) else "PASS"

    # 8. Structural Forbidden Content Check status
    has_structural_forbidden = any(
        "FORBIDDEN" in f or "ESPN_RAW_FIELD" in f or "SQLITE_FORBIDDEN" in f or "SQLITE_ESPN" in f
        for f in failed
    )
    structural_forbidden_content_check = "FAIL" if has_structural_forbidden else "PASS"

    # Verdict
    verdict = "PASS" if not failed else "FAIL"

    forbidden_payload_check = "FAIL" if any(f.startswith("FORBIDDEN") or "RAW" in f for f in failed) else "PASS"
    secret_leak_check = "FAIL" if any("SECRET" in f or "KEYWORD" in f or "LEAK" in f for f in failed) else "PASS"
    production_activation_check = "FAIL" if any("PRODUCTION" in f or "SELECTABLE" in f or "ACTIVATION" in f for f in failed) else "PASS"
    sqlite_artifact_check = "FAIL" if "SQLITE_ARTIFACT_OUTSIDE_ALLOWED_PATH" in failed else "PASS"
    sqlite_content_check = "FAIL" if any("SQLITE_" in f for f in failed) else "PASS"
    odds_reference_check = "FAIL" if "SPORTDB_ODDS_CLASSIFIED_AS_BETTING_DECISION" in failed else "PASS"

    result = {
        "verdict": verdict,
        "failed_requirements": sorted(list(set(failed))),
        "provider_ids": provider_ids,
        "provider_fact_counts": {p: len([f for f in facts if f.get("source") == p]) for p in REQUIRED_PROVIDERS},
        "score_consensus": score,
        "conflicts": conflicts,
        "forbidden_payload_check": forbidden_payload_check,
        "secret_leak_check": secret_leak_check,
        "production_activation_check": production_activation_check,
        "sqlite_artifact_check": sqlite_artifact_check,
        "sqlite_content_check": sqlite_content_check,
        "live_network_check": network_probe_check,
        "reviewability_check": reviewability_check_status,
        "odds_reference_check": odds_reference_check,
        "shadow_status": shadow_status or "NONE",
        "network_probe_check": network_probe_check,
        "fixture_slug_source_check": fixture_slug_source_check,
        "sqlite_table_check": sqlite_table_check,
        "sqlite_row_count_check": sqlite_row_count_check,
        "committed_test_artifact_check": committed_test_artifact_check,
        "structural_forbidden_content_check": structural_forbidden_content_check,
    }
    
    return result
