"""Barra lateral: logo da Casa dos Ventos e itens de navegação (por enquanto só visuais)."""

from pathlib import Path

import streamlit as st

PAGES = {"Geral": "nav_geral", "Previsões": "nav_previsoes", "Impacto": "nav_impacto"}
DEFAULT_PAGE = "Geral"

_CSS_PATH = Path(__file__).with_name("sidebar.css")
_LOGO_PATH = Path(__file__).with_name("logo_casa_dos_ventos.svg")


def render_sidebar() -> None:
    """Renderiza o logo e a navegação na barra lateral. Chame uma vez por página."""
    st.session_state.setdefault("sidebar_page", DEFAULT_PAGE)
    st.logo(str(_LOGO_PATH), size="large")
    st.html(_CSS_PATH)
    with st.sidebar:
        _nav()


@st.fragment
def _nav() -> None:
    # Fragment: trocar o item destacado re-executa só a navegação, não a página inteira.
    # O item ativo é "primary" e os demais "tertiary"; o CSS estiliza cada tipo.
    with st.container(key="sidebar_nav"):
        for page, key in PAGES.items():
            st.button(
                page,
                key=key,
                type="primary" if page == st.session_state.sidebar_page else "tertiary",
                width="stretch",
                on_click=_select,
                args=(page,),
            )


def _select(page: str) -> None:
    st.session_state.sidebar_page = page
