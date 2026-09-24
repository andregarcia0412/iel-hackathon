"""Tela de entrada: abas de Login e Cadastro com email e senha, sem validação nem integração."""

from pathlib import Path

import streamlit as st

# Aba → (título do card, rótulo do botão). As duas abas têm os mesmos campos.
MODES = {"Login": ("Login", "Entrar"), "Cadastro": ("Cadastro", "Cadastrar")}
DEFAULT_MODE = "Login"
EMAIL_PLACEHOLDER = "Digite seu e-mail..."
PASSWORD_PLACEHOLDER = "Digite sua senha..."

_CSS_PATH = Path(__file__).with_name("login.css")
_LOGO_MARKUP = (
    '<img class="login-logo" src="app/static/login/logo_casa_dos_ventos.svg"'
    ' width="182" height="87.5789" alt="Casa dos Ventos">'
)
_TITLE_MARKUP = '<h1 class="login-title">Seja muito bem-vindo ao <span>SinVision</span>!</h1>'


def render_login() -> bool:
    """Renderiza a tela de entrada e retorna True quando o formulário é enviado, com quaisquer valores."""
    mode = st.session_state.setdefault("login_mode", DEFAULT_MODE)
    title, submit_label = MODES[mode]
    st.html(_CSS_PATH)

    with st.container(key="login_page"):
        st.html(_LOGO_MARKUP)
        with st.container(key="login_content"):
            st.html(_TITLE_MARKUP)
            with st.container(key="login_card"):
                with st.container(key="login_header"):
                    _tabs()
                    st.markdown(title)
                with st.form(key="login_form", border=False):
                    with st.container(key="login_fields"):
                        st.text_input(
                            "Email", placeholder=EMAIL_PLACEHOLDER, key="login_email", autocomplete="email"
                        )
                        st.text_input(
                            "Senha",
                            type="password",
                            placeholder=PASSWORD_PLACEHOLDER,
                            key="login_password",
                            autocomplete="new-password" if mode == "Cadastro" else "current-password",
                        )
                    return st.form_submit_button(submit_label, key="login_submit", type="primary", width="stretch")


def _tabs() -> None:
    # A aba ativa é "primary" e a outra "secondary"; o CSS estiliza cada tipo, como na sidebar.
    with st.container(key="login_tabs", horizontal=True):
        for mode in MODES:
            st.button(
                mode,
                key=f"login_tab_{mode.lower()}",
                type="primary" if mode == st.session_state.login_mode else "secondary",
                on_click=_select,
                args=(mode,),
            )


def _select(mode: str) -> None:
    st.session_state.login_mode = mode
