#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys

PROVIDER_KEYS = {
    "football-data-org": {
        "canonical": "FOOTBALL_DATA_ORG_KEY",
        "aliases": ["FOOTBALL_DATA_ORG_KEY"],
    },
    "api-football": {
        "canonical": "API_FOOTBALL_KEY",
        "aliases": ["API_FOOTBALL_KEY", "API_SPORTS_KEY"],
    },
    "sportdb": {
        "canonical": "SPORTDB_API_KEY",
        "aliases": ["SPORTDB_API_KEY", "SPORTDB_KEY"],
    },
    "highlightly": {
        "canonical": "HIGHLIGHTLY_API_KEY",
        "aliases": ["HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"],
    },
}


def parse_dot_env(file_path):
    env_dict = {}
    if not os.path.exists(file_path):
        return env_dict
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if len(val) >= 2 and (
                        (val[0] == '"' and val[-1] == '"')
                        or (val[0] == "'" and val[-1] == "'")
                    ):
                        val = val[1:-1]
                    env_dict[key] = val
    except Exception:
        pass
    return env_dict


def main():
    parser = argparse.ArgumentParser(
        description="Preflight check for live environment provider keys."
    )
    parser.add_argument(
        "--provider", required=True, help="Provider name (e.g., football-data-org)"
    )
    parser.add_argument(
        "--required",
        action="store_true",
        help="Exit with non-zero code if key is missing",
    )
    args = parser.parse_args()

    provider = args.provider
    if provider not in PROVIDER_KEYS:
        sys.stderr.write(f"Error: Unknown provider '{provider}'\n")
        sys.exit(1)

    provider_info = PROVIDER_KEYS[provider]
    canonical_key = provider_info["canonical"]
    aliases = provider_info["aliases"]

    val = ""
    source = "missing"
    present = False
    found_key = canonical_key

    # Check environment
    for alias in aliases:
        env_val = os.environ.get(alias, "")
        if env_val:
            val = env_val
            source = "environment"
            present = True
            found_key = alias
            break

    # Check .env
    if not present:
        dot_env_path = os.path.join(os.getcwd(), ".env")
        dot_env_dict = parse_dot_env(dot_env_path)
        for alias in aliases:
            dot_env_val = dot_env_dict.get(alias, "")
            if dot_env_val:
                val = dot_env_val
                source = "dot_env"
                present = True
                found_key = alias
                break

    length = len(val)
    sha256_prefix = ""
    if present:
        sha256_prefix = hashlib.sha256(val.encode("utf-8")).hexdigest()[:8]

    result = {
        "provider": provider,
        "canonical_key": canonical_key,
        "found_key": found_key,
        "present": present,
        "source": source,
        "length": length,
        "sha256_prefix": sha256_prefix,
    }

    # Output only a compact JSON object
    print(json.dumps(result))

    if args.required and not present:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
