from collections.abc import Iterator
from typing import Literal, TypedDict

from ollama import Client

from . import config, prompts


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


def is_configured() -> bool:
    return config.api_key() is not None


def stream_response(messages: list[Message], snapshot: str) -> Iterator[str]:
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
    return {"Authorization": f"Bearer {key}"} if key else None
