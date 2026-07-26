#!/usr/bin/env python3
"""Find StatBank tables whose variable values include Danish municipality codes."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_BASE = "https://api.statbank.dk/v1"
USER_AGENT = "statbank-municipality-table-finder/1.0"
WORKERS = 4
REQUEST_DELAY_SECONDS = 0.1
CACHE_DIR = Path(".cache/statbank")
JSON_OUTPUT = Path("municipality_tables.json")
CSV_OUTPUT = Path("municipality_tables.csv")

# Current (post-2007 reform) municipality codes and Danish names, excluding
# regions and "all Denmark". The API's English metadata only translates
# København to Copenhagen; the remaining municipality proper names are stable.
MUNICIPALITIES = dict(
    line.strip().split("|", 1)
    for line in """
    101|København
    147|Frederiksberg
    151|Ballerup
    153|Brøndby
    155|Dragør
    157|Gentofte
    159|Gladsaxe
    161|Glostrup
    163|Herlev
    165|Albertslund
    167|Hvidovre
    169|Høje-Taastrup
    173|Lyngby-Taarbæk
    175|Rødovre
    183|Ishøj
    185|Tårnby
    187|Vallensbæk
    190|Furesø
    201|Allerød
    210|Fredensborg
    217|Helsingør
    219|Hillerød
    223|Hørsholm
    230|Rudersdal
    240|Egedal
    250|Frederikssund
    253|Greve
    259|Køge
    260|Halsnæs
    265|Roskilde
    269|Solrød
    270|Gribskov
    306|Odsherred
    316|Holbæk
    320|Faxe
    326|Kalundborg
    329|Ringsted
    330|Slagelse
    336|Stevns
    340|Sorø
    350|Lejre
    360|Lolland
    370|Næstved
    376|Guldborgsund
    390|Vordingborg
    400|Bornholm
    410|Middelfart
    420|Assens
    430|Faaborg-Midtfyn
    440|Kerteminde
    450|Nyborg
    461|Odense
    479|Svendborg
    480|Nordfyns
    482|Langeland
    492|Ærø
    510|Haderslev
    530|Billund
    540|Sønderborg
    550|Tønder
    561|Esbjerg
    563|Fanø
    573|Varde
    575|Vejen
    580|Aabenraa
    607|Fredericia
    615|Horsens
    621|Kolding
    630|Vejle
    657|Herning
    661|Holstebro
    665|Lemvig
    671|Struer
    706|Syddjurs
    707|Norddjurs
    710|Favrskov
    727|Odder
    730|Randers
    740|Silkeborg
    741|Samsø
    746|Skanderborg
    751|Aarhus
    756|Ikast-Brande
    760|Ringkøbing-Skjern
    766|Hedensted
    773|Morsø
    779|Skive
    787|Thisted
    791|Viborg
    810|Brønderslev
    813|Frederikshavn
    820|Vesthimmerlands
    825|Læsø
    840|Rebild
    846|Mariagerfjord
    849|Jammerbugt
    851|Aalborg
    860|Hjørring
    """.strip().splitlines()
)
MUNICIPALITY_CODES = frozenset(MUNICIPALITIES)
MUNICIPALITY_NAME_ALIASES = {"101": {"København", "Copenhagen"}}


def normalized_municipality_label(label: str) -> str:
    """Remove API direction/administrative wording from a municipality label."""
    normalized = " ".join(label.split()).casefold()
    for prefix in ("til ", "fra ", "to ", "from "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    for suffix in (" kommune", " municipality"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def is_municipality_value(code: str, label: Any) -> bool:
    """Check that both a value's code and its label identify one municipality."""
    if code not in MUNICIPALITIES or not isinstance(label, str):
        return False
    expected = MUNICIPALITY_NAME_ALIASES.get(code, {MUNICIPALITIES[code]})
    return normalized_municipality_label(label) in {
        normalized_municipality_label(name) for name in expected
    }


