"""Regression coverage for the rdt-cli source pin."""

import agent_reach.channels.reddit as reddit
import agent_reach.cli as cli

RDT_REQUESTS_FIX_COMMIT = "3ff6db5c96c31dc0cf68a0431ede064903237818"
EXPECTED_RDT_GIT_SOURCE = (
    "git+https://github.com/public-clis/rdt-cli.git@" + RDT_REQUESTS_FIX_COMMIT
)


def test_rdt_cli_sources_use_requests_fix_pin_and_stay_synchronized():
    assert cli._RDT_GIT_SOURCE == EXPECTED_RDT_GIT_SOURCE
    assert reddit._RDT_GIT_SOURCE == EXPECTED_RDT_GIT_SOURCE
    assert cli._RDT_GIT_SOURCE == reddit._RDT_GIT_SOURCE
