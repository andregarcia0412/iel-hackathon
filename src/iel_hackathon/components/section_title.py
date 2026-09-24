from html import escape
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("section_title.css")


def render_section_title(text: str) -> None:
    st.html(_CSS_PATH)
    st.html(_markup(text))


def _markup(text: str) -> str:
    return f'<p class="section-title">{escape(text)}</p>'
