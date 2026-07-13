from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from open_knowledge_document.server import app


PAYLOAD = {
    "code": 0,
    "data": {
        "items": [
            {"block_id": "page", "block_type": 1, "page": {}, "children": ["heading", "image"]},
            {
                "block_id": "heading",
                "block_type": 3,
                "heading1": {"elements": [{"text_run": {"content": "Admin API document"}}]},
            },
            {"block_id": "image", "block_type": 27, "image": {"token": "image-token", "width": 800, "height": 600}},
        ]
    },
}


def test_admin_import_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OKD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OKD_ADMIN_TOKEN", "test-token")
    headers = {"X-Admin-Token": "test-token"}
    request = {
        "payload": PAYLOAD,
        "document_id": "doc-api-test",
        "revision": "7",
        "title": "Admin API document",
        "space_id": "engineering",
        "path": ["Engineering", "Tests"],
        "permissions": {"visibility": "organization"},
    }

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/admin/session").status_code == 401
        assert client.get("/api/admin/session", headers=headers).json()["authenticated"] is True

        response = client.post("/api/admin/import/feishu", headers=headers, json=request)
        assert response.status_code == 200, response.text
        imported = response.json()
        assert imported["status"] == "succeeded"
        document_id = imported["document"]["id"]

        overview = client.get("/api/admin/overview", headers=headers).json()
        assert overview["documents"] == 1
        assert overview["assets"] == 1
        assert overview["pending_assets"] == 1

        documents = client.get("/api/admin/documents?query=Admin", headers=headers).json()
        assert documents["total"] == 1
        assert documents["items"][0]["revision"] == "7"
        assert client.get(f"/api/admin/documents/{document_id}", headers=headers).status_code == 200
        assert client.get("/api/admin/jobs", headers=headers).json()[0]["status"] == "succeeded"
        assert client.get("/api/admin/assets", headers=headers).json()[0]["source_asset_id"] == "image-token"
        assert client.get("/api/admin/audit", headers=headers).json()[0]["event_type"] == "document.imported"

        archive = client.post(f"/api/admin/documents/{document_id}/archive", headers=headers)
        assert archive.json() == {"archived": True}
        assert client.get("/api/admin/documents?status=archived", headers=headers).json()["total"] == 1

    assert (tmp_path / "snapshots" / "feishu" / "doc-api-test" / "7.json").is_file()


def test_preview_does_not_persist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OKD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OKD_ADMIN_TOKEN", "test-token")
    headers = {"X-Admin-Token": "test-token"}
    with TestClient(app) as client:
        response = client.post(
            "/api/convert/feishu",
            headers=headers,
            json={"payload": PAYLOAD, "document_id": "preview", "revision": 1},
        )
        assert response.status_code == 200
        assert client.get("/api/admin/overview", headers=headers).json()["documents"] == 0
