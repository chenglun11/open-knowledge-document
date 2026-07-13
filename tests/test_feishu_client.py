from __future__ import annotations

import httpx

from open_knowledge_document.feishu_client import FeishuAppConfig, FeishuConfigStore, FeishuOpenAPIClient


def make_client(handler) -> FeishuOpenAPIClient:
    config = FeishuAppConfig(app_id="cli_test", app_secret="secret", brand="feishu")
    transport = httpx.MockTransport(handler)
    return FeishuOpenAPIClient(config, client=httpx.Client(transport=transport, base_url=config.resolved_base_url))


def test_bot_lists_spaces_and_reuses_tenant_token() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("tenant_access_token/internal"):
            token_calls += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tenant-token", "expire": 7200})
        assert request.headers["Authorization"] == "Bearer tenant-token"
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"space_id": "space-1"}], "has_more": False}})

    with make_client(handler) as client:
        assert client.list_spaces()[0]["space_id"] == "space-1"
        assert client.list_spaces()[0]["space_id"] == "space-1"
    assert token_calls == 1


def test_bot_fetches_all_document_block_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token", "expire": 7200})
        assert request.url.path == "/open-apis/docx/v1/documents/docx123/blocks"
        if request.url.params.get("page_token") == "next":
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"block_id": "b2"}], "has_more": False}})
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"block_id": "b1"}], "has_more": True, "page_token": "next"}})

    with make_client(handler) as client:
        assert [block["block_id"] for block in client.list_document_blocks("docx123")] == ["b1", "b2"]


def test_config_store_never_exposes_secret(tmp_path) -> None:
    store = FeishuConfigStore(tmp_path / "feishu.json")
    store.save(FeishuAppConfig(app_id="cli_test", app_secret="top-secret"))
    assert store.load().app_secret == "top-secret"
    assert "app_secret" not in store.public()
    assert store.public()["app_secret_configured"] is True
