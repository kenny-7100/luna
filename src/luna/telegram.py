"""Telegram user-account tools for Codex. Read calls do not mark messages as read."""

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path


def store(root: Path) -> Path:
    directory = root / ".local" / "telegram"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def private_json(path: Path, data: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def peer(value: str) -> int | str:
    return int(value) if value.lstrip("-").isdigit() else value


def since(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError("时间必须包含时区，例如 2026-11-11T22:00:00+08:00")
    return result.astimezone(UTC)


def draft_digest(chat_id: int, text: str, reply_to: int | None) -> str:
    payload = json.dumps([chat_id, text, reply_to], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def check_draft(data: dict) -> None:
    if not isinstance(data.get("chat_id"), int) or not isinstance(data.get("text"), str):
        raise ValueError("草稿缺少有效的接收方或正文")
    if not data["text"].strip() or len(data["text"]) > 4096:
        raise ValueError("仅支持 1–4096 字符的文本消息")
    if data.get("sent_at"):
        raise ValueError("该草稿已有发送记录，拒绝重复发送")
    if data.get("send_attempted_at"):
        raise ValueError("该草稿已有发送尝试，请先在 Telegram 核实结果，禁止直接重试")
    if data.get("digest") != draft_digest(data["chat_id"], data["text"], data.get("reply_to")):
        raise ValueError("草稿已变更，请重新生成并审阅")


def authorize_send(data: dict) -> None:
    check_draft(data)
    if not sys.stdin.isatty():
        raise ValueError("发送需要交互终端审阅；没有自动确认开关")
    print(f"接收方：{data['chat_title']} ({data['chat_id']})")
    print(f"回复消息：{data.get('reply_to')}\n正文：\n{data['text']}")
    answer = input(f"确认上述接收方和正文后，输入 send {data['digest']}：")
    if answer.strip() != f"send {data['digest']}":
        raise ValueError("未确认，未发送")


def make_client(root: Path):
    try:
        from telethon import TelegramClient
    except ImportError as error:
        raise RuntimeError("请先运行 uv sync --extra telegram") from error
    directory = store(root)
    credentials = json.loads((directory / "credentials.json").read_text())
    return TelegramClient(
        str(directory / "account"),
        credentials["api_id"],
        credentials["api_hash"],
        flood_sleep_threshold=0,
        request_retries=0,
    )


@asynccontextmanager
async def connected(root: Path):
    client = make_client(root)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("尚未登录；请在本机终端运行 uv run luna tg login")
        yield client
    finally:
        await client.disconnect()


async def login(root: Path) -> None:
    if not sys.stdin.isatty():
        raise ValueError("请在本机交互终端登录，验证码和密码不要发到聊天中")
    directory = store(root)
    credentials_path = directory / "credentials.json"
    if not credentials_path.exists():
        print("从 https://my.telegram.org 的 API development tools 获取自己的 API 配置。")
        api_id = int(input("API ID："))
        api_hash = getpass.getpass("API hash（隐藏输入）：").strip()
        if api_id <= 0 or len(api_hash) != 32 or any(c not in "0123456789abcdef" for c in api_hash):
            raise ValueError("API ID 或 API hash 格式不正确")
        private_json(credentials_path, {"api_id": api_id, "api_hash": api_hash})
    client = make_client(root)
    try:
        await client.start(
            phone=lambda: input("Telegram 手机号（含国家码）：").strip(),
            code_callback=lambda: getpass.getpass("Telegram 登录验证码（隐藏输入）："),
            password=lambda: getpass.getpass("Telegram 两步验证密码（隐藏输入）："),
        )
        me = await client.get_me()
        print(json.dumps({"authorized": True, "user_id": me.id}, ensure_ascii=False))
    finally:
        await client.disconnect()


def message_record(message, chat_id: int) -> dict:
    return {
        "chat_id": chat_id,
        "message_id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "edited_at": message.edit_date.isoformat() if message.edit_date else None,
        "sender_id": message.sender_id,
        "outgoing": message.out,
        "reply_to": message.reply_to_msg_id,
        "topic_id": (
            getattr(message.reply_to, "reply_to_top_id", None)
            or (
                message.reply_to_msg_id if getattr(message.reply_to, "forum_topic", False) else None
            )
        )
        if getattr(message, "reply_to", None)
        else None,
        "text": message.raw_text or "",
        "has_media": message.media is not None,
    }


async def execute(args) -> None:
    if args.action == "login":
        await login(args.root)
        return
    if args.action == "status":
        if not (store(args.root) / "credentials.json").exists():
            print(json.dumps({"configured": False, "authorized": False}))
            return
        async with connected(args.root) as client:
            me = await client.get_me()
            print(json.dumps({"configured": True, "authorized": True, "user_id": me.id}))
        return
    from telethon import utils

    if args.action == "send":
        data = json.loads(args.draft.read_text(encoding="utf-8"))
        authorize_send(data)
        async with connected(args.root) as client:
            entity = await client.get_entity(data["chat_id"])
            title = utils.get_display_name(entity)
            if title != data["chat_title"]:
                raise ValueError("接收方名称已变化，请重新生成草稿并审阅")
            data["send_attempted_at"] = datetime.now(UTC).isoformat()
            private_json(args.draft, data)
            message = await client.send_message(
                entity,
                data["text"],
                reply_to=data.get("reply_to"),
                parse_mode=None,
                link_preview=False,
            )
            data.update(sent_at=datetime.now(UTC).isoformat(), sent_message_id=message.id)
            private_json(args.draft, data)
            print(json.dumps({"sent": True, "chat_id": data["chat_id"], "message_id": message.id}))
        return
    async with connected(args.root) as client:
        if args.action == "dialogs":
            result = []
            async for dialog in client.iter_dialogs(limit=args.limit):
                result.append(
                    {
                        "chat_id": dialog.id,
                        "title": dialog.name,
                        "unread_count": dialog.unread_count,
                        "latest_message_at": dialog.date.isoformat() if dialog.date else None,
                        "forum": bool(getattr(dialog.entity, "forum", False)),
                    }
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        entity = await client.get_entity(peer(args.chat))
        chat_id = utils.get_peer_id(entity)
        if args.action == "topics":
            from telethon import functions

            result = await client(
                functions.messages.GetForumTopicsRequest(
                    peer=entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=args.limit,
                )
            )
            print(
                json.dumps(
                    {
                        "chat_id": chat_id,
                        "topics": [
                            {
                                "topic_id": topic.id,
                                "title": getattr(topic, "title", None),
                                "latest_message_id": getattr(topic, "top_message", None),
                            }
                            for topic in result.topics
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        if args.action == "draft":
            text = args.text_file.read_text(encoding="utf-8")
            data = {
                "chat_id": chat_id,
                "chat_title": utils.get_display_name(entity),
                "text": text,
                "reply_to": args.reply_to,
                "created_at": datetime.now(UTC).isoformat(),
                "digest": draft_digest(chat_id, text, args.reply_to),
            }
            check_draft(data)
            directory = store(args.root) / "drafts"
            directory.mkdir(exist_ok=True, mode=0o700)
            target = directory / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
            private_json(target, data)
            print(target)
            return
        records = []
        scanned = 0
        async for message in client.iter_messages(
            entity,
            limit=args.limit,
            min_id=args.since_id,
            search=(args.search or None) if args.topic is None else None,
            reply_to=args.topic,
        ):
            scanned += 1
            if args.after and message.date and message.date < args.after:
                break
            if (
                args.topic is not None
                and args.search.casefold() not in (message.raw_text or "").casefold()
            ):
                continue
            records.append(message_record(message, chat_id))
        print(
            json.dumps(
                {
                    "observed_at": datetime.now(UTC).isoformat(),
                    "chat_id": chat_id,
                    "title": utils.get_display_name(entity),
                    "order": "newest_first",
                    "limit": args.limit,
                    "scanned": scanned,
                    "may_have_more": scanned == args.limit,
                    "search_mode": "local_within_topic_limit"
                    if args.topic is not None
                    else "server",
                    "messages": records,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram 账号读取、草稿与经确认的发送")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("login", help="仅在本机交互终端登录")
    actions.add_parser("status", help="检查配置与账号授权状态")
    dialogs = actions.add_parser("dialogs", help="列出最近会话，不标记已读")
    dialogs.add_argument("--limit", type=int, default=30)
    topics = actions.add_parser("topics", help="列出论坛群的话题 ID 与名称")
    topics.add_argument("--chat", required=True)
    topics.add_argument("--limit", type=int, default=50)
    messages = actions.add_parser("messages", help="读取或搜索消息，最新在前，不标记已读")
    messages.add_argument("--chat", required=True)
    messages.add_argument("--limit", type=int, default=50)
    messages.add_argument("--since-id", type=int, default=0)
    messages.add_argument("--after", type=since)
    messages.add_argument("--search", default="")
    messages.add_argument("--topic", type=int, help="论坛话题根消息 ID")
    draft = actions.add_parser("draft", help="解析接收方并保存本地草稿，不发送")
    draft.add_argument("--chat", required=True)
    draft.add_argument("--text-file", type=Path, required=True)
    draft.add_argument("--reply-to", type=int, help="回复消息或论坛话题根消息 ID")
    send = actions.add_parser("send", help="交互审阅接收方与正文后发送；无自动确认参数")
    send.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args(argv)
    if hasattr(args, "limit") and not 1 <= args.limit <= 200:
        parser.error("limit 必须为 1–200")
    args.root = args.root.resolve()
    os.umask(0o077)
    try:
        asyncio.run(execute(args))
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(f"Telegram 操作失败：{error}", file=sys.stderr)
        return 1
    except Exception as error:
        # RPC errors can include private request details; report type only, without retrying.
        print(f"Telegram 请求失败：{type(error).__name__}；未自动重试", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
