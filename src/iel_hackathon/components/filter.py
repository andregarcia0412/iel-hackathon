"""Filtro: grupos de opções clicáveis em uma barra horizontal, com a opção marcada em verde-escuro."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).with_name("filter.css")


@contextmanager
def filter_bar() -> Iterator[None]:
    """Barra horizontal que agrupa filtros, separados por uma linha vertical. Use uma por página."""
    st.html(_CSS_PATH)
    with st.container(key="filter_bar", horizontal=True, vertical_alignment="center", gap=None):
        yield


def render_filter(label: str, options: Sequence[str], *, key: str) -> str:
    """Renderiza um grupo de opções dentro de `filter_bar()` e retorna a opção marcada.

    Sempre há exatamente uma opção marcada (a primeira, por padrão); clicar na já marcada não a desmarca.
    A seleção fica em `st.session_state[key]`.
    """
    return st.pills(label, options, selection_mode="single", required=True, default=options[0], key=key)
