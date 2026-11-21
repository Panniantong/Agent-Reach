"""The test process guard must remain compatible with standard subprocess users."""

import subprocess
import sys

import pytest


def test_asyncio_can_run_a_local_command_with_the_guard():
    import asyncio

    async def run():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "print('ok')", stdout=subprocess.PIPE,
        )
        output, _ = await process.communicate()
        assert process.returncode == 0
        assert output.strip() == b"ok"

    asyncio.run(run())


def test_guard_still_blocks_unmocked_pip_install():
    with pytest.raises(pytest.fail.Exception, match="Unmocked pip install"):
        subprocess.run([sys.executable, "-m", "pip", "install", "example"])
