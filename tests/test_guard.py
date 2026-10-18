#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guard.py 的规则测试。每个规则至少一条正例；关键反例防止过度拦截。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import guard  # noqa: E402


class TokenizeTests(unittest.TestCase):
    def test_simple_tokens(self):
        p = guard.tokenize("rm -rf ./build")
        self.assertEqual([t.value for t in p.tokens], ["rm", "-rf", "./build"])
        self.assertFalse(p.ambiguous)

    def test_quoted_target_with_space(self):
        p = guard.tokenize('rd /s /q "D:\\My Projects\\x"')
        self.assertEqual(p.tokens[-1].value, "D:\\My Projects\\x")
        self.assertTrue(p.tokens[-1].quoted)

    def test_unterminated_quote_is_ambiguous(self):
        p = guard.tokenize('rm -rf "/tmp/unterminated')
        self.assertTrue(p.ambiguous)
        self.assertIsNotNone(p.ambiguous_reason)


class IntentTests(unittest.TestCase):
    def test_cmd_flags_not_targets(self):
        intent = guard.extract_intent(guard.tokenize("rd /s /q D:\\data"))
        self.assertEqual(intent.verb, "rd")
        self.assertTrue(intent.recursive)
        self.assertTrue(intent.force)
        self.assertEqual(intent.targets, ["D:\\data"])

    def test_combined_short_flags(self):
        intent = guard.extract_intent(guard.tokenize("rm -rf /tmp/x"))
        self.assertTrue(intent.recursive)
        self.assertTrue(intent.force)
        self.assertEqual(intent.targets, ["/tmp/x"])

    def test_wsl_mount_path_is_not_flag(self):
        intent = guard.extract_intent(guard.tokenize("rm -r /mnt/d/data"))
        self.assertEqual(intent.targets, ["/mnt/d/data"])
        self.assertTrue(intent.recursive)

    def test_powershell_long_flags(self):
        intent = guard.extract_intent(
            guard.tokenize("Remove-Item -Recurse -Force D:\\Photo")
        )
        self.assertTrue(intent.recursive)
        self.assertTrue(intent.force)
        self.assertEqual(intent.targets, ["D:\\Photo"])

    def test_move_detection(self):
        intent = guard.extract_intent(guard.tokenize("move C:\\a D:\\b"))
        self.assertTrue(intent.is_move)
        self.assertFalse(intent.is_delete)


class PathHazardTests(unittest.TestCase):
    def test_drive_root_win(self):
        for p in ("D:\\", "D:/", "D:", "C:\\", "/mnt/d", "/mnt/d/"):
            with self.subTest(p=p):
                self.assertTrue(guard.is_drive_root(p))

    def test_drive_root_not_overmatched(self):
        for p in ("D:\\data", "/mnt/d/data", "./", "D:\\a\\b"):
            with self.subTest(p=p):
                self.assertFalse(guard.is_drive_root(p))

    def test_wsl_mount(self):
        self.assertTrue(guard.is_wsl_windows_mount("/mnt/d/x"))
        # /mnt/d 本身是卷根，走 H2，不重复走 H6
        self.assertFalse(guard.is_wsl_windows_mount("/mnt/d"))
        self.assertFalse(guard.is_wsl_windows_mount("/home/u"))

    def test_cjk(self):
        self.assertTrue(guard.has_cjk("C:\\Users\\杨洋"))
        self.assertFalse(guard.has_cjk("C:\\Users\\yang"))

    def test_ancestor_of_cwd(self):
        base = tempfile.mkdtemp()
        child = os.path.join(base, "child")
        os.makedirs(child)
        self.assertTrue(guard.is_ancestor_of_cwd(base, child))
        self.assertTrue(guard.is_ancestor_of_cwd(child, child))
        sibling = os.path.join(base, "..", "other")
        self.assertFalse(guard.is_ancestor_of_cwd(sibling, child))


class BlastRadiusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "proj" / "sub").mkdir(parents=True)
        (root / "proj" / "main.py").write_text("print(1)")
        (root / "proj" / "sub" / "a.log").write_text("log")
        (root / "precious").mkdir()
        (root / "precious" / "keep.txt").write_text("keep")
        os.symlink(root / "precious", root / "proj" / "link")

    def test_counts_and_reparse(self):
        br = guard.walk_blast_radius(os.path.join(self.tmp.name, "proj"))
        self.assertTrue(br.is_dir)
        self.assertEqual(br.files, 2)  # main.py + a.log；link 单独计入 reparse
        self.assertEqual(br.reparse_points, 1)

    def test_missing_target_notes(self):
        br = guard.walk_blast_radius("/nonexistent/path/xyz")
        self.assertFalse(br.exists)
        self.assertIn("不存在", br.note)

    def test_single_file(self):
        f = os.path.join(self.tmp.name, "proj", "main.py")
        br = guard.walk_blast_radius(f)
        self.assertFalse(br.is_dir)
        self.assertEqual(br.files, 1)
        self.assertEqual(br.bytes, len("print(1)"))


class JudgeCommandTests(unittest.TestCase):
    def test_real_incident_quote_chain_blocked(self):
        # claude-code#56603: cmd /c rd + 嵌套引号 + Unicode/空格路径
        result = guard.judge_command(
            'cmd /c "rd /s /q \\"D:\\★zRC With Claude\\.claude\\worktrees\\x\\""'
        )
        self.assertEqual(result["verdict"], "block")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H1_QUOTE_CHAIN", codes)

    def test_drive_root_blocked(self):
        result = guard.judge_command("rd /s /q D:\\")
        self.assertEqual(result["verdict"], "block")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H2_DRIVE_ROOT", codes)

    def test_cjk_path_warns(self):
        result = guard.judge_command("del C:\\Users\\杨洋\\Desktop\\报告.txt")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H5_CJK_SILENT_FAIL", codes)
        self.assertEqual(result["verdict"], "warn")

    def test_wsl_mount_warns(self):
        result = guard.judge_command('wsl rm -rf "/mnt/d/data"')
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H6_WSL_CROSS_FS", codes)

    def test_glob_recursive_warns(self):
        result = guard.judge_command("rm -rf /tmp/logs/*.log")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H8_GLOB_RECURSIVE", codes)

    def test_ancestor_of_cwd_blocked(self):
        with tempfile.TemporaryDirectory() as base:
            child = os.path.join(base, "child")
            os.makedirs(child)
            result = guard.judge_command(f"rm -rf {base}", cwd=child)
            codes = [h["code"] for h in result["hazards"]]
            self.assertIn("H7_ANCESTOR_OF_CWD", codes)
            self.assertEqual(result["verdict"], "block")

    def test_non_windows_host_declares_unknowns(self):
        if os.name == "nt":
            self.skipTest("仅在非 Windows 宿主上断言 unknown 声明")
        result = guard.judge_command("rm -rf ./build")
        self.assertTrue(result["unknowns"], "非 Windows 宿主必须声明未验证项")

    def test_result_is_json_serializable(self):
        result = guard.judge_command("rm -rf /tmp/x")
        json.dumps(result, ensure_ascii=False)


class AllowPathTests(unittest.TestCase):
    """反例：这些不该 block。防止工具变成「什么都拦」的噪声发生器。"""

    def test_plain_relative_rm_allows(self):
        result = guard.judge_command("rm -rf ./build")
        self.assertEqual(result["verdict"], "warn")  # 仅 H9 永久删除提示

    def test_move_allows(self):
        result = guard.judge_command('mv "a b.txt" "d b.txt"')
        self.assertNotEqual(result["verdict"], "block")

    def test_non_delete_command_allowed(self):
        result = guard.judge_command("git status")
        self.assertEqual(result["verdict"], "allow")
        self.assertEqual(result["hazards"], [])

    def test_reading_files_not_flagged(self):
        result = guard.judge_command("cat D:\\data\\report.txt")
        self.assertEqual(result["verdict"], "allow")


if __name__ == "__main__":
    unittest.main()
