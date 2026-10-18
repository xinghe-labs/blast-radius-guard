# windows-delete-guard

**在破坏性命令执行之前，判定它在 Windows 上的真实爆炸半径。**

一个 [Agent Skill](https://agentskills.io)：任何 agent（Claude Code / Codex / Cursor / pi）在跑 `rm -rf`、`rd /s /q`、`Remove-Item -Recurse -Force` 之前，先过一遍判定器，拿到 `allow / warn / block` 和带事故编号的理由。

## 调用方式：三层

**③ 硬拦截（推荐，装完就和）**

- pi：安装本包后，`src/extension.ts` 拦截所有 bash/powershell 删除命令，block 级在执行前拒绝，改写建议直接回给模型
- Claude Code：`hooks/pretooluse.py` 挂进 `PreToolUse`，exit 2 硬拦截
- fail-open 设计：guard.py 缺失/超时一律放行——安全工具因为误拦被用户禁用，比偶尔漏拦更糟

**② 软自动（装 skill 即得）**

agent 读到 SKILL.md 的 description 后，删除前自觉跑判定器。对携带 hook 机制的宿主，这只是后备。

**① 手动 CLI**

```powershell
python scripts\guard.py command 'rd /s /q "D:\★有些目录 with space"'
python scripts\guard.py path "D:\old-outputs"
python scripts\guard.py command "rm -rf /mnt/d/data" --json
```

退出码：`0` = allow，`1` = warn（需人工确认），`2` = block（拒绝执行）。

## 为什么是这个方向

2025-2026 年，AI agent 在 Windows 上静默销毁用户数据的公开事故记录已经成了一类：

| 事故 | 根因 | 造成的损失 |
|---|---|---|
| [claude-code#56603](https://github.com/anthropics/claude-code/issues/56603) | PowerShell→cmd 引号链断裂，路径含 Unicode+空格 | 整个 worktree 目录被清空 |
| [cursor 论坛](https://forum.cursor.com/t/severe-data-loss-agents-mis-quoted-rmdir-command-recursively-deleted-my-entire-c-drive-had-to-reinstall-windows/163626) | `rmdir /s /q` 引号退化成 `rmdir /s /q C:\` | **整盘 C:\ 被删除，重装系统** |
| [cursor 论坛](https://forum.cursor.com/t/agent-autonomous-rd-s-q-wiped-the-entire-d-drive-windows/174156.md) | 引号解析错误，`rd /s /q` 落到盘根 | 微信记录+源码+应用全毁 |
| [claude-code#60442](https://github.com/anthropics/claude-code/issues/60442) | NTFS 大小写不敏感，`rm -rf "D:\CampusconnECT"` 解析到真实目录 | **9 个生产代码库被毁** |
| [claude-code#68343](https://github.com/anthropics/claude-code/issues/68343) | CJK 路径经 PowerShell/WSL2 静默返回空输出 | agent 误判"文件不存在"，基于错误前提行动 |
| Claude Code v2.1.205 官方修复 | 删 worktree 穿透嵌套 NTFS junction，删到树外 | （官方 changelog 承认的 bug 类） |
| [codex#14487](https://github.com/openai/codex/issues/14487) | 默认权限下自主删除 D:\Photo，持续两天 | ~30MB×N 照片不可恢复 |

共同点：**这些命令文本在 POSIX 直觉里全都是"安全"的**。现有的同类工具（savestate、agent-rollback、file-safety-guard）由 macOS/Linux 作者编写，防不住 Windows 特有的失败路径。

## 项目原则

1. **不可解析即拒绝。** 引号链断裂不是边界情况，它是事故本体。
2. **无法验证就声明 unknown，不默认安全。** WSL 里看不到 NTFS reparse 属性，就说看不到。
3. **每条规则对应一个已归档的公开事故。** 没有编号的规则不进代码。

## 安装

```bash
npx skills add xinghe-labs/windows-delete-guard
```

或克隆到任意 agent 的 skill 目录：

```bash
git clone --depth 1 https://github.com/xinghe-labs/windows-delete-guard.git "$env:USERPROFILE\.agents\skills\windows-delete-guard"
```

零依赖，只要 Python 3.10+（Windows 自带或 winget 一条命令）。

## 直接使用（不经 agent）

```powershell
# 判定一条命令
python scripts\guard.py command 'rd /s /q "D:\★有些目录 with space"'

# 判定一个路径
python scripts\guard.py path "D:\old-outputs"

# 机器可读输出
python scripts\guard.py command "rm -rf /mnt/d/data" --json
```

退出码：`0` = allow，`1` = warn（需人工确认），`2` = block（拒绝执行）。

## 判定的危险（每条对应真实事故）

| 编号 | 危险 | 级别 |
|---|---|---|
| H0 | 命令文本无法无歧义解析（引号未闭合、层间转义） | block |
| H1 | 跨 shell 引号链（cmd /c、powershell -Command）+ 空格/CJK 路径 | block |
| H2 | 目标是卷根（`D:\`、`/mnt/d`） | block |
| H3 | 路径大小写与磁盘实际不一致（NTFS 不敏感） | block |
| H4 | 子树含 junction/符号链接，递归会穿透 | block |
| H5 | CJK 路径可能静默空输出 | warn |
| H6 | 目标在 `/mnt/` 下（WSL 跨文件系统语义） | warn |
| H7 | 目标是当前工作目录的祖先 | block |
| H8 | 递归+通配符（半径取决于运行时目录内容） | warn |
| H9 | 永久删除（不进回收站） | warn |

## 测试

```bash
python -m unittest discover tests -v
```

28 个用例：tokenize / intent / path→hazard / 真实事故回归 / 防"过度拦截"反例（普通 `rm -rf ./build` 不该 block）。

## 真机边界（诚实清单）

本项目在 **WSL2 (Linux) 宿主** 上开发和测试。以下判定在真实 Windows 上**逻辑正确但未经真机验证**，代码里已按要求声明 unknown：

- H3 的大小写碰撞（`case_collision` 只在 `os.name == "nt"` 时激活）
- H4 的 NTFS reparse 属性读取（`st_file_attributes`）
- PowerShell `-LiteralPath` 对 CJK 的行为

Plan：拿到一台干净 Windows 后跑 `tests/incidents/` 里的真机回归（待补）。

## License

MIT
