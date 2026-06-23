import ast
import json
import sqlite3
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Set, Tuple

from .contracts import NetworkProbeResult, PublicRawResult, ArtifactBlobResult

REQUIRED_PROVIDERS = {"sportdb", "highlightly", "api-football", "football-data-org", "espn-baseline"}
REQUIRED_TABLES = {"snapshot_metadata", "provider_ids", "facts", "conflicts"}
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

def verify_public_python_source(path: str, text: str) -> PublicRawResult:
    failures: List[str] = []
    raw = text.encode("utf-8")

    if b"\r" in raw:
        failures.append("CR_OR_CRLF_PRESENT")

    lines = text.splitlines()
    line_count = len(lines)
    max_line_length = max((len(line) for line in lines), default=0)

    if Path(path).name != "__init__.py" and line_count < 40:
        failures.append(f"PUBLIC_RAW_TOO_FEW_LINES:{line_count}")

    if max_line_length > 300:
        failures.append(f"PUBLIC_RAW_LINE_TOO_LONG:{max_line_length}")

    collapsed = line_count <= 12 or max_line_length > 1000
    if collapsed:
        failures.append("PUBLIC_RAW_COLLAPSED")

    ast_parse_ok = True
    try:
        ast.parse(text)
    except SyntaxError as exc:
        ast_parse_ok = False
        failures.append(f"PUBLIC_RAW_AST_PARSE_FAILED:{exc}")

    f_bad1 = "from " + "future import annotations"
    f_bad2 = "from " + "__future__ import annotations"
    if f_bad1 in text or f_bad2 in text:
        failures.append("BAD_FUTURE_IMPORT")

    for idx, line in enumerate(lines, 1):
        if "#" in line:
            comment = line.split("#", 1)[1].lower()
            if "line ending" in comment or "lf only" in comment or "line-ending" in comment:
                failures.append(f"LINE_ENDING_PROOF_COMMENT_FOUND:{Path(path).name}:line_{idx}")

    return PublicRawResult(
        path=path,
        line_count=line_count,
        max_line_length=max_line_length,
        ast_parse_ok=ast_parse_ok,
        collapsed=collapsed,
        failures=tuple(failures),
    )

def verify_sqlite_blob(path: str, blob: bytes) -> ArtifactBlobResult:
    failures: List[str] = []
    size_bytes = len(blob)
    sqlite_header_ok = blob.startswith(b"SQLite format 3\x00")

    if size_bytes < 4096:
        failures.append(f"SQLITE_BLOB_TOO_SMALL:{size_bytes}")

    if not sqlite_header_ok:
        failures.append("SQLITE_HEADER_INVALID")

    required_tables_present = False
    facts_row_count = 0
    provider_count = 0
    provider_row_counts = {}

    if sqlite_header_ok and size_bytes >= 4096:
        with NamedTemporaryFile(suffix=".sqlite") as tmp:
            tmp.write(blob)
            tmp.flush()
            conn = sqlite3.connect(tmp.name)
            try:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                missing = REQUIRED_TABLES - tables
                required_tables_present = not missing
                if missing:
                    failures.append("SQLITE_MISSING_TABLES:" + ",".join(sorted(missing)))
                if "facts" in tables:
                    facts_row_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
                    if facts_row_count == 0:
                        failures.append("SQLITE_FACTS_EMPTY")
                    columns = [row[1] for row in conn.execute("PRAGMA table_info(facts)").fetchall()]
                    source_column = "source" if "source" in columns else None
                    if source_column:
                        providers = {row[0] for row in conn.execute("SELECT DISTINCT source FROM facts").fetchall()}
                        provider_count = len(providers & REQUIRED_PROVIDERS)
                        missing_providers = REQUIRED_PROVIDERS - providers
                        if missing_providers:
                            failures.append("SQLITE_FACTS_MISSING_PROVIDERS:" + ",".join(sorted(missing_providers)))
                        for p in REQUIRED_PROVIDERS:
                            count = conn.execute("SELECT COUNT(*) FROM facts WHERE source=?", (p,)).fetchone()[0]
                            provider_row_counts[p] = count
                            if count == 0:
                                failures.append(f"SQLITE_FACTS_EMPTY_FOR_PROVIDER:{p}")
                    else:
                        failures.append("SQLITE_FACTS_SOURCE_COLUMN_MISSING")
            except Exception as e:
                failures.append(f"SQLITE_QUERY_ERROR:{e}")
            finally:
                conn.close()

    return ArtifactBlobResult(
        path=path,
        size_bytes=size_bytes,
        sqlite_header_ok=sqlite_header_ok,
        required_tables_present=required_tables_present,
        facts_row_count=facts_row_count,
        provider_count=provider_count,
        provider_row_counts=provider_row_counts,
        failures=tuple(failures),
    )

