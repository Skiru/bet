#!/usr/bin/env python3
"""
Phase 3 Fixture — Large Output Case
Generates large output to test output limit enforcement.

Usage:
    python scripts/fixtures/bet-script-large-output.py [--size-kb N]

Exit codes:
    0 — Success
    2 — Invalid arguments
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Large output fixture")
    parser.add_argument("--size-kb", type=int, default=64,
                        help="Kilobytes of output to generate (default: 64)")
    args = parser.parse_args()

    # Validate size
    if not 1 <= args.size_kb <= 1024:
        print(json.dumps({"error": "size_kb must be 1-1024"}), file=sys.stderr)
        sys.exit(2)

    # Generate JSON with large data field
    # Each 'X' is 1 byte, so we need size_kb * 1024 bytes
    target_bytes = args.size_kb * 1024
    
    # Use a JSON structure with a large data field
    # Account for JSON overhead: {"data": "..."}
    overhead = 12  # {"data": ""}
    data_size = target_bytes - overhead
    
    if data_size < 1:
        data_size = 1
    
    large_data = "X" * data_size
    
    result = {
        "status": "large_output",
        "size_kb": args.size_kb,
        "data": large_data
    }

    print(json.dumps(result))
    sys.exit(0)


if __name__ == "__main__":
    main()
