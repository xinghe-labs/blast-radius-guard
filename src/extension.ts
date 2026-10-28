/**
 * blast-radius-guard pi extension（原 windows-delete-guard）
 *
 * 在 bash / powershell 工具调用执行之前，把命令交给同仓库的判定器
 * （scripts/guard.py -> delete_guard 包，Windows / Linux / macOS 通用）：
 *   verdict=block -> { block: true, reason: 带事故编号的理由 + 改写建议 }
 *   verdict=warn  -> 放行（不弹窗、不打断；理由由模型侧的 skill 负责）
 *   verdict=allow -> 放行
 *
 * 设计取向：
 *   - fail-open：guard.py 缺失/超时/非零异常时放行，只在 reason 缺位时报一次。
 *     安全工具被误拦逼到禁用，比偶尔漏拦更糟。
 *   - 只拦不问：不打断用户（不调用 ctx.ui），block 的 reason 会回到模型，
 *     由模型按 reason 里的建议改写命令后重试。
 */

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const GUARD_TIMEOUT_MS = 5_000;

function guardScript(): string | null {
	const here = dirname(fileURLToPath(import.meta.url));
	const p = join(here, "..", "scripts", "guard.py");
	return existsSync(p) ? p : null;
}

/**
 * Windows 原生通常只有 `python`（`python3` 常是 Microsoft Store 假别名桩），
 * WSL/Linux/macOS 通常是 `python3`。按序探测第一个可用的；
 * 环境变量 WDG_PYTHON 可覆盖。
 */
let pythonResolved: string[] | null | undefined;
async function resolvePython(): Promise<string[] | null> {
	if (process.env.WDG_PYTHON) return [process.env.WDG_PYTHON];
	if (pythonResolved !== undefined) return pythonResolved;
	pythonResolved = null;
	for (const cmd of ["python3", "python", "py"]) {
		const candidate = cmd === "py" ? [cmd, "-3"] : [cmd];
		if (await probe(candidate)) {
			pythonResolved = candidate;
			break;
		}
	}
	return pythonResolved;
}

function probe(cmd: string[]): Promise<boolean> {
	return new Promise((resolve) => {
		execFile(cmd[0], cmd.slice(1).concat(["-c", "pass"]), { timeout: 3_000 }, (err) => {
			resolve(!err);
		});
	});
}

function runGuard(
	python: string[],
	script: string,
	command: string,
): Promise<{ verdict: string; text: string } | null> {
	return new Promise((resolve) => {
		execFile(
			python[0],
			python.slice(1).concat([script, "command", command, "--json"]),
			{ timeout: GUARD_TIMEOUT_MS, maxBuffer: 1024 * 1024 },
			(err, stdout) => {
				if (err && !stdout) {
					resolve(null); // fail-open
					return;
				}
				try {
					const parsed = JSON.parse(stdout.toString());
					resolve({ verdict: parsed.verdict ?? "allow", text: stdout.toString() });
				} catch {
					resolve(null);
				}
			},
		);
	});
}

interface InputLike {
	command?: unknown;
	[key: string]: unknown;
}

export default function (pi: ExtensionAPI) {
	const script = guardScript();

	pi.on("tool_call", async (event) => {
		if (!script) return undefined;
		if (event.toolName !== "bash" && event.toolName !== "powershell") {
			return undefined;
		}
		const input = event.input as InputLike | undefined;
		const command = typeof input?.command === "string" ? input.command : undefined;
		if (!command || !command.trim()) return undefined;

		// 快速预筛：不含删除/移动动词时不启动子进程（省掉 python 探测和 ~50ms）
		if (!/\b(rm|rmdir|del|erase|rd|unlink|shred|trash|remove-item|ri|move-item|move|mv)\b/i.test(command)) {
			return undefined;
		}

		const python = await resolvePython();
		if (!python) return undefined; // fail-open：环境里没有可用 Python

		const result = await runGuard(python, script, command);
		if (!result) return undefined;

		if (result.verdict === "block") {
			const reasons = (() => {
				try {
					const parsed = JSON.parse(result.text);
					return (parsed.hazards ?? [])
						.map((h: { code: string; evidence: string }) => `${h.code}（依据: ${h.evidence}）`)
						.join("; ");
				} catch {
					return result.text.slice(0, 400);
				}
			})();
			return {
				block: true,
				reason:
					`blast-radius-guard 拒绝执行该删除命令：${reasons}。` +
					"先改写成单层 shell、绝对路径的目标（Windows 用 -LiteralPath）；" +
					"或先 rename 进隔离目录（Windows: %USERPROFILE%\\.delete-quarantine\\<date>；" +
					"POSIX: ~/.delete-quarantine/<date>）观察后再删；" +
					"不要把算好的路径管道进 cmd /c 或嵌套引号链。完整判定输出已写入扩展日志。",
			};
		}
		return undefined;
	});
}
