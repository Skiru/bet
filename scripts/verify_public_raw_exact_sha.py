#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request


def get_thresholds(path: str) -> dict[str, int]:
    if "test_source_admission_benchmark.py" in path:
        return {"lf": 250, "max_line": 140}
    elif "source_admission_benchmark.py" in path:
        return {"lf": 800, "max_line": 140}
    elif "source_probe_runner.py" in path:
        return {"lf": 350, "max_line": 140}
    elif "source_probe_contracts.py" in path:
        return {"lf": 30, "max_line": 140}
    elif "05_corrected_source_value_scorecard.json" in path:
        return {"lf": 250, "max_line": 240}
    elif "06_corrected_admission_decision_matrix.json" in path:
        return {"lf": 100, "max_line": 240}
    elif "07_corrected_next_implementation_plan.md" in path:
        return {"lf": 20, "max_line": 240}
    elif "r2_consistency_validation.json" in path:
        return {"lf": 40, "max_line": 240}
    elif "l2b_corrected_admission_manifest.json" in path:
        return {"lf": 40, "max_line": 240}
    return {"lf": 0, "max_line": 999999}

def is_valid_sha(sha: str) -> bool:
    if len(sha) != 40:
        return False
    try:
        int(sha, 16)
        return True
    except ValueError:
        return False

def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python3 verify_public_raw_exact_sha.py <END_SHA> <path1> <path2> ...", file=sys.stderr)
        sys.exit(1)

    end_sha = sys.argv[1].strip()
    paths = [p.strip() for p in sys.argv[2:]]

    # Validate that end_sha is a valid 40-character hex commit SHA, not a branch name or branch URL
    if not is_valid_sha(end_sha):
        print(f"ERROR: Invalid END_SHA format '{end_sha}'. Must be a 40-character hexadecimal git commit SHA. Branch names/URLs are rejected.", file=sys.stderr)
        sys.exit(1)

    results = []
    overall_success = True

    for path in paths:
        # Construct public raw URL using exact END_SHA
        # Reject if path contains branch name or anything suspicious
        if "feat" in path or "main" in path or "origin" in path:
            # wait, path itself shouldn't have branches, but let's be careful
            pass

        url = f"https://raw.githubusercontent.com/Skiru/bet/{end_sha}/{path}"

        # 1. Fetch public raw
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.getcode()
                public_bytes = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            public_bytes = b""
            print(f"HTTP error fetching {path}: {e}", file=sys.stderr)
        except Exception as e:
            status = 500
            public_bytes = b""
            print(f"Network error fetching {path}: {e}", file=sys.stderr)

        if status != 200:
            print(f"ERROR: Non-200 HTTP status ({status}) for {path}", file=sys.stderr)
            overall_success = False
            results.append({
                "path": path,
                "url": url,
                "status": "FETCH_FAILED",
                "http_status": status
            })
            continue

        # 2. Get local git object bytes from git show
        res = subprocess.run(["git", "show", f"{end_sha}:{path}"], capture_output=True)
        if res.returncode != 0:
            print(f"ERROR: git show {end_sha}:{path} failed!", file=sys.stderr)
            overall_success = False
            results.append({
                "path": path,
                "url": url,
                "status": "GIT_SHOW_FAILED"
            })
            continue

        git_bytes = res.stdout

        # 3. Compare bytes
        public_sha256 = hashlib.sha256(public_bytes).hexdigest()
        git_sha256 = hashlib.sha256(git_bytes).hexdigest()

        bytes_match = (public_sha256 == git_sha256)

        # 4. Metrics & Thresholds
        lf_count = public_bytes.count(b'\n')
        cr_count = public_bytes.count(b'\r')
        crlf_count = public_bytes.count(b'\r\n')

        lines = public_bytes.split(b'\n')
        max_line_len = 0
        if public_bytes:
            line_lengths = []
            for line in lines:
                stripped = line
                if stripped.endswith(b'\r'):
                    stripped = stripped[:-1]
                line_lengths.append(len(stripped))
            max_line_len = max(line_lengths) if line_lengths else 0

        thresh = get_thresholds(path)
        thresholds_passed = (lf_count >= thresh["lf"]) and (max_line_len <= thresh["max_line"])

        path_ok = bytes_match and thresholds_passed

        if not path_ok:
            overall_success = False
            print(f"ERROR: Verification failed for {path}", file=sys.stderr)
            print(f"  Bytes Match: {bytes_match} (Git: {git_sha256[:8]}, Public: {public_sha256[:8]})", file=sys.stderr)
            print(f"  LF Count: {lf_count} (threshold >= {thresh['lf']})", file=sys.stderr)
            print(f"  Max Line Length: {max_line_len} (threshold <= {thresh['max_line']})", file=sys.stderr)

        results.append({
            "path": path,
            "url": url,
            "git_object_sha256": git_sha256,
            "public_raw_sha256": public_sha256,
            "bytes_match": bytes_match,
            "lf_count": lf_count,
            "cr_count": cr_count,
            "crlf_count": crlf_count,
            "max_line_len": max_line_len,
            "thresholds_passed": thresholds_passed,
            "status": "PASSED" if path_ok else "FAILED"
        })

    # Print machine-readable JSON output on stdout
    print(json.dumps({
        "overall_success": overall_success,
        "results": results
    }, indent=2))

    if not overall_success:
        sys.exit(1)

if __name__ == "__main__":
    main()
