import httpx
import pytest
import respx

from gateway.proxy import ProxyResult, forward


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


@respx.mock
async def test_forward_returns_upstream_body(client):
    respx.post("http://upstream/mcp").respond(
        200, json={"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
    )
    result = await forward(
        client=client,
        upstream_url="http://upstream/mcp",
        body=b'{"jsonrpc":"2.0","method":"tools/call","id":1}',
        headers={"content-type": "application/json"},
    )
    assert isinstance(result, ProxyResult)
    assert result.status == 200
    assert b'"ok"' in result.body
    assert result.duration_ms >= 0


@respx.mock
async def test_forward_upstream_5xx_passes_through(client):
    respx.post("http://upstream/mcp").respond(503, text="upstream busy")
    result = await forward(
        client=client,
        upstream_url="http://upstream/mcp",
        body=b"{}",
        headers={"content-type": "application/json"},
    )
    assert result.status == 503
    assert b"upstream busy" in result.body


@respx.mock
async def test_forward_timeout_raises(client):
    respx.post("http://upstream/mcp").mock(side_effect=httpx.ReadTimeout("slow"))
    from gateway.proxy import ProxyTimeout

    with pytest.raises(ProxyTimeout):
        await forward(
            client=client,
            upstream_url="http://upstream/mcp",
            body=b"{}",
            headers={"content-type": "application/json"},
        )
