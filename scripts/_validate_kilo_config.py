"""Validate kilo.jsonc — strip JSONC comments then parse."""
import json
import re
import sys

with open("kilo.jsonc", encoding="utf-8") as f:
    content = f.read()

# Remove full-line comments
content = re.sub(r"(?m)^\s*//.*$", "", content)
# Remove inline comments (only if outside a string — simplified heuristic)
content = re.sub(r'(?<=[\],}"0-9a-z])\s*//[^\n]*', "", content)
# Remove trailing commas before } or ]
content = re.sub(r",(\s*[}\]])", r"\1", content)

try:
    data = json.loads(content)
    print("✓ kilo.jsonc valid")
    print(f"  Provider: {list(data.get('provider', {}).keys())}")
    print(f"  Agents: {len(data.get('agent', {}))}")
    models = set(a.get("model", "N/A") for a in data.get("agent", {}).values())
    print(f"  Models: {models}")
except json.JSONDecodeError as e:
    print(f"✗ JSON error: {e}", file=sys.stderr)
    # Show context around error
    lines = content.split("\n")
    lineno = e.lineno - 1
    start = max(0, lineno - 2)
    end = min(len(lines), lineno + 3)
    for i in range(start, end):
        marker = ">>>" if i == lineno else "   "
        print(f"  {marker} {i+1}: {lines[i][:100]}", file=sys.stderr)
    sys.exit(1)
