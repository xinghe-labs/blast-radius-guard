# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-11-08

### Added

- **H15_OVERWRITE** (warn) — overwrite-destruction: glob mv/cp into an
  existing directory (Gemini CLI cascade overwrite), `>` redirect to a
  non-empty file (PowerShell encoding wipe). Three independent incident
  sources. Everyday forms verified to pass (8/8 matcher cases).
- **find -exec nesting** — `find ... -exec rm {} \;` inner command now
  recursively judged; container gets H8 batch semantics.
- SKILL.md: "删除不入自写脚本" discipline (48k-file incident, 2026-09) +
  principle-boundary section for MCP/script-mediated deletion with
  host-permission guidance.

### Fixed

- `/d`-style single-letter POSIX paths no longer eaten by the cmd
  single-flag whitelist for non-cmd verbs (audit regression find).

Tests: 104 -> 112.

## [0.4.0] - 2026-11-02

### Added

- **H14_CLOUD_TOOLING** — destructive verbs of cloud/container/ORM/SQL
  tooling, the biggest judgment gap found in the incident sweeps:
  - block: `terraform destroy`, `pulumi destroy`,
    `kubectl delete namespace/ns`, SQL `DROP TABLE/DATABASE/SCHEMA`
    and `TRUNCATE` via psql/mysql -c/-e
  - warn: `docker volume rm`, `docker volume prune --all`,
    `docker system prune --volumes`, `docker compose down -v`,
    `prisma migrate reset`, `prisma db push --force-reset`,
    `alembic downgrade base`, `drizzle-kit push --force`,
    `railway volume delete`, `aws s3 rb`,
    `gcloud sql instances delete`, `supabase db reset`
  - every verb carries a cited incident (AID-2026-0106 PocketOS,
    claude-code#14944/#41357/#26913/#27063, DataTalks.Club terraform,
    Prisma blog); over-blocking guardrails verified (prune without
    --volumes, terraform plan, kubectl get, prisma migrate dev all pass)
