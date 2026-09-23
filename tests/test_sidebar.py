import pytest
from streamlit.testing.v1 import AppTest

from iel_hackathon.sidebar import ui


def _app() -> None:
    from iel_hackathon.sidebar import render_sidebar

    render_sidebar()


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_function(_app).run()


def _active_labels(at: AppTest) -> list[str]:
    return [button.label for button in at.sidebar.button if button.proto.type == "primary"]


def test_sidebar_shows_nav_items_in_order(at):
    assert [button.label for button in at.sidebar.button] == ["Geral", "Previsões", "Impacto"]


def test_geral_is_active_by_default(at):
    assert _active_labels(at) == ["Geral"]
    assert at.session_state.sidebar_page == "Geral"


def test_clicking_item_makes_it_the_only_active_one(at):
    at.button(key="nav_previsoes").click().run()

    assert _active_labels(at) == ["Previsões"]
    assert at.session_state.sidebar_page == "Previsões"


def test_css_has_no_less_than_sign():
    # O sanitizador do frontend do Streamlit descarta o <style> inteiro se o CSS contiver "<".
    assert "<" not in ui._CSS_PATH.read_text(encoding="utf-8")
