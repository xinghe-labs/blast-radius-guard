"""跨平台通用规则：无论宿主是什么系统都适用。"""

# code -> (severity, 一句话理由, 证据出处)
# severity: block = 必须拒绝, warn = 需人工确认, info = 记录
RULES_COMMON: dict[str, tuple[str, str, str]] = {
    "H0_AMBIGUOUS": (
        "block",
        "引号/转义无法无歧义地解析出目标，拒绝执行",
        "claude-code#56603, cursor-forum#163626",
    ),
    "H1_QUOTE_CHAIN": (
        "block",
        "多层 shell 传递（如 PowerShell->cmd）+ 引号 + 空格/非ASCII 路径，"
        "参数会在某一层被重新解释，目标可能退化成卷根",
        "claude-code#56603, cursor-forum#163626, cursor-forum#174156",
    ),
    "H7_ANCESTOR_OF_CWD": (
        "block",
        "目标是当前工作目录的祖先，删除会连正在使用的工程一起带走",
        "claude-code#60442",
    ),
    "H8_GLOB_RECURSIVE": (
        "warn",
        "递归删除叠加通配符，爆炸半径取决于运行时目录内容而非命令文本",
        "codex#14487",
    ),
    "H9_PERMANENT_DELETE": (
        "warn",
        "永久删除而非移入隔离区，删除通常不进回收站/废纸篓",
        "codex#14487, cursor-forum#174156",
    ),
    # H15：覆盖型销毁 —— 动词是 mv/cp/echo（非删除），但效果是既有数据
    # 被无声覆盖。Gemini CLI 级联覆盖 + PowerShell 编码清空 + vscode 覆写
    # 三个独立事故源（INCIDENTS.md 候选 2/12/14）。
    "H15_OVERWRITE": (
        "warn",
        "覆盖型销毁：批量 mv/cp 落入已存在目录、> 重定向清空非空文件 ——"
        "既有数据被无声覆盖，且常见于 mkdir 失败后 agent 继续执行的场景",
        "Agent Incident Ledger (Gemini CLI 2025-07), linux.do#2402993 "
        "(PS 编码清空), microsoft/vscode#298393",
    ),
    # H14：云/容器/ORM/SQL 工具的破坏性动词 —— 动词不在 shell 删除词表里，
    # 但破坏力等同 rm -rf（PocketOS 9 秒清掉生产库+备份；terraform destroy
    # 毁掉 2.5 年生产设施）。完整动词表与事故背书见 INCIDENTS.md 候选 7-10。
    "H14_CLOUD_TOOLING": (
        "warn",
        "云/容器/ORM 工具的破坏性动词（delete volume/destroy/migrate reset/"
        "downgrade/DROP），作用于云资源或持久数据， Shell 删除词表覆盖不到",
        "AID-2026-0106 (PocketOS), claude-code#26913/#27063/#41357/#14944, "
        "prisma blog 2026-07",
    ),
    # H10：sudo 提权 + 删除，爆炸半径受 root 权限放大（Steam 2015、
    # macOS sudo rm -R / .Spotlight-v100 空格笔误等历史事故的共同放大器）
    "H10_SUDO_DELETE": (
        "block",
        "提权执行删除：root 权限会绕过几乎所有文件系统保护，"
        "目标解析错误时没有任何回收余地",
        "macrumors#1176135 (sudo rm -R / .Spotlight-v100), steam-for-linux 2015",
    ),
}
