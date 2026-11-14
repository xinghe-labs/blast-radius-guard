# 事故收集与规则孵化（INCIDENTS.md）

本项目原则 3：**每条规则对应一个已归档的公开事故。没有编号的规则不进代码。**

本文件是事故收集的工作台：新发现的事故先进「候选区」，验证通过并提炼成
规则（或加固现有规则的测试用例）后移入「已消化区」。这样规则集能随真实
世界持续进化，同时保持每条规则的可溯源。

## 事故验证标准（三条全过才入规则）

1. **可归档**：有公开、可链接的记录（GitHub issue / 官方 changelog /
   技术论坛 / 技术博客）。私聊截图、无法核实的转述不算。
2. **有根因形态**：能提炼出命令文本层面的失败模式（引号、变量、大小写、
   挂载、提权……），而不是"用户自己手滑"。
3. **非重复**：不能被现有 H0–H13 规则捕获。如果现有规则**理论上**能捕获
   但**实际上**漏了，那是 bug，进 tests/ 加回归用例，而不是新规则。

## 状态标记

- `📋 候选` — 已记录，待验证
- `🔍 验证中` — 正在核实链接与根因
- `✅ 已入规则` — 已成为 H 系规则（链接到 rules/ 与 tests/）
- `🧪 已入测试` — 现有规则能捕获，已加回归用例
- `❌ 不采纳` — 附理由（不可归档 / 无根因形态 / 重复）

---

## 候选区

### [候选] 第三轮全网扫描（2026-11-08）：Agent Incident Ledger 全列 + 48k 文件事故

#### [🧪 部分入测试] 13. Windows junction + os.walk 穿透：48,218 文件 / 103 秒（2026-09）
- **来源**：https://www.reddit.com/r/ClaudeAI/comments/1wl5cgo/ + https://cybersecuritynews.com/claude-code-agent-file-deletion/
- **原始记录**：Reddit r/ClaudeAI 1wl5cgo + cybersecuritynews.com 报道（有
  verifier 报告，非独立取证）
- **命令形态**：`python cleanup.py <mirror>` —— agent 生成的清理脚本内部
  `os.walk(followlinks=False)` + `os.path.islink()`，在 Windows 上对
  directory junction 返回 False → 穿透 614 个 junction 删掉源树 48,218 个
  活文件，`.git/objects` 全空无法 git 恢复
- **根因分析**：**判定器结构性盲区** —— 删除发生在 agent 生成的 Python
  脚本内部，shell 命令文本只是 `python cleanup.py <dir>`，无任何删除动词。
  这是"间接删除"：命令文本无害，脚本行为有害
- **实测**：allow ⚠️（结构性）
- **建议动作**：部分可防御 —— ① SKILL.md 铁律加一条：删除操作不写入
  脚本文件再执行，shell 直接跑判定器可见的命令；② H4 已覆盖"直接
  rm -rf 含 junction 目录"（实测 block ✓）；③ 脚本间接删除是宿主层
  权限问题，判定器无法覆盖 → 文档声明范围外
- **注意**：此事故反证 H4 的价值——如果 agent 直接跑 rm -rf，我们拦得住

#### [✅ 已入规则 H15] 14. Gemini CLI move 级联覆盖（2025-07，Agent Incident Ledger）
- **来源**：https://www.manifold.security/incidents (Gemini CLI 2.5-pro, 2025-07-21)
- **原始记录**：manifold.security incident ledger（Gemini CLI 2.5-pro）
- **命令形态**：`mv source/* dest/` —— mkdir 失败后 agent 继续当作成功，
  连环 mv 覆盖用户文件直到剩一个
- **根因分析**：**覆盖型销毁**——mv/cp 到已存在路径的批量覆盖；与
  H15_OVERWRITE 候选同型。目标目录不存在时 mv 不报错（尾斜杠语义），
  文件被平铺覆盖
- **实测**：bulk mv → allow ⚠️（H15 候选核心场景）
- **建议动作**：并入 H15_OVERWRITE 候选（等误报数据定宽严）

#### 15. AWS Kiro 删环境重建（2025-12，FT 报道）
- **来源**：https://www.manifold.security/incidents (AWS Kiro, 2025-12, FT 报道)
- **原始记录**：Agent Incident Ledger（Amazon Kiro agent，FT 报道 13 小时故障）
- **命令形态**：`kiro environment delete`
- **实测**：✅ **已即时修复** —— H14 收录 `kiro environment delete`
  （block 级），并顺带修了 `npx neon db sql "TRUNCATE users"` 的漏判
  （SQL 客户端检测补 npx/yarn 前缀 + neon/supabase 客户端；SQL 检测
  优先于工具表匹配）
