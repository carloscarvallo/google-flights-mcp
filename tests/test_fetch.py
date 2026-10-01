import json
from datetime import date
from typing import ClassVar

import pytest

from google_flights_mcp import fetch
from google_flights_mcp.flights import build_query, validate_search


class FakeResponse:
    def __init__(self, url: str, text: str = "<html></html>"):
        self.url = url
        self.text = text


class FakeClient:
    """Stands in for primp.Client and records the last request."""

    response = FakeResponse("https://www.google.com/travel/flights?tfs=x")
    last_request: ClassVar[dict] = {}

    def __init__(self, **kwargs):
        FakeClient.last_request = {"client": kwargs}

    def get(self, url, params=None, cookies=None):
        FakeClient.last_request.update(url=url, params=params, cookies=cookies)
        return FakeClient.response


@pytest.fixture
def query():
    request = validate_search({"SOF": "Sofia", "DUB": "Dublin"}, "SOF", "DUB", "2030-11-02", today=date(2030, 1, 1))
    return build_query(request)


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(fetch, "Client", FakeClient)
    FakeClient.response = FakeResponse("https://www.google.com/travel/flights?tfs=x", "<html>ok</html>")
    return FakeClient


def test_fetch_html_sends_consent_cookie_and_query(fake_client, query):
    html = fetch.GoogleFlightsFetcher(proxy="http://proxy:8080").fetch_html(query)

    assert html == "<html>ok</html>"
    assert fake_client.last_request["cookies"] == fetch.CONSENT_COOKIES
    assert fake_client.last_request["params"] == query.params()
    assert fake_client.last_request["client"]["proxy"] == "http://proxy:8080"


def test_fetch_html_accepts_raw_string_query(fake_client):
    fetch.GoogleFlightsFetcher().fetch_html("flights from SOF to DUB")

    assert fake_client.last_request["params"] == {"q": "flights from SOF to DUB"}


def test_fetch_html_raises_clear_error_on_consent_redirect(fake_client, query):
    fake_client.response = FakeResponse("https://consent.google.com/m?continue=https://www.google.com/travel/flights")

    with pytest.raises(fetch.ConsentRequiredError, match="cookie-consent"):
        fetch.GoogleFlightsFetcher().fetch_html(query)


def make_row(airline: str, price: int, origin: str, destination: str) -> list:
    """Build one itinerary row in the layout fast_flights.parser.parse_js reads."""
    segment = [None] * 22
    segment[3], segment[4], segment[5], segment[6] = origin, f"{origin} Airport", f"{destination} Airport", destination
    segment[8], segment[10], segment[11], segment[17] = [7, 30], [10], 150, "Boeing 737"
    segment[20], segment[21] = [2030, 11, 5], [2030, 11, 5]
    flight = [None] * 23
    flight[0], flight[1], flight[2] = "FR", [airline], [segment]
    flight[22] = [None] * 7 + [50_000, 60_000]
    return [flight, [[None, price]]]


def make_script(best: list | None, other: list | None) -> str:
    payload = [None] * 8
    payload[2] = [best] if best is not None else None
    payload[3] = [other, "other-meta"] if other is not None else None
    payload[7] = [None, [[["STAR", "Star Alliance"]], [["FR", "Ryanair"]]]]
    return f"AF_initDataCallback({{key: 'ds:1', data:{json.dumps(payload)}, sideChannel: {{}}}});"


def test_merge_best_flights_puts_best_before_other():
    js = make_script([make_row("Ryanair", 73, "SOF", "DUB")], [make_row("Lufthansa", 225, "SOF", "DUB")])

    results = fetch.parse_js(fetch.merge_best_flights(js))

    assert [(r.airlines, r.price) for r in results] == [(["Ryanair"], 73), (["Lufthansa"], 225)]


def test_merge_best_flights_keeps_other_block_metadata():
    js = make_script([make_row("Ryanair", 73, "SOF", "DUB")], [])

    merged = fetch.merge_best_flights(js)

    assert '"other-meta"' in merged


def test_merge_best_flights_handles_missing_other_list():
    js = make_script([make_row("Ryanair", 73, "SOF", "DUB")], None)

    results = fetch.parse_js(fetch.merge_best_flights(js))

    assert [r.price for r in results] == [73]


def test_merge_best_flights_without_best_list_is_unchanged():
    js = make_script(None, [make_row("Lufthansa", 225, "SOF", "DUB")])

    assert fetch.merge_best_flights(js) == js


def test_merge_best_flights_passes_error_payload_through():
    js = "AF_initDataCallback({key: 'ds:1', data:errorHasStatus: true, x});"

    assert fetch.merge_best_flights(js) == js


class StaticFetcher(fetch.FetchIntegration):
    def __init__(self, html: str):
        self.html = html

    def fetch_html(self, q, /):
        return self.html


def test_fetch_flights_parses_best_and_other_flights(query):
    js = make_script([make_row("Ryanair", 73, "SOF", "DUB")], [make_row("Lufthansa", 225, "SOF", "DUB")])
    html = f'<html><script class="ds:1">{js}</script></html>'

    results = fetch.fetch_flights(query, StaticFetcher(html))

    assert [r.price for r in results] == [73, 225]
    assert results[0].flights[0].from_airport.code == "SOF"


def test_fetch_flights_raises_page_format_error_without_data_script(query):
    with pytest.raises(fetch.PageFormatError):
        fetch.fetch_flights(query, StaticFetcher("<html>captcha</html>"))
