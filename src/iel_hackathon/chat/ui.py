"""Chat de IA: botão flutuante no canto inferior direito que abre um painel lateral."""

import logging
from pathlib import Path

import streamlit as st

from . import model, prompts

TITLE = "IA Assistente"
EMPTY_STATE = "Envie uma mensagem para iniciar, ou toque em uma sugestão:"
# Mostrado no balão da IA até chegar o primeiro trecho da resposta.
TYPING_INDICATOR = "...."
INPUT_PLACEHOLDER = "Pergunte sobre o dashboard..."
ERROR_MESSAGE = "Não foi possível obter uma resposta do modelo. Tente novamente."
NOT_CONFIGURED_MESSAGE = (
    "O assistente ainda não está configurado: defina a variável OLLAMA_API_KEY no ambiente."
)

_CSS_PATH = Path(__file__).with_name("chat.css")
_CLOSING_CSS_PATH = Path(__file__).with_name("chat_closing.css")
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
        # Logo depois de fechar, o botão entra com o painel encolhendo até a estrela. O estilo vale
        # só para esta execução; nas seguintes ele sai e a animação não se repete.
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
        # Lido antes de preencher as mensagens para o estado vazio não aparecer junto do primeiro envio.
        prompt = st.chat_input(INPUT_PLACEHOLDER, key="chat_input", submit_mode="disable")

    # Chip de sugestão clicado no rerun anterior (o on_click grava aqui).
    suggestion = st.session_state.pop("chat_suggestion", None)

    history: list[model.Message] = st.session_state.chat_history
    with messages_box:
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt or suggestion:
            _respond(prompt or suggestion, history)
        elif not history:
            # A estrela acima do texto vem do CSS.
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
        # O primeiro trecho da resposta (ou o erro) substitui o indicador no mesmo espaço.
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
