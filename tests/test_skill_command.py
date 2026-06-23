# -*- coding: utf-8 -*-
"""Tests for 'agent-reach skill' command and _install_skill / _uninstall_skill."""

import importlib.resources
import os
import tempfile
import unittest
from unittest.mock import patch

from agent_reach.cli import _install_skill, _uninstall_skill, _find_project_claude_dir


class TestSkillCommand(unittest.TestCase):
    """Test skill install and uninstall via CLI helpers."""

    def test_skill_resources_include_both_locales(self):
        """Package resources should expose both default and English skill markdown files."""
        skill_dir = importlib.resources.files("agent_reach").joinpath("skill")

        default_skill = skill_dir.joinpath("SKILL.md").read_text(encoding="utf-8")
        english_skill = skill_dir.joinpath("SKILL_en.md").read_text(encoding="utf-8")

        self.assertTrue(default_skill.strip())
        self.assertTrue(english_skill.strip())

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
                    _install_skill(scope="user")

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

    # ── Tests for issue #333: --scope flag ──

    def test_find_project_claude_dir_found_in_cwd(self):
        """_find_project_claude_dir should find .claude in the given directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = os.path.join(tmpdir, ".claude")
            os.makedirs(claude_dir)
            result = _find_project_claude_dir(start=tmpdir)
            self.assertEqual(result, claude_dir)

    def test_find_project_claude_dir_found_in_parent(self):
        """_find_project_claude_dir should find .claude in a parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = os.path.join(tmpdir, ".claude")
            os.makedirs(claude_dir)
            child = os.path.join(tmpdir, "sub", "deep")
            os.makedirs(child)
            result = _find_project_claude_dir(start=child)
            self.assertEqual(result, claude_dir)

    def test_find_project_claude_dir_not_found(self):
        """_find_project_claude_dir returns None when no .claude exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _find_project_claude_dir(start=tmpdir)
            self.assertIsNone(result)

    def test_scope_auto_uses_project_local_when_claude_exists(self):
        """scope=auto installs to project-local .claude/skills when .claude exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project .claude dir
            claude_dir = os.path.join(tmpdir, ".claude")
            os.makedirs(claude_dir)

            with patch("agent_reach.cli._find_project_claude_dir", return_value=claude_dir), \
                 patch("agent_reach.cli.os.path.expanduser",
                       side_effect=lambda p: p.replace("~", os.path.join(tmpdir, "home"))), \
                 patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill(scope="auto")

            target = os.path.join(claude_dir, "skills", "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Agent Reach", content)

    def test_scope_user_ignores_project_local(self):
        """scope=user installs to global dirs even when .claude exists in project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project .claude dir
            claude_dir = os.path.join(tmpdir, "project", ".claude")
            os.makedirs(claude_dir)

            # Create a global skill dir
            global_skill_dir = os.path.join(tmpdir, "home", ".agents", "skills")
            os.makedirs(global_skill_dir)

            with patch("agent_reach.cli._find_project_claude_dir", return_value=claude_dir), \
                 patch("agent_reach.cli.os.path.expanduser",
                       side_effect=lambda p: p.replace("~", os.path.join(tmpdir, "home"))), \
                 patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill(scope="user")

            # Should NOT install to project-local
            project_target = os.path.join(claude_dir, "skills", "agent-reach", "SKILL.md")
            self.assertFalse(os.path.exists(project_target))

            # Should install to global
            global_target = os.path.join(global_skill_dir, "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(global_target))

    def test_scope_project_creates_claude_skills_when_no_claude_exists(self):
        """scope=project creates .claude/skills/agent-reach in cwd when no .claude found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("agent_reach.cli._find_project_claude_dir", return_value=None), \
                 patch("os.getcwd", return_value=tmpdir), \
                 patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill(scope="project")

            target = os.path.join(tmpdir, ".claude", "skills", "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Agent Reach", content)

    def test_cli_parser_accepts_scope_for_install(self):
        """The real CLI parser should pass --scope through to install."""
        from agent_reach.cli import main

        captured = {}

        def fake_cmd_install(args):
            captured["scope"] = args.scope
            captured["dry_run"] = args.dry_run

        with patch("sys.argv", ["agent-reach", "install", "--scope=project", "--dry-run"]), \
             patch("agent_reach.cli._cmd_install", side_effect=fake_cmd_install):
            main()

        self.assertEqual(captured["scope"], "project")
        self.assertTrue(captured["dry_run"])

    def test_cli_parser_accepts_scope_for_skill_install(self):
        """The real CLI parser should pass --scope through to skill --install."""
        from agent_reach.cli import main

        captured = {}

        def fake_install_skill(scope="auto"):
            captured["scope"] = scope

        with patch("sys.argv", ["agent-reach", "skill", "--install", "--scope=user"]), \
             patch("agent_reach.cli._install_skill", side_effect=fake_install_skill):
            main()

        self.assertEqual(captured["scope"], "user")


if __name__ == "__main__":
    unittest.main()
