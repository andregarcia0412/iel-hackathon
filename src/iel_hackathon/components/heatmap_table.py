import math
from bisect import bisect_left
from collections.abc import Mapping, Sequence
from html import escape
from itertools import pairwise
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("heatmap_table.css")

_GREEN = "#d9ffed"
_YELLOW = "#feffd9"
_ORANGE = "#ffefd9"
_RED = "#ffd9d9"

BAND_COLORS = (_GREEN, _YELLOW, _ORANGE, _RED)

EMPTY_COLORS = (
    (_GREEN, _YELLOW, _GREEN, _YELLOW, _ORANGE),
    (_YELLOW, _RED, _YELLOW, _ORANGE, _YELLOW),
    (_ORANGE, _YELLOW, _GREEN, _RED, _RED),
    (_RED, _GREEN, _YELLOW, _ORANGE, _RED),
)


def render_heatmap_table(
    *,
    rows: Sequence[str],
    columns: Sequence[str],
    thresholds: Sequence[float],
    values: Mapping[str, Mapping[str, float | None]] | None = None,
    rows_label: str = "",
    colors: Sequence[str] = BAND_COLORS,
    empty_colors: Sequence[Sequence[str]] = EMPTY_COLORS,
    placeholder: str = "—",
    title: str | None = None,
) -> None:
    st.html(_CSS_PATH)
    st.html(
        _markup(
            rows=rows,
            columns=columns,
            thresholds=thresholds,
            values=values,
            rows_label=rows_label,
            colors=colors,
            empty_colors=empty_colors,
            placeholder=placeholder,
            title=title,
        )
    )


def _markup(
    *,
    rows: Sequence[str],
    columns: Sequence[str],
    thresholds: Sequence[float],
    values: Mapping[str, Mapping[str, float | None]] | None = None,
    rows_label: str = "",
    colors: Sequence[str] = BAND_COLORS,
    empty_colors: Sequence[Sequence[str]] = EMPTY_COLORS,
    placeholder: str = "—",
    title: str | None = None,
) -> str:
    if len(colors) != len(thresholds) + 1:
        raise ValueError(f"São {len(thresholds)} limites, então são {len(thresholds) + 1} cores, não {len(colors)}.")
    if any(low >= high for low, high in pairwise(thresholds)):
        raise ValueError(f"Os limites precisam ser estritamente crescentes: {tuple(thresholds)}.")

    values = values or {}
    header = "".join(
        [
            f'<p class="heatmap-table__corner">{escape(rows_label)}</p>',
            *(f'<p class="heatmap-table__column">{escape(column)}</p>' for column in columns),
        ]
    )
    table_rows = [f'<div class="heatmap-table__row">{header}</div>']
    for i, row in enumerate(rows):
        row_values = values.get(row, {})
        cells = [f'<p class="heatmap-table__row-label">{escape(row)}</p>']
        for j, column in enumerate(columns):
            value = row_values.get(column)
            if value is None or math.isnan(value):
                pattern_row = empty_colors[i % len(empty_colors)]
                text, color = placeholder, pattern_row[j % len(pattern_row)]
            else:
                text, color = _format(value), colors[bisect_left(thresholds, value)]
            cells.append(f'<p class="heatmap-table__cell" style="background-color: {escape(color)}">{escape(text)}</p>')
        table_rows.append(f'<div class="heatmap-table__row">{"".join(cells)}</div>')

    title_markup = f'<p class="heatmap-table__title">{escape(title)}</p>' if title is not None else ""
    card = f'<div class="heatmap-table__card">{"".join(table_rows)}</div>'
    return f'<div class="heatmap-table">{title_markup}{card}</div>'


def _format(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + "%"
