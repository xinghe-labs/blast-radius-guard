#!/usr/bin/env python3
"""Claude Code PreToolUse hook — 在 Bash/PowerShell 工具执行前调用 guard.py。

安装（Claude Code 的 settings.json，~/.claude/settings.json）：

{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/blast-radius-guard/hooks/pretooluse.py"

Python 探测顺序：BRG_PYTHON 环境变量 > python3 > python > py -3；
全部缺失时 fail-open 放行。
          }
        ]
      }
    ]
  }
}

协议：从 stdin 读 {"tool_name": "Bash", "tool_input": {"command": "..."}}
     退出码 2 = 拦截，stderr 会回给模型作为拒绝原因。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

GUARD_TIMEOUT = 5
RELEVANT_TOOLS = {"Bash", "PowerShell"}

_PY_CACHE: list[str] | None = None


def resolve_python() -> list[str] | None:
    """按序探测可用的 Python 解释器，返回命令前缀。

    Windows 原生通常只有 `python`（`python3` 常是 Microsoft Store 假别名桩）
    或 `py -3` 启动器；WSL/Linux/macOS 通常是 `python3`。
    环境变量 BRG_PYTHON 可强制指定（如 conda 环境）。结果缓存一次。
    """
    global _PY_CACHE
    if _PY_CACHE is not None:
        return _PY_CACHE or None
    env = os.environ.get("BRG_PYTHON")
    if env:
        _PY_CACHE = [env]
        return _PY_CACHE
    for candidate in (["python3"], ["python"], ["py", "-3"]):
        try:
            probe = subprocess.run(
                candidate + ["-c", "pass"],
                capture_output=True, timeout=3,
            )
            if probe.returncode == 0:
                _PY_CACHE = candidate
                return _PY_CACHE
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    _PY_CACHE = []
    return None
QUICK_PREDICATE = (
    "rm ", "rm -", "rmdir", "del ", "erase", "rd ", "unlink", "shred",
    "remove-item", "move-item", " move ", "mv ", "sudo rm", "trash ",
    "rmrf", " find ... -delete",
)


def guard_path() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    p = here / "scripts" / "guard.py"
    return p if p.exists() else None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    if payload.get("tool_name") not in RELEVANT_TOOLS:
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0

    low = command.lower()
    if not any(tok in low for tok in QUICK_PREDICATE):
        return 0

    gp = guard_path()
    if gp is None:
        return 0  # fail-open

    py = resolve_python()
    if py is None:
        return 0  # fail-open：环境里没有可用 Python
    try:
        proc = subprocess.run(
            py + [str(gp), "command", command, "--json"],
            capture_output=True, text=True, timeout=GUARD_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 0  # fail-open

    if proc.returncode != 2:
        return 0  # allow / warn 时放行

    try:
        result = json.loads(proc.stdout)
        reasons = "; ".join(
            f"{h['code']}（依据: {h['evidence']}）" for h in result.get("hazards", [])
        )
    except json.JSONDecodeError:
        reasons = proc.stdout[:400]

    print(
        f"delete-guard 拦截该删除命令：{reasons}。"
        "改写为单层 shell、绝对路径的目标（Windows 用 -LiteralPath）；"
        "或先 rename 进隔离目录观察后再删；"
        "不要把算好的路径管道进 cmd /c 或嵌套引号链。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
