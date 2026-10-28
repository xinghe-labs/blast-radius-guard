"""命令行入口：command / path 两种模式，--json 机器可读输出。

退出码：0 = allow，1 = warn，2 = block。与 0.1.0 的 guard.py 保持一致。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable

from .core import judge_command, judge_path


def render_text(result: dict) -> str:
    icon = {"allow": "ALLOW", "warn": "WARN ", "block": "BLOCK"}
    lines = [f"[{icon[result['verdict']]}]"]

    if result["hazards"]:
        lines.append("")
        for h in result["hazards"]:
            lines.append(f"  {h['severity'].upper():5} {h['code']}")
            lines.append(f"        {h['why']}")
            if h["detail"]:
                lines.append(f"        实测：{h['detail']}")
            lines.append(f"        依据：{h['evidence']}")

    if result["blast_radius"]:
        lines.append("")
        lines.append("  爆炸半径：")
        for r in result["blast_radius"]:
            lines.append(
                f"    {r['target']}  ->  {r['files']} 文件 / {r['dirs']} 目录 / "
                f"{r['bytes_human']}，链接 {r['reparse_points']} 个"
            )
            if r["truncated"]:
                lines.append("    （统计已截断，实际更大）")
            if r["note"]:
                lines.append(f"    注：{r['note']}")

    if result["unknowns"]:
        lines.append("")
        lines.append("  未能验证（不构成安全保证）：")
        for u in result["unknowns"]:
            lines.append(f"    - {u}")

    if result["verdict"] == "block":
        lines.append("")
        lines.append("  拒绝执行。先改写成单层、显式、绝对路径的命令，或改用隔离区 rename。")

    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="guard.py",
        description="判定破坏性命令/路径在当前平台上的真实爆炸半径",
    )
    sub = ap.add_subparsers(dest="mode", required=True)

    c = sub.add_parser("command", help="分析一条 shell 命令")
    c.add_argument("text", help="命令原文")
    c.add_argument("--cwd", default=None)
    c.add_argument("--json", action="store_true")

    p = sub.add_parser("path", help="分析一个目标路径")
    p.add_argument("path")
    p.add_argument("--cwd", default=None)
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.mode == "command":
        result = judge_command(args.text, args.cwd)
    else:
        result = judge_path(args.path, args.cwd)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))

    return 0 if result["verdict"] == "allow" else (1 if result["verdict"] == "warn" else 2)


if __name__ == "__main__":
    sys.exit(main())