def api_post(endpoint: str, payload: dict[str, Any], retries: int = 4) -> Any:
    """POST JSON, retrying transient HTTP and network failures."""
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise
            retry_after = error.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else 2**attempt + random.random()
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            wait = 2**attempt + random.random()
        time.sleep(wait)
    raise AssertionError("retry loop exited unexpectedly")


def municipality_dimensions(
    metadata: dict[str, Any], threshold: int
) -> list[dict[str, Any]]:
    """Return variables with enough values matching municipality code and name."""
    matches = []
    for variable in metadata.get("variables", []):
        if variable.get("time"):
            continue
        # StatBank uses this exact map ID for the 271 municipalities before the
        # 2007 reform. Some unchanged code/name pairs overlap the current 98.
        if str(variable.get("map", "")).casefold() == "denmark_municipality":
            continue
        values_by_id = {
            str(value.get("id")): value
            for value in variable.get("values", [])
            if value.get("id") is not None
        }
        matched_codes = sorted(
            code
            for code in MUNICIPALITY_CODES.intersection(values_by_id)
            if is_municipality_value(code, values_by_id[code].get("text"))
        )
        if len(matched_codes) < threshold:
            continue
        matches.append(
            {
                "id": variable.get("id"),
                "text": variable.get("text"),
                "map": variable.get("map"),
                "municipality_count": len(matched_codes),
                "coverage": round(len(matched_codes) / len(MUNICIPALITY_CODES), 4),
                "municipalities": [values_by_id[code] for code in matched_codes],
            }
        )
    return sorted(matches, key=lambda item: item["municipality_count"], reverse=True)


def derive_time_grain(time_dimension: dict[str, Any]) -> str:
    """Classify a StatBank time dimension from all of its period codes."""
    grains = set()
    for value in time_dimension.get("values", []):
        period = str(value.get("id", "")).strip()
        if re.fullmatch(r"\d{4}", period):
            grains.add("year")
        elif re.fullmatch(r"\d{4}H[12]", period, re.IGNORECASE):
            grains.add("half-year")
        elif re.fullmatch(r"\d{4}(?:K|KV)[1-4]", period, re.IGNORECASE):
            grains.add("quarter")
        elif re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", period, re.IGNORECASE):
            grains.add("month")
        elif re.fullmatch(
            r"\d{4}M(?:0[1-9]|1[0-2])D(?:0[1-9]|[12]\d|3[01])",
            period,
            re.IGNORECASE,
        ):
            grains.add("day")
        elif re.fullmatch(r"\d{4}U(?:0?[1-9]|[1-4]\d|5[0-3])", period, re.IGNORECASE):
            grains.add("week")
        elif (
            ":" in period
            or re.search(r"\d{4}.*[-–].*\d{4}", period)
            or re.search(r"\s[-–]\s", period)
        ):
            grains.add("interval")
        else:
            grains.add("unknown")
    if not grains:
        return "unknown"
    return next(iter(grains)) if len(grains) == 1 else "mixed"


def cache_path(cache_dir: Path, language: str, table_id: str) -> Path:
    return cache_dir / language / f"{table_id.upper()}.json"


def load_cached_metadata(
    path: Path, catalogue_updated: str | None
) -> dict[str, Any] | None:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if catalogue_updated and metadata.get("updated") != catalogue_updated:
        return None
    return metadata


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fetch_table_metadata(
    table: dict[str, Any], language: str, cache_dir: Path, delay: float
) -> tuple[dict[str, Any], bool]:
    path = cache_path(cache_dir, language, table["id"])
    cached = load_cached_metadata(path, table.get("updated"))
    if cached is not None:
        return cached, True
    if delay:
        time.sleep(delay)
    metadata = api_post("tableinfo", {"table": table["id"], "lang": language})
    write_json_atomic(path, metadata)
    return metadata, False


