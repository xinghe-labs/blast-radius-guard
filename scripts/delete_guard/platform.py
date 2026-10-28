"""宿主平台探测与跨平台 unknown 声明。

原则 2（无法验证就声明 unknown，不默认安全）的集中实现：
判定器跑在与目标平台不同的宿主上时，把验证不到的语义明确说出来。
"""

from __future__ import annotations

import platform as _platform


def host_name() -> str:
    """返回 'windows' / 'linux' / 'macos' / 'unknown'。"""
    s = sys_name()
    if s == "Windows":
        return "windows"
    if s == "Darwin":
        return "macos"
    if s == "Linux":
        return "linux"
    return "unknown"


def sys_name() -> str:
    return _platform.system()


def is_wsl() -> bool:
    if sys_name() != "Linux":
        return False
    if "microsoft" in _platform.release().lower():
        return True
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def unknowns_for_host(host: str | None = None) -> list[str]:
    """当前宿主验证不到的语义清单。绝不默认安全。"""
    host = host or host_name()
    out: list[str] = []
    if host != "windows":
        out.append(
            "当前不是 Windows 宿主：junction / 大小写碰撞 / 盘符语义未能真机验证，"
            "请在真实 Windows 上复跑本判定再决定是否执行"
        )
    if host != "linux":
        out.append(
            "当前不是 Linux 宿主：/proc/mounts 挂载点核对与系统前缀语义"
            "未能真机验证"
        )
    if host != "macos":
        out.append(
            "当前不是 macOS 宿主：/Users 特殊目录语义与大小写不敏感卷行为"
            "未能真机验证"
        )
    return out


def platform_rules(host: str | None = None):
    """当前宿主适用的规则表与平台专属 code（委托给 rules 包）。"""
    from .rules import platform_rules as _pr

    return _pr(host or host_name())
