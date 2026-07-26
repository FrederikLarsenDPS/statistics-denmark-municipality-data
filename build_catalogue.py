#!/usr/bin/env python3
"""Compile municipality_tables.json into one self-contained HTML catalogue."""

from __future__ import annotations

import json
from itertools import count
from pathlib import Path
from typing import Any, Iterable

from htpy import (
    Node,
    a,
    article,
    body,
    button,
    div,
    form,
    h1,
    h2,
    head,
    html,
    input,
    label,
    li,
    main as main_element,
    meta,
    option,
    p,
    script,
    select,
    small,
    span,
    style,
    time,
    title,
    ul,
)
from markupsafe import Markup


SOURCE = Path("municipality_tables.json")
OUTPUT = Path("municipality_tables.html")

CSS = """
:root {
  color-scheme: light;
  font-family: system-ui, sans-serif;
  color: #222;
  background: #fff;
}
* { box-sizing: border-box; }
body { margin: 0; }
a { color: inherit; }
.page-header, main { width: min(100% - 2rem, 90rem); margin-inline: auto; }
.page-header { padding-block: 2.5rem 1.5rem; }
h1 { margin: 0; font-size: clamp(1.5rem, 4vw, 2rem); }
.lede { max-width: 52rem; margin: .5rem 0 0; color: #666; line-height: 1.5; }
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: .75rem 1rem;
  align-items: end;
  margin-block: 0 1.25rem;
}
.control { display: grid; gap: .25rem; color: #555; font-size: .75rem; }
.control--search { flex: 1 1 16rem; }
input, select {
  min-height: 2.25rem;
  padding: .35rem .5rem;
  color: inherit;
  background: #fff;
  border: 1px solid #aaa;
  border-radius: .2rem;
  font: inherit;
}
input:focus, select:focus { outline: 2px solid currentColor; outline-offset: 1px; }
.result-count { margin: 0 0 .5rem auto; color: #666; font-size: .85rem; }
.catalogue-frame { overflow-x: auto; margin-bottom: 4rem; border-block: 1px solid #bbb; }
.catalogue { min-width: 72rem; }
.grid {
  display: grid;
  grid-template-columns: minmax(15rem, 1.2fr) minmax(18rem, 1.35fr) minmax(14rem, 1fr) minmax(9rem, .65fr) 7rem;
  gap: 1.25rem;
  align-items: start;
}
.grid-header {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: .65rem .75rem;
  color: #555;
  background: #fff;
  border-bottom: 1px solid #bbb;
  font-size: .75rem;
  font-weight: 650;
}
.dataset-row { padding: .9rem .75rem; border-bottom: 1px solid #ddd; }
.dataset:last-child .dataset-row { border-bottom: 0; }
.table-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .5rem; }
.table-id { font-weight: 700; text-underline-offset: .2em; }
.table-title { margin: .25rem 0 0; color: #555; line-height: 1.4; }
.dimensions { display: flex; flex-direction: column; align-items: flex-start; gap: .3rem; min-width: 0; }
.dimension {
  max-width: 100%;
  padding: 0;
  color: inherit;
  background: transparent;
  border: 0;
  font: inherit;
  line-height: 1.35;
  text-align: left;
  text-decoration: underline dotted;
  text-underline-offset: .2em;
  white-space: normal;
  overflow-wrap: anywhere;
  cursor: pointer;
}
.dimension:hover { text-decoration-style: solid; }
.dimension:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
.count, .meta, .period { color: #666; }
.meta { font-size: .8rem; }
.period { display: block; margin-top: .3rem; font-size: .8rem; }
.updated { font-variant-numeric: tabular-nums; white-space: nowrap; }
.empty { color: #999; }
[popover] {
  width: max-content;
  max-width: min(30rem, calc(100vw - 2rem));
  max-height: min(34rem, calc(100vh - 2rem));
  padding: 0;
  overflow: auto;
  color: #222;
  background: #fff;
  border: 1px solid #777;
  border-radius: .2rem;
  box-shadow: .25rem .5rem 1rem rgb(0 0 0 / .12);
}
[popover]::backdrop { background: transparent; }
@supports (position-area: block-end) {
  [popover] {
    inset: auto;
    margin: .45rem 0 0;
    position-area: block-end;
    justify-self: anchor-center;
    position-try-fallbacks: flip-block, flip-inline;
  }
}
.popover-title {
  position: sticky;
  top: 0;
  margin: 0;
  padding: .75rem;
  background: #fff;
  border-bottom: 1px solid #bbb;
  font-size: 1rem;
}
.value-list {
  display: grid;
  grid-template-columns: max-content minmax(0, auto);
  margin: 0;
  padding: 0;
  list-style: none;
}
.value-list li {
  display: grid;
  grid-template-columns: subgrid;
  grid-column: 1 / -1;
  gap: .75rem;
  padding: .6rem .75rem;
  border-bottom: 1px solid #ddd;
  line-height: 1.35;
}
.value-list li:last-child { border-bottom: 0; }
.value-index { color: #666; font-variant-numeric: tabular-nums; }
@media (max-width: 700px) {
  .page-header { padding-top: 1.5rem; }
  .catalogue-frame { width: calc(100% + 1rem); }
}
"""

