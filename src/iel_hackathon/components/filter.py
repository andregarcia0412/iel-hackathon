from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("filter.css")


@contextmanager
def filter_bar() -> Iterator[None]:
    st.html(_CSS_PATH)
    with st.container(key="filter_bar", horizontal=True, vertical_alignment="center", gap=None):
        yield


def render_filter(label: str, options: Sequence[str], *, key: str) -> str:
    return st.pills(label, options, selection_mode="single", required=True, default=options[0], key=key)
