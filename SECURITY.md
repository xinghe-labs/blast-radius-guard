# Security Policy

## What this project is

A guard that judges destructive commands **before** they run. It is itself
security-relevant code, so its own failure modes matter:

## Design commitments

1. **Fail-open, loudly.** If `guard.py` is missing, times out (5 s), or errors,
   the hook/extension **allows** the command. We deliberately chose
   "never wedge the user's workflow" over "block on doubt". A guard that bricks
   every command gets uninstalled, and then protects nothing.
2. **No network.** Zero dependencies (Python stdlib only). No telemetry. No
   phoning home. Judge output stays on your machine.
3. **No silent mutation.** The judge never edits your commands; it only
   blocks (with reasons) or passes. The rewrite suggestions it returns are
   prose for the model, never auto-executed.
4. **Cited rules.** Every hazard rule carries the public incident (issue
   number) that justifies it. A rule without a citation is not shipped.

## Threat model boundaries (what this does NOT protect against)

- Commands the model rewrites to dodge the prefilter (e.g. base64-encoded
  payloads). The quick-predicate prefilter is an optimization, not a security
  boundary — only the layered checks are.
- Non-shell deletion paths (a malicious MCP tool, an `edit`/`write` tool
  truncating files). Scope is bash/powershell tool calls.
- Hosts without hook/extension mechanisms (Codex) — skill layer only.
- A model that fabricates files, deletes via `mv` onto ` /dev/null`, or
  corrupts rather than deletes. This is a delete-guard, not a total safety net.

## Reporting a vulnerability

Open a GitHub issue at `xinghe-labs/windows-delete-guard` describing the
command shape that was mis-judged (allowed when it should block, or blocked
when safe). Include: exact command string, OS, and (if possible) the `--json`
output. Please do not include real paths containing credentials.