JS = """
const rows = [...document.querySelectorAll('.dataset')];
const host = document.querySelector('.rows');
const search = document.querySelector('#search');
const status = document.querySelector('#status');
const grain = document.querySelector('#grain');
const unit = document.querySelector('#unit');
const sort = document.querySelector('#sort');
const resultCount = document.querySelector('#result-count');
const collator = new Intl.Collator(undefined, {numeric: true});

function refresh() {
  const query = search.value.trim().toLocaleLowerCase();
  for (const row of rows) {
    row.hidden = Boolean(
      (query && !row.dataset.search.includes(query)) ||
      (status.value !== 'all' && row.dataset.status !== status.value) ||
      (grain.value !== 'all' && row.dataset.grain !== grain.value) ||
      (unit.value !== 'all' && row.dataset.unit !== unit.value)
    );
  }
  const [key, direction] = sort.value.split(':');
  rows.sort((a, b) => {
    const left = key === 'coverage' ? Number(a.dataset[key]) : a.dataset[key];
    const right = key === 'coverage' ? Number(b.dataset[key]) : b.dataset[key];
    return direction === 'asc' ? collator.compare(left, right) : collator.compare(right, left);
  });
  host.append(...rows);
  resultCount.textContent = `${rows.filter(row => !row.hidden).length} tables`;
}

search.addEventListener('input', refresh);
for (const control of [status, grain, unit, sort]) control.addEventListener('change', refresh);
document.querySelector('.controls').addEventListener('submit', event => event.preventDefault());
refresh();
"""


def value_popover(
    popover_id: str,
    label: str,
    values: Iterable[dict[str, Any]],
    *,
    button_text: str | None = None,
) -> tuple[Node, Node]:
    values = list(values)
    trigger = button(
        type="button",
        class_="dimension",
        popovertarget=popover_id,
        aria_haspopup="dialog",
    )[button_text or f"{label} · {len(values)}"]
    panel = div(id=popover_id, class_="value-popover", popover=True)[
        h2(class_="popover-title")[f"{label} ({len(values)})"],
        ul(class_="value-list")[(
            li(data_value_code=str(value.get("id", "")))[
                span(class_="value-index")[str(index)],
                span[str(value.get("text", ""))],
            ]
            for index, value in enumerate(values, start=1)
        )],
    ]
    return trigger, panel


