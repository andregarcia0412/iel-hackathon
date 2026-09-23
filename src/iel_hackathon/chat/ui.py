"""Chat de IA: botão flutuante no canto inferior direito que abre um painel lateral."""

import logging
from pathlib import Path

import streamlit as st

from . import model

TITLE = "Assistente IA"
EMPTY_STATE = "Envie uma mensagem para começar."
INPUT_PLACEHOLDER = "Digite sua mensagem..."
ERROR_MESSAGE = "Não foi possível obter uma resposta do modelo. Tente novamente."

_CSS_PATH = Path(__file__).with_name("chat.css")
# O Streamlit não expõe as cores do tema como variáveis CSS; estes são os fundos padrão
# dos temas claro e escuro, usados quando `theme.backgroundColor` não está configurado.
_DEFAULT_BACKGROUND = {"light": "#ffffff", "dark": "#0e1117"}
# Altura fixa exigida pelo `autoscroll`; o CSS a substitui para ocupar o espaço livre do painel.
_MESSAGES_HEIGHT_PX = 400

_logger = logging.getLogger(__name__)


def render_chat() -> None:
    """Renderiza o botão flutuante e o painel de chat. Chame uma vez por página."""
    st.session_state.setdefault("chat_open", False)
    st.session_state.setdefault("chat_history", [])
    st.html(_CSS_PATH)
    _chat()


@st.fragment
def _chat() -> None:
    # Fragment: abrir, fechar e conversar re-executam só o chat, não a página inteira.
    # Os botões mostram só o ícone; o rótulo é ocultado pelo CSS, mas segue acessível.
    if not st.session_state.chat_open:
        st.button(
            "Abrir chat",
            key="chat_fab",
            icon=":material/chat:",
            type="primary",
            help="Abrir chat",
            on_click=_set_open,
            args=(True,),
        )
        return

    with st.container(key="chat_panel"):
        _panel_background()
        with st.container(key="chat_header", horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{TITLE}**")
            st.space("stretch")
            st.button(
                "Limpar conversa",
                key="chat_clear",
                icon=":material/delete:",
                type="tertiary",
                help="Limpar conversa",
                on_click=_clear_history,
            )
            st.button(
                "Fechar chat",
                key="chat_close",
                icon=":material/close:",
                type="tertiary",
                help="Fechar chat",
                on_click=_set_open,
                args=(False,),
            )
        messages_box = st.container(
            key="chat_messages_box", height=_MESSAGES_HEIGHT_PX, border=False, autoscroll=True
        )
        # Lido antes de preencher as mensagens para o estado vazio não aparecer junto do primeiro envio.
        prompt = st.chat_input(INPUT_PLACEHOLDER, key="chat_input", submit_mode="disable")

    history: list[model.Message] = st.session_state.chat_history
    with messages_box:
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt:
            _respond(prompt, history)
        elif not history:
            st.caption(EMPTY_STATE)


def _respond(prompt: str, history: list[model.Message]) -> None:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(model.stream_response(history))
        except Exception:
            _logger.exception("Falha ao gerar a resposta do modelo")
            st.error(ERROR_MESSAGE)
            return
    history.append({"role": "assistant", "content": str(reply)})


def _panel_background() -> None:
    color = st.get_option("theme.backgroundColor") or _DEFAULT_BACKGROUND.get(
        st.context.theme.type or "light", _DEFAULT_BACKGROUND["light"]
    )
    st.html(f"<style>.st-key-chat_panel {{ background-color: {color}; }}</style>")


def _set_open(is_open: bool) -> None:
    st.session_state.chat_open = is_open


def _clear_history() -> None:
    st.session_state.chat_history = []
