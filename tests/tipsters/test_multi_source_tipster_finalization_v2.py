import pytest
from pathlib import Path
from bet.tipsters.contracts import RawDocument, ExtractorVerdict
from bet.tipsters.typersi import extract_typersi_document
from bet.tipsters.sportsgambler import extract_sportsgambler_documents
from bet.tipsters.protipster import extract_protipster_document
from bet.tipsters.pipeline_adapter import consensus_from_picks, to_legacy_pick, write_artifact
from bet.tipsters.handoff import build_tipster_evidence_handoff, write_handoff_artifact
from bet.tipsters.source_registry import CERTIFIED_SHADOW_SOURCE_IDS


def test_certified_shadow_consensus_and_handoff(tmp_path):
    doc_zawodtyper = RawDocument(
        source_id="zawodtyper",
        url="https://www.zawodtyper.pl/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<div class='item'>Legia Warszawa - Lech Poznan Obie strzela: Tak @ 1.85</div>",
        status_code=200,
        content_type="text/html"
    )
    # We can create Typersi picks
    doc_typersi = RawDocument(
        source_id="typersi",
        url="https://typersi.pl/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<table><tr><td>18:00</td><td>@user</td><td>Legia Warszawa - Lech Poznan</td><td>BTTS</td><td>1.85</td><td>STS</td></tr></table>",
        status_code=200,
        content_type="text/html"
    )

    res_zawod = extract_typersi_document(doc_typersi) # simulate extraction
    res_zawod.source_id = "zawodtyper"
    for p in res_zawod.picks:
        p.source_id = "zawodtyper"
        p.source_name = "ZawodTyper"

    res_typersi = extract_typersi_document(doc_typersi)
    
    all_results = [res_zawod, res_typersi]
    picks = [p for r in all_results for p in r.picks]
    
    assert len(picks) == 2
    
    consensus = consensus_from_picks(picks)
    assert len(consensus) == 1
    assert consensus[0]["total_tipsters"] == 2
    assert "ZawodTyper" in consensus[0]["tipster_sources"]
    assert "Typersi" in consensus[0]["tipster_sources"]

    # Verify handoff marks this as certified_only
    payload = {
        "total_picks": len(picks),
        "sources": [r.to_dict() for r in all_results],
        "consensus": consensus,
    }
    
    handoff = build_tipster_evidence_handoff(payload)
    assert len(handoff["events"]) == 1
    event = handoff["events"][0]
    assert event["source_risk_mix"] == "certified_only"
    assert event["certified_sources"] == ["typersi", "zawodtyper"]
    assert not event["operator_risk_sources"]
    assert event["evidence_quality"] == "LOW" # Average quality of Typersi-style is 0.48 (< 0.5)


def test_sportsgambler_index_only_rejection():
    # If we pass an index page html to parse_sportsgambler_detail, it must return 0 picks
    index_html = "<h1>Predictions for Today</h1> <a href='/predictions/real-vs-barca'>Real Madrid vs Barcelona</a>"
    # Detail parsing of index page URL must produce no picks (handled by path ends with /football/ or /predictions/)
    picks = extract_sportsgambler_documents([RawDocument(
        source_id="sportsgambler",
        url="https://www.sportsgambler.com/betting-tips/football/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html=index_html,
        status_code=200,
        content_type="text/html"
    )]).picks
    assert len(picks) == 0


def test_no_forbidden_betting_fields_generated():
    # Verify no extractor or adapter generates EV, stake, coupon, or combined odds
    doc_typersi = RawDocument(
        source_id="typersi",
        url="https://typersi.pl/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<table><tr><td>18:00</td><td>@user</td><td>Legia Warszawa - Lech Poznan</td><td>1</td><td>1.95</td><td>STS</td></tr></table>",
        status_code=200,
        content_type="text/html"
    )
    res = extract_typersi_document(doc_typersi)
    for p in res.picks:
        legacy = to_legacy_pick(p)
        for forbidden in ["EV", "stake", "coupon", "final_bet", "superbet_combined_odds"]:
            assert forbidden not in legacy
            assert forbidden.upper() not in legacy
