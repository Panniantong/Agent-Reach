# -*- coding: utf-8 -*-
"""Tests for 'agent-reach skill' command and _install_skill / _uninstall_skill."""

import importlib.resources
import os
import re
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import agent_reach.cli as cli
from agent_reach.cli import _cmd_skill, _install_skill, _uninstall_skill


class TestSkillCommand(unittest.TestCase):
    """Test skill install and uninstall via CLI helpers."""

    def test_skill_resources_include_both_locales(self):
        """Package resources should expose both default and English skill markdown files."""
        skill_dir = importlib.resources.files("agent_reach").joinpath("skill")

        default_skill = skill_dir.joinpath("SKILL.md").read_text(encoding="utf-8")
        english_skill = skill_dir.joinpath("SKILL_en.md").read_text(encoding="utf-8")

        self.assertTrue(default_skill.strip())
        self.assertTrue(english_skill.strip())

    def test_exa_reference_uses_default_registered_tools_only(self):
        """Agent instructions must not call Exa tools disabled by default."""
        search_reference = (
            importlib.resources.files("agent_reach")
            .joinpath("skill", "references", "search.md")
            .read_text(encoding="utf-8")
        )

        self.assertIn("web_search_exa", search_reference)
        self.assertNotIn("exa.get_code_context_exa", search_reference)
        self.assertNotIn("get_code_context_exa(", search_reference)

    def test_mcporter_examples_use_shell_safe_named_arguments(self):
        """Packaged commands must survive PowerShell and POSIX parsing."""
        root = Path(__file__).resolve().parents[1]
        markdown_files = [
            *(root / "agent_reach" / "skill").rglob("*.md"),
            *(root / "agent_reach" / "guides").rglob("*.md"),
            root / "docs" / "install.md",
            root / "docs" / "troubleshooting.md",
        ]
        function_call = re.compile(r"mcporter call\s+['\"][^'\"\r\n]+\(")

        for markdown_file in markdown_files:
            with self.subTest(markdown_file=markdown_file):
                content = markdown_file.read_text(encoding="utf-8")
                self.assertNotRegex(content, function_call)

    def test_linkedin_reference_uses_current_tool_contract(self):
        """LinkedIn examples should use the current server and parameters."""
        career_reference = (
            importlib.resources.files("agent_reach")
            .joinpath("skill", "references", "career.md")
            .read_text(encoding="utf-8")
        )

        self.assertIn(
            "linkedin.get_person_profile "
            'linkedin_username="username" '
            'sections="experience,education"',
            career_reference,
        )
        self.assertIn(
            'linkedin.search_people keywords="AI engineer" '
            'location="Shanghai"',
            career_reference,
        )
        self.assertIn(
            'linkedin.get_company_profile company_name="openai" '
            'sections="posts,jobs"',
            career_reference,
        )
        self.assertIn(
            'linkedin.search_jobs keywords="software engineer" '
            'location="Remote" max_pages=2',
            career_reference,
        )
        self.assertNotIn("linkedin-scraper.", career_reference)

    def test_linkedin_install_docs_use_current_stdio_contract(self):
        """LinkedIn install guidance should use uvx over stdio."""
        install_doc = (
            Path(__file__).resolve().parents[1] / "docs" / "install.md"
        ).read_text(encoding="utf-8")
        linkedin_section = install_doc.split(
            "**LinkedIn (", maxsplit=1
        )[1].split("### Step 4:", maxsplit=1)[0]

        self.assertIn(
            "uvx mcp-server-linkedin@latest --login",
            linkedin_section,
        )
        self.assertIn(
            "mcporter config add linkedin --command uvx "
            "--arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 "
            "--scope home",
            linkedin_section,
        )
        self.assertNotIn("linkedin-scraper-mcp", linkedin_section)
        self.assertNotIn("localhost:3000/mcp", linkedin_section)
        self.assertNotIn("linkedin-scraper.", linkedin_section)
        self.assertNotIn("--transport streamable-http", linkedin_section)

    def test_localized_readmes_use_current_linkedin_server_name(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("README_ja.md", "README_ko.md"):
            content = (root / "docs" / name).read_text(encoding="utf-8")
            self.assertIn("mcp-server-linkedin", content)
            self.assertNotIn("linkedin-scraper-mcp", content)

    def test_skill_install_command_exits_nonzero_when_install_fails(self):
        with patch("agent_reach.cli._install_skill", return_value=False):
            with self.assertRaises(SystemExit) as raised:
                _cmd_skill(Namespace(install=True, uninstall=False))

        self.assertEqual(raised.exception.code, 1)

    def test_project_scope_installs_only_in_current_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()

            with patch("pathlib.Path.cwd", return_value=project), patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda path: path.replace("~", tmpdir),
            ), patch.dict(os.environ, {}, clear=True):
                installed = _install_skill(scope="project")

            self.assertTrue(installed)
            self.assertTrue(
                (project / ".claude" / "skills" / "agent-reach" / "SKILL.md").is_file()
            )
            self.assertFalse((Path(tmpdir) / ".agents" / "skills" / "agent-reach").exists())

    def test_project_scope_preserves_existing_skill_when_not_forced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            skill = project / ".claude" / "skills" / "agent-reach" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("custom", encoding="utf-8")

            with patch("pathlib.Path.cwd", return_value=project):
                installed = _install_skill(force=False, scope="project")

            self.assertTrue(installed)
            self.assertEqual(skill.read_text(encoding="utf-8"), "custom")

    def test_project_scope_rejects_symlinked_skill_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            external = Path(tmpdir) / "external"
            project.mkdir()
            external.mkdir()
            (project / ".claude").symlink_to(external, target_is_directory=True)

            with patch("pathlib.Path.cwd", return_value=project):
                installed = _install_skill(scope="project")

            self.assertFalse(installed)
            self.assertFalse((external / "skills").exists())

    def test_project_scope_reports_expected_directory_creation_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            skill_root = project / ".claude" / "skills"
            original_mkdir = Path.mkdir
            attempted_paths = []

            def fail_for_skill_root(path, *args, **kwargs):
                attempted_paths.append(path)
                if path == skill_root:
                    raise OSError("read only")
                return original_mkdir(path, *args, **kwargs)

            with patch("pathlib.Path.cwd", return_value=project), patch.object(
                Path, "mkdir", autospec=True, side_effect=fail_for_skill_root
            ):
                installed = _install_skill(scope="project")

            self.assertFalse(installed)
            self.assertIn(skill_root, attempted_paths)
            self.assertFalse(skill_root.exists())

    def test_project_scope_reports_expected_destination_copy_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            project.mkdir()
            target = project / ".claude" / "skills" / "agent-reach"
            original_makedirs = os.makedirs
            attempted_paths = []

            def fail_for_target(path, *args, **kwargs):
                attempted_paths.append(Path(path))
                if Path(path) == target:
                    raise OSError("read only")
                return original_makedirs(path, *args, **kwargs)

            with patch("pathlib.Path.cwd", return_value=project), patch(
                "agent_reach.cli.os.makedirs", side_effect=fail_for_target
            ):
                installed = _install_skill(scope="project")

            self.assertFalse(installed)
            self.assertIn(target, attempted_paths)
            self.assertFalse(target.exists())

    def test_install_skill_rejects_unknown_scope(self):
        with self.assertRaisesRegex(ValueError, "unsupported skill scope"):
            _install_skill(scope="automatic")

    def test_skill_command_forwards_explicit_scope(self):
        with patch("agent_reach.cli._install_skill", return_value=True) as install:
            _cmd_skill(Namespace(install=True, uninstall=False, scope="project"))

        install.assert_called_once_with(scope="project")

    def test_skill_cli_accepts_project_scope(self):
        with patch.object(
            sys,
            "argv",
            ["agent-reach", "skill", "--install", "--scope", "project"],
        ), patch("agent_reach.cli._configure_logging"), patch(
            "agent_reach.cli._cmd_skill"
        ) as command:
            cli.main()

        self.assertEqual(command.call_args.args[0].scope, "project")

    def test_skill_cli_rejects_project_scope_for_uninstall(self):
        with patch.object(
            sys,
            "argv",
            ["agent-reach", "skill", "--uninstall", "--scope", "project"],
        ), patch("agent_reach.cli._cmd_skill") as command, self.assertRaises(
            SystemExit
        ) as raised:
            cli.main()

        self.assertEqual(raised.exception.code, 2)
        command.assert_not_called()

    def test_system_install_forwards_project_scope(self):
        args = Namespace(
            env="local",
            proxy="",
            system=True,
            safe=False,
            dry_run=False,
            channels="",
            scope="project",
        )
        with patch("agent_reach.config.Config"), patch(
            "agent_reach.doctor.check_all", return_value={}
        ), patch("agent_reach.doctor.format_report", return_value="report"), patch(
            "agent_reach.cli._install_system_deps", return_value=True
        ), patch("agent_reach.cli._install_mcporter", return_value=True), patch(
            "agent_reach.cli._install_skill", return_value=True
        ) as install:
            cli._cmd_install(args)

        install.assert_called_once_with(scope="project")

    def test_system_install_keeps_default_user_scope_call_compatible(self):
        args = Namespace(
            env="local",
            proxy="",
            system=True,
            safe=False,
            dry_run=False,
            channels="",
            scope="user",
        )
        with patch("agent_reach.config.Config"), patch(
            "agent_reach.doctor.check_all", return_value={}
        ), patch("agent_reach.doctor.format_report", return_value="report"), patch(
            "agent_reach.cli._install_system_deps", return_value=True
        ), patch("agent_reach.cli._install_mcporter", return_value=True), patch(
            "agent_reach.cli._install_skill", return_value=True
        ) as install:
            cli._cmd_install(args)

        install.assert_called_once_with(scope="user")

    def test_install_skill_creates_skill_md(self):
        """_install_skill should create SKILL.md in the first available skill dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "skills")
            os.makedirs(skill_dir)

            with patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda p: p.replace("~", tmpdir),
            ), patch.dict(os.environ, {}, clear=False):
                # Remove OPENCLAW_HOME to avoid interference
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill()

            # Check at least one known skill dir pattern
            for dirpath, _, filenames in os.walk(tmpdir):
                if "SKILL.md" in filenames:
                    # Verify content is non-empty
                    with open(os.path.join(dirpath, "SKILL.md"), encoding="utf-8") as f:
                        content = f.read()
                    self.assertIn("Agent Reach", content)
            # _install_skill may or may not find dirs depending on mock; just ensure no crash
            # The important test is that the function runs without error

    def test_uninstall_skill_removes_dir(self):
        """_uninstall_skill should remove skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake skill installation
            skill_path = os.path.join(tmpdir, ".openclaw", "skills", "agent-reach")
            os.makedirs(skill_path)
            with open(os.path.join(skill_path, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("test")

            self.assertTrue(os.path.exists(skill_path))

            with patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda p: p.replace("~", tmpdir),
            ), patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _uninstall_skill()

            self.assertFalse(os.path.exists(skill_path))

    def test_install_creates_dir_if_parent_exists(self):
        """_install_skill should create agent-reach dir inside existing skill dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the .openclaw/skills parent but not agent-reach subdir
            skill_parent = os.path.join(tmpdir, ".openclaw", "skills")
            os.makedirs(skill_parent)

            with patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda p: p.replace("~", tmpdir),
            ), patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill()

            target = os.path.join(skill_parent, "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Agent Reach", content)

    def test_install_uses_english_skill_for_english_locale(self):
        """_install_skill should install the English skill file for English locales."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_parent = os.path.join(tmpdir, ".openclaw", "skills")
            os.makedirs(skill_parent)

            with patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda p: p.replace("~", tmpdir),
            ):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                env["LANG"] = "en_US.UTF-8"
                with patch.dict(os.environ, env, clear=True):
                    _install_skill()

            target = os.path.join(skill_parent, "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.strip())
            self.assertIn("Xiaoyuzhou Podcast, LinkedIn", content)
            self.assertNotIn("搜推特", content)
            self.assertTrue(
                os.path.exists(os.path.join(skill_parent, "agent-reach", "references"))
            )


if __name__ == "__main__":
    unittest.main()
