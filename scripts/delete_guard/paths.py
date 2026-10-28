"""纯字符串/文件系统路径助手 —— 不依赖本包其他模块，供 core 与 platform 共用。"""

from __future__ import annotations

import ntpath
import os
import re
import stat

# 删除类动词（跨 cmd / PowerShell / POSIX / 各语言运行时）
DELETE_VERBS_WIN = {"del", "erase", "rd", "rmdir"}
DELETE_VERBS_PS = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}
DELETE_VERBS_POSIX = {"rm", "rmdir", "unlink", "shred"}

MOVE_VERBS = {
    "move", "mv", "move-item", "ren", "rename", "rename-item",
    "xcopy", "robocopy",
}

SHELL_LAUNCHERS = {"cmd", "powershell", "pwsh", "bash", "sh", "wsl", "zsh"}

# 递归语义的短选项字母：-r / -rf / -Recurse / /s / /e
RECURSIVE_SHORT = set("rRsSe")
RECURSIVE_LONG = {"--recursive", "-recurse", "--recurse", "-Recurse"}
# 强制/静默语义：-f / -rf / /q / /f / /y
FORCE_SHORT = set("fFqQyY")
FORCE_LONG = {
    "--force", "-force", "--yes", "-yes",
    "/q", "/f", "/y", "/Q", "/F", "/Y",
}

# Linux 系统关键前缀（H11）：递归删除会破坏操作系统本体或全部用户数据。
# 分两组管理命中深度，避免把用户日常工作路径误判成系统目标：
#   OS 关键组：前缀本身或其直接子目录命中（/usr、/usr/bin）——
#     这些是包管理器领地，agent 删它们几乎必然是事故；
#   用户数据组（/home /var /opt /srv /root）：仅前缀本身命中——
#     /home/u/proj 是 Linux 用户的日常工作目录，误拦会让工具被禁用，
#     而 `rm -rf /home`（整目录）仍必须 block。
OS_CRITICAL_PREFIXES = {
    "usr", "etc", "bin", "sbin", "lib", "lib32", "lib64", "libx32",
    "boot", "proc", "sys", "dev",
}
USER_DATA_PREFIXES = {"home", "var", "opt", "srv", "root"}
SYSTEM_PREFIXES = OS_CRITICAL_PREFIXES | USER_DATA_PREFIXES

# 提权动词（H10）
PRIVILEGE_ESCALATORS = {"sudo", "doas", "su"}

# macOS 家目录特殊目录（H13）：Finder / Time Machine / iCloud / 应用依赖
MACOS_HOME_SPECIALS = {
    "Desktop", "Documents", "Downloads", "Library",
    "Movies", "Music", "Pictures", "Public", "Applications",
}

# cmd 的选项形如 /s /q /f /e /r /t /c /k /d —— 单个或两个字母，且没有后续斜杠。
# 刻意收紧：/mnt/d 这类挂载路径不会命中。
_CMD_FLAG_RE = re.compile(r"^/[A-Za-z]{1,2}$")

_REPARSE_ATTR = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_drive_root(path: str) -> bool:
    """卷根判定：盘符根（D:\\、D:/、D:）、POSIX 根 /、WSL 挂载卷根 /mnt/d。"""
    p = path.strip().strip("'\"")
    if not p:
        return False
    if p == "/" or p == "\\":
        return True
    drive, rest = ntpath.splitdrive(p)
    if drive and rest.strip("\\/") == "":
        return True
    if len(p) == 2 and p[1] == ":":
        return True
    # WSL 形态 /mnt/d  /mnt/d/
    norm = p.replace("\\", "/").rstrip("/")
    return norm.startswith("/mnt/") and len(norm) == len("/mnt/") + 1


def is_wsl_windows_mount(path: str) -> bool:
    norm = path.replace("\\", "/").rstrip("/")
    # /mnt/<盘> 本身是卷根（走 H2），只有盘下更深的路径才属于 H6
    return norm.startswith("/mnt/") and len(norm) > len("/mnt/") + 1


def is_windows_style_path(path: str) -> bool:
    """盘符形态或含反斜杠的路径。"""
    p = path.strip().strip("'\"")
    if not p:
        return False
    drive, _ = ntpath.splitdrive(p)
    if drive:
        return True
    return "\\" in p


def is_posix_style_path(path: str) -> bool:
    p = path.strip().strip("'\"")
    return p.startswith("/")


def posix_system_prefix(path: str) -> str | None:
    """若目标命中 Linux 系统关键前缀，返回该前缀（如 /usr），否则 None。

    命中深度按事故画像收紧：Steam 2015 事故（`rm -rf "$STEAMROOT/"*`
    退化为 `rm -rf /*`）打中的是顶层目录本身。OS 关键组允许到直接
    子目录（/usr/bin）；用户数据组（/home 等）只有前缀本身才命中，
    让 /home/u/proj 这类日常工作路径照常放行。
    """
    p = path.strip().strip("'\"")
    if not p.startswith("/"):
        return None
    parts = [seg for seg in p.replace("\\", "/").split("/") if seg]
    if not parts:
        return None
    first = parts[0]
    if first in OS_CRITICAL_PREFIXES and len(parts) <= 2:
        return "/" + first
    if first in USER_DATA_PREFIXES and len(parts) == 1:
        return "/" + first
    return None


def macos_home_special(path: str) -> str | None:
    """若目标形如 /Users/<name>/<特殊目录>，返回该目录名，否则 None。"""
    p = path.strip().strip("'\"")
    if not p.startswith("/Users/"):
        return None
    parts = [seg for seg in p.split("/") if seg]
    # /Users/<name>/<special> —— parts = [Users, name, special]
    if len(parts) >= 3 and parts[2] in MACOS_HOME_SPECIALS:
        return parts[2]
    return None


def has_cjk(s: str) -> bool:
    for ch in s:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x3000 <= cp <= 0x303F
            or 0xFF00 <= cp <= 0xFFEF
            or 0x20000 <= cp <= 0x2FA1F
        ):
            return True
    return False


def is_ancestor_of_cwd(target: str, cwd: str) -> bool:
    try:
        t = os.path.abspath(os.path.expanduser(target))
        c = os.path.abspath(cwd)
    except Exception:
        return False
    if t == c:
        return True
    try:
        return os.path.commonpath([t, c]) == t and t != c
    except ValueError:
        return False


def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size: float = n * 1.0
    for i, unit in enumerate(units):
        if size < 1024 or i == len(units) - 1:
            if i == 0:
                return f"{n} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
