#!/usr/bin/env python3
"""Clear the local usage counter for one or more providers.

The counter in betting/data/.api_usage/ records what *this project* spent
against a key. The quota, though, belongs to the key — so after you swap in a
fresh one the old count is stale and ENRICH's preflight keeps reporting the
provider as exhausted while the new key is untouched. Run this then.

    python3 scripts/simple/reset_provider_quota.py --provider highlightly
    python3 scripts/simple/reset_provider_quota.py --all
    python3 scripts/simple/reset_provider_quota.py --status

It does not touch anything at the provider: it only forgets what we counted.
To change the ceiling itself, set BET_LIMIT_<PROVIDER> in .env instead
(BET_LIMIT_HIGHLIGHTLY=250, or -1 for no local cap, 0 to disable the provider).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from bet.api_clients.env import ENV_PATH  # noqa: E402
from bet.api_clients.rate_limiter import RateLimiter  # noqa: E402


def _known_providers(limiter: RateLimiter) -> list[str]:
    return sorted(set(limiter.limits) | set(limiter.rate_limits))


def _print_status(limiter: RateLimiter, providers: list[str]) -> None:
    print(f"{'provider':22} {'used':>6} {'limit':>7} {'left':>6}  override w .env")
    print("-" * 72)
    for provider in providers:
        snap = limiter.usage_snapshot(provider)
        limit = snap["limit"]
        left = "—" if limit is None else max(0, limit - snap["used"])
        print(
            f"{provider:22} {snap['used']:>6} {str(limit if limit is not None else '∞'):>7} "
            f"{str(left):>6}  {snap['limit_env_var']}"
        )
    print(f"\n.env: {ENV_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--provider", action="append", help="Provider to reset (repeatable)")
    group.add_argument("--all", action="store_true", help="Reset every known provider")
    group.add_argument("--status", action="store_true", help="Show counters without changing anything")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    limiter = RateLimiter()
    known = _known_providers(limiter)

    if args.status:
        _print_status(limiter, known)
        return

    targets = known if args.all else list(dict.fromkeys(args.provider or []))
    unknown = [p for p in targets if p not in known]
    if unknown:
        # A typo would otherwise create an empty counter file under a name
        # nothing reads, and look like it worked.
        print(f"Unknown provider(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Known: {', '.join(known)}", file=sys.stderr)
        sys.exit(2)

    print("About to clear local usage counters for:")
    for provider in targets:
        snap = limiter.usage_snapshot(provider)
        print(f"  {provider:22} used={snap['used']} limit={snap['limit']}")

    if not args.yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted — nothing changed.")
            sys.exit(1)

    for provider in targets:
        discarded = limiter.reset(provider)
        print(f"reset {provider}: discarded count={discarded}")

    print()
    _print_status(limiter, targets)


if __name__ == "__main__":
    main()
