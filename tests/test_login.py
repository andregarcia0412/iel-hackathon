import pytest
from streamlit.testing.v1 import AppTest

from iel_hackathon.login import ui


def _app() -> None:
    import streamlit as st

    from iel_hackathon.login import render_login

    if render_login():
        st.caption("enviado")


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_function(_app).run()


def _tabs(at: AppTest) -> list:
    return [at.button(key=f"login_tab_{mode.lower()}") for mode in ui.MODES]


def _primary_tab_labels(at: AppTest) -> list[str]:
    return [button.label for button in _tabs(at) if button.proto.type == "primary"]


def _submitted(at: AppTest) -> bool:
    return [caption.value for caption in at.caption] == ["enviado"]


def test_starts_on_login_tab(at):
    assert _primary_tab_labels(at) == ["Login"]
    assert [markdown.value for markdown in at.markdown] == ["Login"]
    assert at.button(key="login_submit").label == "Entrar"
    assert not _submitted(at)


def test_fields_have_design_labels_and_placeholders(at):
    email, password = at.text_input
    assert (email.label, email.placeholder) == ("Email", "Digite seu e-mail...")
    assert (password.label, password.placeholder) == ("Senha", "Digite sua senha...")
    assert password.proto.type == password.proto.PASSWORD


def test_cadastro_tab_changes_title_and_button(at):
    at.button(key="login_tab_cadastro").click().run()

    assert _primary_tab_labels(at) == ["Cadastro"]
    assert [markdown.value for markdown in at.markdown] == ["Cadastro"]
    assert at.button(key="login_submit").label == "Cadastrar"


def test_submitting_empty_fields_is_accepted(at):
    at.button(key="login_submit").click().run()

    assert _submitted(at)


@pytest.mark.parametrize("mode", ["login", "cadastro"])
def test_submitting_any_values_is_accepted(at, mode):
    at.button(key=f"login_tab_{mode}").click().run()
    at.text_input(key="login_email").input("qualquer coisa")
    at.text_input(key="login_password").input("123")
    at.button(key="login_submit").click().run()

    assert _submitted(at)


def test_css_has_no_less_than_sign():
    assert "<" not in ui._CSS_PATH.read_text(encoding="utf-8")
