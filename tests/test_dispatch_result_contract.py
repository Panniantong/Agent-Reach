"""Backend results must be list[dict]; anything else is UPSTREAM_BROKEN, never fake success.

A backend that returns a str used to be mangled character-by-character into
items with ok=True, a dict became its key list, non-dict elements passed
through untouched, and None became an empty success. The envelope is the
agent-facing contract, so malformed results are rejected at the dispatch
boundary and the next backend is tried.
"""

from agent_reach.channels.base import Action, Channel, Param
from agent_reach.runtime.dispatch import run_action


def _channel(name, results):
    """A fake channel whose backends return the given values, in order."""
    attrs = {"name": name}
    pairs = []
    for index, value in enumerate(results):
        method = f"_backend_{index}"
        pairs.append((f"b{index}", method))

        def _make(v):
            def _backend(self, *, query, timeout):
                return v

            return _backend

        attrs[method] = _make(value)
    attrs["actions"] = (Action("go", "go", (Param("query", "q"),), tuple(pairs)),)

    def can_handle(self, url):
        return False

    attrs["can_handle"] = can_handle
    return type(f"Fake{name}", (Channel,), attrs)()


def test_str_result_is_broken_not_mangled_into_items():
    out = run_action(_channel("StrOnly", ["hello"]), "go", {"query": "x"}, timeout=5)
    assert not out["ok"]
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    assert out["items"] == []
    # The message names types only; it must not embed the raw return value.
    assert "hello" not in out["error"]["message"]


def test_str_result_falls_back_to_next_backend():
    good = [{"title": "real", "url": "https://example.com"}]
    out = run_action(_channel("StrFallback", ["hello", good]), "go", {"query": "x"}, timeout=5)
    assert out["ok"], out
    assert out["backend"] == "b1"
    assert out["items"] == good
    attempts = out["meta"]["attempts"]
    assert attempts[0]["backend"] == "b0" and attempts[0]["result"] == "UPSTREAM_BROKEN"
    assert attempts[1]["backend"] == "b1" and attempts[1]["result"] == "ok"


def test_dict_result_is_broken_not_a_key_list():
    out = run_action(_channel("DictOnly", [{"title": "t", "url": "u"}]), "go", {"query": "x"}, timeout=5)
    assert not out["ok"]
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    assert out["items"] == []


def test_list_with_non_dict_element_is_broken():
    out = run_action(_channel("BadItems", [[{"title": "t"}, 42]]), "go", {"query": "x"}, timeout=5)
    assert not out["ok"]
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    assert out["items"] == []


def test_none_result_is_broken_not_empty_success():
    out = run_action(_channel("NoneOnly", [None]), "go", {"query": "x"}, timeout=5)
    assert not out["ok"]
    assert out["error"]["code"] == "UPSTREAM_BROKEN"
    assert out["items"] == []


def test_valid_list_of_dicts_passes_through_unchanged():
    items = [{"title": "a"}, {"title": "b", "raw": {"n": 1}}]
    out = run_action(_channel("Good", [items]), "go", {"query": "x"}, timeout=5)
    assert out["ok"], out
    assert out["items"] == items
    assert out["error"] is None


def test_empty_list_is_a_valid_empty_success():
    out = run_action(_channel("Empty", [[]]), "go", {"query": "x"}, timeout=5)
    assert out["ok"], out
    assert out["items"] == []
    assert out["error"] is None
