"""Fetching and parsing of Google Flights result pages.

Two fixes on top of fast_flights:

1. For visitors whose IP is in the EU/EEA, Google redirects every request to
   consent.google.com until cookies are accepted. The default fast_flights
   fetcher does not handle this, so its parser fails with a confusing
   AttributeError. GoogleFlightsFetcher sends a SOCS cookie that records the
   consent choice.
2. Google returns two itinerary lists: "Best flights" (payload[2]) and "Other
   flights" (payload[3]). fast_flights only parses the second one, which drops
   the best and often cheapest options, for example Ryanair nonstops.
   fetch_flights merges both lists before parsing.
"""

import json
from urllib.parse import urlparse

from fast_flights import Query, ResultList
from fast_flights.fetcher import URL
from fast_flights.integrations.base import FetchIntegration
from fast_flights.parser import parse_js
from primp import Client
from selectolax.lexbor import LexborHTMLParser

BEST_FLIGHTS_INDEX = 2
OTHER_FLIGHTS_INDEX = 3
DATA_SCRIPT_SELECTOR = r"script.ds\:1"

# Consent cookie value that google.com accepts as "consent given".
# If Google stops accepting it, searches from the EU fail with ConsentRequiredError.
CONSENT_COOKIES = {"SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg"}
CONSENT_HOST = "consent.google.com"


class ConsentRequiredError(RuntimeError):
    """Google returned its cookie-consent page instead of flight results."""


class PageFormatError(RuntimeError):
    """The Google Flights page did not contain the expected flight data."""


class GoogleFlightsFetcher(FetchIntegration):
    """Fetch the Google Flights results page with a consent cookie set."""

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy

    def fetch_html(self, q: Query | str, /) -> str:
        client = Client(
            impersonate="chrome_145",
            impersonate_os="macos",
            referer=True,
            proxy=self._proxy,
            cookie_store=True,
        )
        params = q.params() if isinstance(q, Query) else {"q": q}
        response = client.get(URL, params=params, cookies=CONSENT_COOKIES)
        if urlparse(response.url).hostname == CONSENT_HOST:
            raise ConsentRequiredError(
                "Google redirected to its cookie-consent page; the SOCS consent cookie was not accepted"
            )
        return response.text


def _itineraries(payload: list, index: int) -> list:
    block = payload[index] if len(payload) > index else None
    return (block[0] or []) if block else []


def merge_best_flights(js: str) -> str:
    """Return the data script with "Best flights" placed before "Other flights".

    The result keeps the format that fast_flights.parser.parse_js expects:
    "<prefix>data:<json>,<suffix>". Error payloads are returned unchanged.
    """
    prefix, rest = js.split("data:", 1)
    data, suffix = rest.rsplit(",", 1)
    if data.endswith("errorHasStatus: true"):
        return js

    payload = json.loads(data)
    best = _itineraries(payload, BEST_FLIGHTS_INDEX)
    if not best:
        return js

    other_block = payload[OTHER_FLIGHTS_INDEX] or [None]
    merged_block = [best + _itineraries(payload, OTHER_FLIGHTS_INDEX), *other_block[1:]]
    merged = [*payload[:OTHER_FLIGHTS_INDEX], merged_block, *payload[OTHER_FLIGHTS_INDEX + 1 :]]
    return f"{prefix}data:{json.dumps(merged)},{suffix}"


def fetch_flights(query: Query, fetcher: FetchIntegration) -> ResultList:
    """Fetch a results page and parse both the best and the other flights."""
    html = fetcher.fetch_html(query)
    script = LexborHTMLParser(html).css_first(DATA_SCRIPT_SELECTOR)
    if script is None:
        raise PageFormatError("Google Flights page has no flight data script")
    return parse_js(merge_best_flights(script.text()))
