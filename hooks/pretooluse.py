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
            "command": "python3 /path/to/windows-delete-guard/hooks/pretooluse.py"
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
QUICK_PREDICATE = (
    "rm", "rmdir", "del", "erase", "rd ", "unlink", "shred",
    "remove-item", "move-item", " move ", "mv ",
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

    try:
        proc = subprocess.run(
            ["python3", str(gp), "command", command, "--json"],
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
        f"windows-delete-guard 拦截该删除命令：{reasons}。"
        "改写为单层、绝对路径（-LiteralPath）的目标，或先 rename 进隔离目录再删；"
        "不要把算好的路径管道进 cmd /c。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
