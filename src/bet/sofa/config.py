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
    # Fitted to the bridge, not guessed. scripts/sofa/measure_bridge_capacity.py
    # ramped the rate on 2026-09-22 with three tabs open: the plateau is
    # 3.9 req/s and it arrives at a target of 4. Asking for 14 delivered the
    # same 3.9 and took the bridge round trip from 605 ms to 5,603 ms, so
    # anything above this buys queue, not speed - and queue costs STALE_PRICE.
    # 360 requests, zero non-200, no 403.
    #
    # This is NOT the 2026-09-17 shape. That burst was one curl_cffi client
    # with 100 workers peaking at 550 req/s and no browser in the path. Here
    # the per-connection pace is still the userscript's MIN_INTERVAL_MS = 350,
    # which is why a single tab stays safe at this setting: the bucket simply
    # stops being the binding constraint and the tab's own floor takes over.
    #
    # Re-run measure_bridge_capacity.py when the number of tabs changes. Never
    # set this above the plateau it reports.
    target_rps: int = 4
    # One in-flight job per tab. bridge_server.claim() is not bound to a tab,
    # so three tabs can serve three jobs at once; with fewer tabs the extra
    # jobs simply queue, bounded by this number.
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
            target_rps=int(os.environ.get("SOFA_TARGET_RPS", "4")),
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
