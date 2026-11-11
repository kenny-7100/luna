"""Verify Telegram boundaries without logging in or sending real messages."""

import argparse
import importlib.util
import json
import stat
import unittest
from contextlib import asynccontextmanager, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from luna.telegram import authorize_send, check_draft, draft_digest, execute, private_json, since


def draft():
    return {
        "chat_id": 1,
        "chat_title": "Work",
        "text": "reviewed text",
        "reply_to": None,
        "digest": draft_digest(1, "reviewed text", None),
    }


class TelegramBoundaryTests(unittest.TestCase):
    def test_send_rejects_noninteractive_execution(self):
        with patch("luna.telegram.sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "交互终端"):
                authorize_send(draft())

    def test_send_requires_matching_confirmation(self):
        with patch("luna.telegram.sys.stdin.isatty", return_value=True):
            with patch("builtins.input", return_value="yes"), redirect_stdout(StringIO()):
                with self.assertRaisesRegex(ValueError, "未确认"):
                    authorize_send(draft())

    def test_changed_or_attempted_draft_is_rejected(self):
        data = draft()
        data["text"] = "changed text"
        with self.assertRaisesRegex(ValueError, "变更"):
            check_draft(data)
        data = draft()
        data["send_attempted_at"] = "2026-11-11T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "发送尝试"):
            check_draft(data)

    def test_dates_require_explicit_timezone(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            since("2026-11-11T22:00:00")
        self.assertEqual(since("2026-11-11T22:00:00+08:00").hour, 14)

    def test_private_files_are_owner_only(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "draft.json"
            private_json(path, draft())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


@unittest.skipUnless(importlib.util.find_spec("telethon"), "requires telegram extra")
class TelegramRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_messages_pass_filters_and_do_not_send_or_mark_read(self):
        from telethon.tl.types import User

        entity = User(id=1, first_name="Work")
        calls = []

        async def messages(*args, **kwargs):
            calls.append(kwargs)
            yield SimpleNamespace(
                id=42,
                date=datetime(2026, 11, 11, 14, tzinfo=UTC),
                edit_date=None,
                sender_id=2,
                out=False,
                reply_to_msg_id=10,
                raw_text="verified",
                media=None,
            )

        client = SimpleNamespace(get_entity=AsyncMock(return_value=entity), iter_messages=messages)

        @asynccontextmanager
        async def connection(root):
            yield client

        args = SimpleNamespace(
            action="messages",
            root=Path.cwd(),
            chat="1",
            limit=20,
            since_id=30,
            search="verified",
            topic=10,
            after=since("2026-11-11T00:00:00+08:00"),
        )
        output = StringIO()
        with patch("luna.telegram.connected", connection), redirect_stdout(output):
            await execute(args)
        result = json.loads(output.getvalue())
        self.assertEqual(result["messages"][0]["message_id"], 42)
        self.assertEqual(calls, [{"limit": 20, "min_id": 30, "search": None, "reply_to": 10}])
        self.assertEqual(result["search_mode"], "local_within_topic_limit")

    async def test_unknown_send_result_prevents_direct_retry(self):
        from telethon.tl.types import User

        client = SimpleNamespace(
            get_entity=AsyncMock(return_value=User(id=1, first_name="Work")),
            send_message=AsyncMock(side_effect=TimeoutError("unknown result")),
        )

        @asynccontextmanager
        async def connection(root):
            yield client

        with TemporaryDirectory() as directory:
            path = Path(directory) / "draft.json"
            private_json(path, draft())
            args = SimpleNamespace(action="send", root=Path(directory), draft=path)
            with patch("luna.telegram.connected", connection):
                with patch("luna.telegram.authorize_send"):
                    with self.assertRaises(TimeoutError):
                        await execute(args)
            with self.assertRaisesRegex(ValueError, "发送尝试"):
                check_draft(json.loads(path.read_text()))
            self.assertEqual(client.send_message.await_count, 1)


if __name__ == "__main__":
    unittest.main()
