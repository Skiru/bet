import pytest
from bet.tipsters.contracts import RawDocument, ExtractorVerdict
from bet.tipsters.typersi import (
    is_allowed_typersi_url,
    clean_typersi_team_name,
    parse_typersi_static_tables,
    extract_typersi_document,
)

def test_typersi_url_allowance():
    assert is_allowed_typersi_url("https://typersi.pl/") is True
    assert is_allowed_typersi_url("https://www.typersi.pl/r/betclic") is False
    assert is_allowed_typersi_url("https://typersi.pl/odds.php") is False

def test_typersi_clean_team_name():
    assert clean_typersi_team_name("Sandecja Nowy Sącz - 28 kolejka Aktualizacja") == "Sandecja Nowy Sącz"
    assert clean_typersi_team_name("PSG Aktualizacja") == "PSG"
    assert clean_typersi_team_name("Nantes - kolejka 30") == "Nantes"
    assert clean_typersi_team_name("Lyon - 30 kolejka Aktualizacja") == "Lyon"

def test_typersi_parse_static_tables():
    # Construct typical Typersi table row HTML
    html = """
    <table>
        <tr>
            <th>Godzina</th>
            <th>Typer</th>
            <th>Mecz</th>
            <th>Typ</th>
            <th>Kurs</th>
            <th>Bukmacher</th>
        </tr>
        <tr>
            <td>18:00</td>
            <td>@zawodowiec</td>
            <td>Sandecja Nowy Sącz - KKS 1925 Kalisz - 28 kolejka Aktualizacja</td>
            <td>1X</td>
            <td>1.45</td>
            <td>Superbet</td>
        </tr>
        <tr>
            <td>20:45</td>
            <td>@experci</td>
            <td>Paris Saint-Germain - Lyon - Aktualizacja</td>
            <td>1</td>
            <td>1.85</td>
            <td>STS</td>
        </tr>
    </table>
    """
    picks = parse_typersi_static_tables(html, "https://typersi.pl/")
    assert len(picks) == 2

    p0 = picks[0]
    assert p0.home_team == "Sandecja Nowy Sącz"
    assert p0.away_team == "KKS 1925 Kalisz"
    assert p0.market == "Winner: 1X"
    assert p0.direction == "DC"
    assert p0.odds_decimal == 1.45
    assert p0.tipster_name == "@zawodowiec"
    assert p0.valuable_signals["bookmaker_metadata"] == ["Superbet"]

    p1 = picks[1]
    assert p1.home_team == "Paris Saint-Germain"
    assert p1.away_team == "Lyon"
    assert p1.market == "Winner: 1"
    assert p1.direction == "HOME"
    assert p1.odds_decimal == 1.85

def test_typersi_extract_document():
    doc = RawDocument(
        source_id="typersi",
        url="https://typersi.pl/",
        fetched_at_utc="2026-07-07T04:00:00Z",
        html="<table><tr><td>18:00</td><td>@user</td><td>Legia Warszawa - Lech Poznan</td><td>1</td><td>1.95</td><td>STS</td></tr></table>",
        status_code=200,
        content_type="text/html"
    )
    res = extract_typersi_document(doc)
    assert res.verdict == ExtractorVerdict.OK
    assert len(res.picks) == 1
    assert res.picks[0].event == "Legia Warszawa vs Lech Poznan"


# --- Regressions from the live run of 2026-08-25 ---------------------------


TYPERSI_LIVE_ROW_SHAPE = """
<table>
<tr>
  <td></td><td>Kasia</td><td>11:00</td><td></td>
  <td>Orix Buffaloes - Rakuten Gold. Eagles</td><td> 1 </td><td>1.76</td><td>Baseball</td>
</tr>
<tr>
  <td></td><td>ifonka75</td><td>21:30</td><td></td>
  <td>Semenistaja D. - Kinoshita H.</td><td> 1 </td><td>1.62</td><td>Tenis</td>
</tr>
<tr>
  <td></td><td>townjuju</td><td>12:00</td><td></td>
  <td>Gimcheon Sangmu - Jeonbuk</td><td> 1 </td><td>3.17</td><td>Pi&#322;ka no&#380;na</td>
</tr>
</table>
"""


def _live_shape_picks():
    from bet.tipsters.extractors import make_raw
    from bet.tipsters.typersi import extract_typersi_document

    return extract_typersi_document(
        make_raw("typersi", "https://typersi.pl/", TYPERSI_LIVE_ROW_SHAPE)
    ).picks


def test_sport_comes_from_the_discipline_cell_not_the_team_names():
    """detect_sport found no football keyword in "Semenistaja D. - Kinoshita H."
    and returned its football default, so all 29 live picks came out football --
    tennis and NPB baseball included. The site states the discipline itself."""
    picks = {p.home_team: p.sport for p in _live_shape_picks()}
    assert picks["Orix Buffaloes"] == "baseball"
    assert picks["Semenistaja D."] == "tennis"
    assert picks["Gimcheon Sangmu"] == "football"


def test_an_inferred_sport_is_flagged_as_inferred():
    from bet.tipsters.extractors import make_raw
    from bet.tipsters.typersi import extract_typersi_document

    no_discipline = """
    <table><tr><td></td><td>anon</td><td>12:00</td><td></td>
    <td>Arsenal - Chelsea</td><td> 1 </td><td>2.10</td></tr></table>
    """
    picks = extract_typersi_document(make_raw("typersi", "https://typersi.pl/", no_discipline)).picks
    assert picks
    assert "sport_inferred_no_discipline_cell" in picks[0].warnings


def test_tipster_name_survives_the_empty_bookmaker_cell():
    """The cell before the event is the bookmaker-logo column and is empty, so
    taking event_idx-1 attributed every pick to the source itself."""
    names = {p.tipster_name for p in _live_shape_picks()}
    assert names == {"Kasia", "ifonka75", "townjuju"}
    assert "Typersi" not in names


def test_a_kickoff_time_is_never_read_as_a_tipster_name():
    names = {p.tipster_name for p in _live_shape_picks()}
    assert not any(":" in name for name in names)
