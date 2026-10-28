"""Linux 专属规则（H11-H12）。每条对应已归档的公开事故。"""

RULES_LINUX: dict[str, tuple[str, str, str]] = {
    # H11：删除目标是关键系统前缀 —— Steam 2015 年脚本缺陷
    # `rm -rf "$STEAMROOT/"*` 因 STEAMROOT 为空退化为 `rm -rf /*`，
    # 无数用户整盘 /usr 被删。变量退化 + 系统前缀的组合至今仍是
    # AI agent 命令的经典失败模式（Amazon Q 恶意注入事件也瞄准这里）。
    "H11_SYSTEM_PREFIX": (
        "block",
        "目标是系统关键前缀（/usr /etc /bin /sbin /lib /boot /var /proc /sys /dev），"
        "递归删除会破坏操作系统本体",
        "steam-for-linux 2015 (rm -rf \"$STEAMROOT/\"* -> /*), dev.ua/amazon-q",
    ),
    # H12：目标是挂载点 —— 误把移动硬盘/NAS/备份卷的挂载目录当作普通
    # 空目录删除或 rsync --delete 清空，是 Linux 运维最经典的整卷数据
    # 消失事故（rsync 邮件列表、个人博客多人复述）。
    "H12_MOUNT_POINT": (
        "block",
        "目标是挂载点：删除的不是这个空目录，而是挂载进来的整个卷的内容；"
        "卸载前的 rm -rf 会直接作用于卷内全部数据",
        "rsync mailing list 2010#025330, blog.theodorc.no 2022",
    ),
}
