# Statistics Denmark municipality table finder

This script scans the official [StatBank API](https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api) catalogue and finds tables where at least one variable contains Danish municipality codes. It inspects metadata only; it does not download the tables' observations.

**[Browse the generated catalogue](https://frederiklarsendps.github.io/statistics-denmark-municipality-data/)**

## Setup and run

The project uses [uv](https://docs.astral.sh/uv/) with Python 3.10 or newer.

```bash
uv sync
uv run find_municipality_tables.py
```

The scan includes both active and discontinued tables and accepts a variable when at least 15 values match both the code and municipality name of Denmark's 98 current municipalities. Results are written to `municipality_tables.json` (detailed and machine-readable) and `municipality_tables.csv` (one row per matching table/variable pair). Each JSON table also contains its complete time dimension, a derived `time_grain`, and every remaining variable with all allowed values, so it can drive a metadata catalogue interface without additional API calls. Use each table's `active` field to distinguish currently maintained and discontinued tables in downstream interfaces.

Useful options:

```bash
# Require complete coverage of all 98 municipalities
uv run find_municipality_tables.py --threshold 98

# Return English metadata
uv run find_municipality_tables.py --language en

# See all options
uv run find_municipality_tables.py --help
```

Metadata is cached under `.cache/statbank/`. A cached entry is automatically refreshed when the table catalogue reports a new `updated` timestamp, so interrupted scans can simply be run again. Delete the cache if you want to force a complete refresh.

## Matching method and caveats

The matcher validates both the three-digit code and its municipality label for every non-time variable value. It normalizes directional labels used by migration tables, such as `Til København`, `Fra København`, `To Copenhagen`, and `From Copenhagen`. Requiring the label prevents unrelated numeric classifications—book subjects, weight bands, candidates, securities, and similar values—from becoming false positives merely because their IDs overlap municipality codes. Variables tagged with StatBank's `Denmark_municipality` map are excluded because that map represents the pre-2007 system; post-reform map IDs use the `_07` suffix. Inspect `municipality_dimensions` in the JSON output for coverage and source metadata.

The catalogue is a point-in-time API scan. Run the script periodically to discover newly published or updated tables. Statistics Denmark data is available under CC BY 4.0; attribute Statistics Denmark when reusing it.

## Build the standalone catalogue

Compile the generated JSON into a single, self-contained HTML file:

```bash
uv run build_catalogue.py
```

This writes `municipality_tables.html` with all table metadata, styles, scripts, and dimension values inline. The interface uses a CSS grid, native HTML popovers, CSS anchor positioning, and a small amount of JavaScript for filtering and sorting. It needs no server or external assets.

GitHub Actions rebuilds and publishes the catalogue to GitHub Pages every Sunday. The workflow can also be run manually from the repository's Actions tab.

## Test

```bash
uv run python -m unittest -v
```
