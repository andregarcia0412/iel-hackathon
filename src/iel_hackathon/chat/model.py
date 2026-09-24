"""Integração com o Ollama Cloud.

A UI do chat depende apenas de `stream_response`: guardrails de escopo,
montagem do system prompt com o snapshot do dashboard e streaming da resposta.
A chave vem de `OLLAMA_API_KEY` (ver `config.py` e `.env.example`).
"""

from collections.abc import Iterator
from typing import Literal, TypedDict

from ollama import Client

from . import config, prompts


class Message(TypedDict):
    """Mensagem do chat, no mesmo formato do endpoint `/api/chat` do Ollama."""

    role: Literal["system", "user", "assistant"]
    content: str


def is_configured() -> bool:
    """`True` quando `OLLAMA_API_KEY` está definida e o chat pode chamar o modelo."""
    return config.api_key() is not None


def stream_response(messages: list[Message], snapshot: str) -> Iterator[str]:
    """Gera a resposta do modelo em pedaços de texto (streaming).

    `messages` é o histórico completo, terminando na mensagem mais recente do
    usuário; `snapshot` é o resumo textual do dashboard (ver
    `prompts.build_dashboard_snapshot`).

    Guardrails, em camadas: (1) filtro prévio recusa perguntas claramente fora
    do escopo sem chamar o modelo; (2) o system prompt define escopo, tom e a
    recusa padrão; (3) o snapshot limita os números que o modelo conhece.
    """
    last_user_message = messages[-1]["content"] if messages else ""
    if prompts.is_out_of_scope(last_user_message):
        yield prompts.REFUSAL_MESSAGE
        return

    client = Client(host=config.OLLAMA_HOST, headers=_auth_headers())
    system: Message = {"role": "system", "content": prompts.build_system_prompt(snapshot)}
    stream = client.chat(
        model=config.OLLAMA_MODEL,
        messages=[system, *messages],
        stream=True,
    )
    for chunk in stream:
        content = chunk.message.content
        if content:
            yield content


def _auth_headers() -> dict[str, str] | None:
    key = config.api_key()
    # `is_configured` é checado pela UI antes de chamar; se ainda assim faltar
    # a chave, deixamos o cliente falhar com erro claro no log do servidor.
    return {"Authorization": f"Bearer {key}"} if key else None
