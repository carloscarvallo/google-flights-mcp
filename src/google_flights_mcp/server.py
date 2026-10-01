"""Flight Planner MCP server.

Searches Google Flights through the fast-flights library and looks up airport
codes from a bundled CSV file. Runs over stdio by default.
"""

import logging
from datetime import date, timedelta

import anyio.to_thread
from fast_flights import FlightsNotFound
from mcp.server.mcpserver import Context, MCPServer

from .airports import is_iata_code, load_airports, search_airports
from .fetch import GoogleFlightsFetcher, fetch_flights
from .flights import SearchError, build_query, format_results, validate_search

logger = logging.getLogger("google_flights_mcp")

MAX_AIRPORT_MATCHES = 20
MAX_LISTED_AIRPORTS = 100
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100
DEFAULT_ADVANCE_DAYS = 30
DEFAULT_TRIP_DAYS = 7
MAX_ADVANCE_DAYS = 365

AIRPORTS = load_airports()
FETCHER = GoogleFlightsFetcher()

mcp = MCPServer("Flight Planner")


@mcp.tool()
async def search_flights(
    from_airport: str,
    to_airport: str,
    departure_date: str,
    ctx: Context,
    return_date: str | None = None,
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    seat_class: str = "economy",
) -> str:
    """
    Search for flights between two airports on Google Flights.

    Args:
        from_airport: Departure airport code (3-letter IATA code, e.g., 'LAX')
        to_airport: Arrival airport code (3-letter IATA code, e.g., 'JFK')
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (optional, for round trips)
        adults: Number of adult passengers (default: 1)
        children: Number of children (default: 0)
        infants_in_seat: Number of infants in seat (default: 0)
        infants_on_lap: Number of infants on lap (default: 0)
        seat_class: economy, premium-economy, business or first (default: economy)

    Returns:
        Flight search results as formatted text, with prices in USD
    """
    try:
        request = validate_search(
            AIRPORTS, from_airport, to_airport, departure_date, return_date,
            adults, children, infants_in_seat, infants_on_lap, seat_class,
        )
    except SearchError as e:
        return f"Error: {e}"

    logger.info("Searching flights: %s", request)
    await ctx.report_progress(0.5, 1.0)
    try:
        # fetch_flights does blocking network I/O, so keep it off the event loop.
        query = build_query(request)
        results = await anyio.to_thread.run_sync(fetch_flights, query, FETCHER)
    except FlightsNotFound:
        return "No flights found matching your criteria."
    except Exception:
        logger.exception("Flight search failed for %s", request)
        return "Error: The flight search failed. Google Flights may be unavailable or has changed its page format. Please try again later."
    finally:
        await ctx.report_progress(1.0, 1.0)

    return format_results(results, request.trip_type)


@mcp.tool()
def airport_search(query: str) -> str:
    """
    Search for airport codes by name, city, country or partial code.

    Args:
        query: The search term (city name, airport name, or partial code)

    Returns:
        List of matching airports with their codes
    """
    query = query.strip()
    if not MIN_QUERY_LENGTH <= len(query) <= MAX_QUERY_LENGTH:
        return f"Please provide {MIN_QUERY_LENGTH} to {MAX_QUERY_LENGTH} characters to search for airports."

    matches = search_airports(AIRPORTS, query)
    if not matches:
        return f"No airports found matching '{query}'."

    result = [f"Found {len(matches)} airports matching '{query}':", *matches[:MAX_AIRPORT_MATCHES]]
    if len(matches) > MAX_AIRPORT_MATCHES:
        result.append(f"...and {len(matches) - MAX_AIRPORT_MATCHES} more. Please refine your search.")
    return "\n".join(result)


@mcp.tool()
def get_travel_dates(days_from_now: int = DEFAULT_ADVANCE_DAYS, trip_length: int = DEFAULT_TRIP_DAYS) -> str:
    """
    Get suggested travel dates based on days from now and trip length.

    Args:
        days_from_now: Number of days from today for departure (default: 30)
        trip_length: Length of the trip in days (default: 7)

    Returns:
        Suggested travel dates in YYYY-MM-DD format
    """
    if not 1 <= days_from_now <= MAX_ADVANCE_DAYS:
        return f"Error: Days from now must be between 1 and {MAX_ADVANCE_DAYS}."
    if not 1 <= trip_length <= MAX_ADVANCE_DAYS:
        return f"Error: Trip length must be between 1 and {MAX_ADVANCE_DAYS} days."

    departure = date.today() + timedelta(days=days_from_now)
    return_date = departure + timedelta(days=trip_length)
    return f"Departure date: {departure.isoformat()}\nReturn date: {return_date.isoformat()}"


@mcp.resource("airports://all")
def get_all_airports() -> str:
    """Get the first airports in the database, sorted by code."""
    listed = sorted(AIRPORTS.items())[:MAX_LISTED_AIRPORTS]
    result = [f"Available Airports ({len(AIRPORTS)} total):", *(f"{code}: {name}" for code, name in listed)]
    if len(AIRPORTS) > MAX_LISTED_AIRPORTS:
        result.append(f"... and {len(AIRPORTS) - MAX_LISTED_AIRPORTS} more airports. Use the airport_search tool to find specific airports.")
    return "\n".join(result)


@mcp.resource("airports://{code}")
def get_airport_info(code: str) -> str:
    """Get information about a specific airport by its IATA code."""
    code = code.strip().upper()
    if is_iata_code(code) and code in AIRPORTS:
        return f"{code}: {AIRPORTS[code]}"
    return "Airport code not found. Use a 3-letter IATA code."


@mcp.prompt()
def plan_trip(destination: str) -> str:
    """Create a prompt for trip planning to a specific destination."""
    return f"""I'd like to plan a trip to {destination}. Can you help me with the following:

1. What's the best time of year to visit {destination}?
2. How long should I plan to stay to see the major attractions?
3. What are the must-see places in {destination}?
4. What's the typical cost range for accommodations?
5. Are there any travel advisories or cultural considerations I should be aware of?

After you answer these questions, could you help me find flights to {destination} using the flight search tool?"""


@mcp.prompt()
def compare_destinations(destination1: str, destination2: str) -> str:
    """Create a prompt for comparing two travel destinations."""
    return f"""I'm trying to decide between traveling to {destination1} and {destination2}.
Can you help me compare these destinations on the following factors:

1. Weather and best time to visit each location
2. Cost of travel and accommodations
3. Popular attractions and activities
4. Food and cultural experiences
5. Safety and travel considerations

Based on these factors, which would you recommend and why?
After your recommendation, could you show me flight options for both destinations?"""


def main() -> None:
    """Run the server over stdio. Logs go to stderr so stdout stays clean for MCP."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting Flight Planner server with %d airports", len(AIRPORTS))
    mcp.run()


if __name__ == "__main__":
    main()
