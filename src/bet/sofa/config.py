import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SofaConfig:
    db_path: str = "data/sofa.db"
    runs_dir: str = "runs/sofa"
    # 2 req/s, not the 10 this used to default to. An unpaced burst from this
    # machine (~2800 requests in 15 minutes, peaking at 550 req/s) coincided
    # with Sofascore closing /api/v1/ on 2026-09-17. We are a guest on someone
    # else's production API; pace like one.
    target_rps: int = 2
    max_concurrency: int = 2
    breaker_threshold: int = 3
    events_ttl_min: int = 360
    sample_n: int = 10
    min_sample: int = 5
    price_max_age_min: int = 45
    shrink_k: int = 10

    @classmethod
    def from_env(cls) -> "SofaConfig":
        return cls(
            db_path=os.environ.get("SOFA_DB_PATH", "data/sofa.db"),
            runs_dir=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"),
            target_rps=int(os.environ.get("SOFA_TARGET_RPS", "2")),
            max_concurrency=int(os.environ.get("SOFA_MAX_CONCURRENCY", "2")),
            breaker_threshold=int(os.environ.get("SOFA_BREAKER_THRESHOLD", "3")),
            events_ttl_min=int(os.environ.get("SOFA_EVENTS_TTL_MIN", "360")),
            sample_n=int(os.environ.get("SOFA_SAMPLE_N", "10")),
            min_sample=int(os.environ.get("SOFA_MIN_SAMPLE", "5")),
            price_max_age_min=int(os.environ.get("SOFA_PRICE_MAX_AGE_MIN", "45")),
            shrink_k=int(os.environ.get("SOFA_SHRINK_K", "10")),
        )
