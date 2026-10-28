"""macOS 专属规则（H13）。每条对应已归档的公开事故。"""

RULES_MACOS: dict[str, tuple[str, str, str]] = {
    # H13：macOS 家目录特殊目录（Desktop/Documents/Downloads/Library/
    # Movies/Music/Pictures/Public）是 Finder、Time Machine、iCloud、
    # 各类应用的挂载点级依赖 —— superuser#1925324（删 ~/Downloads 后
    # iCloud/备份链路坏掉）、macrumors#1192684（sudo rm 家目录废纸篓
    # 连带 Mail/日历数据重置）都是删这些目录引发的连锁事故。
    "H13_MACOS_HOME_SPECIAL": (
        "block",
        "目标是 macOS 家目录特殊目录（Desktop/Documents/Downloads/Library 等），"
        "删除会破坏 Finder/Time Machine/iCloud/应用数据链路",
        "superuser#1925324, macrumors#1192684",
    ),
}
