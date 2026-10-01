from datetime import date, timedelta

import pytest
from fast_flights import FlightsNotFound

from google_flights_mcp import server


class FakeContext:
    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    async def info(self, data):
        self.messages.append(("info", data))

    async def error(self, data):
        self.messages.append(("error", data))

    async def report_progress(self, progress, total=None, message=None):
        self.messages.append(("progress", f"{progress}/{total}"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def future_date() -> str:
    return (date.today() + timedelta(days=30)).isoformat()


@pytest.mark.anyio
async def test_search_flights_returns_formatted_results(monkeypatch, future_date, nonstop_option):
    calls = []

    def fake_fetch_flights(query, fetcher):
        calls.append((query, fetcher))
        return [nonstop_option]

    monkeypatch.setattr(server, "fetch_flights", fake_fetch_flights)
    ctx = FakeContext()

    text = await server.search_flights("lax", "jfk", future_date, ctx, seat_class="Business")

    assert "Price: USD 250" in text
    assert len(calls) == 1
    assert calls[0][1] is server.FETCHER
    assert ("progress", "1.0/1.0") in ctx.messages


@pytest.mark.anyio
async def test_search_flights_rejects_invalid_input_without_network(monkeypatch):
    def fail(query, fetcher):
        raise AssertionError("fetch_flights must not be called")

    monkeypatch.setattr(server, "fetch_flights", fail)

    text = await server.search_flights("LAX", "JFK", "2000-01-01", FakeContext())

    assert text == "Error: Departure date cannot be in the past."


@pytest.mark.anyio
async def test_search_flights_handles_no_results(monkeypatch, future_date):
    def not_found(query, fetcher):
        raise FlightsNotFound("none")

    monkeypatch.setattr(server, "fetch_flights", not_found)

    text = await server.search_flights("LAX", "JFK", future_date, FakeContext())

    assert text == "No flights found matching your criteria."


@pytest.mark.anyio
async def test_search_flights_hides_internal_error_details(monkeypatch, future_date):
    def broken(query, fetcher):
        raise RuntimeError("secret /Users/someone/path")

    monkeypatch.setattr(server, "fetch_flights", broken)
    ctx = FakeContext()

    text = await server.search_flights("LAX", "JFK", future_date, ctx)

    assert text.startswith("Error: The flight search failed.")
    assert "secret" not in text
    assert all("secret" not in message for _, message in ctx.messages)


def test_airport_search_finds_matches():
    text = server.airport_search("Los Angeles")

    assert "(LAX)" in text


def test_airport_search_validates_query_length():
    assert server.airport_search(" a ").startswith("Please provide")
    assert server.airport_search("x" * 101).startswith("Please provide")


def test_airport_search_no_match():
    assert server.airport_search("zzzzqqqq") == "No airports found matching 'zzzzqqqq'."


def test_airport_search_truncates_long_lists():
    text = server.airport_search("airport")

    assert text.endswith("Please refine your search.")
    assert len(text.splitlines()) == server.MAX_AIRPORT_MATCHES + 2


def test_get_travel_dates_defaults():
    departure = date.today() + timedelta(days=30)
    expected = f"Departure date: {departure}\nReturn date: {departure + timedelta(days=7)}"

    assert server.get_travel_dates() == expected


@pytest.mark.parametrize(("days", "length"), [(0, 7), (366, 7), (30, 0), (30, 366)])
def test_get_travel_dates_rejects_out_of_range(days, length):
    assert server.get_travel_dates(days, length).startswith("Error:")


def test_airport_resources():
    assert server.get_all_airports().startswith(f"Available Airports ({len(server.AIRPORTS)} total):")
    assert server.get_airport_info("lax").startswith("LAX: ")
    assert server.get_airport_info("nope") == "Airport code not found. Use a 3-letter IATA code."


def test_prompts_include_destinations():
    assert "Lisbon" in server.plan_trip("Lisbon")
    text = server.compare_destinations("Lisbon", "Porto")
    assert "Lisbon" in text and "Porto" in text
