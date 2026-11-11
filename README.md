# Luna

个人分身的工作基地：把协作中的知识、经验、方法和工具沉淀为可持续维护的项目，再逐步连接 Telegram、Linear、GitHub、开发环境和线上项目。

当前已提供协作约定、文档与知识库、工作区规范、Python 包与本地检查命令。持续运行服务和外部账号集成尚未实现。

## 开始使用

需要 [uv](https://docs.astral.sh/uv/)。项目使用 Python 3.12，uv 可在需要时安装对应解释器。

```sh
uv sync --locked
uv run luna doctor
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests
```

`doctor` 只检查本地项目结构，不连接外部服务；失败时返回非零退出码。在其他目录可运行 `uv run --project /path/to/luna luna doctor --root /path/to/luna`。

## 项目布局

```text
AGENTS.md           高频协作规则，供后续会话读取
docs/               稳定入口、方法和架构说明
  knowledge/        平铺、版本化的长期知识与维护日志
  assets/           知识附件（平铺，按主题命名）
src/luna/           可复用 Python 工具和命令入口
tests/              有实际行为需要验证时添加的测试
scripts/            少量命令封装
workspaces/         本地任务工作区，任务内容默认不入 Git
.local/             本地状态、缓存和日志，不入 Git
```

从 [文档导航](docs/README.md) 开始了解协作方式。以后可以直接在本目录发起需求；助手应按约定自动检索和沉淀有价值的知识。项目文件承接长期记忆，下一次会话需要读取它们才能恢复上下文。

## 技术选择

Python 3.12+ 承载核心逻辑，uv 管理解释器、依赖和运行，Ruff 负责检查与格式化，标准库 unittest 用于行为测试。初始运行时代码只依赖标准库；Markdown + Git 管理知识与版本。未来有持久任务状态时再引入 SQLite，有实际 UI 或 Node 工具链需求时再引入 TypeScript/tsx。详见 [技术决策](docs/architecture.md)。