- **建议动作**：已完成 ✓

#### 16. Replit Agent 删生产库（2025-07，SaaStr 创始人）
- **来源**：https://www.manifold.security/incidents (Replit Agent, 2025-07-18)
- **原始记录**：Agent Incident Ledger（Replit Agent，声明 code freeze 期间删除）
- **命令形态**：数据库 SQL 层（psql DROP/TRUNCATE 形态）
- **实测**：block ✓（H14 SQL 检测覆盖）—— 但 Replit 是 agent 内部
  数据库工具调用，非 shell 命令，判定器实际看不见；README 事故表
  值得补这行（知名度最高的 agent 数据丢失事故之一）
- **建议动作**：README 事故表补行

#### 17. Claude Cowork 删 15 年照片（2026-02，Agent Incident Ledger）
- **来源**：https://www.manifold.security/incidents (Claude Cowork, 2026-02-07)
- **原始记录**：Agent Incident Ledger（Claude Cowork，"tidy desktop" 任务）
- **命令形态**：`rm -rf <photos>`（agent 误判为空目录）
- **实测**：warn（H9）—— rm -rf 文本形态可拦，但"误判空目录"是
  语义层错误，判定器只能给 warn 不能证伪
- **建议动作**：README 事故表补行；印证"隔离 rename 优先"铁律的价值

#### 18. GPT-5.6 Sol TRUNCATE Neon users 表（2026-07，Agent Incident Ledger）
- **来源**：https://www.manifold.security/incidents (GPT-5.6 Sol Neon, 2026-07-13)
- **原始记录**：Agent Incident Ledger（Codex + GPT-5.6 Sol，只要 seed data
  却对生产 Neon 库跑破坏性清理）
- **命令形态**：`npx neon db sql "TRUNCATE users"`
- **实测**：✅ **已即时修复**（同 15 号：npx 前缀 SQL 检测）
- **建议动作**：已完成 ✓

#### 第三轮后续（2026-11-08 更新）
- 候选 14 已实现为 **H15_OVERWRITE**（覆盖型销毁，warn 级，OverwriteTests 4 用例）
- 候选 13 的防御动作已落地：SKILL.md 铁律「删除不入自写脚本」+ 原理边界节
  （MCP/脚本间接删除 → 宿主 permission 配置指引）
- find -exec 嵌套删除判定已实现（0.6-1）：`find ... -exec rm {} \;` 内层
  命令递归判定，FindExecTests 4 用例

#### 第三轮结论
- **新增收录 6 项**（13-18），其中 2 项（15/18）发现 H14 实测漏洞并当场修复
  （kiro、npx neon SQL），1 项（13）揭示"间接删除"结构性盲区 → 文档声明
  范围外，1 项（14）充实 H15_OVERWRITE 候选
- Agent Incident Ledger（manifold.security）是高质量事故源，含官方
  response 与时间线，建议作为常规监控渠道
- H15_OVERWRITE 的证据链持续加厚：Gemini move 覆盖 + PowerShell 编码清空
  （第二轮候选 12）+ vscode 覆写（第一轮候选 2）——三个独立来源

### [✅ 已入规则 H14] 第二轮全网扫描（2026-11-02）：H14 动词表的事故背书

第一轮发现了"云工具链删除"这个空白；本轮专门为 H14 的每类动词收集事故背书，
并意外发现了中文社区的大量同类事故。**10/10 实测全部 allow** —— H14 的
紧迫性比第一轮估计的更高。（2026-11-02 更新：候选 7-10 已实现为
H14_CLOUD_TOOLING，block/warn 分级，tests CloudToolingTests 17 用例；
候选 11 三形态已入 ChineseIncidentRegressionTests）

#### 7. Docker 卷删除（3 个独立事故，deedglass 称 compose down -v 为"删得最多"）
- **来源**：
  - claude-code#14944（2025-12）：agent 自主 `docker volume rm` 删光本地
    Supabase 数据
  - claude-code#41357（2026-03）：agent 跑 `docker system prune -af --volumes`
    "释放磁盘"，删掉**多个无关客户项目**的镜像与卷
  - deedglass.com 博客（2026-10）：`docker compose down -v` 删 named volumes
    （本地数据库的数据所在），列为 agent 场景最危险命令
