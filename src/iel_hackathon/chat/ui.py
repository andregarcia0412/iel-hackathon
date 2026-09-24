import logging
from pathlib import Path

import streamlit as st

from . import model, prompts

TITLE = "IA Assistente"
EMPTY_STATE = "Envie uma mensagem para iniciar, ou toque em uma sugestão:"
TYPING_INDICATOR = "...."
INPUT_PLACEHOLDER = "Pergunte sobre o dashboard..."
ERROR_MESSAGE = "Não foi possível obter uma resposta do modelo. Tente novamente."
NOT_CONFIGURED_MESSAGE = (
    "O assistente ainda não está configurado: defina a variável OLLAMA_API_KEY no ambiente."
)

_CSS_PATH = Path(__file__).with_name("chat.css")
_CLOSING_CSS_PATH = Path(__file__).with_name("chat_closing.css")
_MESSAGES_HEIGHT_PX = 400

_logger = logging.getLogger(__name__)


def render_chat() -> None:
    st.session_state.setdefault("chat_open", False)
    st.session_state.setdefault("chat_history", [])
    st.html(_CSS_PATH)
    _chat()


@st.fragment
def _chat() -> None:
    if not st.session_state.chat_open:
        if st.session_state.pop("chat_closing", False):
            st.html(_CLOSING_CSS_PATH)
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
        prompt = st.chat_input(INPUT_PLACEHOLDER, key="chat_input", submit_mode="disable")

    suggestion = st.session_state.pop("chat_suggestion", None)

    history: list[model.Message] = st.session_state.chat_history
    with messages_box:
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt or suggestion:
            _respond(prompt or suggestion, history)
        elif not history:
            with st.container(key="chat_empty"):
                st.caption(EMPTY_STATE)
                for index, suggestion_text in enumerate(prompts.SUGGESTIONS):
                    st.button(
                        suggestion_text,
                        key=f"chat_suggestion_{index}",
                        type="tertiary",
                        on_click=_set_suggestion,
                        args=(suggestion_text,),
                    )


def _respond(prompt: str, history: list[model.Message]) -> None:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        slot = st.empty()
        if not model.is_configured():
            slot.error(NOT_CONFIGURED_MESSAGE)
            return
        slot.markdown(TYPING_INDICATOR)
        try:
            snapshot = prompts.build_dashboard_snapshot(st.session_state.get("dashboard_data"))
            with slot:
                reply = st.write_stream(model.stream_response(history, snapshot))
        except Exception:
            _logger.exception("Falha ao gerar a resposta do modelo")
            slot.error(ERROR_MESSAGE)
            return
    history.append({"role": "assistant", "content": str(reply)})


def _set_open(is_open: bool) -> None:
    st.session_state.chat_open = is_open
    st.session_state.chat_closing = not is_open


def _set_suggestion(text: str) -> None:
    st.session_state["chat_suggestion"] = text
