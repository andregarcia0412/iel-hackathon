from collections.abc import Iterator

import pytest
from streamlit.testing.v1 import AppTest

from iel_hackathon.chat import model, prompts, ui

FAKE_REPLY = "OK"


def _app() -> None:
    from iel_hackathon.chat import render_chat

    render_chat()


@pytest.fixture(autouse=True)
def fake_configured_model(monkeypatch):
    monkeypatch.setattr(model, "is_configured", lambda: True)

    def default_stream(messages: list[model.Message], snapshot: str) -> Iterator[str]:
        yield FAKE_REPLY

    monkeypatch.setattr(model, "stream_response", default_stream)


@pytest.fixture
def at() -> AppTest:
    return AppTest.from_function(_app).run()


def _open(at: AppTest) -> AppTest:
    return at.button(key="chat_fab").click().run()


def _send(at: AppTest, text: str) -> AppTest:
    return at.chat_input(key="chat_input").set_value(text).run()


def _button_keys(at: AppTest) -> list[str]:
    return [button.key for button in at.button]


def _closing_style_injected(at: AppTest) -> bool:
    return any("@keyframes chat-panel-close" in element.proto.body for element in at.get("html"))


def _captions(at: AppTest) -> list[str]:
    return [caption.value for caption in at.caption]


def test_starts_closed_showing_only_floating_button(at):
    assert _button_keys(at) == ["chat_fab"]
    assert len(at.chat_input) == 0


def test_floating_button_opens_empty_panel(at):
    _open(at)

    assert "chat_fab" not in _button_keys(at)
    assert len(at.chat_input) == 1
    assert len(at.chat_message) == 0
    assert ui.EMPTY_STATE in _captions(at)


def test_empty_panel_shows_suggestion_chips(at):
    _open(at)

    suggestion_labels = {button.label for button in at.button}
    for suggestion in prompts.SUGGESTIONS:
        assert suggestion in suggestion_labels


def test_clicking_suggestion_sends_it_as_user_message(at):
    _open(at)
    at.button(key="chat_suggestion_0").click().run()

    assert [message.name for message in at.chat_message] == ["user", "assistant"]
    assert at.chat_message[0].markdown[0].value == prompts.SUGGESTIONS[0]
    assert at.chat_message[1].markdown[0].value == FAKE_REPLY
    assert at.session_state.chat_history == [
        {"role": "user", "content": prompts.SUGGESTIONS[0]},
        {"role": "assistant", "content": FAKE_REPLY},
    ]
    assert "chat_suggestion_0" not in _button_keys(at)


def test_sending_message_shows_it_and_streamed_reply(at):
    _open(at)
    _send(at, "Olá")

    assert [message.name for message in at.chat_message] == ["user", "assistant"]
    assert at.chat_message[0].markdown[0].value == "Olá"
    assert at.chat_message[1].markdown[0].value == FAKE_REPLY
    assert ui.EMPTY_STATE not in _captions(at)
    assert at.session_state.chat_history == [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": FAKE_REPLY},
    ]


def test_model_receives_full_history_including_new_message(at, monkeypatch):
    def fake_stream(messages: list[model.Message], snapshot: str) -> Iterator[str]:
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


def test_closing_animation_runs_only_right_after_closing(at):
    assert not _closing_style_injected(at)

    _open(at)
    assert not _closing_style_injected(at)

    at.button(key="chat_close").click().run()
    assert _closing_style_injected(at)

    at.run()
    assert not _closing_style_injected(at)


def test_model_error_shows_message_and_keeps_only_user_turn(at, monkeypatch):
    def failing_stream(messages: list[model.Message], snapshot: str) -> Iterator[str]:
        raise ConnectionError("ollama fora do ar")
        yield

    monkeypatch.setattr(model, "stream_response", failing_stream)
    _open(at)
    _send(at, "Olá")

    assert [error.value for error in at.error] == [ui.ERROR_MESSAGE]
    assert len(at.exception) == 0
    assert at.session_state.chat_history == [{"role": "user", "content": "Olá"}]


def test_missing_api_key_shows_friendly_message(at, monkeypatch):
    monkeypatch.setattr(model, "is_configured", lambda: False)
    _open(at)
    _send(at, "Olá")

    assert [error.value for error in at.error] == [ui.NOT_CONFIGURED_MESSAGE]
    assert at.session_state.chat_history == [{"role": "user", "content": "Olá"}]


@pytest.mark.parametrize("css_path", [ui._CSS_PATH, ui._CLOSING_CSS_PATH])
def test_css_has_no_less_than_sign(css_path):
    assert "<" not in css_path.read_text(encoding="utf-8")
