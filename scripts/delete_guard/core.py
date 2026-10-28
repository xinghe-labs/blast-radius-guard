"""Platform-neutral judging core: tokenizer, intent extraction, disk probing.

Split from windows-delete-guard 0.1.0 guard.py; rule tables live in the
rules/ subpackage, host differences in platform.py. Chinese user-facing
text is preserved verbatim from the original module.
"""

from __future__ import annotations

import ntpath
import os
import re
from dataclasses import dataclass, field

from .paths import (
    DELETE_VERBS_POSIX,
    DELETE_VERBS_PS,
    DELETE_VERBS_WIN,
    MOVE_VERBS,
    PRIVILEGE_ESCALATORS,
    RECURSIVE_LONG,
    RECURSIVE_SHORT,
    FORCE_LONG,
    FORCE_SHORT,
    SHELL_LAUNCHERS,
    _CMD_FLAG_RE,
    _REPARSE_ATTR,
    has_cjk,
    human_bytes,
    is_ancestor_of_cwd,
    is_drive_root,
    glob_base_dir,
    is_wsl_windows_mount,
    macos_home_special,
    posix_system_prefix,
)
from .platform import host_name, is_wsl, unknowns_for_host
from .rules import RULES, VERDICT_ORDER

# cmd 多字母 flag（/MIR /PURGE /E /S /XD 等）。排除单字母白名单已覆盖的，
# 避免与 _CMD_FLAG_RE 语义重叠；/mnt、/usr 这类以元音开头的常见目录前缀
# 仍可能被误收 —— 但 is_flag_token 仅在删除/移动动词之后消费，且误收
# flag 只是把 flag 从 targets 里排除（不改变爆炸半径），方向是安全的。
_CMD_LONG_FLAG_RE = re.compile(r"^/[A-Za-z]{1,8}$")

# 大小写不敏感宿主：Windows（NTFS）与 macOS（APFS/HFS+ 默认不敏感）。
# Linux 通常敏感，但挂载的 Windows/macOS 卷除外 —— 后者声明为 unknown。
_CASE_INSENSITIVE_HOSTS = ("windows", "macos")


def case_insensitive_host() -> bool:
    """当前宿主是否大小写不敏感。

    刻意做成函数而非模块常量：导入时求值会让 macOS 的 POSIX 逐级核对
    分支在本机永久不可测，也让测试无法模拟其他宿主。
    """
    return host_name() in _CASE_INSENSITIVE_HOSTS


@dataclass
class Token:
    value: str
    quoted: bool
    quote_char: str | None = None


@dataclass
class ParsedCommand:
    tokens: list[Token]
    ambiguous: bool
    ambiguous_reason: str | None = None
    shell_layers: list[str] = field(default_factory=list)


@dataclass
class Hazard:
    code: str
    severity: str
    why: str
    evidence: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "why": self.why,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass
class BlastRadius:
    target: str
    exists: bool = False
    is_dir: bool = False
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    reparse_points: int = 0
    truncated: bool = False
    unreadable: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "exists": self.exists,
            "is_dir": self.is_dir,
            "files": self.files,
            "dirs": self.dirs,
            "bytes": self.bytes,
            "bytes_human": human_bytes(self.bytes),
            "reparse_points": self.reparse_points,
            "truncated": self.truncated,
            "unreadable": self.unreadable,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# 命令解析
# ---------------------------------------------------------------------------


