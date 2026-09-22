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
    # Fitted, not guessed, and deliberately ABOVE the tabs' own capacity:
    # starving the bucket leaves tabs idle between jobs, paying a 20 s /pull
    # cycle. Re-fitted 2026-09-22 against FIVE windows, once Chrome's
    # background throttling was removed by launch_bridge_browser.py:
    # max_concurrency is the window count (conc 3 measured 0.15 req/s against
    # conc 5's 11.67), and the bucket sits above 5 x 2.86 = 14.3 req/s.
    assert config.target_rps == 20
    assert config.max_concurrency == 5
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


def test_from_env_defaults_match_the_dataclass_defaults():
    """`from_env` repeats every default as a string, so the two can drift.

    They did: raising `SofaConfig.target_rps` to 4 changed nothing for the
    pipeline, because every stage builds its config through `from_env`, whose
    own literal still said "2" - and `test_env_defaults` passed throughout,
    because it asserts on `from_env`. This guard compares the two directly, so
    the next edit cannot silently apply to only one of them.
    """
    import dataclasses
    import os

    from bet.sofa.config import SofaConfig

    saved = {k: v for k, v in os.environ.items() if k.startswith("SOFA_")}
    for key in list(saved):
        del os.environ[key]
    try:
        from_env = SofaConfig.from_env()
    finally:
        os.environ.update(saved)

    plain = SofaConfig()
    drifted = {
        field.name: (getattr(plain, field.name), getattr(from_env, field.name))
        for field in dataclasses.fields(SofaConfig)
        # run_id is genuinely different: the dataclass default is empty and
        # the environment supplies it per run.
        if field.name != "run_id"
        and getattr(plain, field.name) != getattr(from_env, field.name)
    }
    assert not drifted, f"dataclass default != from_env default: {drifted}"
