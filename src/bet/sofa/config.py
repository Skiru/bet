import os
from dataclasses import dataclass

# Bump whenever the entity-matching logic changes in a way that could turn a
# miss into a hit: the gates in match_quality, the kickoff window, normalize_name.
#
# A negative cache remembers "we looked and found nothing". That is only a fact
# about the world if the looking was correct. When it was not, the miss records
# the *bug*, and F4's seven-day TTL then outlives the fix — measured on
# 2026-09-18: a wrong gender gate made 175 women's tennis players unresolvable,
# recorded them all as misses, and after the gate was fixed RESOLVE produced a
# byte-identical artifact because it never asked again. Stamping the misses
# with the version of the logic that produced them makes a fix invalidate them
# automatically (F34).
MATCH_LOGIC_VERSION = 3


@dataclass(frozen=True)
class SofaConfig:
    db_path: str = "data/sofa.db"
    runs_dir: str = "runs/sofa"
    # Fitted to the bridge, not guessed - and the direction is the opposite of
    # what "pace like a guest" suggests, so read this before lowering it.
    #
    # The real limiter is the userscript's MIN_INTERVAL_MS = 350 per TAB. That
    # is the number that keeps each connection human-paced, and it is never
    # relaxed. This bucket is a global gate in front of it, and starving it is
    # actively worse than opening it: measured 2026-09-22 with three tabs,
    #
    #     target_rps  6  ->  2.00 req/s     tabs go idle between jobs and pay
    #     target_rps  8  ->  2.17 req/s     a 20 s poll cycle to be claimed
    #     target_rps 10  ->  2.23 req/s
    #     target_rps 14  ->  8.64 req/s     tabs never idle, full speed
    #
    # reproduced twice within 0.03 req/s, 360 requests each, zero non-200. The
    # behaviour is bimodal: either the tabs stay saturated and deliver
    # 3 x 2.86 = 8.6 req/s, or they idle and collapse to ~2. So the bucket has
    # to sit ABOVE the tabs' own capacity and let them be the limiter.
    target_rps: int = 14
    # One in-flight job per tab, and no more. At target_rps 14 with three tabs:
    #
    #     3 workers ->  8.62 req/s, p50  357 ms   <- 357 ms IS MIN_INTERVAL_MS
    #     6 workers ->  8.72 req/s, p50  707 ms
    #    12 workers ->  8.59 req/s, p50 1378 ms
    #    24 workers ->  1.88 req/s, p50 2714 ms   <- collapses
    #
    # Extra workers buy no throughput and only deepen the queue, which costs
    # STALE_PRICE. Raise this only alongside the number of open tabs, and
    # re-run scripts/sofa/measure_bridge_capacity.py when you do.
    max_concurrency: int = 3
    breaker_threshold: int = 3
    # How long an open circuit waits before letting one probe through, and
    # the ceiling that repeated failures escalate to. Without these the
    # breaker never closed and one blip killed a multi-hour run.
    breaker_cooldown_s: int = 30
    breaker_max_cooldown_s: int = 300
    events_ttl_min: int = 360
    # A name Sofascore does not know is worth remembering, but not forever:
    # teams get added. A week is long enough to stop paying for the lookup
    # every day, short enough that a newly listed team is found eventually.
    entity_miss_ttl_min: int = 10080
    # A listing that 404s is worth remembering, but only for the day. A team
    # with no upcoming match today has one next week, so an eternal memory
    # would trade 28% of the request budget for a silent hole in the data —
    # the worse of the two errors (F17).
    listing_miss_ttl_min: int = 720
    # /event/{id} for a match that has not been played yet. Short, because
    # the payload legitimately changes — the referee is announced late, which
    # is why that field is filled for only 9% of fixtures, so an eternal cache
    # would freeze an empty referee in place. A finished match is immutable and
    # is cached permanently regardless of this value (F33).
    event_detail_ttl_min: int = 60
    sample_n: int = 10
    min_sample: int = 5
    price_max_age_min: int = 45
    shrink_k: int = 10
    # Identifies one execution across every stage's log rows. Analysing a
    # single run used to mean guessing its start time and filtering by hand.
    run_id: str = ""

    @classmethod
    def from_env(cls) -> "SofaConfig":
        return cls(
            db_path=os.environ.get("SOFA_DB_PATH", "data/sofa.db"),
            runs_dir=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"),
            target_rps=int(os.environ.get("SOFA_TARGET_RPS", "14")),
            max_concurrency=int(os.environ.get("SOFA_MAX_CONCURRENCY", "3")),
            breaker_threshold=int(os.environ.get("SOFA_BREAKER_THRESHOLD", "3")),
            breaker_cooldown_s=int(os.environ.get("SOFA_BREAKER_COOLDOWN_S", "30")),
            breaker_max_cooldown_s=int(
                os.environ.get("SOFA_BREAKER_MAX_COOLDOWN_S", "300")
            ),
            events_ttl_min=int(os.environ.get("SOFA_EVENTS_TTL_MIN", "360")),
            entity_miss_ttl_min=int(
                os.environ.get("SOFA_ENTITY_MISS_TTL_MIN", "10080")
            ),
            listing_miss_ttl_min=int(
                os.environ.get("SOFA_LISTING_MISS_TTL_MIN", "720")
            ),
            event_detail_ttl_min=int(
                os.environ.get("SOFA_EVENT_DETAIL_TTL_MIN", "60")
            ),
            sample_n=int(os.environ.get("SOFA_SAMPLE_N", "10")),
            min_sample=int(os.environ.get("SOFA_MIN_SAMPLE", "5")),
            price_max_age_min=int(os.environ.get("SOFA_PRICE_MAX_AGE_MIN", "45")),
            shrink_k=int(os.environ.get("SOFA_SHRINK_K", "10")),
            run_id=os.environ.get("SOFA_RUN_ID", ""),
        )