- Chinese-community incident regression tests: grandparent-dir delete
  (V2EX#1238217), `wsl.exe bash -lc` cross-layer wipe (V2EX#1233011),
  PowerShell nested-quote wipe (linux.do#2934749).
- INCIDENTS.md — sustainable incident-collection workbench with two
  full-network sweeps (12 candidates) documenting the evidence chain
  for every H14 verb.
- README incident table: 8 new rows (cloud/container/Chinese community);
  rule table 14 -> 15 rows; test count 85 -> 101.
- SKILL.md description: cloud-tooling trigger phrases for agent routing.

## [0.3.1] - 2026-11-02

### Changed

- README: drop rename note; sync facts to 0.3.0 (85 tests, 0.1→0.3
  evolution, H5 platform-scope note, code-structure versioning).
- Add LINUX DO community acknowledgement.
- Add INCIDENTS.md — sustainable incident-collection workbench
  (verification criteria, candidate lifecycle, monitoring channels)
  with the first full-network sweep: 6 candidates logged, including
  the cloud-tooling deletion gap (H14 proposal for 0.4.0).

## [0.3.0] - 2026-10-28

### Changed

- `find <path> -delete` and git subcommands (`clean -f`, `worktree remove`)
  are now judged natively instead of relying on skill-layer discipline:
  - `find ... -delete` maps to a destructive intent (recursive+force);
    `-name`/`-path` predicate arguments are not treated as targets;
    `find` without `-delete` is untouched.
  - `git clean -f` variants warn (H9); `-n` (dry-run), alone or combined,
    allows. Other git subcommands unaffected.
  - `git worktree remove` warns (H9) — the H4 incident prototype.
  - `sudo find ... -delete` blocks (H10).
- Unexpanded-variable detection narrowed to real variable shapes
  ($VAR / ${VAR} / %VAR%): literal `$` in directory names (e.g. tmp$)
  no longer false-positives.
- package.json files now includes pyrightconfig.json for editor lint.

### Fixed

- NUL byte in a command crashed the judge chain instead of hardcoding python3 —
  probe order BRG_PYTHON env > python3 > python > py -3 (mirrors
  extension.ts), cached once, fail-open when none found.
- `is_flag_token` takes the cmd-verb context as a parameter instead of a
  function attribute — removes a cross-call race under concurrent judging.
- Add `.github/ISSUE_TEMPLATE/false-positive.yml` for real-world
  mis-judgment reports (feeds the 0.3 rule-tuning loop).
- docs/demo.svg redrawn: one incident per OS + blast-radius JSON.
- SKILL.md: new "范围外形态" section (find -delete / git clean / git
  worktree remove need manual discipline); README documents that `path`
  mode is static-only (H8/H9/H10 not applicable).

### Fixed

- NUL byte in a command crashed the judge chain (os.* raise ValueError)
  and fell through the hook's fail-open path. The judge now blocks NUL
  commands explicitly as H0_AMBIGUOUS (no shell can execute them anyway)
  and the hook rejects them with exit 2 before spawning the judge.
  Regression tests added (74 total).
- Audit findings (judge bypasses):
  - `sudo bash -c "rm ..."` / `su -c` / `doas bash -c` were fully allowed —
    privilege verbs now count as a shell layer, and the privileged context
    is inherited by the recursive inner judgment (H10 fires).
  - `rm -rf /*` and the Steam-2015 form `rm -rf "$UNSET/"*` only warned —
    glob targets now get a blast-radius pre-check: no determinable prefix
    or a prefix hitting a volume root / system prefix blocks (H0/H2/H11);
    `/tmp/*` style cleanups still warn.
  - Targets containing unexpanded `$VAR` / `%VAR%` now block as H0
    (path unknowable before execution).
  - `robocopy /MIR` and `rsync --delete` were fully allowed despite being
    the H12 incident protagonists — mirror verbs now map to
    recursive+force and H9 fires with mirror semantics.
  - `/usr`, `/etc` etc. were briefly eaten by the multi-letter cmd-flag
    regex; long flags are now scoped to cmd-family verbs only.
  - Single-letter POSIX paths (`/x`) no longer match the cmd single-flag
    whitelist (letters restricted to cmd's actual flag set).

## [0.2.0] - 2026-10-28

### Changed

- **Project renamed**: windows-delete-guard → blast-radius-guard. The old
  `scripts/guard.py` CLI and module API keep working as a compatibility shim
  (delegates to the new `delete_guard` package); repo URL will move to
  `xinghe-labs/blast-radius-guard`.
- Rule engine split into a package, rules per platform:
  `delete_guard/rules/{common,windows,linux,macos}.py`. Host detection and
  cross-host `unknowns` declarations centralized in `delete_guard/platform.py`.
- H3 case-collision now also applies to macOS (APFS/HFS+ case-insensitive),
  with posixpath-style segment walking on darwin hosts.
- H6 WSL cross-filesystem warning is now gated on WSL context (host is WSL,
  or command launched via `wsl`) instead of firing on any `/mnt/...` path
  on native Linux.

### Added

- H10 sudo/doas/su-escalated deletes (block) — macrumors#1176135, Steam 2015.
- H11 Linux system-prefix wipes: /usr /etc /bin /home ... (block) —
  Steam 2015 `rm -rf "$STEAMROOT/"*` degenerating to `rm -rf /*`.
- H12 mount-point deletion (block) — rsync --delete backup-volume incidents.
- H13 macOS home special directories: Desktop/Documents/Downloads/Library...
  (block) — superuser#1925324, macrumors#1192684.
- Cross-host `unknowns` per platform (Linux/macOS semantics declared when
  judging from a different host).
- Extension/hook prescreen now also matches `trash`, `sudo rm`.

### Verified

- Full legacy behavior regression (H0–H9 incidents) passes on the new engine.
- H12 mount-point verified on a real WSL host against `/mnt/d`.
- Legacy test suite passes via the `guard.py` shim with zero edits.

## [0.1.0] - 2026-10-18

### Added

- `scripts/guard.py`: blast-radius judge for destructive commands, 10 hazard rules
  (H0 ambiguous parse → H9 permanent delete), each tied to a documented public
  incident. `command` / `path` modes, `--json` output, exit codes 0/1/2.
- Shell-layer unwrapping: `cmd /c "rd ..."` / `powershell -Command "..."` inner
  commands are re-parsed recursively; quote-chain degradation reported as H1.
- Quarantine-rename guidance instead of permanent deletes.
- `SKILL.md`: Agent Skill entry point (works in Claude Code / Codex / pi).
- pi extension (`src/extension.ts`): hard enforcement via `tool_call` —
  blocks verdict=`block` bash/powershell deletes before execution and returns
  rewrite guidance to the model. Python resolution probing (python3/python/py,
  `WDG_PYTHON` override). Fail-open on missing judge or timeout.
- Claude Code PreToolUse hook (`hooks/pretooluse.py`): exit-2 deny protocol.
- CI: unit-test matrix on ubuntu + windows runners, `tsc --strict` job,
  PreToolUse hook smoke test.
- 28+ unit tests including over-blocking counterexamples (`rm -rf ./build`
  must NOT be blocked).

### Verified

- End-to-end in a real pi session: extension loaded via `-e`, model issued
  `rm -rf /tmp/guard-e2e/project` (symlink inside), extension ran the judge,
  command was blocked with H4 + H9 reasons returned to the model. Positive
  control (`ls && cat && echo`) passed untouched.

[Unreleased]: https://github.com/xinghe-labs/blast-radius-guard/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/xinghe-labs/blast-radius-guard/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/xinghe-labs/blast-radius-guard/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/xinghe-labs/blast-radius-guard/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/xinghe-labs/blast-radius-guard/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/xinghe-labs/blast-radius-guard/compare/0.1.0...v0.2.0
[0.1.0]: https://github.com/xinghe-labs/windows-delete-guard/releases/tag/0.1.0
