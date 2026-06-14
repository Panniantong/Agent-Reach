# -*- coding: utf-8 -*-
"""Tests for agent_reach.utils.paths.make_private_dir and Config dir perms."""

import os
import stat
import sys

import pytest

from agent_reach.config import Config
from agent_reach.utils.paths import make_private_dir

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file modes not enforced on Windows"
)


def test_creates_directory(tmp_path):
    d = tmp_path / "a" / "b"
    out = make_private_dir(d)
    assert out.is_dir()
    assert out == d


@posix_only
def test_leaf_is_owner_only(tmp_path):
    d = tmp_path / "secrets"
    make_private_dir(d)
    mode = stat.S_IMODE(os.stat(d).st_mode)
    assert mode == 0o700


def test_idempotent_on_existing_dir(tmp_path):
    d = tmp_path / "exists"
    d.mkdir()
    # Must not raise when the dir already exists.
    make_private_dir(d)
    assert d.is_dir()


@posix_only
def test_config_dir_is_owner_only(tmp_path, monkeypatch):
    cfg_dir = tmp_path / ".agent-reach"
    cfg_path = cfg_dir / "config.yaml"
    monkeypatch.setattr(Config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", cfg_path)
    Config(config_path=cfg_path)  # __init__ calls _ensure_dir
    mode = stat.S_IMODE(os.stat(cfg_dir).st_mode)
    assert mode == 0o700
