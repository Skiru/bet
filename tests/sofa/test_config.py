import os

from bet.sofa.config import SofaConfig


def test_config_defaults() -> None:
    # Clear env vars that might affect tests
    for key in [
        "SOFA_DB_PATH", "SOFA_RUNS_DIR", "SOFA_TARGET_RPS", "SOFA_MAX_CONCURRENCY",
        "SOFA_BREAKER_THRESHOLD", "SOFA_EVENTS_TTL_MIN", "SOFA_SAMPLE_N",
        "SOFA_MIN_SAMPLE", "SOFA_PRICE_MAX_AGE_MIN", "SOFA_SHRINK_K"
    ]:
        if key in os.environ:
            del os.environ[key]

    config = SofaConfig.from_env()
    assert config.db_path == "data/sofa.db"
    assert config.runs_dir == "runs/sofa"
    assert config.target_rps == 10
    assert config.max_concurrency == 8
    assert config.breaker_threshold == 3
    assert config.events_ttl_min == 360
    assert config.sample_n == 10
    assert config.min_sample == 5
    assert config.price_max_age_min == 45
    assert config.shrink_k == 10
