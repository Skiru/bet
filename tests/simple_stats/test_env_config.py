""".env is the single source for credentials and quota overrides.

Regression cover for the removal of config/api_keys.json and
config/odds_api_key.txt as silent fallbacks: one secret in two stores drifts,
and the drift was real (.env carried TheSportsDB's demo key `123` while
config/api_keys.json held a live one, and the demo key silently won).
"""
import json

import pytest

import bet.api_clients.env as envmod
from bet.api_clients.env import (
    MissingCredentialError,
    get_env,
    get_env_int,
    get_limit_override,
    limit_env_var,
    require_env,
)
from bet.api_clients.rate_limiter import RateLimiter


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    """Point the loader at a throwaway .env and clear the module cache."""
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(envmod, "ENV_PATH", path)
    envmod.reload_env()

    def write(text: str) -> None:
        path.write_text(text, encoding="utf-8")
        envmod.reload_env()

    yield write
    envmod.reload_env()


def test_reads_value_from_dotenv(env_file, monkeypatch):
    monkeypatch.delenv("HIGHLIGHTLY_API_KEY", raising=False)
    env_file("HIGHLIGHTLY_API_KEY=abc123\n")
    assert get_env("HIGHLIGHTLY_API_KEY") == "abc123"


def test_process_environment_wins_over_dotenv(env_file, monkeypatch):
    env_file("HIGHLIGHTLY_API_KEY=from-file\n")
    monkeypatch.setenv("HIGHLIGHTLY_API_KEY", "from-process")
    assert get_env("HIGHLIGHTLY_API_KEY") == "from-process"


def test_aliases_are_tried_in_order(env_file, monkeypatch):
    monkeypatch.delenv("SPORTDB_API_KEY", raising=False)
    monkeypatch.delenv("SPORTDB_KEY", raising=False)
    env_file("SPORTDB_KEY=fallback\n")
    assert get_env("SPORTDB_API_KEY", "SPORTDB_KEY") == "fallback"


def test_quoting_and_export_prefix_are_handled_by_dotenv(env_file, monkeypatch):
    """Delegating to python-dotenv rather than hand-splitting on '=' is the
    point: quoting and `export` are exactly what a hand-rolled parser gets
    wrong."""
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    env_file('SERPAPI_KEY="quoted value"\nexport API_FOOTBALL_KEY=exported\n')
    assert get_env("SERPAPI_KEY") == "quoted value"
    assert get_env("API_FOOTBALL_KEY") == "exported"


def test_edited_dotenv_is_picked_up_without_a_restart(env_file, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    env_file("ODDS_API_KEY=first\n")
    assert get_env("ODDS_API_KEY") == "first"
    env_file("ODDS_API_KEY=second\n")
    assert get_env("ODDS_API_KEY") == "second"


def test_missing_value_is_empty_string_not_none(env_file, monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    assert get_env("NOPE_KEY") == ""


def test_require_env_names_the_variable_and_the_file(env_file, monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    with pytest.raises(MissingCredentialError) as excinfo:
        require_env("NOPE_KEY", "ALSO_NOPE")
    message = str(excinfo.value)
    assert "NOPE_KEY" in message and "ALSO_NOPE" in message
    assert ".env" in message


def test_no_json_fallback_remains(tmp_path, monkeypatch):
    """A key present only in config/api_keys.json must no longer resolve."""
    from bet.api_clients.base_client import BaseAPIClient

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "api_keys.json").write_text(json.dumps({"api-football": "from-json"}))
    monkeypatch.setattr("bet.api_clients.base_client.CONFIG_DIR", config_dir)

    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(envmod, "ENV_PATH", env_path)
    envmod.reload_env()
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)

    class _Client(BaseAPIClient):
        def get_fixtures(self, date):
            return []

        def get_fixture_stats(self, fixture_id):
            return []

        def get_h2h(self, a, b, last_n=10):
            return []

    client = _Client(api_name="api-football", base_url="https://x", rate_limiter=RateLimiter(usage_dir=tmp_path))
    assert client.api_key is None


@pytest.mark.parametrize(
    "provider,expected",
    [("highlightly", "BET_LIMIT_HIGHLIGHTLY"), ("api-football", "BET_LIMIT_API_FOOTBALL")],
)
def test_limit_env_var_naming(provider, expected):
    assert limit_env_var(provider) == expected


def test_limit_override_read_from_dotenv(env_file, monkeypatch):
    monkeypatch.delenv("BET_LIMIT_HIGHLIGHTLY", raising=False)
    env_file("BET_LIMIT_HIGHLIGHTLY=250\n")
    assert get_limit_override("highlightly") == 250


def test_rate_limiter_honours_the_dotenv_override(env_file, monkeypatch, tmp_path):
    monkeypatch.delenv("BET_LIMIT_HIGHLIGHTLY", raising=False)
    env_file("BET_LIMIT_HIGHLIGHTLY=250\n")
    limiter = RateLimiter(usage_dir=tmp_path / "usage")
    assert limiter._effective_limit("highlightly") == (250, "daily")


def test_negative_override_means_no_local_cap(env_file, monkeypatch, tmp_path):
    monkeypatch.delenv("BET_LIMIT_HIGHLIGHTLY", raising=False)
    env_file("BET_LIMIT_HIGHLIGHTLY=-1\n")
    limiter = RateLimiter(usage_dir=tmp_path / "usage")
    assert limiter._effective_limit("highlightly") == (None, "daily")
    assert limiter.can_request("highlightly") is True


def test_zero_override_disables_the_provider(env_file, monkeypatch, tmp_path):
    monkeypatch.delenv("BET_LIMIT_HIGHLIGHTLY", raising=False)
    env_file("BET_LIMIT_HIGHLIGHTLY=0\n")
    limiter = RateLimiter(usage_dir=tmp_path / "usage")
    assert limiter.can_request("highlightly") is False


def test_explicit_limits_are_not_overridden_by_the_ambient_env(env_file, monkeypatch, tmp_path):
    """A test that passes explicit limits describes a closed world; letting the
    developer's .env leak in would make it machine-dependent."""
    env_file("BET_LIMIT_HIGHLIGHTLY=250\n")
    limiter = RateLimiter(usage_dir=tmp_path / "usage", limits={"highlightly": 7}, rate_limits={})
    assert limiter._effective_limit("highlightly") == (7, "daily")


def test_unparseable_override_falls_back_to_the_default(env_file, monkeypatch, tmp_path):
    monkeypatch.delenv("BET_LIMIT_HIGHLIGHTLY", raising=False)
    env_file("BET_LIMIT_HIGHLIGHTLY=not-a-number\n")
    assert get_env_int("BET_LIMIT_HIGHLIGHTLY", default=None) is None
    limiter = RateLimiter(usage_dir=tmp_path / "usage")
    assert limiter._effective_limit("highlightly")[0] == 100
