from datetime import date

import pytest
from conftest import make_option, make_segment
from fast_flights.querying import REVERSE_SEAT_LOOKUP, REVERSE_TRIP_LOOKUP

from google_flights_mcp.flights import (
    SearchError,
    SearchRequest,
    build_query,
    format_results,
    validate_search,
)

AIRPORTS = {"LAX": "Los Angeles", "JFK": "New York", "DEN": "Denver"}
TODAY = date(2030, 1, 1)


def search(**overrides):
    args = {"from_airport": "lax", "to_airport": "jfk", "departure_date": "2030-01-15", "today": TODAY}
    return validate_search(AIRPORTS, **{**args, **overrides})


def test_validate_search_normalizes_input():
    request = search(from_airport=" lax ", seat_class="Business", return_date="2030-01-20")

    assert request == SearchRequest(
        from_airport="LAX",
        to_airport="JFK",
        departure_date="2030-01-15",
        return_date="2030-01-20",
        passengers=(1, 0, 0, 0),
        seat="business",
    )
    assert request.trip_type == "round-trip"


def test_validate_search_maps_legacy_premium_economy_spelling():
    assert search(seat_class="premium_economy").seat == "premium-economy"
    assert search(seat_class="PREMIUM-ECONOMY").seat == "premium-economy"


def test_one_way_trip_type():
    assert search().trip_type == "one-way"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"departure_date": "15/01/2030"}, "YYYY-MM-DD"),
        ({"departure_date": "2029-12-31"}, "in the past"),
        ({"return_date": "2030-01-10"}, "before departure"),
        ({"return_date": "not-a-date"}, "Return date must use"),
        ({"from_airport": "LA"}, "3-letter IATA"),
        ({"to_airport": "ZZZ"}, "not in the airport database"),
        ({"to_airport": "LAX"}, "must be different"),
        ({"adults": 0}, "At least one adult"),
        ({"children": -1}, "cannot be negative"),
        ({"adults": 5, "children": 5}, "at most 9"),
        ({"adults": 1, "infants_on_lap": 2}, "infant on lap"),
        ({"seat_class": "luxury"}, "Seat class must be one of"),
    ],
)
def test_validate_search_rejects_invalid_input(overrides, message):
    with pytest.raises(SearchError, match=message):
        search(**overrides)


def test_departure_today_is_allowed():
    assert search(departure_date="2030-01-01").departure_date == "2030-01-01"


def test_build_query_one_way():
    query = build_query(search(adults=2, children=1, seat_class="first"))

    assert len(query.flight_data) == 1
    assert REVERSE_TRIP_LOOKUP[query.trip] == "one-way"
    assert REVERSE_SEAT_LOOKUP[query.seat] == "first"
    assert len(query.passengers) == 3
    assert query.currency == "USD"


def test_build_query_round_trip_adds_return_leg():
    query = build_query(search(return_date="2030-01-20"))

    assert REVERSE_TRIP_LOOKUP[query.trip] == "round-trip"
    outbound, inbound = query.flight_data
    assert (outbound.from_airport.airport, outbound.to_airport.airport) == ("LAX", "JFK")
    assert (inbound.from_airport.airport, inbound.to_airport.airport, inbound.date) == ("JFK", "LAX", "2030-01-20")


def test_format_results_empty():
    assert format_results([], "one-way") == "No flights found matching your criteria."


def test_format_results_nonstop(nonstop_option):
    text = format_results([nonstop_option], "one-way")

    assert "Found 1 flight options." in text
    assert "Airlines: Example Air" in text
    assert "Departure: LAX 2030-01-15 08:05" in text
    assert "Arrival: JFK 2030-01-15 11:00" in text
    assert "Flight time: 5h 30m" in text
    assert "Stops: 0" in text
    assert "Price: USD 250" in text
    assert "round-trip search" not in text


def test_format_results_connecting_flight(one_stop_option):
    text = format_results([one_stop_option], "round-trip")

    assert "Arrival: JFK 2030-01-15 15:00" in text
    assert "Flight time: 5h 55m" in text
    assert "Stops: 1" in text
    assert "round-trip search" in text


def test_format_results_limits_output():
    options = [make_option(100 + i, [make_segment("LAX", "JFK", 300)]) for i in range(3)]

    text = format_results(options, "one-way", max_results=2)

    assert "Option 2:" in text
    assert "Option 3:" not in text
    assert "... and 1 more flight options available." in text


def test_format_results_handles_missing_segments_and_airlines():
    text = format_results([make_option(99, [], airlines=[])], "one-way")

    assert "Airlines: unknown" in text
    assert "Price: USD 99" in text
    assert "Stops" not in text
