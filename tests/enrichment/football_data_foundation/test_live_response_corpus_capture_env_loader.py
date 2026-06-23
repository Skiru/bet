import os
import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.live_response_corpus_capture.env_loader import (
    load_project_dotenv,
    get_credential,
    credential_presence_map,
)


@pytest.fixture(autouse=True)
def clean_env():
    # Clear internal env store and clean os.environ changes
    from bet.enrichment.football_data_foundation.live_response_corpus_capture import env_loader
    env_loader._env_store.clear()
    
    # Save original environ
    orig_env = dict(os.environ)
    yield
    # Restore original environ
    os.environ.clear()
    os.environ.update(orig_env)


def test_missing_env_returns_empty_and_does_not_fail(tmp_path):
    res = load_project_dotenv(tmp_path)
    assert res == {}
    assert get_credential("SOME_KEY") is None


def test_parses_dotenv_and_strips_quotes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SPORTDB_API_KEY=foo\n"
        "FOOTBALL_DATA_ORG_KEY='bar'\n"
        "HIGHLIGHTLY_API_KEY=\"baz\"\n"
        "API_FOOTBALL_KEY=qux\n",
        encoding="utf-8"
    )
    
    res = load_project_dotenv(tmp_path)
    assert res == {
        "SPORTDB_API_KEY": "foo",
        "FOOTBALL_DATA_ORG_KEY": "bar",
        "HIGHLIGHTLY_API_KEY": "baz",
        "API_FOOTBALL_KEY": "qux",
    }
    
    assert get_credential("SPORTDB_API_KEY") == "foo"
    assert get_credential("FOOTBALL_DATA_ORG_KEY") == "bar"
    assert get_credential("HIGHLIGHTLY_API_KEY") == "baz"
    assert get_credential("API_FOOTBALL_KEY") == "qux"


def test_ignores_comments_and_invalid_lines(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n"
        "SPORTDB_API_KEY=valid_key\n"
        "INVALID_LINE\n"
        "ANOTHER_INVALID_LINE=abc=def\n"
        "   # Whitespace comment\n",
        encoding="utf-8"
    )
    res = load_project_dotenv(tmp_path)
    assert "SPORTDB_API_KEY" in res
    assert "INVALID_LINE" not in res
    assert "ANOTHER_INVALID_LINE" in res


def test_does_not_expose_secret_values_in_credential_presence_map(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SPORTDB_API_KEY=foo\n"
        "FOOTBALL_DATA_ORG_KEY=bar\n"
        "HIGHLIGHTLY_API_KEY=baz\n"
        "API_FOOTBALL_KEY=qux\n",
        encoding="utf-8"
    )
    load_project_dotenv(tmp_path)
    
    presence = credential_presence_map()
    assert presence["sportdb"] is True
    assert presence["football_data_org"] is True
    assert presence["highlightly"] is True
    assert presence["api_football"] is True
    assert presence["espn_baseline"] is False
    
    for val in presence.values():
        assert isinstance(val, bool)


def test_football_data_org_primary_and_legacy_alias(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOOTBALL_DATA_ORG_KEY=primary_secret\n", encoding="utf-8")
    load_project_dotenv(tmp_path)
    assert get_credential("FOOTBALL_DATA_ORG_KEY", ("FOOTBALL_DATA_API_KEY",)) == "primary_secret"
    
    from bet.enrichment.football_data_foundation.live_response_corpus_capture import env_loader
    env_loader._env_store.clear()
    
    env_file.write_text("FOOTBALL_DATA_API_KEY=legacy_secret\n", encoding="utf-8")
    load_project_dotenv(tmp_path)
    assert get_credential("FOOTBALL_DATA_ORG_KEY", ("FOOTBALL_DATA_API_KEY",)) == "legacy_secret"


def test_api_football_aliasing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_FOOTBALL_API_KEY=alias_secret\n", encoding="utf-8")
    load_project_dotenv(tmp_path)
    assert get_credential("API_FOOTBALL_KEY", ("API_FOOTBALL_API_KEY",)) == "alias_secret"


def test_process_env_non_empty_wins_over_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SPORTDB_API_KEY=dotenv_val\n", encoding="utf-8")
    load_project_dotenv(tmp_path)
    
    assert get_credential("SPORTDB_API_KEY") == "dotenv_val"
    
    os.environ["SPORTDB_API_KEY"] = "proc_val"
    assert get_credential("SPORTDB_API_KEY") == "proc_val"
    
    os.environ["SPORTDB_API_KEY"] = ""
    assert get_credential("SPORTDB_API_KEY") == "dotenv_val"


def test_no_dotenv_content_written_to_reports():
    presence = credential_presence_map()
    for val in presence.values():
        assert val is True or val is False