- **命令形态**：`docker volume rm <v>`、`docker system prune -a --volumes`、
  `docker compose down -v`、`docker volume prune --all`
- **根因**：动词是 prune/rm/down，删除语义藏在 flag（-v / --volumes）里
- **建议动作**：H14 收录；注意 `docker system prune -f`（无 --volumes）是
  日常清理，AgentTrail 的实现也刻意放行 —— 边界：只有带 --volumes /
  volume rm / down -v 才 warn

#### 8. Kubernetes 删除（namespace 级联删除无确认）
- **来源**：
  - deedglass.com（2026-10）：`kubectl delete namespace prod` 一个工具调用
    删光 namespace 内一切，无两阶段提交无确认
  - agenticcontrolplane.com（2026-04）：同样结论
- **命令形态**：`kubectl delete namespace <n>`、`kubectl delete pvc <v>`
- **根因**：namespace 是级联删除的天然放大器；社区 RFC（2021）就要求加保护
- **建议动作**：H14 收录 namespace/pv/pvc 的 delete

#### 9. ORM/迁移工具清库（4 个独立事故，Prisma 官方下场写防护文章）
- **来源**：
  - claude-code#26913（2026-02）：`alembic downgrade base` 清掉 21 张表
  - claude-code#27063（2026-02）：`drizzle-kit push --force` 清空生产库
  - Prisma 事故（manifold.security AID）：Claude Opus 5 把生产 Supabase 当
    shadow DB，`prisma migrate reset` 清表
  - claude-code#74557：agent 调 init_db(drop_existing=True) 删 500GB/6 亿行库
- **命令形态**：`prisma migrate reset`、`prisma db push --force-reset`、
  `alembic downgrade base`、`drizzle-kit push --force`
- **根因**：开发期工具被 agent 用在生产连接串上；Prisma 6.15 甚至内置了
  agent 检测拦截 —— 工具厂商都承认这是真实威胁面
- **建议动作**：H14 收录（reset / --force-reset / downgrade base /
  push --force）

#### 10. SQL 直删（DROP/TRUNCATE）
- **来源**：https://www.prisma.io/blog/stop-your-ai-agent-dropping-your-database
- **原始记录**：prisma.io 官方博客（2026-07）明确指出 "committed DROP TABLE or
  TRUNCATE can't be undone"
- **命令形态**：`psql -c "DROP TABLE users"`、`TRUNCATE ... CASCADE`
- **建议动作**：H14 收录 psql/mysql/sh 的 -c 参数里的 DROP/TRUNCATE 检测
  （需要解析引号内 SQL —— 与 H1 引号链解析互补）

#### 11.【中文社区】V2EX/L 站四起整盘/整环境删除（第一轮遗漏的富矿）
- **来源**：
  - V2EX#1233011（2026-08）：Codex + GPT-5.6 full-access，**C 盘 D 盘全删，
    两三百 GB 上百万文件**（`wsl.exe bash -lc '...'` 跨层形态）
  - V2EX#1238217（2026-08）：GLM agent **删掉上上级文件夹**（cwd 祖先的
    祖先！），8 亿 token 的工作成果丢失
  - linux.do#2925817（2026-09）：Kimi-code 删光整个开发环境（连 bashrc 都丢）
  - linux.do#2934749（2026-09）：grok4.7 删光 G 盘；回复指出"删盘问题都
    出现在 win 的 PowerShell"
- **根因**：与 H0-H13 大部分同型（PowerShell 引号链、跨层 wsl.exe、
  祖先目录），但出现了两个值得注意的新特征：
  a) **上上级目录**（#1238217）—— 现有 H7 只查 cwd 的祖先链，
     理论可拦 ✓（需加测试用例验证 grandparent）
  b) **wsl.exe bash -lc 跨层** —— shell_layers 已覆盖 wsl/bash，
     理论可拦 ✓（需加测试用例验证 -lc 形态）
- **建议动作**：**加固现有规则**：加 2 个回归测试（祖先的祖先、
  wsl.exe bash -lc 'rm -rf /'）；中文社区事故作为 README 事故表补充
  （证明中文用户同样受害，L 站推广有共鸣点）

#### 12. PowerShell 编码错误清空文件（linux.do#2402993 回复）
- **来源**：https://linux.do/t/topic/2402993
- **原始记录**：linux.do 佬友经历：agent 用 PowerShell 编辑文件，编码错误把
  未备份文件清空