def tokenize(command: str) -> ParsedCommand:
    """最小 shell 分词器。

    只做一件事：判断「能不能无歧义地认出目标」。认不出就报 ambiguous——
    这是刻意的，因为真实事故里，目标恰恰是在引号层间被悄悄改写的。
    """
    tokens: list[Token] = []
    buf: list[str] = []
    quoted = False
    quote_char: str | None = None
    i = 0
    n = len(command)

    def flush() -> None:
        nonlocal buf, quoted, quote_char
        if buf or quoted:
            tokens.append(Token("".join(buf), quoted, quote_char))
        buf = []
        quoted = False
        quote_char = None

    while i < n:
        ch = command[i]

        if quote_char is None and ch in "\"'":
            # 进入引号：如果前面已经有内容（非空且未加引号），视为同 token 内嵌引号
            if buf and not quoted:
                # 形如 D:\a"b c" —— 引号嵌在未加引号 token 中，属于歧义温床
                pass
            quote_char = ch
            quoted = True
            i += 1
            continue

        if quote_char is not None:
            if ch == "\\" and quote_char == '"' and i + 1 < n and command[i + 1] in "\"\\":
                # 反斜杠转义引号：这是最危险的一种，层间会二次解释
                buf.append(command[i + 1])
                i += 2
                continue
            if ch == quote_char:
                quote_char = None
                i += 1
                # 引号闭合后如果紧跟非空白，继续积累（相邻拼接）
                if i < n and command[i] not in " \t":
                    quoted = True
                    continue
                flush()
                continue
            buf.append(ch)
            i += 1
            continue

        if ch in " \t\n\r":
            flush()
            i += 1
            continue

        if ch == "\\" and i + 1 < n and command[i + 1] in "\"' ":
            buf.append(command[i + 1])
            i += 2
            continue

        buf.append(ch)
        quoted = False
        i += 1

    if quote_char is not None:
        return ParsedCommand(
            tokens=tokens,
            ambiguous=True,
            ambiguous_reason=f"引号未闭合（{quote_char}）",
        )

    flush()

    ambiguous = False
    reason = None

    text = command
    # 引号层间转义：同时出现 shell 启动器与转义引号，是 H1 的温床
    layers = detect_shell_layers(tokens)
    if len(layers) >= 2 and '\\"' in text:
        ambiguous = True
        reason = "多层 shell 链中出现转义引号，目标参数会在层间被重新解释"

    return ParsedCommand(tokens=tokens, ambiguous=ambiguous, ambiguous_reason=reason, shell_layers=layers)


def unwrap_launcher_text(command: str, tokens: list[Token]) -> tuple[str | None, list[str]]:
    """若命令形如 `cmd /c "..."` / `powershell -Command "..."` / `wsl rm ...`，
    提取内层命令文本。返回 (内层文本, 经过的层)；提取不出返回 (None, layers)。
    """
    if not tokens:
        return None, []
    first = tokens[0].value.lower().removesuffix(".exe")
    if first not in SHELL_LAUNCHERS:
        return None, []
    layers = [first]
    inner_idx = None
    for i, t in enumerate(tokens[1:], start=1):
        lv = t.value.lower()
        if lv in {"/c", "/k", "-c", "-command", "--command", "--", "-e"}:
            inner_idx = i + 1
            break
    if inner_idx is None:
        for i, t in enumerate(tokens[1:], start=1):
            if not is_flag_token(t.value):
                inner_idx = i
                break
    if inner_idx is None or inner_idx >= len(tokens):
        return None, layers

    rest = tokens[inner_idx:]
    return " ".join(t.value for t in rest), layers


def detect_shell_layers(tokens: list[Token]) -> list[str]:
    layers = []
    for tok in tokens:
        base = ntpath.basename(tok.value.lower()).removesuffix(".exe")
        if base in SHELL_LAUNCHERS:
            layers.append(base)
    return layers


def is_flag_token(v: str, cmd_verb: bool = False) -> bool:
    """判断一个 token 是选项而不是路径目标。

    这里必须保守：误把路径当选项 → 漏判爆炸半径；误把选项当路径 → 噪声。
    `/mnt/d`、`/usr/bin` 这类不会被判成选项。

    cmd_verb：当前命令的动词是否属于 cmd 系（rd/del/robocopy/xcopy/move）。
    多字母 cmd flag（/MIR /E /PURGE）只在该语境下成立 —— POSIX 删除动词的
    /usr /etc 是真实路径，绝不能当 flag 剔除。作为参数显式传递而非函数
    属性：属性会在并发判定（线程池跑 tool_call）时产生跨调用竞态。
    """
    if v.startswith(("./", "../")):
        return False
    if v.startswith("-") and not re.match(r"^-\d", v):
        return True
    if _CMD_FLAG_RE.match(v):
        return True
    if _CMD_LONG_FLAG_RE.match(v) and cmd_verb:
        return True
    return False


@dataclass
class Intent:
    verb: str | None
    recursive: bool
    force: bool
    targets: list[str]
    is_delete: bool
    is_move: bool
    wildcard: bool
    escalated: bool


