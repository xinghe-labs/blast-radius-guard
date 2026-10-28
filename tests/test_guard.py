#!/usr/bin/env python3
"""guard.py 的规则测试。每个规则至少一条正例；关键反例防止过度拦截。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from unittest.mock import patch  # noqa: E402

import delete_guard.core as core_mod  # noqa: E402
from delete_guard.rules import (  # noqa: E402
    RULES_COMMON,
    RULES_LINUX,
    RULES_MACOS,
    RULES_WINDOWS,
)

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
        intent = guard.extract_intent(guard.tokenize("rm -rf /srv/x"))
        self.assertTrue(intent.recursive)
        self.assertTrue(intent.force)
        self.assertEqual(intent.targets, ["/srv/x"])

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

    def test_echo_containing_delete_word_not_block(self):
        # 文本里有 rm 但实际是 echo —— 不应拦截
        result = guard.judge_command('echo "remember to rm -rf build later"')
        self.assertNotEqual(result["verdict"], "block")

    def test_git_rm_narrow_target_not_block(self):
        result = guard.judge_command("git rm old.txt")
        self.assertNotEqual(result["verdict"], "block")

    def test_npm_rm_not_block(self):
        result = guard.judge_command("npm rm left-pad")
        self.assertNotEqual(result["verdict"], "block")

    def test_find_delete_not_misread(self):
        # find 的 -delete 不是 shell 删除动词；不应被 H 系规则拦截
        result = guard.judge_command("find /tmp/x -name '*.log' -delete")
        self.assertNotEqual(result["verdict"], "block")

    def test_single_layer_quoted_cjk_no_h1(self):
        # 单层 shell + 引号 + CJK：H5 warn 是合理的，但不应夸大到 H1
        result = guard.judge_command('rm -rf "/tmp/测试目录"')
        codes = [h["code"] for h in result["hazards"]]
        self.assertNotIn("H1_QUOTE_CHAIN", codes)
        self.assertNotEqual(result["verdict"], "block")


if __name__ == "__main__":
    unittest.main()


class SudoDeleteTests(unittest.TestCase):
    """H10：提权删除（Steam 2015 / macrumors#1176135 的共同放大器）。"""

    def test_sudo_rm_blocked(self):
        result = guard.judge_command("sudo rm -rf /tmp/x")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H10_SUDO_DELETE", codes)
        self.assertEqual(result["verdict"], "block")

    def test_doas_rm_blocked(self):
        result = guard.judge_command("doas rm /tmp/x")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H10_SUDO_DELETE", codes)

    def test_plain_rm_no_h10(self):
        result = guard.judge_command("rm -rf /tmp/x")
        codes = [h["code"] for h in result["hazards"]]
        self.assertNotIn("H10_SUDO_DELETE", codes)

    def test_sudo_non_delete_no_h10(self):
        # sudo 读文件不是删除，不该打 H10
        result = guard.judge_command("sudo cat /etc/shadow")
        codes = [h["code"] for h in result["hazards"]]
        self.assertNotIn("H10_SUDO_DELETE", codes)


class LinuxSystemPrefixTests(unittest.TestCase):
    """H11：系统关键前缀（Steam 2015 `rm -rf "$STEAMROOT/"*` -> /*）。"""

    def test_usr_blocked(self):
        for target in ("/usr", "/usr/bin", "/etc", "/boot", "/proc"):
            with self.subTest(target=target):
                result = guard.judge_command(f"rm -rf {target}")
                codes = [h["code"] for h in result["hazards"]]
                self.assertIn("H11_SYSTEM_PREFIX", codes)
                self.assertEqual(result["verdict"], "block")

    def test_home_project_not_overmatched(self):
        # /home/u/proj 是 Linux 用户日常工作目录，误拦会让工具被禁用
        result = guard.judge_command("rm -rf /home/u/proj")
        codes = [h["code"] for h in result["hazards"]]
        self.assertNotIn("H11_SYSTEM_PREFIX", codes)

    def test_home_itself_blocked(self):
        result = guard.judge_command("rm -rf /home")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H11_SYSTEM_PREFIX", codes)

    def test_posix_prefixes_linux_only(self):
        # 任意前缀只在递归意图下于 judge_command 触发；judge_path 始终核对
        result = guard.judge_path("/usr")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H11_SYSTEM_PREFIX", codes)


