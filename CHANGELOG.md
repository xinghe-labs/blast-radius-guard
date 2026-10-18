# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
