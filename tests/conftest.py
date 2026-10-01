import pytest
from fast_flights.model import (
    Airport,
    CarbonEmission,
    Flights,
    SimpleDatetime,
    SingleFlight,
)


def make_segment(origin: str, destination: str, duration: int, dep_hour: int = 8) -> SingleFlight:
    return SingleFlight(
        from_airport=Airport(name=f"{origin} Airport", code=origin),
        to_airport=Airport(name=f"{destination} Airport", code=destination),
        departure=SimpleDatetime(date=(2030, 1, 15), time=(dep_hour, 5)),
        arrival=SimpleDatetime(date=(2030, 1, 15), time=(dep_hour + 3, 0)),
        duration=duration,
        plane_type="Airbus A321",
    )


def make_option(price: int, segments: list[SingleFlight], airlines: list[str] | None = None) -> Flights:
    return Flights(
        type="XX",
        price=price,
        airlines=airlines if airlines is not None else ["Example Air"],
        flights=segments,
        carbon=CarbonEmission(typical_on_route=100_000, emission=90_000),
    )


@pytest.fixture
def nonstop_option() -> Flights:
    return make_option(250, [make_segment("LAX", "JFK", 330)])


@pytest.fixture
def one_stop_option() -> Flights:
    return make_option(199, [make_segment("LAX", "DEN", 125), make_segment("DEN", "JFK", 230, dep_hour=12)])
