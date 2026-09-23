"""Ponto de integração com o modelo de linguagem.

A UI do chat depende apenas de `stream_response`. Para integrar o Ollama, basta
substituir o corpo dessa função; o restante do chat não precisa mudar.
"""

import re
import time
from collections.abc import Iterator
from typing import Literal, TypedDict

STUB_REPLY = (
    "Esta é uma resposta simulada. A integração com o Ollama ainda não foi feita."
)
_STUB_CHUNK_DELAY_S = 0.03


class Message(TypedDict):
    """Mensagem do chat, no mesmo formato do endpoint `/api/chat` do Ollama."""

    role: Literal["user", "assistant"]
    content: str


def stream_response(messages: list[Message]) -> Iterator[str]:
    """Gera a resposta do modelo para a conversa em pedaços de texto (streaming).

    `messages` é o histórico completo, terminando na mensagem mais recente do usuário.

    TODO(ollama): substituir o stub abaixo pela chamada real, por exemplo:

        for chunk in ollama.chat(model=MODEL, messages=messages, stream=True):
            yield chunk["message"]["content"]
    """
    for chunk in re.findall(r"\S+\s*", STUB_REPLY):
        time.sleep(_STUB_CHUNK_DELAY_S)
        yield chunk
