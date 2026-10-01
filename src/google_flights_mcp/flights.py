"""Validation, query building and formatting for flight searches.

This module has no MCP or network code so it can be tested in isolation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from fast_flights import FlightQuery, Passengers, Query, create_query
from fast_flights.model import Flights, SimpleDatetime

from .airports import is_iata_code

MAX_PASSENGERS = 9  # Google Flights limit, also enforced by fast_flights
MAX_RESULTS = 10
LANGUAGE = "en-US"
CURRENCY = "USD"
DATE_FORMAT = "%Y-%m-%d"

# Accept the underscore spelling used by earlier versions of this server.
SEAT_CLASSES = {
    "economy": "economy",
    "premium-economy": "premium-economy",
    "premium_economy": "premium-economy",
    "business": "business",
    "first": "first",
}


class SearchError(ValueError):
    """Invalid search input. The message is safe to show to the user."""


@dataclass(frozen=True)
class SearchRequest:
    from_airport: str
    to_airport: str
    departure_date: str
    return_date: str | None
    passengers: tuple[int, int, int, int]  # adults, children, infants in seat, on lap
    seat: str

    @property
    def trip_type(self) -> str:
        return "round-trip" if self.return_date else "one-way"


def _parse_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        raise SearchError(f"{label} must use the YYYY-MM-DD format.") from None


def _validate_airport(code: str, label: str, airports: Mapping[str, str]) -> str:
    code = code.strip().upper()
    if not is_iata_code(code):
        raise SearchError(f"{label} airport must be a 3-letter IATA code.")
    if code not in airports:
        raise SearchError(f"{label} airport code '{code}' is not in the airport database.")
    return code


def _validate_passengers(adults: int, children: int, in_seat: int, on_lap: int) -> None:
    if min(adults, children, in_seat, on_lap) < 0:
        raise SearchError("Passenger numbers cannot be negative.")
    if adults < 1:
        raise SearchError("At least one adult passenger is required.")
    if adults + children + in_seat + on_lap > MAX_PASSENGERS:
        raise SearchError(f"Google Flights allows at most {MAX_PASSENGERS} passengers.")
    if on_lap > adults:
        raise SearchError("Each infant on lap needs one adult.")


def validate_search(
    airports: Mapping[str, str],
    from_airport: str,
    to_airport: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    seat_class: str = "economy",
    today: date | None = None,
) -> SearchRequest:
    """Check user input and return a normalized SearchRequest.

    Raises:
        SearchError: if any input is invalid.
    """
    departure = _parse_date(departure_date, "Departure date")
    if departure < (today or date.today()):
        raise SearchError("Departure date cannot be in the past.")

    normalized_return = None
    if return_date:
        returning = _parse_date(return_date, "Return date")
        if returning < departure:
            raise SearchError("Return date cannot be before departure date.")
        normalized_return = returning.strftime(DATE_FORMAT)

    origin = _validate_airport(from_airport, "Departure", airports)
    destination = _validate_airport(to_airport, "Arrival", airports)
    if origin == destination:
        raise SearchError("Departure and arrival airports must be different.")

    _validate_passengers(adults, children, infants_in_seat, infants_on_lap)

    seat = SEAT_CLASSES.get(seat_class.strip().lower())
    if seat is None:
        valid = ", ".join(sorted(set(SEAT_CLASSES.values())))
        raise SearchError(f"Seat class must be one of: {valid}.")

    return SearchRequest(
        from_airport=origin,
        to_airport=destination,
        departure_date=departure.strftime(DATE_FORMAT),
        return_date=normalized_return,
        passengers=(adults, children, infants_in_seat, infants_on_lap),
        seat=seat,
    )


def build_query(request: SearchRequest) -> Query:
    """Convert a validated SearchRequest into a fast_flights Query."""
    legs = [FlightQuery(date=request.departure_date, from_airport=request.from_airport, to_airport=request.to_airport)]
    if request.return_date:
        legs.append(FlightQuery(date=request.return_date, from_airport=request.to_airport, to_airport=request.from_airport))

    adults, children, in_seat, on_lap = request.passengers
    return create_query(
        flights=legs,
        seat=request.seat,
        trip=request.trip_type,
        passengers=Passengers(adults=adults, children=children, infants_in_seat=in_seat, infants_on_lap=on_lap),
        language=LANGUAGE,
        currency=CURRENCY,
    )


def _format_time(moment: SimpleDatetime) -> str:
    year, month, day = moment.date
    hour, minute = moment.time
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _format_option(index: int, option: Flights) -> list[str]:
    segments = option.flights
    lines = [f"Option {index}:", f"  Airlines: {', '.join(option.airlines) or 'unknown'}"]
    if segments:
        first, last = segments[0], segments[-1]
        lines.append(f"  Departure: {first.from_airport.code} {_format_time(first.departure)}")
        lines.append(f"  Arrival: {last.to_airport.code} {_format_time(last.arrival)}")
        lines.append(f"  Flight time: {_format_duration(sum(s.duration for s in segments))}")
        lines.append(f"  Stops: {len(segments) - 1}")
    lines.append(f"  Price: {CURRENCY} {option.price}")
    return lines


def format_results(results: Sequence[Flights], trip_type: str, max_results: int = MAX_RESULTS) -> str:
    """Format search results into readable text."""
    if not results:
        return "No flights found matching your criteria."

    output = [f"Found {len(results)} flight options.", ""]
    for index, option in enumerate(results[:max_results], 1):
        output.extend(_format_option(index, option))
        output.append("")

    if len(results) > max_results:
        output.append(f"... and {len(results) - max_results} more flight options available.")
    if trip_type == "round-trip":
        output.append("Note: options show the outbound flights. Prices are as Google Flights shows them for a round-trip search.")
    return "\n".join(output)
