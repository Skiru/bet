import json
import logging
import statistics
from pathlib import Path

from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig

logging.basicConfig(level=logging.INFO)


def main() -> None:
    config = SofaConfig(
        runs_dir="docs/sofascore-api/evidence",
        target_rps=2,
        # Was 100, which meant a blocked API got hammered 100 times before the
        # breaker noticed. A smoke test that cannot reach the provider should
        # say so after a few tries, not keep knocking.
        breaker_threshold=5,
    )

    # overriding log path manually for the smoke test requirement
    client = SofascoreClient(config)
    client.log_path = Path("docs/sofascore-api/evidence/impl_e1_smoke.jsonl")

    # remove existing file
    if client.log_path.exists():
        client.log_path.unlink()

    ids = [16363633, 15345277, 16416342]

    success = 0
    failures = 0
    times = []
    statuses = []

    print("Starting smoke test of 30 requests...")
    for i in range(30):
        try:
            if i % 3 == 0:
                client.search("Real Madrid")
            elif i % 3 == 1:
                client.event(ids[i % len(ids)])
            else:
                client.event_statistics(ids[i % len(ids)])
            success += 1
        except Exception as e:
            failures += 1
            print(f"Req {i + 1}: {e}")

    # analyze log file
    with open(client.log_path) as f:
        for line in f:
            data = json.loads(line)
            times.append(data["elapsed_ms"])
            statuses.append(data["status"])

    status_dist: dict[int, int] = {}
    for s in statuses:
        status_dist[s] = status_dist.get(s, 0) + 1

    median_time = statistics.median(times) if times else 0

    print("\n--- Smoke Test Results ---")
    print(f"Total Logged Requests: {len(times)}")
    print(f"Status Distribution: {status_dist}")
    print(f"Median Elapsed Time: {median_time} ms")


if __name__ == "__main__":
    main()