def extract_intent(parsed: ParsedCommand) -> Intent:
    toks = [t.value for t in parsed.tokens]
    lower = [t.lower() for t in toks]

    verb = None
    verb_index = -1
    all_delete = DELETE_VERBS_WIN | DELETE_VERBS_PS | DELETE_VERBS_POSIX
    for idx, t in enumerate(lower):
        base = ntpath.basename(t).removesuffix(".exe")
        if base in all_delete or t in all_delete:
            verb = base
            verb_index = idx
            break

    is_move = False
    if verb is None:
        for idx, t in enumerate(lower):
            base = ntpath.basename(t).removesuffix(".exe")
            if base in MOVE_VERBS or t in MOVE_VERBS:
                verb = base
                verb_index = idx
                is_move = True
                break

    # cmd 系动词认得多字母 /FLAG（/MIR /E）；POSIX 动词不认
    cmd_verb = verb in {"rd", "del", "robocopy", "xcopy", "move"}

    # 提权判定（H10）：删除动词之前出现 sudo/doas/su
    escalated = False
    if verb_index > 0:
        escalated = any(t in PRIVILEGE_ESCALATORS for t in lower[:verb_index])

    # 选项拆解：既要认 `-recursive` 这种长选项，也要认 `-rf` 这种合写短选项。
    recursive = False
    force = False
    for tok in lower:
        # 工具特定镜像/删除语义（先于通用解析）：
        #   robocopy /MIR —— 镜像复制：目标中源里没有的文件会被删除
        #   rsync --delete —— 使目标与源严格一致：多余文件删除
        if tok in {"/mir", "/mirror"}:
            recursive = True
            force = True
        if tok == "--delete":
            recursive = True
            force = True
        if tok in {"/purge", "--prune-empty-dirs"}:
            force = True
        if tok in {f.lower() for f in RECURSIVE_LONG}:
            recursive = True
        elif tok in RECURSIVE_LONG:
            recursive = True
        elif tok.startswith("-") and not tok.startswith("--"):
            body = tok.lstrip("-")
            letters = set(body)
            if letters & RECURSIVE_SHORT or body.lower() == "recursive":
                recursive = True
            if letters & FORCE_SHORT or body.lower() in {"force", "yes"}:
                force = True
        elif tok in FORCE_LONG or tok.lower() in FORCE_LONG:
            force = True
        elif _CMD_FLAG_RE.match(tok):
            letter = tok[1]
            if letter in RECURSIVE_SHORT:
                recursive = True
            if letter in FORCE_SHORT:
                force = True

    targets: list[str] = []
    wildcard = False
    if verb_index >= 0:
        for tok in parsed.tokens[verb_index + 1 :]:
            v = tok.value
            if not v:
                continue
            if is_flag_token(v, cmd_verb):
                continue
            targets.append(v)
            if any(c in v for c in "*?"):
                wildcard = True

    return Intent(
        verb=verb,
        recursive=recursive,
        force=force,
        targets=targets,
        is_delete=(verb in all_delete),
        is_move=is_move,
        wildcard=wildcard,
        escalated=escalated,
    )


# ---------------------------------------------------------------------------
# 路径判定
# ---------------------------------------------------------------------------


def case_collision(path: str, windows_layout: bool | None = None) -> str | None:
    """若路径的大小写与磁盘上的实际条目不一致但确实能解析到，返回实际路径。

    NTFS/APFS 大小写不敏感 —— 这正是 D:\\CampusconnECT 删掉
    D:\\CampusConnect 的原因（claude-code#60442）。

    windows_layout 为 None 时按当前宿主推断，仅用于测试显式指定布局。
    """
    if not path or not case_insensitive_host():
        return None
    if windows_layout is None:
        windows_layout = os.name == "nt"
    # 逐级比对大小写：Windows 走盘符/反斜杠布局，macOS 走 POSIX 布局
    if windows_layout:
        drive, tail = ntpath.splitdrive(path)
        segments = [s for s in tail.replace("/", "\\").split("\\") if s]
        cur = drive + "\\" if drive else ""
        root = cur or "."
    else:
        segments = [s for s in path.replace("\\", "/").split("/") if s]
        cur = ""
        root = "/"
    for seg in segments:
        try:
            entries = os.listdir(cur or root)
        except OSError:
            return None
        match = next((e for e in entries if e == seg), None)
        if match is None:
            ci = next((e for e in entries if e.lower() == seg.lower()), None)
            if ci is not None:
                return os.path.join(cur or root, ci)
            return None
        cur = os.path.join(cur, match)
    return None


