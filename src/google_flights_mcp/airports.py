"""Airport lookup backed by a CSV file bundled with the package.

The data comes from https://github.com/mborsetti/airportsdata (MIT license, see
data/LICENSE-airportsdata.txt), pinned to commit
47ae282a8491758e6dafe28d4139539e561b54d5 and trimmed to airports that have an
IATA code. Shipping the file avoids network access at startup and removes the
dependency on unpinned remote content.
"""

import csv
from collections.abc import Iterable, Mapping
from importlib import resources
from types import MappingProxyType

DATA_PACKAGE = "google_flights_mcp.data"
DATA_FILE = "airports.csv"
MAX_FIELD_LENGTH = 120


def is_iata_code(code: str) -> bool:
    """Return True if code looks like a 3-letter IATA airport code."""
    return len(code) == 3 and code.isascii() and code.isalpha()


def _clean(value: str | None) -> str:
    """Remove control characters and cap the length of a CSV field."""
    text = "".join(ch for ch in (value or "") if ch.isprintable())
    return text.strip()[:MAX_FIELD_LENGTH]


def _describe(row: Mapping[str, str | None]) -> str:
    parts = (_clean(row.get("name")), _clean(row.get("city")), _clean(row.get("country")))
    return ", ".join(part for part in parts if part)


def parse_airports(lines: Iterable[str]) -> Mapping[str, str]:
    """Parse CSV lines into a read-only mapping of IATA code to description."""
    airports = {
        code: _describe(row)
        for row in csv.DictReader(lines)
        if is_iata_code(code := (row.get("iata") or "").strip().upper())
    }
    return MappingProxyType(airports)


def load_airports() -> Mapping[str, str]:
    """Load the bundled airport data."""
    data = resources.files(DATA_PACKAGE).joinpath(DATA_FILE)
    with data.open("r", encoding="utf-8", newline="") as f:
        return parse_airports(f)


def search_airports(airports: Mapping[str, str], query: str) -> list[str]:
    """Return sorted "Description (CODE)" entries matching a code or text query."""
    needle = query.strip().upper()
    return sorted(
        f"{name} ({code})"
        for code, name in airports.items()
        if needle in code or needle in name.upper()
    )
