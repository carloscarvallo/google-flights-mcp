import pytest

from google_flights_mcp.airports import (
    is_iata_code,
    load_airports,
    parse_airports,
    search_airports,
)

SAMPLE_CSV = [
    "iata,name,city,country",
    "AAA,Alpha Airport,Alpha City,US",
    "bbb,Beta Field,,CA",
    ",No Code Strip,Nowhere,US",
    "TOOLONG,Bad Code,Nowhere,US",
    "CCC,Evil\x1b[31m Name,Gamma,FR",
]


def test_is_iata_code_accepts_three_letters_only():
    assert is_iata_code("LAX")
    assert is_iata_code("lax")
    assert not is_iata_code("LA")
    assert not is_iata_code("LAXX")
    assert not is_iata_code("L4X")
    assert not is_iata_code("ÄBC")


def test_parse_airports_keeps_valid_codes_and_normalizes_case():
    airports = parse_airports(SAMPLE_CSV)

    assert set(airports) == {"AAA", "BBB", "CCC"}
    assert airports["AAA"] == "Alpha Airport, Alpha City, US"
    assert airports["BBB"] == "Beta Field, CA"


def test_parse_airports_strips_control_characters():
    airports = parse_airports(SAMPLE_CSV)

    assert "\x1b" not in airports["CCC"]


def test_parse_airports_returns_read_only_mapping():
    airports = parse_airports(SAMPLE_CSV)

    with pytest.raises(TypeError):
        airports["ZZZ"] = "x"  # type: ignore[index]


def test_load_airports_reads_bundled_data():
    airports = load_airports()

    assert len(airports) > 5000
    assert "Los Angeles" in airports["LAX"]
    assert "JFK" in airports


def test_search_airports_matches_code_and_name_case_insensitively():
    airports = parse_airports(SAMPLE_CSV)

    assert search_airports(airports, "aaa") == ["Alpha Airport, Alpha City, US (AAA)"]
    assert search_airports(airports, " beta ") == ["Beta Field, CA (BBB)"]
    assert search_airports(airports, "nothing-here") == []
