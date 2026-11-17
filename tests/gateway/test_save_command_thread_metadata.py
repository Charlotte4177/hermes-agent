"""Regression tests for Telegram topic routing on session-save attachments."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform
from gateway.platforms.event import MessageEvent
from gateway.session import SessionSource
from gateway.slash_commands_session import GatewaySessionCommandsMixin


class _DocumentAdapter:
    def __init__(self):
        self.calls = []

    async def send_document(self, **kwargs):
        self.calls.append({
            "chat_id": kwargs["chat_id"],
            "file_name": kwargs["file_name"],
            "metadata": kwargs.get("metadata"),
            "contents": Path(kwargs["file_path"]).read_text(encoding="utf-8"),
        })


@pytest.mark.parametrize(
    ("source", "expected_metadata"),
    [
        pytest.param(
            SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="forum-chat-1",
                chat_type="group",
                thread_id="87",
            ),
            {"thread_id": "87"},
            id="forum-topic",
        ),
        pytest.param(
            SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="private-chat-1",
                chat_type="dm",
                user_id="private-user-1",
                thread_id="42",
            ),
            {
                "thread_id": "42",
                "telegram_dm_topic_reply_fallback": True,
                "direct_messages_topic_id": "42",
                "telegram_reply_to_message_id": "message-17",
            },
            id="private-chat-topic",
        ),
    ],
)
@pytest.mark.asyncio
async def test_save_command_sends_export_in_the_current_telegram_topic(
    source, expected_metadata, monkeypatch
):
    from hermes_cli import session_export

    monkeypatch.setattr(session_export, "load_save_snapshot", lambda *args, **kwargs: {"fixture": True})
    monkeypatch.setattr(session_export, "render_session_for_save", lambda _data, _fmt: "synthetic transcript")

    adapter = _DocumentAdapter()
    runner = SimpleNamespace(
        async_session_store=SimpleNamespace(
            get_or_create_session=AsyncMock(return_value=SimpleNamespace(session_id="fixture-session")),
        ),
        persistence=object(),
        _delivery_adapter_for=lambda _source: adapter,
    )
    event = MessageEvent(text="/save json", source=source, message_id="message-17")

    result = await GatewaySessionCommandsMixin._handle_save_command(runner, event)

    assert result
    assert len(adapter.calls) == 1
    sent = adapter.calls[0]
    assert sent["chat_id"] == source.chat_id
    assert sent["metadata"] == expected_metadata
    assert sent["contents"] == "synthetic transcript"
    assert sent["file_name"].endswith(".json")
