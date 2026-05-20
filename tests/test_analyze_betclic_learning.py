import sys
import types

import scripts.analyze_betclic_learning as learning_mod


def _coupon(status: str, stake: float = 10.0, payout: float = 0.0):
    return {
        "coupon_status": status,
        "stake_pln": stake,
        "tax_free_payout_pln": payout,
        "winnings_pln": payout,
        "legs": [],
        "is_ended": True,
    }


def test_analyze_prefers_db_over_larger_json(tmp_path, monkeypatch):
    db_history = [_coupon("won", payout=18.0)]
    json_history = [_coupon("lost"), _coupon("lost")]

    history_path = tmp_path / "betclic_bets_history.json"
    history_path.write_text(learning_mod.json.dumps(json_history), encoding="utf-8")

    dummy_loader = types.SimpleNamespace(load_betclic_history_from_db=lambda: db_history)
    monkeypatch.setitem(sys.modules, "db_data_loader", dummy_loader)
    monkeypatch.setattr(learning_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(learning_mod, "HISTORY_JSON", history_path)

    bets, _rules = learning_mod.analyze()

    assert bets == db_history


def test_analyze_falls_back_to_json_when_db_empty(tmp_path, monkeypatch):
    json_history = [_coupon("won", payout=18.0)]

    history_path = tmp_path / "betclic_bets_history.json"
    history_path.write_text(learning_mod.json.dumps(json_history), encoding="utf-8")

    dummy_loader = types.SimpleNamespace(load_betclic_history_from_db=lambda: [])
    monkeypatch.setitem(sys.modules, "db_data_loader", dummy_loader)
    monkeypatch.setattr(learning_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(learning_mod, "HISTORY_JSON", history_path)

    bets, _rules = learning_mod.analyze()

    assert bets == json_history


def test_analyze_does_not_report_missing_file_for_empty_json(tmp_path, monkeypatch, capsys):
    history_path = tmp_path / "betclic_bets_history.json"
    history_path.write_text("[]", encoding="utf-8")

    dummy_loader = types.SimpleNamespace(load_betclic_history_from_db=lambda: [])
    monkeypatch.setitem(sys.modules, "db_data_loader", dummy_loader)
    monkeypatch.setattr(learning_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(learning_mod, "HISTORY_JSON", history_path)

    bets, _rules = learning_mod.analyze()
    captured = capsys.readouterr()

    assert bets == []
    assert "WARNING: Not found" not in captured.out


def test_analyze_keeps_db_data_when_json_is_unreadable(tmp_path, monkeypatch, capsys):
    db_history = [_coupon("won", payout=18.0)]

    history_path = tmp_path / "betclic_bets_history.json"
    history_path.write_text("{not-json", encoding="utf-8")

    dummy_loader = types.SimpleNamespace(load_betclic_history_from_db=lambda: db_history)
    monkeypatch.setitem(sys.modules, "db_data_loader", dummy_loader)
    monkeypatch.setattr(learning_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(learning_mod, "HISTORY_JSON", history_path)

    bets, _rules = learning_mod.analyze()
    captured = capsys.readouterr()

    assert bets == db_history
    assert "JSON file unreadable" in captured.out