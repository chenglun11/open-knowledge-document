"""Feishu/Lark bot OpenAPI client, migrated from Doc Candidate Search API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, Iterator

import httpx
from pydantic import BaseModel, Field, field_validator


BRAND_BASE_URLS = {"feishu": "https://open.feishu.cn", "lark": "https://open.larksuite.com"}


class FeishuAppConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    brand: str = Field(default="feishu", pattern="^(feishu|lark)$")
    base_url: str = ""

    @field_validator("app_id", "app_secret", "base_url", mode="before")
    @classmethod
    def strip_string(cls, value: object) -> str:
        return str(value or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    @property
    def resolved_base_url(self) -> str:
        return (self.base_url or BRAND_BASE_URLS[self.brand]).rstrip("/")


class FeishuConfigStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> FeishuAppConfig:
        if not self.path.exists():
            return FeishuAppConfig()
        try:
            return FeishuAppConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return FeishuAppConfig()

    def save(self, config: FeishuAppConfig) -> FeishuAppConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        return config

    def public(self) -> dict[str, Any]:
        config = self.load()
        return {"configured": config.configured, "app_id": config.app_id, "app_secret_configured": bool(config.app_secret), "brand": config.brand, "base_url": config.resolved_base_url, "identity_mode": "tenant_access_token"}


class FeishuAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(message)


@dataclass
class CachedToken:
    token: str
    expires_at: float


class FeishuOpenAPIClient:
    def __init__(self, config: FeishuAppConfig, *, timeout: float = 20, client: httpx.Client | None = None) -> None:
        if not config.configured:
            raise FeishuAPIError("请先配置飞书机器人 App ID 和 App Secret")
        self.config = config
        self._client = client or httpx.Client(base_url=config.resolved_base_url, timeout=timeout)
        self._owns_client = client is None
        self._tenant_token: CachedToken | None = None

    def __enter__(self) -> "FeishuOpenAPIClient":
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_client:
            self._client.close()

    def tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_token and self._tenant_token.expires_at - now > 300:
            return self._tenant_token.token
        payload = self._request_raw("POST", "/open-apis/auth/v3/tenant_access_token/internal", json={"app_id": self.config.app_id, "app_secret": self.config.app_secret})
        token = str(payload.get("tenant_access_token") or "")
        if not token:
            raise FeishuAPIError("飞书未返回 tenant_access_token")
        self._tenant_token = CachedToken(token, now + max(int(payload.get("expire") or 7200) - 60, 60))
        return token

    def list_spaces(self) -> list[dict[str, Any]]:
        return list(self._paginate("/open-apis/wiki/v2/spaces", key="items", page_size=50))

    def list_nodes(self, space_id: str, parent_node_token: str = "") -> list[dict[str, Any]]:
        params = {"parent_node_token": parent_node_token} if parent_node_token else {}
        return list(self._paginate(f"/open-apis/wiki/v2/spaces/{space_id}/nodes", key="items", page_size=50, params=params))

    def iter_nodes(self, space_id: str, parent_node_token: str = "", path: list[str] | None = None) -> Iterator[tuple[dict[str, Any], list[str]]]:
        for node in self.list_nodes(space_id, parent_node_token):
            title = str(node.get("title") or node.get("obj_token") or node.get("node_token") or "Untitled")
            node_path = [*(path or []), title]
            yield node, node_path
            if node.get("has_child") and node.get("node_token"):
                yield from self.iter_nodes(space_id, str(node["node_token"]), node_path)

    def list_document_blocks(self, document_id: str) -> list[dict[str, Any]]:
        return list(self._paginate(f"/open-apis/docx/v1/documents/{document_id}/blocks", key="items", page_size=500))

    def _paginate(self, path: str, *, key: str, page_size: int, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        page_token = ""
        while True:
            query = {**(params or {}), "page_size": page_size}
            if page_token:
                query["page_token"] = page_token
            data = self._request("GET", path, params=query)
            for item in data.get(key) or []:
                if isinstance(item, dict):
                    yield item
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {self.tenant_access_token()}"
        payload = self._request_raw(method, path, headers=headers, **kwargs)
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}

    def _request_raw(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise FeishuAPIError(f"无法连接飞书 OpenAPI: {exc}") from exc
            try:
                payload = response.json() if response.content else {}
            except ValueError as exc:
                raise FeishuAPIError(f"飞书返回了非 JSON 响应 ({response.status_code})", status_code=response.status_code) from exc
            code = payload.get("code") if isinstance(payload, dict) else None
            if response.status_code < 400 and code in (None, 0):
                return payload
            if (response.status_code in {408, 429, 500, 502, 503, 504} or code == 99991400) and attempt < 2:
                time.sleep(0.5 * (2**attempt))
                continue
            message = payload.get("msg") or payload.get("message") or response.text or "飞书 OpenAPI 请求失败"
            raise FeishuAPIError(f"{path}: {message}", status_code=response.status_code, code=code if isinstance(code, int) else None)
        raise FeishuAPIError(f"{path}: 重试后仍然失败")
