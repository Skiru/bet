from pathlib import Path

import pytest

from bet.api_clients import env as env_module
from bet.api_clients.base_client import BaseAPIClient
from bet.api_clients.google_sports_client import GoogleSportsClient
from bet.api_clients.highlightly import HighlightlyClient
from bet.api_clients.oddspapi import OddspapiConfig
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sportdb_mcp import SportDBMCPClient


class ProbeClient(BaseAPIClient):
    def __init__(self, api_name: str):
        super().__init__(api_name, "https://example.test", RateLimiter())

    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        return []


@pytest.fixture
def dotenv_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(env_module, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_all_example_provider_keys_are_read_from_dotenv(
    dotenv_project: Path,
) -> None:
    provider_env_names = {
        "api-football": "API_FOOTBALL_KEY",
        "api-basketball": "API_BASKETBALL_KEY",
        "api-hockey": "API_HOCKEY_KEY",
        "api-volleyball": "API_VOLLEYBALL_KEY",
        "football-data-org": "FOOTBALL_DATA_ORG_KEY",
        "thesportsdb": "THESPORTSDB_API_KEY",
        "odds-api": "ODDS_API_KEY",
        "serpapi": "SERPAPI_KEY",
        "odds-api-io": "ODDS_API_IO_KEY",
    }
    dotenv_project.joinpath(".env").write_text(
        "\n".join(f"{env_name}=dotenv-{api_name}" for api_name, env_name in provider_env_names.items()),
        encoding="utf-8",
    )

    for api_name, env_name in provider_env_names.items():
        assert ProbeClient(api_name).api_key == f"dotenv-{api_name}"


def test_specialized_clients_read_dotenv(dotenv_project: Path) -> None:
    dotenv_project.joinpath(".env").write_text(
        "SERPAPI_KEY=dotenv-serpapi\n"
        "HIGHLIGHTLY_API_KEY=dotenv-highlightly\n"
        "SPORTDB_API_KEY=dotenv-sportdb\n"
        "ODDSPAPI_API_KEY=dotenv-oddspapi\n",
        encoding="utf-8",
    )

    rate_limiter = RateLimiter()
    assert GoogleSportsClient(rate_limiter).api_key == "dotenv-serpapi"
    assert HighlightlyClient(rate_limiter).api_key == "dotenv-highlightly"
    assert SportDBMCPClient().api_key == "dotenv-sportdb"
    assert OddspapiConfig.from_env().api_key == "dotenv-oddspapi"


def test_process_environment_overrides_dotenv(
    dotenv_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_project.joinpath(".env").write_text(
        "API_FOOTBALL_KEY=dotenv-value\n", encoding="utf-8"
    )
    monkeypatch.setenv("API_FOOTBALL_KEY", "process-value")

    assert ProbeClient("api-football").api_key == "process-value"
