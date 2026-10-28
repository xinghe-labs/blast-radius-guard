"""Windows 专属规则（H2-H6）。每条对应已归档的公开事故。"""

RULES_WINDOWS: dict[str, tuple[str, str, str]] = {
    "H2_DRIVE_ROOT": (
        "block",
        "目标是盘符根目录或文件系统根，递归删除的爆炸半径是整个卷",
        "cursor-forum#163626",
    ),
    "H3_CASE_COLLISION": (
        "block",
        "路径大小写与实际不符但 NTFS 大小写不敏感会解析到真实目录，"
        "看起来删的是别的东西",
        "claude-code#60442",
    ),
    "H4_REPARSE_TRAVERSAL": (
        "block",
        "子树含 junction / 符号链接，递归删除会穿透到链接目标（树外）",
        "claude-code v2.1.205 fix, qiita/kai_kou",
    ),
    "H5_CJK_SILENT_FAIL": (
        "warn",
        "路径含 CJK，经 cmd/PowerShell 传递时可能静默产出空结果，"
        "agent 会把它误判成「文件不存在」并基于错误前提继续行动",
        "claude-code#68343",
    ),
    "H6_WSL_CROSS_FS": (
        "warn",
        "目标是 /mnt/<盘> 下的 Windows 文件系统，WSL 侧权限位不可靠、"
        "删除语义与 ext4 不同",
        "wsl-drvfs",
    ),
}
