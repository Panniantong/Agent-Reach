# -*- coding: utf-8 -*-
"""Guard against the test suite writing into the developer's real home.

Running `agent-reach doctor` auto-installs SKILL.md into every agent
directory it finds and creates ~/.agent-reach/ via Config(). Before the
conftest `_isolate_home` fixture existed, `test_doctor_runs` called the
real doctor against the real $HOME, silently installing skill files for
the developer's live AI agents just by running `pytest`.

These tests assert the isolation is actually in effect, so the leak
cannot regress unnoticed: if the fixture is removed or stops redirecting
$HOME, expanduser("~") reverts to the real home and these fail.
"""

import os
from argparse import Namespace

from agent_reach.config import Config


def test_home_is_sandboxed(_isolate_home):
    """expanduser and Config paths must resolve under the throwaway home."""
    sandbox = str(_isolate_home)
    assert os.path.expanduser("~") == sandbox
    assert str(Config().config_dir).startswith(sandbox)


def test_doctor_writes_stay_under_sandboxed_home(_isolate_home):
    """Running doctor must not touch anything outside the sandbox home.

    _install_skill only writes into agent dirs that already exist, so we
    pre-create a Claude skills dir *inside* the sandbox and confirm the
    skill lands there — proving the write is HOME-relative and therefore
    contained by the fixture rather than escaping to the real home.
    """
    from agent_reach.cli import _cmd_doctor

    claude_skills = _isolate_home / ".claude" / "skills"
    claude_skills.mkdir(parents=True)

    _cmd_doctor(Namespace(json=False))

    installed = claude_skills / "agent-reach" / "SKILL.md"
    assert installed.exists(), "skill should install under the sandboxed home"
    # And the config dir Config() created is under the sandbox, not real ~.
    assert str(Config().config_dir).startswith(str(_isolate_home))
