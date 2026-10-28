#!/usr/bin/env python3
"""guard.py — 兼容 shim。

0.2.0 起判定引擎拆分为 delete_guard 包（core / platform / rules/*），
本文件保留旧的单文件入口：`python guard.py command ...` 与
`import guard` 的模块级 API 均继续可用。新代码请直接 import delete_guard。

无需 sys.path 操作：以脚本运行时其所在目录（scripts/）自动成为
sys.path[0]；测试与本仓库内调用方均已把 scripts/ 显式加入 sys.path。
"""

from __future__ import annotations

import sys

# noqa/E402 + pyright ignore：本 shim 与 delete_guard/ 同目录，依赖「脚本目录自动进 sys.path」的运行时行为；静态分析器在仓库布局下
# 无法解析同级包，属预期。
from delete_guard import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    BlastRadius,
    Hazard,
    Intent,
    ParsedCommand,
    RULES,
    Token,
    VERDICT_ORDER,
    detect_shell_layers,
    extract_intent,
    has_cjk,
    host_name,
    human_bytes,
    is_ancestor_of_cwd,
    is_drive_root,
    is_flag_token,
    is_wsl_windows_mount,
    judge_command,
    judge_path,
    tokenize,
    unknowns_for_host,
    unwrap_launcher_text,
    walk_blast_radius,
)
from delete_guard.cli import main, render_text  # pyright: ignore[reportMissingImports]

__all__ = [
    "BlastRadius",
    "Hazard",
    "Intent",
    "ParsedCommand",
    "RULES",
    "Token",
    "VERDICT_ORDER",
    "detect_shell_layers",
    "extract_intent",
    "has_cjk",
    "host_name",
    "human_bytes",
    "is_ancestor_of_cwd",
    "is_drive_root",
    "is_flag_token",
    "is_wsl_windows_mount",
    "judge_command",
    "judge_path",
    "render_text",
    "tokenize",
    "unknowns_for_host",
    "unwrap_launcher_text",
    "walk_blast_radius",
]

if __name__ == "__main__":
    sys.exit(main())
