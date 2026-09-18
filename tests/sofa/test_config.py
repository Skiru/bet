import os

from bet.sofa.config import SofaConfig


def test_config_defaults() -> None:
    # Clear env vars that might affect tests
    for key in [
        "SOFA_DB_PATH",
        "SOFA_RUNS_DIR",
        "SOFA_TARGET_RPS",
        "SOFA_MAX_CONCURRENCY",
        "SOFA_BREAKER_THRESHOLD",
        "SOFA_EVENTS_TTL_MIN",
        "SOFA_SAMPLE_N",
        "SOFA_MIN_SAMPLE",
        "SOFA_PRICE_MAX_AGE_MIN",
        "SOFA_SHRINK_K",
        "SOFA_BREAKER_COOLDOWN_S",
        "SOFA_BREAKER_MAX_COOLDOWN_S",
        "SOFA_ENTITY_MISS_TTL_MIN",
        "SOFA_RUN_ID",
    ]:
        if key in os.environ:
            del os.environ[key]

    config = SofaConfig.from_env()
    assert config.db_path == "data/sofa.db"
    assert config.runs_dir == "runs/sofa"
    # Deliberately low: see SofaConfig for why these dropped from 10/8.
    assert config.target_rps == 2
    assert config.max_concurrency == 2
    assert config.breaker_threshold == 3
    assert config.breaker_cooldown_s == 30
    assert config.breaker_max_cooldown_s == 300
    assert config.events_ttl_min == 360
    assert config.entity_miss_ttl_min == 10080
    assert config.sample_n == 10
    assert config.min_sample == 5
    assert config.price_max_age_min == 45
    assert config.shrink_k == 10
    assert config.run_id == ""