def table_result(
    table: dict[str, Any], metadata: dict[str, Any], dimensions: list[dict[str, Any]]
) -> dict[str, Any]:
    municipality_ids = {dimension["id"] for dimension in dimensions}
    time_dimensions = [
        variable for variable in metadata.get("variables", []) if variable.get("time")
    ]
    time_dimension = time_dimensions[0] if time_dimensions else None
    variables = [
        variable
        for variable in metadata.get("variables", [])
        if not variable.get("time") and variable.get("id") not in municipality_ids
    ]
    return {
        "id": table["id"],
        "text": table.get("text", metadata.get("text")),
        "unit": table.get("unit", metadata.get("unit")),
        "updated": table.get("updated", metadata.get("updated")),
        "first_period": table.get("firstPeriod"),
        "latest_period": table.get("latestPeriod"),
        "active": table.get("active", metadata.get("active")),
        "url": f"https://www.statbank.dk/{table['id']}",
        "time_grain": derive_time_grain(time_dimension or {}),
        "time_dimension": time_dimension,
        "municipality_dimensions": dimensions,
        "variables": variables,
    }


def write_csv(path: Path, tables: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "table_id", "table_title", "unit", "updated", "first_period",
        "latest_period", "active", "table_url", "variable_id", "variable_text",
        "map", "municipality_count", "coverage", "municipality_codes",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for table in tables:
            for dimension in table["municipality_dimensions"]:
                writer.writerow(
                    {
                        "table_id": table["id"],
                        "table_title": table["text"],
                        "unit": table["unit"],
                        "updated": table["updated"],
                        "first_period": table["first_period"],
                        "latest_period": table["latest_period"],
                        "active": table["active"],
                        "table_url": table["url"],
                        "variable_id": dimension["id"],
                        "variable_text": dimension["text"],
                        "map": dimension["map"],
                        "municipality_count": dimension["municipality_count"],
                        "coverage": dimension["coverage"],
                        "municipality_codes": "|".join(
                            value["id"] for value in dimension["municipalities"]
                        ),
                    }
                )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=15, help="minimum matching codes (default: 15)")
    parser.add_argument("--language", choices=("da", "en"), default="da", help="metadata language")
    args = parser.parse_args(argv)
    if not 1 <= args.threshold <= len(MUNICIPALITY_CODES):
        parser.error(f"--threshold must be between 1 and {len(MUNICIPALITY_CODES)}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("Fetching table catalogue...", file=sys.stderr)
    tables = api_post("tables", {"lang": args.language, "includeInactive": True})

    matches: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    cached_count = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_table_metadata,
                table,
                args.language,
                CACHE_DIR,
                REQUEST_DELAY_SECONDS,
            ): table
            for table in tables
        }
        for future in as_completed(futures):
            table = futures[future]
            completed += 1
            try:
                metadata, cached = future.result()
                cached_count += int(cached)
                dimensions = municipality_dimensions(metadata, args.threshold)
                if dimensions:
                    matches.append(table_result(table, metadata, dimensions))
            except Exception as error:  # Keep a long scan useful when one table fails.
                failures.append({"id": table["id"], "error": str(error)})
            if completed == len(tables) or completed % 100 == 0:
                print(
                    f"Scanned {completed}/{len(tables)} tables; found {len(matches)} matches",
                    file=sys.stderr,
                )

    matches.sort(key=lambda table: table["id"])
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": f"{API_BASE}/tables and {API_BASE}/tableinfo",
        "parameters": {
            "threshold": args.threshold,
            "language": args.language,
            "include_inactive": True,
        },
        "municipality_code_count": len(MUNICIPALITY_CODES),
        "tables_scanned": len(tables),
        "tables_from_cache": cached_count,
        "matching_table_count": len(matches),
        "failed_tables": failures,
        "tables": matches,
    }
    write_json_atomic(JSON_OUTPUT, result)
    write_csv(CSV_OUTPUT, matches)
    print(
        f"Wrote {len(matches)} matching tables to {JSON_OUTPUT} and {CSV_OUTPUT}",
        file=sys.stderr,
    )
    if failures:
        print(f"Warning: {len(failures)} table(s) failed; rerun to retry them", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
