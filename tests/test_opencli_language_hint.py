"""OpenCLI waits for English page text; a non-English account looks like a broken platform without a hint."""

import json

from agent_reach.backends.opencli import _opencli_error
from agent_reach.runtime.result import UPSTREAM_BROKEN

LOGIN_HINT = "reach login steps"


def _envelope(message: str, *, code: str = "COMMAND_EXEC", help_text: str = "") -> str:
    help_line = f"  help: {help_text}\n" if help_text else ""
    return f"ok: false\nerror:\n  code: {code}\n  message: {json.dumps(message)}\n{help_line}"


def test_missing_page_text_points_at_the_account_language():
    err = _opencli_error(_envelope("Error: Text not found: Jobs"), LOGIN_HINT)
    assert err.code == UPSTREAM_BROKEN  # still lets the dispatcher try the next backend
    assert err.message == "Error: Text not found: Jobs"
    assert "English" in (err.hint or "")


def test_an_upstream_hint_is_kept_over_the_language_hint():
    err = _opencli_error(
        _envelope("Text not found: Jobs", help_text="Reload the page."), LOGIN_HINT
    )
    assert err.hint == "Reload the page."


def test_other_upstream_errors_get_no_language_hint():
    err = _opencli_error(_envelope("Selector not found: .jobs-list"), LOGIN_HINT)
    assert err.hint is None
