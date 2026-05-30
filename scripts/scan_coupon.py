#!/usr/bin/env python3
"""Scan Betclic coupon screenshots using local MLX Vision model.

Usage:
    python3 scripts/scan_coupon.py <screenshot.png>
    python3 scripts/scan_coupon.py <screenshot.png> --output json
    python3 scripts/scan_coupon.py <screenshot.png> --output json --save
    python3 scripts/scan_coupon.py --batch <directory>          # scan all PNGs in dir
    python3 scripts/scan_coupon.py --batch <directory> --save   # scan + save all
"""
import argparse
import json
import sys
from pathlib import Path

from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

MODEL_ID = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"

EXTRACTION_PROMPT = """Analyze this betting coupon screenshot from Betclic app.
Extract ALL information into this exact JSON structure:

{
  "coupon_type": "single|accumulator|system",
  "stake": <number or null>,
  "potential_return": <number or null>,
  "currency": "PLN|EUR|...",
  "status": "pending|won|lost|partial|void",
  "picks": [
    {
      "event": "<Team A vs Team B or event name>",
      "market": "<market type e.g. Match Winner, Over/Under 2.5, etc>",
      "selection": "<selected outcome e.g. Home, Over, etc>",
      "odds": <decimal odds number>,
      "status": "pending|won|lost|void"
    }
  ]
}

Rules:
- Extract EXACT team/player names as shown
- Convert odds to decimal format
- If status indicators (green check, red X) are visible, set pick status accordingly
- Include ALL picks visible in the screenshot
- Return ONLY valid JSON, no other text"""


def load_model():
    """Load the VLM model (cached after first download)."""
    print("Loading vision model...", file=sys.stderr)
    model, processor = load(MODEL_ID)
    config = load_config(MODEL_ID)
    print("Model ready.", file=sys.stderr)
    return model, processor, config


def scan_coupon(image_path: str, model, processor, config) -> str:
    """Run the VLM on a coupon screenshot and return raw text output."""
    prompt = apply_chat_template(
        processor, config, EXTRACTION_PROMPT, num_images=1
    )
    result = generate(
        model, processor, prompt,
        image=image_path,
        max_tokens=2048,
        verbose=False,
    )
    # result is a GenerationResult namedtuple
    return result.text if hasattr(result, 'text') else str(result)


def parse_json_output(raw_text: str) -> dict | None:
    """Try to extract JSON from model output, handling various wrapping formats."""
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced code block
    for fence in ['```json', '```']:
        if fence in text:
            try:
                start = text.index(fence)
                start = text.index('\n', start) + 1
                end = text.index('```', start)
                candidate = text[start:end].strip()
                return json.loads(candidate)
            except (ValueError, json.JSONDecodeError):
                continue

    # Strategy 3: find outermost JSON object via brace matching
    first_brace = text.find('{')
    if first_brace == -1:
        return None

    depth = 0
    end = -1
    for i in range(first_brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        return None  # Unbalanced braces

    try:
        return json.loads(text[first_brace:end])
    except json.JSONDecodeError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Scan Betclic coupon screenshots")
    parser.add_argument("image", nargs="?", help="Path to coupon screenshot")
    parser.add_argument("--batch", help="Scan all PNG/JPG files in a directory")
    parser.add_argument("--output", choices=["json", "text"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--save", action="store_true",
                        help="Save output to betting/coupons/ directory")
    args = parser.parse_args()

    if not args.image and not args.batch:
        parser.error("Either provide an image path or use --batch <directory>")

    model, processor, config = load_model()

    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"Error: {batch_dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        images = sorted(
            p for p in batch_dir.iterdir()
            if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
        )
        if not images:
            print(f"No image files found in {batch_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Scanning {len(images)} coupon screenshots...", file=sys.stderr)
        results = []
        for idx, img_path in enumerate(images, 1):
            print(f"  [{idx}/{len(images)}] {img_path.name}...", file=sys.stderr)
            try:
                raw_output = scan_coupon(str(img_path), model, processor, config)
            except Exception as e:
                print(f"    ✗ VLM error for {img_path.name}: {e}", file=sys.stderr)
                results.append({"_source_file": img_path.name, "_error": str(e), "_parse_failed": True})
                continue
            parsed = parse_json_output(raw_output)
            if parsed:
                parsed["_source_file"] = img_path.name
                results.append(parsed)
            else:
                print(f"    ⚠ Could not parse JSON for {img_path.name}", file=sys.stderr)
                results.append({"_source_file": img_path.name, "_raw": raw_output, "_parse_failed": True})

        formatted = json.dumps(results, indent=2, ensure_ascii=False)
        print(formatted)
        if args.save:
            out_dir = Path("betting/coupons")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"batch_scan_{batch_dir.name}.json"
            out_file.write_text(formatted)
            print(f"\nSaved {len(results)} scans to {out_file}", file=sys.stderr)
    else:
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"Error: {image_path} not found", file=sys.stderr)
            sys.exit(1)

        raw_output = scan_coupon(str(image_path), model, processor, config)

        if args.output == "text":
            print(raw_output)
        else:
            parsed = parse_json_output(raw_output)
            if parsed:
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                print(formatted)
                if args.save:
                    out_dir = Path("betting/coupons")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_file = out_dir / f"scan_{image_path.stem}.json"
                    out_file.write_text(formatted)
                    print(f"\nSaved to {out_file}", file=sys.stderr)
            else:
                print("Warning: Could not parse JSON from model output.", file=sys.stderr)
                print("Raw output:", file=sys.stderr)
                print(raw_output)


if __name__ == "__main__":
    main()
