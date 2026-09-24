from html import escape
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("metric_card.css")


def render_metric_card(title: str, value: str, caption: str, *, highlight: bool = False) -> None:
    st.html(_CSS_PATH)
    st.html(_markup(title, value, caption, highlight))


def _markup(title: str, value: str, caption: str, highlight: bool) -> str:
    value_class = "metric-card__value metric-card__value--highlight" if highlight else "metric-card__value"
    return (
        '<div class="metric-card">'
        f'<p class="metric-card__title">{escape(title)}</p>'
        f'<p class="{value_class}">{escape(value)}</p>'
        f'<p class="metric-card__caption">{escape(caption)}</p>'
        "</div>"
    )
