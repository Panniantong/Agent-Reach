# -*- coding: utf-8 -*-

from unittest.mock import patch

import agent_reach.cli as cli


class _DummyConfig:
    def get(self, _key):
        return None


def test_install_xiaoyuzhou_deps_does_not_raise_when_no_groq_key(capsys):
    with patch("agent_reach.config.Config", return_value=_DummyConfig()), \
         patch("os.path.isfile", side_effect=lambda p: True if str(p).endswith("transcribe.sh") else False), \
         patch("shutil.which", return_value=None):
        cli._install_xiaoyuzhou_deps()

    out = capsys.readouterr().out
    assert "Xiaoyuzhou" in out
    assert "Groq API key not set" in out
