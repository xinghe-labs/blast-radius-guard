"""delete_guard — 破坏性命令的爆炸半径判定核心。

三条设计原则，每条都是被真实事故逼出来的：

1. **不可解析即拒绝。** 引号链断裂（PowerShell -> cmd -> rd）正是 Cursor 整盘被删的
   根因。解析不确定不是边界情况，它就是事故本体。
2. **无法验证就标 unknown，不默认安全。** 在 WSL 上读不到 NTFS reparse point，
   就明说读不到，而不是报告"没有链接"。
3. **每条规则对应一个已归档的公开事故。** 没有编号的规则不许进来。

只用标准库。Python 3.10+。
"""

from .core import (  # noqa: F401
    VERDICT_ORDER,
    BlastRadius,
    Hazard,
    Intent,
    ParsedCommand,
    Token,
    detect_shell_layers,
    extract_intent,
    has_cjk,
    human_bytes,
    is_ancestor_of_cwd,
    is_drive_root,
    is_flag_token,
    is_wsl_windows_mount,
    judge_command,
    judge_path,
    tokenize,
    unwrap_launcher_text,
    walk_blast_radius,
)
from .platform import host_name, platform_rules, unknowns_for_host  # noqa: F401
from .rules import RULES  # noqa: F401

__all__ = [
    "VERDICT_ORDER",
    "BlastRadius",
    "Hazard",
    "Intent",
    "ParsedCommand",
    "Token",
    "RULES",
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
    "platform_rules",
    "tokenize",
    "unknowns_for_host",
    "unwrap_launcher_text",
    "walk_blast_radius",
]
