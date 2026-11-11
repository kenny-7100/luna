"""Local project tools."""

import argparse
from pathlib import Path

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "docs/README.md",
    "docs/context.md",
    "docs/memory.md",
    "docs/architecture.md",
    "docs/automation.md",
    "docs/workspaces.md",
    "workspaces/README.md",
)
REQUIRED_DIRECTORIES = ("src/luna", "docs/knowledge", "docs/assets", "workspaces", ".local")


def check_project(root: Path) -> list[str]:
    """Return missing or empty scaffold entries without changing the filesystem."""
    issues = []
    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            issues.append(f"缺少文件或内容为空：{name}")
    for name in REQUIRED_DIRECTORIES:
        if not (root / name).is_dir():
            issues.append(f"缺少目录：{name}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Luna 本地工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor", help="检查本地项目结构（不连接外部服务）")
    doctor.add_argument("--root", type=Path, default=Path.cwd(), help="项目根目录，默认当前目录")
    observe = subparsers.add_parser("observe", help="本机工作切片采集")
    observe.add_argument("action", choices=["start", "status", "stop", "report"])
    observe.add_argument("--root", type=Path, default=Path.cwd())
    observe.add_argument("--interval", type=float, default=2)
    observe.add_argument("--visual-interval", type=float, default=4)
    args = parser.parse_args(argv)
    if args.command == "observe":
        from luna.observation import main as observation_main

        return observation_main(
            [
                args.action,
                "--root",
                str(args.root),
                "--interval",
                str(args.interval),
                "--visual-interval",
                str(args.visual_interval),
            ]
        )
    try:
        issues = check_project(args.root.resolve())
    except (OSError, UnicodeError) as error:
        print(f"检查失败：{error}")
        return 1
    if issues:
        for issue in issues:
            print(f"FAIL {issue}")
        return 1
    print("OK 本地项目结构完整。此检查不验证观察器运行或外部集成状态。")
    return 0
