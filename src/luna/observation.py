"""Local macOS observation tools. Captured material never leaves .local/."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def base(root: Path) -> Path:
    return root / ".local" / "observation"


def current(root: Path) -> Path:
    return Path(read_json(base(root) / "current.json")["session"])


def running(state: dict) -> bool:
    pid = state.get("pid")
    if not pid or state.get("status") != "recording":
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def worker(root: Path, session: Path, interval: float, visual_interval: float) -> None:
    state = {
        "status": "recording",
        "pid": os.getpid(),
        "started_at": now(),
        "session": str(session),
        "samples": 0,
        "visual_samples": 0,
        "errors": 0,
        "screenshot_bytes": 0,
        "interval_seconds": interval,
        "visual_interval_seconds": visual_interval,
    }
    state_path = session / "state.json"
    write_json(state_path, state)
    last_visual = -float("inf")
    started = time.monotonic()
    try:
        with (session / "events.jsonl").open("a", encoding="utf-8", buffering=1) as events:
            while not (session / "stop").exists() and time.monotonic() - started < 8 * 3600:
                tick = time.monotonic()
                timestamp = now()
                command = [str(base(root) / "sensor")]
                visual = tick - last_visual >= visual_interval
                directory = session / "frames" / f"{state['samples']:06d}"
                if visual:
                    directory.mkdir(parents=True)
                    command.append(str(directory))
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=25)
                    if result.returncode:
                        raise RuntimeError(result.stderr[:2000])
                    event = json.loads(result.stdout)
                    event["at"] = timestamp
                    event["captured_at"] = now()
                    if visual:
                        event["frame_directory"] = str(directory.relative_to(session))
                        last_visual = tick
                        state["visual_samples"] += 1
                        state["screenshot_bytes"] += sum(
                            p.stat().st_size for p in directory.glob("*.jpg")
                        )
                    state["last_app"] = event.get("app")
                    state["screen_permission"] = event.get("screen_permission")
                    state["accessibility_permission"] = event.get("accessibility_permission")
                    if any("capture_error" in s for s in event.get("screens", [])):
                        state["errors"] += 1
                    state["last_event_at"] = timestamp
                except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
                    event = {"at": timestamp, "error": str(error)}
                    state["errors"] += 1
                events.write(json.dumps(event, ensure_ascii=False) + "\n")
                state["samples"] += 1
                state["heartbeat_at"] = now()
                write_json(state_path, state)
                # Bound storage for this explicitly authorized work slice; no deletion of old data.
                if state["screenshot_bytes"] > 4 * 1024**3:
                    state["stop_reason"] = "4 GiB session storage limit"
                    break
                while time.monotonic() - tick < interval and not (session / "stop").exists():
                    time.sleep(0.2)
    finally:
        state["status"] = "stopped"
        state["stopped_at"] = now()
        state.setdefault(
            "stop_reason", "stop requested" if (session / "stop").exists() else "session ended"
        )
        write_json(state_path, state)


def start(root: Path, interval: float, visual_interval: float) -> int:
    directory = base(root)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "current.json").exists():
        existing = current(root)
        if (existing / "state.json").exists() and running(read_json(existing / "state.json")):
            print("观察器已运行；未重复启动。")
            return 1
    sensor = directory / "sensor"
    if (
        not sensor.exists()
        or sensor.stat().st_mtime < (root / "tools/observe.swift").stat().st_mtime
    ):
        subprocess.run(["swiftc", str(root / "tools/observe.swift"), "-o", str(sensor)], check=True)
    session = directory / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    session.mkdir(mode=0o700)
    write_json(directory / "current.json", {"session": str(session)})
    command = [
        sys.executable,
        "-m",
        "luna.observation",
        "worker",
        "--root",
        str(root),
        "--session",
        str(session),
        "--interval",
        str(interval),
        "--visual-interval",
        str(visual_interval),
    ]
    with (session / "process.log").open("a") as log:
        subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    print(f"本地采集进程已启动；使用 luna observe status 验证采集。\n{session}")
    return 0


def status(root: Path) -> int:
    session = current(root)
    state_path = session / "state.json"
    if not state_path.exists():
        print("启动尚未完成；检查本地 process.log。")
        return 1
    state = read_json(state_path)
    state["process_alive"] = running(state)
    if state.get("heartbeat_at"):
        state["heartbeat_age_seconds"] = round(
            (datetime.now(UTC) - datetime.fromisoformat(state["heartbeat_at"])).total_seconds(), 1
        )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def stop(root: Path) -> int:
    session = current(root)
    (session / "stop").touch()
    print("已请求停止，当前采样完成后退出；记录保留在本地。")
    return 0


def report(root: Path) -> int:
    session = current(root)
    output = session / "timeline.md"
    lines = ["# 工作观察时间线", "", "原始事实供 Codex 阅读，不代表已完成语义理解。", ""]
    with (session / "events.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            lines.extend(
                [
                    f"## {event['at']}",
                    "",
                    f"应用：{event.get('app', 'unknown')}",
                    f"窗口：{event.get('window', '')}",
                    "",
                ]
            )
            if "error" in event:
                lines.append(f"采集错误：{event['error']}")
            lines.extend(event.get("accessibility_text", []))
            for screen in event.get("screens", []):
                lines.extend(["", f"显示器 {screen['display']} OCR：", ""])
                lines.extend(screen.get("text", []))
                if "capture_error" in screen:
                    lines.append(screen["capture_error"])
            lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机工作观察器")
    parser.add_argument("action", choices=["start", "status", "stop", "report", "worker"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--session", type=Path)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--visual-interval", type=float, default=4)
    args = parser.parse_args(argv)
    if args.interval < 1 or args.visual_interval < 2:
        parser.error("采样间隔至少 1 秒，视觉间隔至少 2 秒")
    root = args.root.resolve()
    try:
        if args.action == "worker":
            if args.session is None:
                parser.error("worker 需要 --session")
            worker(root, args.session, args.interval, args.visual_interval)
            return 0
        if args.action == "start":
            return start(root, args.interval, args.visual_interval)
        return {"status": status, "stop": stop, "report": report}[args.action](root)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"观察器操作失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