def dataset_row(table: dict[str, Any], ids: count) -> Node:
    variable_controls: list[Node] = []
    popovers: list[Node] = []
    for variable in table["variables"]:
        trigger, panel = value_popover(
            f"values-{next(ids)}", variable["text"], variable.get("values", [])
        )
        variable_controls.append(trigger)
        popovers.append(panel)

    municipality_controls: list[Node] = []
    for dimension in table["municipality_dimensions"]:
        trigger, panel = value_popover(
            f"values-{next(ids)}",
            dimension["text"],
            dimension["municipalities"],
            button_text=f"{dimension['text']} · {dimension['municipality_count']}/98",
        )
        municipality_controls.append(trigger)
        popovers.append(panel)

    time_dimension = table["time_dimension"]
    time_trigger, time_panel = value_popover(
        f"values-{next(ids)}",
        time_dimension["text"],
        time_dimension["values"],
        button_text=f"{table['time_grain']} · {len(time_dimension['values'])}",
    )
    popovers.append(time_panel)

    search_text = " ".join(
        [
            table["id"],
            table["text"],
            table["unit"],
            table["time_grain"],
            *(variable["text"] for variable in table["variables"]),
            *(dimension["text"] for dimension in table["municipality_dimensions"]),
        ]
    ).lower()
    coverage = max(
        dimension["municipality_count"]
        for dimension in table["municipality_dimensions"]
    )
    return article(
        class_="dataset",
        data_search=search_text,
        data_status="active" if table["active"] else "inactive",
        data_grain=table["time_grain"],
        data_unit=table["unit"],
        data_title=table["text"].lower(),
        data_updated=table["updated"],
        data_coverage=str(coverage),
    )[
        div(class_="dataset-row grid")[
            div[
                div(class_="table-line")[
                    a(
                        class_="table-id",
                        href=table["url"],
                        target="_blank",
                        rel="noreferrer",
                    )[table["id"]],
                    span(class_="meta")[f"· {table['unit']}"],
                    not table["active"]
                    and span(class_="meta")["(discontinued)"],
                ],
                p(class_="table-title")[table["text"]],
            ],
            div(class_="dimensions")[
                variable_controls or span(class_="empty")["—"]
            ],
            div(class_="dimensions")[municipality_controls],
            div[
                time_trigger,
                small(class_="period")[
                    f"{table['first_period']} – {table['latest_period']}"
                ],
            ],
            time(datetime=table["updated"], class_="updated")[
                table["updated"].split("T", 1)[0]
            ],
        ],
        popovers,
    ]


def render_catalogue(data: dict[str, Any]) -> str:
    tables = data["tables"]
    active_count = sum(bool(table["active"]) for table in tables)
    generated = data["generated_at"].split("T", 1)[0]
    grains = sorted({table["time_grain"] for table in tables})
    units = sorted({table["unit"] for table in tables})
    id_sequence = count(1)
    document = html(lang=data["parameters"]["language"])[
        head[
            meta(charset="utf-8"),
            meta(name="viewport", content="width=device-width, initial-scale=1"),
            meta(
                name="description",
                content="Municipality-level datasets published by Statistics Denmark",
            ),
            title["Municipality data · Statistics Denmark"],
            style[Markup(CSS)],
        ],
        body[
            div(class_="page-header")[
                h1["Municipality data from Statistics Denmark"],
                p(class_="lede")[
                    f"{len(tables):,} tables ({active_count:,} active, "
                    f"{len(tables) - active_count:,} discontinued). "
                    f"Generated {generated}. Select any dimension to inspect its values."
                ],
            ],
            main_element[
                form(class_="controls")[
                    label(class_="control control--search", for_="search")[
                        "Search",
                        input(
                            id="search",
                            type="search",
                            placeholder="Table, title, or variable",
                            autocomplete="off",
                        ),
                    ],
                    label(class_="control", for_="status")[
                        "Status",
                        select(id="status")[
                            option(value="all")["All"],
                            option(value="active")["Active"],
                            option(value="inactive")["Discontinued"],
                        ],
                    ],
                    label(class_="control", for_="grain")[
                        "Time grain",
                        select(id="grain")[
                            option(value="all")["All"],
                            (option(value=value)[value] for value in grains),
                        ],
                    ],
                    label(class_="control", for_="unit")[
                        "Unit",
                        select(id="unit")[
                            option(value="all")["All"],
                            (option(value=value)[value] for value in units),
                        ],
                    ],
                    label(class_="control", for_="sort")[
                        "Sort",
                        select(id="sort")[
                            option(value="updated:desc", selected=True)[
                                "Updated, newest"
                            ],
                            option(value="updated:asc")["Updated, oldest"],
                            option(value="title:asc")["Title, A–Z"],
                            option(value="coverage:desc")[
                                "Municipalities, most"
                            ],
                        ],
                    ],
                ],
                p(id="result-count", class_="result-count")[f"{len(tables)} tables"],
                div(class_="catalogue-frame")[
                    div(class_="catalogue")[
                        div(class_="grid grid-header", role="row")[
                            span["Table"],
                            span["Variables"],
                            span["Municipality"],
                            span["Time"],
                            span["Updated"],
                        ],
                        div(class_="rows")[(
                            dataset_row(table, id_sequence) for table in tables
                        )],
                    ]
                ]
            ],
            script[Markup(JS)],
        ],
    ]
    return str(document)


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(render_catalogue(data) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['tables'])} tables to {OUTPUT}")


if __name__ == "__main__":
    main()
