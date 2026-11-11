# Telegram 读取与经授权发送

## 当前状态

已实现 Python CLI，基于可选依赖 Telethon 使用用户自己的 Telegram 账号：列出会话和论坛话题、读取消息、关键词搜索、按时间/消息 ID 获取增量、生成草稿、交互审阅后发送文本。供 Codex 调用，不另建 Agent。

2026-11-11 已验证本机 Telegram 桌面画面可读，但辅助功能没有提供完整消息正文。桌面方式是当前可用的补充入口，不代表消息 API 已接通。API 尚未配置登录，真实账号的查询和发送未完成端到端验证；测试使用模拟客户端，未发送测试消息。

## 一次性本机登录

用户在项目目录的终端运行：

```sh
uv sync --extra telegram
uv run --extra telegram luna tg login
```

首次提示输入自己的 API ID 和 API hash，从 [Telegram API development tools](https://my.telegram.org) 获取，再按提示输入手机号、验证码及启用时的两步验证密码。敏感输入在终端隐藏；不要把验证码、API hash 或密码粘贴到 Codex 聊天。工具不提取已登录桌面客户端的会话密钥。

配置与登录会话保存到 `.local/telegram/`，目录权限 0700、工具写入的敏感文件 0600，受 Git 忽略。会话文件具有账号访问能力，按凭据保管；不上传、不复制进知识库。可在 Telegram 的设备管理中撤销该会话。

## 读取

```sh
uv run --extra telegram luna tg status
uv run --extra telegram luna tg dialogs --limit 30
uv run --extra telegram luna tg topics --chat CHAT_ID
uv run --extra telegram luna tg messages --chat CHAT_ID --limit 50
uv run --extra telegram luna tg messages --chat CHAT_ID --search '关键词'
uv run --extra telegram luna tg messages --chat CHAT_ID --after '2026-11-11T22:00:00+08:00'
uv run --extra telegram luna tg messages --chat CHAT_ID --since-id LAST_MESSAGE_ID
uv run --extra telegram luna tg messages --chat CHAT_ID --topic TOPIC_ID --limit 100
```

用实际会话 ID、话题根消息 ID 替换占位符；会话名称只用于展示，避免同名误认。查询返回 JSON，消息最新在前，包含发送/编辑时间、消息 ID、发送者 ID、回复/话题信息及正文。会话查询不主动标记已读、不发送输入状态、不下载附件；仅标注是否有媒体。范围限于账号可访问的云端聊天，不支持端到端加密的 Secret Chat。

每次查询限制 1–200 条，`may_have_more` 表示可能截断，不等于已读完。话题内关键词搜索在最多 `limit` 条话题消息中本地过滤，结果标注 `search_mode`，不能据空结果断言全话题没有该信息。其他关键词查询使用服务端搜索。暂不提供常驻消息监听或完整历史同步。

按当前问题读取相关会话及话题，再看最近的回复、编辑与结果反馈；保留消息 ID 与时间作为结论依据。用户的明确纠正优先于旧画面。不能仅凭没看到后续就将问题列为未解决，也不要把“已验证”擅自扩展成所有流程均已通过。

## 草稿与发送

先在 `.local/telegram/` 中准备 UTF-8 正文文件，再生成不发送的草稿：

```sh
uv run --extra telegram luna tg draft --chat CHAT_ID --text-file .local/telegram/reply.txt
# 回复某条消息或论坛话题时加 --reply-to MESSAGE_ID
uv run --extra telegram luna tg send --draft .local/telegram/drafts/ACTUAL_DRAFT.json
```

发送命令展示解析后的接收方名称、数字 ID、回复对象和完整正文，需要交互终端输入对应确认短语，无 `--yes` 自动确认开关。正文按纯文本发送，不自动展开链接预览。草稿修改后需重新生成并审阅；接收方改名会阻止发送。

Codex 仅在用户已允许具体接收方、内容或明确发送范围后执行发送，不把本功能的开发授权视为消息发送授权。用户明确批准后可按该批准执行确认步骤，不重复要求同一授权；若内容、接收方或范围变化则重新核对。

发送前持久化尝试记录；已发送或已尝试的草稿禁止直接重发。请求超时等情况先到 Telegram 核实是否送达，不能自动重试。发送后成功回执记录消息 ID，实际送达情况仍以 Telegram 为准。

## 验证与限制

自动化测试覆盖非交互/错误确认拦截、草稿变更、发送结果不明时阻止重发、查询参数、时间时区及文件权限。登录完成后先只读验证目标会话、话题和近期消息；需要发送时再按用户的真实授权验证，不为了测试给他人发消息。

参考：[Telethon 登录](https://docs.telethon.dev/en/stable/basic/signing-in.html)、[Telegram 获取 API ID](https://core.telegram.org/api/obtaining_api_id)。