def walk_blast_radius(path: str, max_entries: int = 20000) -> BlastRadius:
    br = BlastRadius(target=path)
    if not os.path.exists(path):
        br.note = "目标不存在（若命令仍会执行，说明路径在别处被改写过）"
        return br
    br.exists = True
    br.is_dir = os.path.isdir(path)

    if not br.is_dir:
        try:
            br.files = 1
            br.bytes = os.lstat(path).st_size
        except OSError:
            br.unreadable += 1
        return br

    stack = [path]
    seen = 0
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries:
                        br.truncated = True
                        stack.clear()
                        break
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        br.unreadable += 1
                        continue
                    if _is_reparse(entry, st):
                        # 链接单独计数：它是穿透风险本体，不算普通文件
                        br.reparse_points += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        br.dirs += 1
                        stack.append(entry.path)
                    else:
                        br.files += 1
                        br.bytes += st.st_size
        except OSError:
            br.unreadable += 1

    from .platform import host_name

    if br.reparse_points and host_name() != "windows":
        br.note = (
            "在非 Windows 宿主上检测到疑似链接；NTFS junction 的 reparse 属性"
            "在 WSL/9p 下可能不可见，结论仅供参考"
        )
    return br


def _is_reparse(entry: os.DirEntry, st: os.stat_result) -> bool:
    if entry.is_symlink():
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & _REPARSE_ATTR:
        return True
    return False


def is_mount_point(path: str) -> bool:
    """Linux H12：目标是否为挂载点（/proc/mounts + os.path.ismount 双核对）。"""
    if not os.path.isabs(path.replace("\\", "/")) and not os.path.exists(path):
        return False
    try:
        if os.path.ismount(path):
            return True
        # ismount 对某些 FUSE/NFS 挂载可能漏报，补一份 /proc/mounts 交叉核对
        if os.name != "nt" and os.path.exists("/proc/mounts"):
            real = os.path.realpath(path)
            with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
                for line in f:
                    fields = line.split()
                    if len(fields) >= 2:
                        mp = fields[1].replace("\\040", " ").replace("\\011", "\t")
                        if mp == real or mp == path:
                            return True
    except OSError:
        return False
    return False


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------