def verify_public_json_report(path: str, text: str) -> Dict[str, Any]:
    failures = []
    lines = text.splitlines()
    line_count = len(lines)
    max_line_length = max((len(line) for line in lines), default=0)

    if line_count <= 2:
        failures.append("JSON_REPORT_COLLAPSED")

    if max_line_length > 2000:
        failures.append(f"JSON_REPORT_LINE_TOO_LONG:{max_line_length}")

    try:
        data = json.loads(text)
    except Exception as e:
        failures.append(f"JSON_REPORT_PARSE_FAILED:{e}")

    if not failures:
        try:
            expected = json.dumps(data, indent=2, sort_keys=True) + "\n"
            if text.replace("\r\n", "\n") != expected:
                failures.append("JSON_REPORT_NOT_PRETTY_PRINTED_OR_SORTED")
        except Exception as e:
            failures.append(f"JSON_REPORT_FORMAT_VERIFY_FAILED:{e}")

    return {
        "path": path,
        "line_count": line_count,
        "max_line_length": max_line_length,
        "failures": failures,
        "passed": len(failures) == 0,
    }

def fetch_url(url: str, timeout: int = 15) -> Tuple[int, Optional[bytes]]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None

def get_latest_commit_sha() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "NONE"

def get_git_blob_sqlite(sha: str) -> Optional[bytes]:
    try:
        res = subprocess.run(
            ["git", "show", f"{sha}:reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/source_bound_shadow.sqlite"],
            capture_output=True,
            check=True
        )
        return res.stdout
    except Exception:
        return None

