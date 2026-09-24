from collections.abc import Iterator

import pytest
from streamlit.testing.v1 import AppTest

from iel_hackathon.chat import model, ui


def _app() -> None:
    from iel_hackathon.chat import render_chat

    render_chat()


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_function(_app).run()


def _open(at: AppTest) -> AppTest:
    return at.button(key="chat_fab").click().run()


def _send(at: AppTest, text: str) -> AppTest:
    return at.chat_input(key="chat_input").set_value(text).run()


def _button_keys(at: AppTest) -> list[str]:
    return [button.key for button in at.button]


def _captions(at: AppTest) -> list[str]:
    return [caption.value for caption in at.caption]


def test_stub_streams_reply_in_multiple_chunks():
    chunks = list(model.stream_response([{"role": "user", "content": "Olá"}]))

    assert len(chunks) > 1
    assert "".join(chunks) == model.STUB_REPLY


def test_starts_closed_showing_only_floating_button(at):
    assert _button_keys(at) == ["chat_fab"]
    assert len(at.chat_input) == 0


def test_floating_button_opens_empty_panel(at):
    _open(at)

    assert "chat_fab" not in _button_keys(at)
    assert len(at.chat_input) == 1
    assert len(at.chat_message) == 0
    assert ui.EMPTY_STATE in _captions(at)


def test_sending_message_shows_it_and_streamed_reply(at):
    _open(at)
    _send(at, "Olá")

    assert [message.name for message in at.chat_message] == ["user", "assistant"]
    assert at.chat_message[0].markdown[0].value == "Olá"
    assert at.chat_message[1].markdown[0].value == model.STUB_REPLY
    assert ui.EMPTY_STATE not in _captions(at)
    assert at.session_state.chat_history == [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": model.STUB_REPLY},
    ]


def test_model_receives_full_history_including_new_message(at, monkeypatch):
    def fake_stream(messages: list[model.Message]) -> Iterator[str]:
        yield f"{len(messages)} mensagens; última: {messages[-1]['content']}"

    monkeypatch.setattr(model, "stream_response", fake_stream)
    _open(at)
    _send(at, "primeira")
    _send(at, "segunda")

    assert len(at.chat_message) == 4
    assert at.chat_message[3].markdown[0].value == "3 mensagens; última: segunda"


def test_close_hides_panel_and_keeps_history(at):
    _open(at)
    _send(at, "Olá")
    at.button(key="chat_close").click().run()

    assert _button_keys(at) == ["chat_fab"]
    assert len(at.chat_input) == 0

    _open(at)

    assert len(at.chat_message) == 2


def test_model_error_shows_message_and_keeps_only_user_turn(at, monkeypatch):
    def failing_stream(messages: list[model.Message]) -> Iterator[str]:
        raise ConnectionError("ollama fora do ar")
        yield

    monkeypatch.setattr(model, "stream_response", failing_stream)
    _open(at)
    _send(at, "Olá")

    assert [error.value for error in at.error] == [ui.ERROR_MESSAGE]
    assert len(at.exception) == 0
    assert at.session_state.chat_history == [{"role": "user", "content": "Olá"}]


def test_css_has_no_less_than_sign():
    # O sanitizador do frontend do Streamlit descarta o <style> inteiro se o CSS contiver "<".
    assert "<" not in ui._CSS_PATH.read_text(encoding="utf-8")
