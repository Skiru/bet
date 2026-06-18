#!/usr/bin/env python3
import os
import sys
import json
import argparse
import hashlib

PROVIDER_KEYS = {
    'football-data-org': 'FOOTBALL_DATA_ORG_KEY'
}

def parse_dot_env(file_path):
    env_dict = {}
    if not os.path.exists(file_path):
        return env_dict
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                        val = val[1:-1]
                    env_dict[key] = val
    except Exception:
        pass
    return env_dict

def main():
    parser = argparse.ArgumentParser(description="Preflight check for live environment provider keys.")
    parser.add_argument('--provider', required=True, help="Provider name (e.g., football-data-org)")
    parser.add_argument('--required', action='store_true', help="Exit with non-zero code if key is missing")
    args = parser.parse_args()

    provider = args.provider
    if provider not in PROVIDER_KEYS:
        sys.stderr.write(f"Error: Unknown provider '{provider}'\n")
        sys.exit(1)

    key_name = PROVIDER_KEYS[provider]
    
    # Check environment
    env_val = os.environ.get(key_name, "")
    
    # Check .env
    dot_env_path = os.path.join(os.getcwd(), '.env')
    dot_env_dict = parse_dot_env(dot_env_path)
    dot_env_val = dot_env_dict.get(key_name, "")

    val = ""
    source = "missing"
    present = False

    if env_val:
        val = env_val
        source = "environment"
        present = True
    elif dot_env_val:
        val = dot_env_val
        source = "dot_env"
        present = True

    length = len(val)
    sha256_prefix = ""
    if present:
        sha256_prefix = hashlib.sha256(val.encode('utf-8')).hexdigest()[:8]

    result = {
        "key_name": key_name,
        "present": present,
        "source": source,
        "length": length,
        "sha256_prefix": sha256_prefix
    }

    # Output only a compact JSON object
    print(json.dumps(result))

    if args.required and not present:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