- **根因**：与 H5 CJK 静默失败同族（PowerShell 编码/编码转换丢内容），
  但发生在**写路径**（Set-Content/编辑）而非删除
- **建议动作**：归入 H15_OVERWRITE 候选的佐证材料（写路径覆盖也是
  数据销毁形态）；单独不成立规则

#### 第二轮结论
- H14 动词表的事故背书已齐：docker(3) / k8s(2) / ORM(4) / SQL(1) /
  云 CLI(第一轮 PocketOS/terraform) —— **每类都有编号可引的事故**
- 中文社区 4 起事故全部可与现有规则对应，补 2 个回归测试即可
- `drizzle-kit push --force` / `alembic downgrade base` / `prisma migrate
  reset` 三条在 Prisma 官方博客里有背书，H14 的 ORM 部分可直接引用

#### 1. 云资源 CLI/API 删除完全在判定范围外（多个独立事故）
- **日期**：2026-02 ~ 2026-04
- **平台**：全平台（云 API 无关本地 OS）
- **来源**：https://github.com/anthropics/claude-code/issues/56603 等（见 README 事故表）
- **原始记录**：
  - PocketOS：Cursor agent 删 Railway volume，9 秒清掉生产库+备份
    （theguardian.com/technology/2026/apr/29, AID-2026-0106）
  - claude-code#27063：`drizzle-kit push --force` 清空生产 PostgreSQL 60+ 表
  - Terraform：Claude Code 跑 `terraform destroy` 毁掉 2.5 年生产设施
    （tomshardware.com 2026-03-07）
- **命令形态**：`railway volume delete <id>`、`drizzle-kit push --force`、
  `terraform destroy -auto-approve`、`aws s3 rb ...` 等
- **根因分析**：破坏力等同 `rm -rf`，但动词不在任何 shell 删除词表里 ——
  云 CLI / ORM / IaC 工具有自己的删除动词（delete/destroy/drop/rb/push --force）
- **现有规则为何没拦住**：H0-H13 只解析 shell 动词；这些命令 verdict=allow
- **建议动作**：**新规则 H14_CLOUD_TOOLING**（warn 起步）：维护云/ORM/IaC
  工具的破坏性动词表（terraform destroy、drizzle-kit push --force、
  railway volume delete、aws s3 rb、gcloud sql instances delete、
  kubectl delete namespace/pv、docker system prune -a --volumes）
- **实测**：全 allow ⚠️

#### 2. 非删除动词的数据销毁：覆写/重定向（vscode#298393 关联面）
- **日期**：2026-02
- **平台**：全平台
- **来源**：https://github.com/anthropics/claude-code/issues/23701, https://github.com/microsoft/vscode/issues/298393
- **原始记录**：claude-code#23701（覆写源码数日工作量，财务损失）；
  microsoft/vscode#298393（agent 未授权删除文件/目录）
- **命令形态**：`echo x > src/main.py`、`cp new old`（不带 -n 覆盖）、
  agent 的 write/edit 工具直接覆写
- **根因分析**：重定向 `>` 和无确认 `cp` 是"删除=覆盖"的隐藏形态，
  现有规则只盯删除动词
- **现有规则为何没拦住**：shell 重定向不在任何规则视野内
- **建议动作**：**新规则 H15_OVERWRITE**（warn）：检测 `> file`（非 `>>`）
  目标为已存在非空文件、`cp/mv` 覆盖已存在文件且无 `-n`/`-i`。
  ⚠️ 覆盖语义噪声风险高，需真实误报数据决定宽严；先入候选观察
- **实测**：`echo x > src/main.py` → allow ⚠️

#### 3. MCP / 非.shell 工具的删除（claude-code#24559）
- **日期**：2026-02
- **平台**：全平台
- **来源**：https://github.com/anthropics/claude-code/issues/24559
- **原始记录**：claude-code#24559（模型无视 MEMORY.md 警告，经 MCP 工具
  不可逆删除）
- **根因分析**：删除不走 shell，MCP 工具调用（filesystem delete 等）
  完全绕过命令行判定器
- **现有规则为何没拦住**：结构限制 —— 判定器只看 bash/powershell 工具
  的 command 字段
- **建议动作**：**文档声明范围外**（判定器无法覆盖 MCP 工具，需宿主层
  permission 系统配合）；SKILL.md「范围外形态」加一条
- **实测**：结构性空白，非规则可修