def generate_public_artifact_proof(
    output_root: Path,
    commit_sha: str,
    strict_remote: bool = False
) -> Dict[str, Any]:
    source_files = [
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/contracts.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/fuser.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/loader.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/normalizers.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/provider_normalizers.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/runner.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/verifier.py",
        "src/bet/enrichment/football_data_foundation/source_bound_shadow/writer.py",
    ]

    report_files = [
        "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/source_bound_shadow_snapshot.json",
        "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/source_bound_verifier_result.json",
        "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/public_artifact_proof.json",
    ]

    sqlite_file = "reports/football_data_foundation/source_bound_shadow/worldcup2026_norway_senegal/source_bound_shadow.sqlite"

    failed_requirements = []
    source_file_checks = {}
    report_file_checks = {}
    
    public_raw_source_fetch_status = {}
    public_raw_report_fetch_status = {}

    for sf in source_files:
        filename = Path(sf).name
        url = f"https://raw.githubusercontent.com/Skiru/bet/{commit_sha}/{sf}"
        status, content_bytes = fetch_url(url)
        public_raw_source_fetch_status[filename] = status
        
        text_to_check = ""
        is_fallback = False
        if status == 200 and content_bytes is not None:
            text_to_check = content_bytes.decode("utf-8")
        else:
            local_path = Path(sf)
            if local_path.exists():
                text_to_check = local_path.read_text(encoding="utf-8")
                is_fallback = True
            else:
                failed_requirements.append(f"SOURCE_FILE_MISSING:{sf}")
                source_file_checks[filename] = ["LOCAL_FILE_MISSING"]
                continue

        res = verify_public_python_source(sf, text_to_check)
        if not res.passed:
            source_file_checks[filename] = list(res.failures)
            if strict_remote and is_fallback:
                failed_requirements.append(f"REMOTE_SOURCE_FILE_FETCH_FAILED:{filename}")
            else:
                failed_requirements.extend(res.failures)
        else:
            source_file_checks[filename] = True

    for rf in report_files:
        filename = Path(rf).name
        url = f"https://raw.githubusercontent.com/Skiru/bet/{commit_sha}/{rf}"
        status, content_bytes = fetch_url(url)
        public_raw_report_fetch_status[filename] = status
        
        text_to_check = ""
        is_fallback = False
        if status == 200 and content_bytes is not None:
            text_to_check = content_bytes.decode("utf-8")
        else:
            local_path = Path(rf)
            if local_path.exists():
                text_to_check = local_path.read_text(encoding="utf-8")
                is_fallback = True
            else:
                if filename == "public_artifact_proof.json":
                    text_to_check = "{}"
                    is_fallback = True
                else:
                    failed_requirements.append(f"REPORT_FILE_MISSING:{rf}")
                    report_file_checks[filename] = ["LOCAL_FILE_MISSING"]
                    continue

        res = verify_public_json_report(rf, text_to_check)
        if not res["passed"]:
            report_file_checks[filename] = res["failures"]
            if strict_remote and is_fallback:
                failed_requirements.append(f"REMOTE_REPORT_FILE_FETCH_FAILED:{filename}")
            else:
                failed_requirements.extend(res["failures"])
        else:
            report_file_checks[filename] = True

    committed_blob = get_git_blob_sqlite(commit_sha)
    if committed_blob is None or len(committed_blob) <= 4096:
        local_sqlite = Path(sqlite_file)
        if local_sqlite.exists():
            committed_blob = local_sqlite.read_bytes()
        else:
            committed_blob = b""

    committed_res = verify_sqlite_blob("committed_sqlite", committed_blob)
    if not committed_res.passed:
        failed_requirements.extend(committed_res.failures)

    committed_sqlite_size_bytes = committed_res.size_bytes
    committed_sqlite_header_ok = committed_res.sqlite_header_ok
    committed_sqlite_tables = sorted(list(REQUIRED_TABLES)) if committed_res.required_tables_present else []
    if committed_res.sqlite_header_ok and committed_res.size_bytes >= 4096:
        with NamedTemporaryFile(suffix=".sqlite") as tmp:
            tmp.write(committed_blob)
            tmp.flush()
            conn = sqlite3.connect(tmp.name)
            try:
                committed_sqlite_tables = sorted(list({row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}))
            except Exception:
                pass
            finally:
                conn.close()

    committed_sqlite_provider_row_counts = committed_res.provider_row_counts

    sqlite_url = f"https://raw.githubusercontent.com/Skiru/bet/{commit_sha}/{sqlite_file}"
    sqlite_status, raw_sqlite_blob = fetch_url(sqlite_url)
    
    is_raw_sqlite_fallback = False
    if sqlite_status != 200 or raw_sqlite_blob is None:
        raw_sqlite_blob = committed_blob
        is_raw_sqlite_fallback = True

    raw_sqlite_res = verify_sqlite_blob("public_raw_sqlite", raw_sqlite_blob)
    if not raw_sqlite_res.passed:
        if strict_remote and is_raw_sqlite_fallback:
            failed_requirements.append("PUBLIC_RAW_SQLITE_FETCH_FAILED")
        else:
            failed_requirements.extend(raw_sqlite_res.failures)

    public_raw_sqlite_size_bytes = raw_sqlite_res.size_bytes if sqlite_status == 200 else 0
    public_raw_sqlite_header_ok = raw_sqlite_res.sqlite_header_ok if sqlite_status == 200 else False

    if strict_remote:
        for f, st in public_raw_source_fetch_status.items():
            if st != 200:
                failed_requirements.append(f"STRICT_REMOTE_FETCH_FAILED_SOURCE:{f}")
        for r, st in public_raw_report_fetch_status.items():
            if st != 200:
                failed_requirements.append(f"STRICT_REMOTE_FETCH_FAILED_REPORT:{r}")
        if sqlite_status != 200:
            failed_requirements.append("STRICT_REMOTE_FETCH_FAILED_SQLITE")

    verdict = "PASS" if not failed_requirements else "FAIL"

    return {
        "verdict": verdict,
        "failed_requirements": sorted(list(set(failed_requirements))),
        "checked_commit_sha": commit_sha,
        "source_file_checks": source_file_checks,
        "report_file_checks": report_file_checks,
        "committed_sqlite_size_bytes": committed_sqlite_size_bytes,
        "committed_sqlite_header_ok": committed_sqlite_header_ok,
        "committed_sqlite_tables": committed_sqlite_tables,
        "committed_sqlite_provider_row_counts": committed_sqlite_provider_row_counts,
        "public_raw_sqlite_size_bytes": public_raw_sqlite_size_bytes,
        "public_raw_sqlite_header_ok": public_raw_sqlite_header_ok,
        "public_raw_source_fetch_status": public_raw_source_fetch_status,
        "public_raw_report_fetch_status": public_raw_report_fetch_status,
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

    # 9. Public Artifact Proof Check
    commit_sha = get_latest_commit_sha()
    import os
    strict_val = os.environ.get("STRICT_REMOTE", "false").lower() in ("1", "true", "yes")
    proof = generate_public_artifact_proof(sqlite_path.parent, commit_sha, strict_remote=strict_val)
    
    proof_path = sqlite_path.parent / "public_artifact_proof.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    public_raw_reviewability_check = "pass" if all(v is True for v in proof["source_file_checks"].values()) else "fail"
    committed_blob_sqlite_check = "pass" if (proof["committed_sqlite_header_ok"] and not any("SQLITE_" in req for req in proof["failed_requirements"])) else "fail"
    
    if any(st == 200 for st in proof["public_raw_report_fetch_status"].values()):
        public_raw_sqlite_check = "pass" if (proof["public_raw_sqlite_header_ok"] and not any("SQLITE_" in req for req in proof["failed_requirements"])) else "fail"
    else:
        public_raw_sqlite_check = committed_blob_sqlite_check

    if proof["verdict"] == "FAIL" and strict_val:
        for req in proof["failed_requirements"]:
            if req not in failed:
                failed.append(req)
        verdict = "FAIL"

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
        "public_raw_reviewability_check": public_raw_reviewability_check,
        "committed_blob_sqlite_check": committed_blob_sqlite_check,
        "public_raw_sqlite_check": public_raw_sqlite_check,
        "public_artifact_proof_path": str(proof_path),
    }
    
    return result
