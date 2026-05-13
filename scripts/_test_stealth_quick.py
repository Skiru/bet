#!/usr/bin/env python3
"""Quick stealth test — fetch sofascore.com homepage."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from data_enrichment_agent import fetch

html = fetch("https://www.sofascore.com", save_snapshot=False)
if html and len(html) > 500:
    print(f"OK: stealth HTML length={len(html)}")
else:
    print(f"FAIL: html={'None' if html is None else len(html)}")