#### 4. Antigravity rd /s /q 引号链（2026-10-21）
- **日期**：2026-10-21
- **平台**：Windows
- **来源**：https://discuss.ai.google.dev/t/antigravity-recursively-wiped-my-d-drive/191206
- **原始记录**：discuss.ai.google.dev/t/antigravity-recursively-wiped-my-d-drive/191206
- **命令形态**：`cmd.exe /c "rd /s /q \"C:\\Users\\...\\Temp\\...\\""`
- **根因分析**：与 H0/H1 完全同型（cmd /c + 嵌套引号），但 2026-10 仍在发生
- **现有规则为何没拦住**：**实测 block（H0_AMBIGUOUS）✓** —— 现有规则已覆盖
- **建议动作**：**加固现有规则**：加入 tests/ 作为 2026 年重复事故回归
  用例（证明 H0/H1 在新产品上仍会复发，规则集持续有效）
- **实测**：block ✓

#### 5. OpenAI 官方承认 GPT-5.6 会误删文件（2026-07）
- **日期**：2026-07-17
- **平台**：macOS（Matt Shumer 报告"删掉几乎所有 Mac 文件"）
- **来源**：https://www.infoworld.com/article/4198216/openai-acknowledges-gpt-5-6-may-accidentally-delete-files-calls-it-an-honest-mistake.html
- **原始记录**：infoworld.com/article/4198216
- **根因分析**：官方确认但未公开具体命令形态 —— 无根因细节，暂无法提炼规则
- **建议动作**：**观察**：等具体命令形态公开（如 form 披露或第三方复现），
  暂不采纳为规则（验证标准第 2 条不过）

#### 6. github community#198646 Copilot agent 删 4-5 天工作
- **日期**：2021-11（早期，但形态仍是 agent 未授权删除）
- **来源**：https://github.com/orgs/community/discussions/198646
- **原始记录**：github.com/orgs/community/discussions/198646
- **建议动作**：与 vscode#298393 同型合并观察，不单独成规则

### 模板

```markdown
### [候选] 事故短标题
- **日期**：事故发生/报告时间
- **平台**：Windows / Linux / macOS / WSL
- **来源**：<可点击链接>
- **命令形态**：`<脱敏后的命令原文>`
- **根因分析**：<为什么命令文本的语义和意图不一致>
- **现有规则为何没拦住**：<逐条对照 H0-H13 说明，或"理论可拦但实测漏" >
- **建议动作**：新规则 H1x / 加固现有规则测试 / 不采纳
```

---

## 已消化区

### ✅ 已入规则（H0–H13，见 rules/ 与 README 事故表）

| 规则 | 事故依据 | 入版本 |
|---|---|---|
| H0 | claude-code#56603, cursor-forum#163626 | 0.1.0 |
| H1 | claude-code#56603, cursor-forum#163626/174156 | 0.1.0 |
| H2 | cursor-forum#163626 | 0.1.0 |
| H3 | claude-code#60442 | 0.1.0 |
| H4 | claude-code v2.1.205 fix, qiita/kai_kou | 0.1.0 |
| H5 | claude-code#68343 | 0.1.0 |
| H6 | wsl-drvfs 语义 | 0.1.0 |
| H7 | claude-code#60442 | 0.1.0 |
| H8 | codex#14487 | 0.1.0 |
| H9 | codex#14487, cursor-forum#174156 | 0.1.0 |
| H10 | macrumors#1176135, steam-for-linux 2015 | 0.2.0 |
| H11 | steam-for-linux 2015（rm -rf "$STEAMROOT/"* → /*） | 0.2.0 |
| H12 | rsync 邮件列表 2010#025330, blog.theodorc.no 2022 | 0.2.0 |
| H13 | superuser#1925324, macrumors#1192684 | 0.2.0 |

### 🧪 已入测试（现有规则的回归加固）

（空 —— 暂无）

### ❌ 不采纳

（空 —— 暂无）

---

## 收集渠道（持续监控）

- GitHub：`anthropics/claude-code`、`openai/codex`、`getcursor/cursor` 相关
  issue 关键词（data loss / deleted files / rm -rf / wiped）
- L 站（linux.do）：开发调优板块的 agent 数据丢失求助帖
- r/LocalLLaMA、r/ChatGPTCoding 的 agent 数据丢失帖
- 技术博客的 agent 事故复盘文章

## 更新节奏

- 有候选就随时追加，不攒批
- 每个版本（0.x）发布前清一次候选区：验证 → 入规则/入测试/不采纳
- 0.4.0 的主题就是第一轮外部数据驱动的规则调优
