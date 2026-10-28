---
name: blast-radius-guard
description: Use before running ANY destructive file operation (rm -rf, rd /s /q, rmdir /s, Remove-Item -Recurse -Force, del, sudo rm, deleting /usr /etc or any system prefix, deleting a mount point, mv across filesystems) on Windows, Linux, macOS, or WSL, or paths that contain spaces, CJK characters, quotes, drive letters, or /mnt mounts. Also use when the agent itself is about to delete a directory it did not create, when cleaning up before rewriting deliverables, or when a user asks to "清理/删除/清空" anything. Judges the true blast radius, catches NTFS/APFS junction and symlink traversal, case-insensitive path collisions, quote-chain degradation, sudo-escalated deletes, system-prefix wipes, mount-point deletions, and CJK silent failures - the platform-specific data-loss paths that POSIX safety habits do not cover. Converts permanent deletes into quarantine renames. Do not use for files inside a normal git worktree cleanup that the agent just created itself in a single-layer POSIX shell on ext4.
---

# Blast Radius Guard

你可以删错一个文件，但你不该删错一整个卷。这个 skill 存在的原因不是"删除危险"，
而是**删除命令的真实语义和 agent 写出来的命令文本经常不是一回事**。
每一条规则下面都埋着一次真实的数据销毁事故。适用于 Windows、Linux、macOS 与 WSL。

## 它怎么被调用（三层）

| 层 | 机制 | 可靠性 |
|---|---|---|
| ① 手动 CLI | 直接跑 `scripts/guard.py command ...` | 100%，但要自己记得 |
| ② 本 skill | agent 读到本文件后，删除前自觉跑判定器 | 高，但依赖模型自觉 |
| ③ 硬拦截 | 宿主 hook / 扩展在命令**执行前**强制判定 | **100%，不依赖自觉（推荐）** |

安装硬拦截层：

- **pi**：把本仓库目录加入 pi 的 extensions（`package.json` 已含 `pi.extensions` 指向 `src/extension.ts`），扩展自动拦截 bash/powershell 删除命令，block 级直接拒绝并把改写建议回给模型
- **Claude Code**：把 `hooks/pretooluse.py` 挂进 `PreToolUse`（见该文件头部注释）
- **Codex**：无 hook 机制，只有 ② 层

## 铁律（先于一切分析）

1. **不把计算出的路径管道进 `cmd /c`。** 用 PowerShell 原生命令做文件操作
   （`Remove-Item`、`Rename-Item`）。`cmd /c "rd /s /q ..."` 加上含空格或
   Unicode 的路径，曾把引号退化成对整个盘符根的删除（cursor 论坛事故：
   整个 C 盘被删到要重装系统）。
2. **永远不用 `rd /s /q` / `rm -rf` 作为第一步。** 第一步是 rename 进隔离区；
   第二步才是观察期；第三步才轮到真删除。隔离目录默认
   `%USERPROFILE%\.delete-quarantine\<date>\`（POSIX：`~/.delete-quarantine/<date>/`），
   同卷 rename 瞬时完成且可撤销。
3. **路径大小写必须从磁盘上核对，不能凭记忆。** NTFS（Windows）与 APFS/HFS+
   （macOS，默认）大小写不敏感：`rm -rf "D:\CampusconnECT"` 会解析到真实存在的
   `D:\CampusConnect`，一次毁掉九个生产仓库（claude-code#60442）。
4. **CJK 路径的空输出不是"文件不存在"。** PowerShell/WSL2 对 CJK 路径可能
   静默返回空结果（claude-code#68343）。看到空输出先换
   `Get-Item -LiteralPath` 复核，再决定下一步。
5. **递归删除前必须检查子树里的 junction / 符号链接。** Claude Code 官方在
   v2.1.205 修复的就是这个：删 worktree 时穿透嵌套 junction，删到了树外。
6. **不用 sudo/doas 执行删除。** root 权限会绕过几乎所有文件系统保护
   （macrumors#1176135：`sudo rm -R / .Spotlight-v100` 多打一个空格）。
   需要提权清理时，先以普通用户视角跑判定器确认目标。
7. **先 `mount` / `/proc/mounts` 再删目录。** 看起来是"空目录"的可能是挂载点：
   删的是挂载进来的整个卷（rsync --delete 清空备份盘是运维最经典的整卷事故）。
8. **非判定宿主的平台语义不算数。** 在 WSL 里看不到 NTFS reparse 属性、
   在 Linux 上验证不了 APFS 大小写语义。判定结果为"无法验证"时，去目标平台复跑。

## 操作流程

### 第 1 步 —— 执行任何删除/移动前，跑判定器

```bash
python scripts/guard.py command "<你要执行的原命令>"
```

退出码：`0` 允许，`1` 需人工确认，`2` 拒绝。输出里每个 hazard 都带事故编号。
**退出码 2 时，改写命令后重跑，而不是向用户 begged permission 后原样执行**——
工具拦的不是"用户没同意"，是"命令文本表达不了你的意图"。

### 第 2 步 —— 把永久删除降级为隔离 rename

判定为 warn/block 时，第一个动作永远是改写成隔离 rename：

```powershell
# Windows（PowerShell）：
$q = "$env:USERPROFILE\.delete-quarantine\$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force -Path $q | Out-Null
Rename-Item -LiteralPath "D:\bad-old-output" -NewName $q\bad-old-output
```

```bash
# POSIX（Linux/macOS/WSL）：
q=~/.delete-quarantine/$(date +%Y%m%d-%H%M%S)
mkdir -p "$q"
mv -- "/path/bad-old-output" "$q/bad-old-output"
```

`-LiteralPath`（Windows）不解释通配符，这是 CJK/特殊字符路径唯一可靠的选择。
对跨卷移动（rename 会 COPY+DELETE）：先复制到同卷隔离区再删原目录。

### 第 3 步 —— 报告时给出爆炸半径，而不是"删除完成"

用户需要看到：`N 文件 / M 目录 / X GB / K 个链接`，链接数不为零时要显式点名。
`guard.py command ... --json` 直接给出这些数字。超过 20,000 项会截断并声明。

## 什么时候可以直接删

- 目标是**本会话内 agent 自己刚创建**的临时目录，路径是代码里写死的单层字符串，
  判定器返回 allow
- 用户显式给出精确目标、命令为单层 shell、全 ASCII 路径、非卷根、
  非系统前缀、非挂载点、爆炸半径里 reparse=0，且判定器返回 allow
- git clean 类操作：优先 `-n`（dry-run）看清单，再真执行

这三种之外不要再给自己找"看起来安全"的理由。工具说 block，就 block。

## 与宿主安全机制的分工

Claude Code 的 permission 系统、Codex 的 sandbox 管的是"这次工具调用能不能跑"；
本 skill 管的是"这条命令文本在目标平台上的真实语义"。两者不互替：
sandbox 拦不住引号链退化（它在单层里合法），permission 拦不住大小写碰撞
（命令文本本身"正确"）。如果你的宿主有 PreToolUse hook，把
`guard.py command` 挂进去；没有的话，本 skill 的纪律就是最后一道防线。