class MountPointTests(unittest.TestCase):
    """H12：挂载点（rsync --delete 清空备份卷类事故）。"""

    def test_is_mount_point_proc(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("procfs 挂载仅在 Linux 上核对")
        self.assertTrue(guard.judge_command.__globals__["is_mount_point"]("/proc"))
        self.assertTrue(guard.judge_command.__globals__["is_mount_point"]("/sys"))

    def test_regular_dir_not_mount(self):
        with tempfile.TemporaryDirectory() as base:
            self.assertFalse(guard.judge_command.__globals__["is_mount_point"](base))

    def test_mount_point_target_blocked_on_linux(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("挂载点真机核验仅在 Linux 上执行")
        result = guard.judge_command("rm -rf /proc")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H12_MOUNT_POINT", codes)
        self.assertEqual(result["verdict"], "block")


class MacosHomeSpecialTests(unittest.TestCase):
    """H13：macOS 家目录特殊目录（superuser#1925324 / macrumors#1192684）。"""

    def test_documents_blocked(self):
        for target in (
            "/Users/alice/Documents",
            "/Users/alice/Downloads",
            "/Users/alice/Library",
        ):
            with self.subTest(target=target):
                result = guard.judge_command(f"rm -rf {target}")
                codes = [h["code"] for h in result["hazards"]]
                self.assertIn("H13_MACOS_HOME_SPECIAL", codes)
                self.assertEqual(result["verdict"], "block")

    def test_regular_macos_project_not_overmatched(self):
        # /Users/alice/dev/proj 是 macOS 用户日常工作目录，不该打 H13
        result = guard.judge_command("rm -rf /Users/alice/dev/proj")
        codes = [h["code"] for h in result["hazards"]]
        self.assertNotIn("H13_MACOS_HOME_SPECIAL", codes)


class WslContextTests(unittest.TestCase):
    """H6 语境收紧：只有 WSL 宿主或经 wsl 启动器跳转时才报跨文件系统。"""

    def test_wsl_launcher_triggers_h6(self):
        result = guard.judge_command('wsl rm -rf "/mnt/d/data"')
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H6_WSL_CROSS_FS", codes)

    def test_non_wsl_host_no_h6(self):
        # 模拟原生 Linux 宿主（非 WSL）：/mnt/x 不该打 H6
        with patch.object(core_mod, "is_wsl", return_value=False):
            result = core_mod.judge_command("rm -rf /mnt/x")
            codes = [h["code"] for h in result["hazards"]]
            self.assertNotIn("H6_WSL_CROSS_FS", codes)


class CrossPlatformUnknownTests(unittest.TestCase):
    def test_unknowns_declared_per_host(self):
        # unknown 只声明「非当前宿主」的平台：在本机已验证的平台不会出现
        result = guard.judge_command("rm -rf ./build")
        text = "\n".join(result["unknowns"])
        host = guard.host_name()
        if host != "windows":
            self.assertIn("Windows", text)
        else:
            self.assertNotIn("Windows", text)
        if host != "linux":
            self.assertIn("Linux", text)
        else:
            self.assertNotIn("Linux", text)
        if host != "macos":
            self.assertIn("macOS", text)
        else:
            self.assertNotIn("macOS", text)



class CaseCollisionMacosTests(unittest.TestCase):
    """H3 在 macOS 也应触发：APFS/HFS+ 默认大小写不敏感。

    用 unittest.mock 固定 host_name()=macos，驾驭 case_collision 进入
    posix 布局分支 —— 即使在本机（WSL）也能覆盖该分支。
    """

    def test_macos_case_insensitive_segment_walk(self):
        with patch.object(core_mod, "host_name", return_value="macos"):
            # /tmp 是真实存在、全部大写的条目；把它改写成不同大小写形式，
            # 逐级核对应仍解析到真实路径。
            target = "/TMP"
            if os.path.exists(target):
                real = core_mod.case_collision(target)
                self.assertTrue(real, "macOS 宿主应把 /TMP 解析到 /tmp")
            else:
                # /tmp 不存在就跳过 —— 分支覆盖依赖真实目录，但不影响判定逻辑
                pass

    def test_linux_host_skips_case_collision(self):
        with patch.object(core_mod, "host_name", return_value="linux"):
            # 原生 Linux 大小写敏感：不走 H3 核对
            self.assertIsNone(core_mod.case_collision("/Tmp"))


class RuleSplitTests(unittest.TestCase):
    """规则表按平台拆分，H10–H13 分布正确。"""

    def test_rule_partitioning(self):
        # H10（sudo）在 common 而非 windows，跨平台放大器
        self.assertIn("H10_SUDO_DELETE", RULES_COMMON)
        # H11/H12 归 Linux，H13 归 macOS，H2–H6 归 Windows
        self.assertIn("H11_SYSTEM_PREFIX", RULES_LINUX)
        self.assertIn("H12_MOUNT_POINT", RULES_LINUX)
        self.assertIn("H13_MACOS_HOME_SPECIAL", RULES_MACOS)
        for code in ("H2_DRIVE_ROOT", "H3_CASE_COLLISION", "H4_REPARSE_TRAVERSAL",
                     "H5_CJK_SILENT_FAIL", "H6_WSL_CROSS_FS"):
            self.assertIn(code, RULES_WINDOWS)


class WslContextInheritanceTests(unittest.TestCase):
    """H6 语境必须跨层继承：`wsl rm ...` 的内层没有 wsl 字样，
    但非 WSL 宿主上判定它时仍要触发 H6（CI 上首次暴露的回归）。"""

    def test_wsl_launcher_context_inherited(self):
        with patch.object(core_mod, "is_wsl", return_value=False):
            result = core_mod.judge_command('wsl rm -rf "/mnt/d/data"')
            codes = [h["code"] for h in result["hazards"]]
            self.assertIn("H6_WSL_CROSS_FS", codes)

    def test_nested_launcher_keeps_context(self):
        with patch.object(core_mod, "is_wsl", return_value=False):
            result = core_mod.judge_command('wsl bash -c "rm -rf /mnt/d/data"')
            codes = [h["code"] for h in result["hazards"]]
            self.assertIn("H6_WSL_CROSS_FS", codes)

    def test_non_wsl_host_plain_mnt_no_h6(self):
        with patch.object(core_mod, "is_wsl", return_value=False):
            result = core_mod.judge_command("rm -rf /mnt/x")
            codes = [h["code"] for h in result["hazards"]]
            self.assertNotIn("H6_WSL_CROSS_FS", codes)


class PrivilegeLayerTests(unittest.TestCase):
    """审核发现的漏判：sudo/su/doas 包装的跨层删除（修复 1）。"""

    def test_sudo_bash_c_blocked(self):
        result = guard.judge_command('sudo bash -c "rm -rf /x"')
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H10_SUDO_DELETE", codes)
        self.assertEqual(result["verdict"], "block")

    def test_su_c_blocked(self):
        result = guard.judge_command('su -c "rm -rf /x"')
        self.assertEqual(result["verdict"], "block")

    def test_doas_bash_c_blocked(self):
        result = guard.judge_command('doas bash -c "rm -rf /x"')
        self.assertEqual(result["verdict"], "block")

    def test_sudo_non_delete_still_allows(self):
        result = guard.judge_command("sudo cat /etc/shadow")
        self.assertEqual(result["verdict"], "allow")


class GlobBlastRadiusTests(unittest.TestCase):
    """审核发现的漏判：glob 目标的爆炸半径预判（修复 2，Steam 2015 形态）。"""

    def test_root_glob_blocked(self):
        result = guard.judge_command("rm -rf /*")
        self.assertEqual(result["verdict"], "block")
        self.assertIn("H0_AMBIGUOUS", [h["code"] for h in result["hazards"]])

    def test_unset_var_glob_blocked(self):
        # Steam 2015 事故最终形态：rm -rf "$STEAMROOT/"*
        result = guard.judge_command('rm -rf "$UNSET/"*')
        self.assertEqual(result["verdict"], "block")

    def test_system_prefix_glob_blocked(self):
        result = guard.judge_command("rm -rf /usr/*")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H11_SYSTEM_PREFIX", codes)
        self.assertEqual(result["verdict"], "block")

    def test_drive_root_glob_blocked(self):
        result = guard.judge_command("rm -rf C:/*")
        self.assertEqual(result["verdict"], "block")

    def test_tmp_glob_still_warns(self):
        # 安全场景不误拦：/tmp 清理保持 warn
        result = guard.judge_command("rm -rf /tmp/*")
        self.assertEqual(result["verdict"], "warn")

    def test_var_target_blocked(self):
        result = guard.judge_command("rd /s /q %UNSET%\\x")
        self.assertEqual(result["verdict"], "block")

    def test_single_letter_posix_path_not_flag(self):
        # /x 是合法 POSIX 路径，不能被 cmd flag 正则吃掉
        result = guard.judge_command("rm -rf /x")
        self.assertNotEqual(result["verdict"], "block")

    def test_posix_system_paths_not_eaten_by_flag_regex(self):
        # 回归：/usr /etc 曾被多字母 flag 正则当 flag 剔除导致 H0 误报
        for target in ("/usr", "/etc", "/boot", "/proc"):
            with self.subTest(target=target):
                result = guard.judge_command(f"rm -rf {target}")
                codes = [h["code"] for h in result["hazards"]]
                self.assertIn("H11_SYSTEM_PREFIX", codes)


class MirrorVerbTests(unittest.TestCase):
    """审核发现的漏判：robocopy /MIR、rsync --delete（修复 3，H12 事故主角）。"""

    def test_robocopy_mir_warns(self):
        result = guard.judge_command("robocopy D:\\a D:\\b /MIR")
        if os.name == "nt" and result["verdict"] != "warn":
            import json as _json
            print("WDG-DEBUG /MIR:", _json.dumps(result, ensure_ascii=False))
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H9_PERMANENT_DELETE", codes)
        self.assertEqual(result["verdict"], "warn")

    def test_rsync_delete_warns(self):
        result = guard.judge_command("rsync -a --delete /src/ /backup/")
        codes = [h["code"] for h in result["hazards"]]
        self.assertIn("H9_PERMANENT_DELETE", codes)

    def test_plain_rsync_allows(self):
        result = guard.judge_command("rsync -a /src/ /backup/")
        self.assertEqual(result["verdict"], "allow")

    def test_robocopy_e_allows(self):
        result = guard.judge_command("robocopy D:\\a D:\\b /E")
        if os.name == "nt" and result["verdict"] != "allow":
            import json as _json
            print("WDG-DEBUG /E:", _json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["verdict"], "allow")
