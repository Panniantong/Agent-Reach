"""Exercise tool registration and calls using the optional SDK, not a fake Server."""

import asyncio

import pytest


def test_native_mcp_sdk_registers_and_serves_status(monkeypatch):
    pytest.importorskip("mcp")
    import agent_reach.integrations.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server.AgentReach, "doctor_report", lambda self: "test status")
    server = mcp_server.create_server()

    from mcp.shared.memory import create_connected_server_and_client_session

    async def exercise():
        async with create_connected_server_and_client_session(server) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools.tools] == ["get_status"]
            result = await client.call_tool("get_status", {})
            assert not result.isError
            assert result.content[0].text == "test status"

    asyncio.run(exercise())
