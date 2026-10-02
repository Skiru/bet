import os
from dataclasses import dataclass
from pathlib import Path

# The repo's config/, resolved against this file rather than the working
# directory (a relative path read another checkout's files when a script ran
# from elsewhere).
REPO_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def config_dir() -> Path:
    """The directory every sofa config reader reads from.

    ``SOFA_CONFIG_DIR`` points a whole process - SHEET, COUPON, CONFIDENCE,
    the cache replay - at another set of files, so a between-days refit can
    be replayed on a scratch copy without touching config/ (scripts/sofa/
    prepare_refit.py). Unset or empty: the repo's config/. Read here and
    nowhere else; module-level paths built from it are fixed when the module
    is imported, so the variable is set for a process, never changed inside
    one. Writers (the fit scripts' --out / --config-dir) are not affected:
    where a fit writes is always named on its command line.
    """
    raw = os.environ.get("SOFA_CONFIG_DIR", "").strip()
    return Path(raw).resolve() if raw else REPO_CONFIG_DIR


def config_path(name: str) -> Path:
    """``config_dir() / name``."""
    return config_dir() / name

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
#
# 4 (2026-09-28): the country aliases. Nations League fixtures went to the miss
# table because the Polish name never reached Sofascore's ("Czarnogóra" vs
# "Montenegro" scored 30), and a miss holds for seven days - through the whole
# international break.
#
# 5 (2026-09-28): search without the "(w)"/"(r)" markers, candidates filtered by
# Sofascore's own team gender and squad level, the gender gate reads
# team.gender. The women's and reserve misses were recorded by a search that
# could not succeed.
#
# 6 (2026-10-01): Sofascore's trailing "Reserve(s)" folds to "(r)"; reserve
# misses recorded without the fold could not succeed.
#
# 7 (2026-10-02): a dash between letters folds to a space ("Al-Wahda FC" ->
# "al wahda fc"). A miss is recorded under the SEARCHED side's key when the
# opponent gate refuses every listed event, and that key does not change - so
# "Baniyas" missed because its opponent "Al Wahda" scored 73.7 against
# Sofascore's "Al-Wahda FC". Those misses would now resolve.
MATCH_LOGIC_VERSION = 7


@dataclass(frozen=True)
class SofaConfig:
    db_path: str = "data/sofa.db"
    runs_dir: str = "runs/sofa"
    # Fitted to the bridge, not guessed, and re-fitted 2026-09-22 after the
    # browser's background throttling was removed (launch_bridge_browser.py).
    #
    # This bucket is a global gate in front of the userscript's per-tab
    # MIN_INTERVAL_MS = 350, which is never relaxed. It has to sit ABOVE the
    # tabs' own capacity and let them be the limiter: five windows at 350 ms
    # is 5 x 2.86 = 14.3 req/s, so a bucket at or under that starves the tabs
    # and they go idle between jobs, paying a /pull cycle (20 s then; 1 s since
    # 663e7102) to be claimed
    # again. Starving it is far worse than opening it.
    target_rps: int = 20
    # One in-flight job per tab - and this must EQUAL the number of open
    # windows, not sit under it. Measured 2026-09-22 against five windows,
    # 60 requests a step, zero non-200:
    #
    #     conc  achieved   p50 net   p90 net
    #        3    0.15/s   20138 ms  20162 ms   <- two tabs idle, poll cycle
    #        5   11.67/s     354 ms    620 ms   <- 354 ms IS MIN_INTERVAL_MS
    #        8   11.72/s     668 ms    704 ms
    #       12   11.66/s    1010 ms   1056 ms
    #
    # Throughput saturates at five and never moves again; only latency grows,
    # which is pure queue depth and costs STALE_PRICE. Below the window count
    # it does not degrade gracefully - it collapses 78x, because a tab that
    # finishes and finds nothing waiting goes back into a /pull (20 s then; 1 s since
    # 663e7102).
    #
    # So this is not a free tuning knob: it is the window count. Change it
    # together with launch_bridge_browser.py --windows, and re-run
    # scripts/sofa/measure_bridge_capacity.py.
    max_concurrency: int = 5
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
            target_rps=int(os.environ.get("SOFA_TARGET_RPS", "20")),
            max_concurrency=int(os.environ.get("SOFA_MAX_CONCURRENCY", "5")),
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
