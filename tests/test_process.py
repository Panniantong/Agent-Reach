from agent_reach.utils.process import utf8_subprocess_env


def test_utf8_subprocess_env_forces_python_utf8():
    env = utf8_subprocess_env({"PYTHONUTF8": "0", "OTHER": "value"})

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["OTHER"] == "value"
