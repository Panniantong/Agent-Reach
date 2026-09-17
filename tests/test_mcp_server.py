"""Security boundaries for the optional Agent Reach MCP server."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

import agent_reach.integrations.mcp_server as mcp_server


class _FakeServer:
    def __init__(self, name):
        self.name = name
        self.list_tools_handler = None
        self.call_tool_handler = None

    def list_tools(self):
        def register(handler):
            self.list_tools_handler = handler
            return handler

        return register

    def call_tool(self):
        def register(handler):
            self.call_tool_handler = handler
            return handler

        return register


def _install_fake_mcp(monkeypatch):
    monkeypatch.setattr(mcp_server, "HAS_MCP", True)
    monkeypatch.setattr(mcp_server, "Server", _FakeServer, raising=False)
    monkeypatch.setattr(
        mcp_server,
        "Tool",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        mcp_server,
        "TextContent",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )


def test_mcp_status_uses_read_only_config(monkeypatch):
    _install_fake_mcp(monkeypatch)
    created_configs = []

    class _RecordingConfig:
        def __init__(self, *, read_only=False):
            self.read_only = read_only
            created_configs.append(self)

    class _AgentReach:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            return "ok"

    monkeypatch.setattr(mcp_server, "Config", _RecordingConfig)
    monkeypatch.setattr(mcp_server, "AgentReach", _AgentReach)

    server = mcp_server.create_server()
    result = asyncio.run(server.call_tool_handler("get_status", {}))

    assert len(created_configs) == 1
    assert created_configs[0].read_only is True
    assert result[0].text == "ok"


def test_mcp_status_exception_credentials_are_scrubbed(monkeypatch):
    _install_fake_mcp(monkeypatch)

    class _Config:
        def __init__(self, *, read_only=False):
            self.read_only = read_only

    class _ExplodingAgentReach:
        def __init__(self, config):
            self.config = config

        def doctor_report(self):
            raise RuntimeError(
                "request https://alice:password@example.test/data?token=top-secret failed"
            )

    monkeypatch.setattr(mcp_server, "Config", _Config)
    monkeypatch.setattr(mcp_server, "AgentReach", _ExplodingAgentReach)

    server = mcp_server.create_server()
    result = asyncio.run(server.call_tool_handler("get_status", {}))
    text = result[0].text

    assert "alice" not in text
    assert "password" not in text
    assert "top-secret" not in text
    assert "https://***@example.test/data?token=***" in text


def _status_server(monkeypatch, report):
    monkeypatch.setattr(mcp_server, "Config", lambda **kwargs: object())
    monkeypatch.setattr(
        mcp_server, "AgentReach", lambda config: SimpleNamespace(doctor_report=report)
    )
    return mcp_server.create_server()


def test_mcp_status_keeps_event_loop_responsive(monkeypatch):
    _install_fake_mcp(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def report():
        started.set()
        try:
            # Bound the broken implementation's blocking call as well as the fix.
            release.wait(2)
            return "ok"
        finally:
            finished.set()

    server = _status_server(monkeypatch, report)

    async def run():
        task = asyncio.create_task(server.call_tool_handler("get_status", {}))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert not finished.is_set(), "doctor blocked the event loop until completion"
            tools = await server.list_tools_handler()
            assert [tool.name for tool in tools] == ["get_status"]
            unknown = await server.call_tool_handler("unknown", {})
            assert unknown[0].text == "Unknown tool: unknown"
        finally:
            release.set()
            result = await task
        assert result[0].text == "ok"

    asyncio.run(run())


@pytest.mark.parametrize("cancel_first", [False, True])
@pytest.mark.parametrize("separate_server", [False, True])
def test_mcp_status_reports_stay_serial_after_cancellation(
    monkeypatch, cancel_first, separate_server
):
    _install_fake_mcp(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    calls = []

    def report():
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            started.set()
            release.wait(2)
            return "first"
        second_started.set()
        return "second"

    server = _status_server(monkeypatch, report)
    other_server = _status_server(monkeypatch, report) if separate_server else server

    async def run():
        first = asyncio.create_task(server.call_tool_handler("get_status", {}))
        second = None
        try:
            assert await asyncio.to_thread(started.wait, 2)
            assert not first.done()
            if cancel_first:
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
            second = asyncio.create_task(other_server.call_tool_handler("get_status", {}))
            assert not await asyncio.to_thread(second_started.wait, 0.1)
        finally:
            release.set()
            await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
        assert second is not None
        assert (await second)[0].text == "second"
        assert calls == [1, 2]
        if not cancel_first:
            assert (await first)[0].text == "first"

    asyncio.run(run())


def test_mcp_status_recovers_after_report_error(monkeypatch):
    _install_fake_mcp(monkeypatch)
    reports = iter([RuntimeError("probe failed"), "ok"])

    def report():
        result = next(reports)
        if isinstance(result, Exception):
            raise result
        return result

    server = _status_server(monkeypatch, report)

    async def run():
        failed = await server.call_tool_handler("get_status", {})
        assert failed[0].text == "Error: probe failed"
        recovered = await asyncio.wait_for(server.call_tool_handler("get_status", {}), 2)
        assert recovered[0].text == "ok"

    asyncio.run(run())


def test_mcp_sdk_ping_and_list_tools_during_status(monkeypatch):
    pytest.importorskip("mcp")
    from mcp.shared.memory import create_connected_server_and_client_session

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def report():
        started.set()
        try:
            release.wait(2)
            return "ok"
        finally:
            finished.set()

    server = _status_server(monkeypatch, report)

    async def run():
        async with create_connected_server_and_client_session(server) as session:
            status = asyncio.create_task(session.call_tool("get_status", {}))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert not finished.is_set(), "status blocked the MCP session"
                await asyncio.wait_for(session.send_ping(), 1)
                tools = await asyncio.wait_for(session.list_tools(), 1)
                assert [tool.name for tool in tools.tools] == ["get_status"]
                assert not finished.is_set()
            finally:
                release.set()
                result = await status
            assert result.isError is False
            assert result.content[0].text == "ok"

    asyncio.run(run())
