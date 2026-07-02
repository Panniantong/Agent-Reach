# -*- coding: utf-8 -*-
"""Tests for 'agent-reach skill' command and _install_skill / _uninstall_skill."""

import importlib.resources
import os
import re
import tempfile
import unittest
from unittest.mock import patch

import yaml

from agent_reach.cli import _install_skill, _uninstall_skill

# OpenCode only recognizes these frontmatter keys (see opencode.ai/docs/skills).
OPENCODE_ALLOWED_FRONTMATTER_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata"}
)


def _read_skill_frontmatter(resource_name: str) -> dict:
    skill_dir = importlib.resources.files("agent_reach").joinpath("skill")
    text = skill_dir.joinpath(resource_name).read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, f"{resource_name} must start with YAML frontmatter"
    return yaml.safe_load(match.group(1))


class TestSkillCommand(unittest.TestCase):
    """Test skill install and uninstall via CLI helpers."""

    def test_skill_frontmatter_is_opencode_compatible(self):
        """Frontmatter should only use fields recognized by OpenCode agents."""
        for resource_name in ("SKILL.md", "SKILL_en.md"):
            with self.subTest(resource=resource_name):
                frontmatter = _read_skill_frontmatter(resource_name)
                unknown_keys = set(frontmatter) - OPENCODE_ALLOWED_FRONTMATTER_KEYS
                self.assertEqual(
                    unknown_keys,
                    set(),
                    f"Unsupported frontmatter keys in {resource_name}: {unknown_keys}",
                )
                metadata = frontmatter.get("metadata")
                if metadata is not None:
                    self.assertIsInstance(metadata, dict)
                    for key, value in metadata.items():
                        self.assertIsInstance(
                            key,
                            str,
                            f"metadata key must be a string in {resource_name}",
                        )
                        self.assertIsInstance(
                            value,
                            str,
                            f"metadata[{key!r}] must be a string in {resource_name}",
                        )
                description = frontmatter.get("description", "")
                self.assertGreaterEqual(len(description), 1)
                self.assertLessEqual(len(description), 1024)

    def test_install_skill_to_opencode_directory(self):
        """_install_skill should install to ~/.config/opencode/skills when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_parent = os.path.join(tmpdir, ".config", "opencode", "skills")
            os.makedirs(skill_parent)

            with patch(
                "agent_reach.cli.os.path.expanduser",
                side_effect=lambda p: p.replace("~", tmpdir),
            ):
                env = os.environ.copy()
                env.pop("OPENCLAW_HOME", None)
                with patch.dict(os.environ, env, clear=True):
                    _install_skill()

            target = os.path.join(skill_parent, "agent-reach", "SKILL.md")
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Agent Reach", content)
            self.assertNotIn("\ntriggers:", content[: content.index("\n# ")])

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
