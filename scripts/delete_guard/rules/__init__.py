"""规则表：按平台拆分模块，各自维护 hazard code -> (severity, why, evidence)。

项目原则：每条规则对应一个已归档的公开事故。没有编号的规则不许进来。
"""

from __future__ import annotations

from .common import RULES_COMMON
from .linux import RULES_LINUX
from .macos import RULES_MACOS
from .windows import RULES_WINDOWS

VERDICT_ORDER = {"allow": 0, "warn": 1, "block": 2}

ALL_RULES: dict[str, tuple[str, str, str]] = {}
ALL_RULES.update(RULES_COMMON)
ALL_RULES.update(RULES_WINDOWS)
ALL_RULES.update(RULES_LINUX)
ALL_RULES.update(RULES_MACOS)

RULES = ALL_RULES

# 同一 code 只允许出现在一个模块里，重复定义直接暴露问题
assert len(ALL_RULES) == len(RULES_COMMON) + len(RULES_WINDOWS) + len(RULES_LINUX) + len(RULES_MACOS), (
    "rules/ 子模块间存在重复的 hazard code"
)


def platform_rules(host: str) -> tuple[dict[str, tuple[str, str, str]], list[str]]:
    """返回 (该宿主适用的规则表, 平台专属 code 列表)。

    common 规则全平台适用；windows/linux/macos 专属规则在非本宿主上
    仍保留在规则表里（跨平台命令可能携带别平台的目标路径，如
    `wsl rm -rf /mnt/d/data`），但对应平台的事实核验能力不同。
    """
    if host == "windows":
        return {**RULES_COMMON, **RULES_WINDOWS}, list(RULES_WINDOWS)
    if host == "linux":
        return {**RULES_COMMON, **RULES_LINUX}, list(RULES_LINUX)
    if host == "macos":
        return {**RULES_COMMON, **RULES_MACOS}, list(RULES_MACOS)
    # 未知宿主：全量规则 + 无平台核验
    return dict(ALL_RULES), []