def judge_command(
    command: str,
    cwd: str | None = None,
    wsl_context: bool | None = None,
    privileged_context: bool | None = None,
) -> dict:
    """wsl_context：外层命令是否经由 wsl 启动器进入。递归判定内层命令时
    必须继承（wsl rm -rf /mnt/... 的内层没有 wsl 字样，但语义上就是
    跨文件系统删除）。None 表示按宿主是否为 WSL 自行判定。

    privileged_context：外层是否带提权（sudo/su/doas）。跨层时必须继承：
    `sudo bash -c "rm ..."` 的内层没有 sudo 字样，但删除就是以 root 跑的。
    """
    if "\x00" in command:
        # NUL 字节无法被任何 shell 执行，但能让下游 os.* 抛
        # ValueError(embedded null byte) 使判定链崩溃 —— hook/扩展层
        # fail-open 放行。显式拒绝而不是崩溃（fail-closed 的正确形态）。
        return _result(
            [Hazard(
                code="H0_AMBIGUOUS",
                severity="block",
                why="命令含 NUL 字节，无法被任何 shell 无歧义执行",
                evidence="posix/execve NUL semantics",
            )],
            [], [],
        )
    cwd = cwd or os.getcwd()
    parsed = tokenize(command)
    hazards: list[Hazard] = []
    unknowns: list[str] = []

    seen: set[tuple[str, str]] = set()

    def add(code: str, detail: str = "") -> None:
        if (code, detail) in seen:
            return
        seen.add((code, detail))
        sev, why, ev = RULES[code]
        hazards.append(Hazard(code=code, severity=sev, why=why, evidence=ev, detail=detail))

    if parsed.ambiguous:
        add("H0_AMBIGUOUS", parsed.ambiguous_reason or "")
        return _result(hazards, [], unknowns)

    # 跨层执行：提取内层命令文本，递归判定，危险按层级累加。
    inner_text, layers = unwrap_launcher_text(command, parsed.tokens)
    if layers:
        if inner_text is None:
            add("H0_AMBIGUOUS", f"经 {layers[0]} 跳转的命令无法无歧义地提取内层目标")
            return _result(hazards, [], unknowns)
        if any(
            (" " in t.value or has_cjk(t.value)) and t.quoted for t in parsed.tokens
        ):
            add(
                "H1_QUOTE_CHAIN",
                f"目标带引号且含空格/CJK，经 {' -> '.join(layers)} 跳转时"
                "参数会在层间被重新解释",
            )
        lower_layers = [l.lower() for l in layers]
        inner_wsl = (
            wsl_context
            if wsl_context is not None
            else "wsl" in lower_layers
        )
        inner_priv = (
            privileged_context
            if privileged_context is not None
            else any(l in PRIVILEGE_ESCALATORS for l in lower_layers)
        )
        return _merge_inner(
            hazards,
            unknowns,
            judge_command(inner_text, cwd, inner_wsl, inner_priv),
            layers,
        )

    intent = extract_intent(parsed)

    # 一次额外 shell 跳转就是一次重新解释的机会。
    # 宿主本身那层不算：纯 `rm -rf ./build` 不该被这条规则打。
    if parsed.shell_layers and (intent.is_delete or intent.is_move):
        risky_chars = any((" " in t or has_cjk(t)) for t in intent.targets)
        has_quote = any(t.quoted for t in parsed.tokens)
        if risky_chars and has_quote:
            add(
                "H1_QUOTE_CHAIN",
                f"经 {' -> '.join(parsed.shell_layers)} 多一跳；"
                f"目标含空格/CJK 且带引号：{intent.targets}",
            )

    if not intent.targets and (intent.is_delete or intent.is_move):
        add("H0_AMBIGUOUS", "识别到破坏性动词但未解析出任何目标")

    # H10 提权删除：动词前有提权词，或外层继承来的提权语境
    if privileged_context is None:
        privileged_context = intent.escalated
    if privileged_context and (intent.is_delete or intent.is_move):
        add(
            "H10_SUDO_DELETE",
            f"提权（{intent.verb} 前有 sudo/doas/su）执行 {intent.verb}",
        )

    # H6 只在 WSL 语境下成立：宿主本身是 WSL，或命令经 wsl 启动器跳转。
    # 原生 Linux 上 /mnt 下可能是任意普通挂载，交由 H12 按真实挂载表判定。
    if wsl_context is None:
        wsl_context = is_wsl() or "wsl" in [
            l.lower() for l in parsed.shell_layers
        ]

    radii: list[BlastRadius] = []
    for target in intent.targets:
        radii.append(walk_blast_radius(target))

        if is_drive_root(target):
            add("H2_DRIVE_ROOT", f"目标 {target!r} 是卷根")

        real = case_collision(target)
        if real and os.path.normcase(real) != os.path.normcase(target):
            add("H3_CASE_COLLISION", f"{target!r} 实际指向已存在的 {real!r}")

        br = radii[-1]
        if br.reparse_points and intent.recursive:
            add(
                "H4_REPARSE_TRAVERSAL",
                f"{target!r} 子树内有 {br.reparse_points} 个链接，递归删除会穿透",
            )

        if has_cjk(target):
            add("H5_CJK_SILENT_FAIL", f"目标含 CJK：{target!r}")

        if wsl_context and is_wsl_windows_mount(target):
            add("H6_WSL_CROSS_FS", f"目标在 Windows 挂载点：{target!r}")

        if is_ancestor_of_cwd(target, cwd):
            add("H7_ANCESTOR_OF_CWD", f"{target!r} 是 cwd {cwd!r} 的祖先或本身")

        if intent.wildcard and intent.recursive:
            add("H8_GLOB_RECURSIVE", f"递归 + 通配符：{target!r}")
            # glob 爆炸半径预判（Steam 2015：rm -rf "$STEAMROOT/"* -> /*）：
            # 命中范围在执行前无法静态确定，必须按前缀可确定性分档。
            base = glob_base_dir(target)
            if base is None:
                pass  # 非通配目标，不适用
            elif base == "":
                add(
                    "H0_AMBIGUOUS",
                    f"{target!r} 的通配符无可确定前缀（变量可能为空/相对根），"
                    "展开范围完全未知 —— Steam 2015 事故形态",
                )
            else:
                # 前缀本身命中卷根或系统前缀：展开必然波及
                if is_drive_root(base):
                    add("H2_DRIVE_ROOT", f"通配目标 {target!r} 的前缀 {base!r} 是卷根")
                sysp = posix_system_prefix(base)
                if sysp:
                    add("H11_SYSTEM_PREFIX", f"通配目标 {target!r} 的前缀命中 {sysp}")

        mirror_semantics = intent.verb in {"robocopy", "rsync"} and intent.force
        if (
            (intent.is_delete or mirror_semantics)
            and intent.force
            and intent.recursive
        ):
            add(
                "H9_PERMANENT_DELETE",
                f"{intent.verb} {'镜像同步' if mirror_semantics else '递归强制删除'}"
                "会删除目标侧多余文件，不进回收站",
            )

        # 目标含未展开的 shell/cmd 变量：真实路径执行前不可知
        # （Steam 2015：$STEAMROOT 为空，rd 落到上层）
        if "$" in target or "%" in target:
            add(
                "H0_AMBIGUOUS",
                f"目标 {target!r} 含未展开变量，真实路径在执行前不可知",
            )

        # H11 系统关键前缀（含变量退化形态，如空变量后剩余的 /*）
        sys_prefix = posix_system_prefix(target)
        if sys_prefix and intent.recursive:
            add("H11_SYSTEM_PREFIX", f"{target!r} 命中系统前缀 {sys_prefix}")

        # H12 挂载点
        if intent.recursive and is_mount_point(target):
            add("H12_MOUNT_POINT", f"{target!r} 是挂载点，删除作用于整个卷")

        # H13 macOS 家目录特殊目录
        special = macos_home_special(target)
        if special:
            add("H13_MACOS_HOME_SPECIAL", f"{target!r} 命中 macOS 家目录特殊目录 {special}")

    unknowns.extend(unknowns_for_host())
    if any(br.truncated for br in radii):
        unknowns.append("爆炸半径统计已达上限，实际文件数更多")

    return _result(hazards, radii, unknowns)


