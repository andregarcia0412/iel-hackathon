"""Chat de IA: botão flutuante no canto inferior direito que abre um painel lateral."""

import logging
from pathlib import Path

import streamlit as st

from . import model

TITLE = "IA Assistente"
EMPTY_STATE = "Envie uma mensagem para iniciar"
# Mostrado no balão da IA até chegar o primeiro trecho da resposta.
TYPING_INDICATOR = "...."
INPUT_PLACEHOLDER = "Digite sua mensagem..."
ERROR_MESSAGE = "Não foi possível obter uma resposta do modelo. Tente novamente."

_CSS_PATH = Path(__file__).with_name("chat.css")
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
    # Os ícones (estrela do botão flutuante e X de fechar) são aplicados pelo CSS.
    if not st.session_state.chat_open:
        st.button(
            "Abrir chat",
            key="chat_fab",
            type="tertiary",
            help="Abrir chat",
            on_click=_set_open,
            args=(True,),
        )
        return

    with st.container(key="chat_panel"):
        with st.container(key="chat_header", horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{TITLE}**")
            st.space("stretch")
            st.button(
                "Fechar chat",
                key="chat_close",
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
            # A estrela acima do texto vem do CSS.
            with st.container(key="chat_empty"):
                st.caption(EMPTY_STATE)


def _respond(prompt: str, history: list[model.Message]) -> None:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        # O primeiro trecho da resposta (ou o erro) substitui o indicador no mesmo espaço.
        slot = st.empty()
        slot.markdown(TYPING_INDICATOR)
        try:
            with slot:
                reply = st.write_stream(model.stream_response(history))
        except Exception:
            _logger.exception("Falha ao gerar a resposta do modelo")
            slot.error(ERROR_MESSAGE)
            return
    history.append({"role": "assistant", "content": str(reply)})


def _set_open(is_open: bool) -> None:
    st.session_state.chat_open = is_open
