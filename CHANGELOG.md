# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/xinghe-labs/windows-delete-guard/compare/0.1.0...HEAD
[0.1.0]: https://github.com/xinghe-labs/windows-delete-guard/releases/tag/0.1.0