def judge_path(path: str, cwd: str | None = None) -> dict:
    cwd = cwd or os.getcwd()
    hazards: list[Hazard] = []
    unknowns: list[str] = []

    seen: set[tuple[str, str]] = set()

    def add(code: str, detail: str = "") -> None:
        if (code, detail) in seen:
            return
        seen.add((code, detail))
        sev, why, ev = RULES[code]
        hazards.append(Hazard(code=code, severity=sev, why=why, evidence=ev, detail=detail))

    if is_drive_root(path):
        add("H2_DRIVE_ROOT", f"{path!r} 是卷根")
    real = case_collision(path)
    if real and os.path.normcase(real) != os.path.normcase(path):
        add("H3_CASE_COLLISION", f"{path!r} 实际指向已存在的 {real!r}")
    if has_cjk(path):
        add("H5_CJK_SILENT_FAIL", f"路径含 CJK：{path!r}")
    if is_wsl() and is_wsl_windows_mount(path):
        add("H6_WSL_CROSS_FS", f"路径在 Windows 挂载点：{path!r}")
    if is_ancestor_of_cwd(path, cwd):
        add("H7_ANCESTOR_OF_CWD", f"{path!r} 是 cwd {cwd!r} 的祖先或本身")

    br = walk_blast_radius(path)
    if br.reparse_points:
        add("H4_REPARSE_TRAVERSAL", f"{path!r} 子树内有 {br.reparse_points} 个链接")

    sys_prefix = posix_system_prefix(path)
    if sys_prefix:
        add("H11_SYSTEM_PREFIX", f"{path!r} 命中系统前缀 {sys_prefix}")
    if is_mount_point(path):
        add("H12_MOUNT_POINT", f"{path!r} 是挂载点")
    special = macos_home_special(path)
    if special:
        add("H13_MACOS_HOME_SPECIAL", f"{path!r} 命中 macOS 家目录特殊目录 {special}")

    unknowns.extend(unknowns_for_host())

    return _result(hazards, [br], unknowns)


def _merge_inner(
    outer_hazards: list[Hazard],
    outer_unknowns: list[str],
    inner: dict,
    layers: list[str],
) -> dict:
    """合并外层危险与内层判定结果。内层 verdict 升级外层。"""
    merged = dict(inner)
    inner_hazards = [Hazard(**h) for h in inner.get("hazards", [])]
    all_hazards = outer_hazards + inner_hazards
    verdict = inner.get("verdict", "allow")
    for h in outer_hazards:
        if VERDICT_ORDER[h.severity] > VERDICT_ORDER[verdict]:
            verdict = h.severity
    merged["hazards"] = [h.as_dict() for h in all_hazards]
    merged["verdict"] = verdict
    merged["unknowns"] = list(
        dict.fromkeys(list(inner.get("unknowns", [])) + outer_unknowns)
    )
    # 跨层命令的爆炸半径以内层为准（外层只是转发）
    if not merged.get("blast_radius"):
        merged["blast_radius"] = []
    return merged


def _result(hazards: list[Hazard], radii: list[BlastRadius], unknowns: list[str]) -> dict:
    verdict = "allow"
    for h in hazards:
        if VERDICT_ORDER[h.severity] > VERDICT_ORDER[verdict]:
            verdict = h.severity
    return {
        "verdict": verdict,
        "hazards": [h.as_dict() for h in hazards],
        "blast_radius": [r.as_dict() for r in radii],
        "unknowns": unknowns,
    }
