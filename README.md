# Flight Planner MCP Server

A Model Context Protocol (MCP) server that searches Google Flights with the
[fast-flights](https://github.com/AWeirdDev/fast-flights) library and looks up
airport codes from a bundled data file.

## Features

- Search one-way and round-trip flights (prices in USD)
- Look up airport codes by city, airport name or partial code
- Get suggested travel dates
- Prompt templates for trip planning and destination comparison

## Requirements

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
uv sync
```

This installs the pinned versions from `uv.lock`.

## Usage

### Run the server

```bash
uv run google-flights-mcp
```

The server uses the stdio transport. Logs go to stderr.

### Claude Desktop

Add this to your Claude Desktop configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "flight-planner": {
      "command": "uv",
      "args": ["run", "--directory", "/PATH/TO/google-flights-mcp", "google-flights-mcp"]
    }
  }
}
```

Replace `/PATH/TO/google-flights-mcp` with the path to this project, then restart Claude Desktop.

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run --directory /PATH/TO/google-flights-mcp google-flights-mcp
```

## Tools

| Tool | Description |
| --- | --- |
| `search_flights` | Search flights between two IATA airport codes. Add `return_date` for a round trip. Seat classes: `economy`, `premium-economy`, `business`, `first`. Up to 9 passengers. |
| `airport_search` | Find airport codes by city, airport name, country or partial code. |
| `get_travel_dates` | Suggest departure and return dates from today. |

## Resources

- `airports://all`: the first 100 airports, sorted by code
- `airports://{code}`: details for one airport, for example `airports://LAX`

## Prompts

- `plan_trip`: plan a trip to a destination
- `compare_destinations`: compare two destinations

## Development

```bash
uv run pytest
```

## Limitations

- fast-flights reads the Google Flights web page. If Google changes the page, searches can fail until fast-flights is updated.
- Round-trip results list the outbound flights, with the price Google Flights shows for the round-trip search.

## Data

Airport data comes from [airportsdata](https://github.com/mborsetti/airportsdata)
(MIT license, see `src/google_flights_mcp/data/LICENSE-airportsdata.txt`),
pinned to commit `47ae282a8491758e6dafe28d4139539e561b54d5` and trimmed to airports with an IATA code.
To update it, download `airportsdata/airports.csv` from a newer commit, keep only rows with a
3-letter IATA code and the columns `iata,name,city,country`, and update the commit hash here and in `airports.py`.

## License

MIT
