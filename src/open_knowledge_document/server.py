"""HTTP API for the OKD administration service."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Iterator
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from open_knowledge_document.converters.feishu import convert_feishu_blocks
from open_knowledge_document.feishu_client import FeishuAPIError, FeishuAppConfig, FeishuConfigStore, FeishuOpenAPIClient
from open_knowledge_document.storage import Database, utc_now


class FeishuConversionRequest(BaseModel):
    payload: dict[str, Any] | list[dict[str, Any]]
    document_id: str = Field(min_length=1)
    revision: str | int
    title: str = ""
    space_id: str = ""
    path: list[str] = Field(default_factory=list)
    source_url: str = ""
    snapshot_ref: str = "workbench://feishu-source.json"
    permissions: dict[str, Any] = Field(default_factory=lambda: {"visibility": "unknown"})


class FeishuBotImportRequest(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = ""
    space_id: str = ""
    node_token: str = ""
    revision: str | int = "latest"
    path: list[str] = Field(default_factory=list)
    source_url: str = ""
    permissions: dict[str, Any] = Field(default_factory=lambda: {"visibility": "organization"})


class FeishuSpaceSyncRequest(BaseModel):
    space_id: str = Field(min_length=1)
    parent_node_token: str = ""
    recursive: bool = True
    limit: int = Field(default=100, ge=1, le=1000)
    source_url_base: str = ""
    permissions: dict[str, Any] = Field(default_factory=lambda: {"visibility": "organization"})


def data_dir() -> Path:
    return Path(os.getenv("OKD_DATA_DIR", "data")).expanduser().resolve()


def schema_path() -> Path:
    configured = os.getenv("OKD_SCHEMA_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "schemas" / "open-knowledge-document-v0.1.schema.json"


def feishu_store() -> FeishuConfigStore:
    return FeishuConfigStore(data_dir() / "feishu-config.json")


def get_database() -> Iterator[Database]:
    database = Database(data_dir() / "okd.db")
    database.initialize()
    yield database


def require_admin(x_admin_token: str = Header(default="")) -> str:
    expected = os.getenv("OKD_ADMIN_TOKEN", "").strip()
    if expected and not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid administrator token")
    return "admin"


def convert_request(request: FeishuConversionRequest, *, snapshot_ref: str | None = None) -> dict[str, Any]:
    try:
        return convert_feishu_blocks(
            request.payload,
            document_id=request.document_id,
            revision=request.revision,
            title=request.title,
            space_id=request.space_id,
            path=request.path,
            source_url=request.source_url,
            snapshot_ref=snapshot_ref or request.snapshot_ref,
            permissions=request.permissions,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def validate_document(document: dict[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator

        schema = json.loads(schema_path().read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: list(error.path))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load OKD schema: {exc}") from exc
    if errors:
        messages = [f"{'/'.join(map(str, error.path)) or '$'}: {error.message}" for error in errors[:10]]
        raise ValueError("Schema validation failed: " + "; ".join(messages))


def safe_segment(value: str | int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip(".-")
    return cleaned[:96] or "unknown"


def write_snapshot(request: FeishuConversionRequest) -> str:
    relative = Path("snapshots") / "feishu" / safe_segment(request.document_id) / f"{safe_segment(request.revision)}.json"
    target = data_dir() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(request.payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return relative.as_posix()


def persist_feishu_request(request: FeishuConversionRequest, database: Database, *, kind: str = "feishu_import") -> dict[str, Any]:
    job_id = f"job:{uuid4().hex}"
    database.create_job({"id": job_id, "kind": kind, "status": "running", "source_type": "feishu", "source_document_id": request.document_id, "started_at": utc_now()})
    try:
        snapshot_ref = write_snapshot(request)
        document = convert_request(request, snapshot_ref=snapshot_ref)
        validate_document(document)
        database.upsert_document(document)
        warning_count = len((document.get("conversion") or {}).get("warnings") or [])
        database.finish_job(job_id, status="succeeded", document_id=str(document["id"]), processed=1, warning_count=warning_count)
        database.add_audit("document.imported", target_id=str(document["id"]), detail={"job_id": job_id, "snapshot_ref": snapshot_ref, "kind": kind})
        return {"job_id": job_id, "status": "succeeded", "document": database.list_documents(query=str(document["id"]), limit=1)["items"][0]}
    except HTTPException as exc:
        database.finish_job(job_id, status="failed", error=str(exc.detail))
        database.add_audit("document.import_failed", target_id=request.document_id, detail={"job_id": job_id, "error": str(exc.detail)})
        raise
    except Exception as exc:
        database.finish_job(job_id, status="failed", error=str(exc))
        database.add_audit("document.import_failed", target_id=request.document_id, detail={"job_id": job_id, "error": str(exc)})
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    Database(data_dir() / "okd.db").initialize()
    yield


app = FastAPI(
    title="Open Knowledge Document Admin API",
    version="0.2.0",
    description="Durable administration API for Feishu-to-OKD synchronization.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "schema_version": "0.1.0", "converter_version": "0.1.0"}


@app.get("/api/admin/session", dependencies=[Depends(require_admin)])
def session() -> dict[str, Any]:
    return {"authenticated": True, "actor": "admin", "token_required": bool(os.getenv("OKD_ADMIN_TOKEN", "").strip())}


@app.get("/api/admin/overview", dependencies=[Depends(require_admin)])
def overview(database: Database = Depends(get_database)) -> dict[str, Any]:
    return database.overview()


@app.post("/api/convert/feishu", dependencies=[Depends(require_admin)])
def convert_feishu(request: FeishuConversionRequest) -> dict[str, Any]:
    return convert_request(request)


@app.post("/api/admin/import/feishu", dependencies=[Depends(require_admin)])
def import_feishu(request: FeishuConversionRequest, database: Database = Depends(get_database)) -> dict[str, Any]:
    return persist_feishu_request(request, database)


@app.get("/api/admin/feishu/config", dependencies=[Depends(require_admin)])
def get_feishu_config() -> dict[str, Any]:
    return feishu_store().public()


@app.post("/api/admin/feishu/config", dependencies=[Depends(require_admin)])
def save_feishu_config(config: FeishuAppConfig, database: Database = Depends(get_database)) -> dict[str, Any]:
    current = feishu_store().load()
    if not config.app_secret and current.app_secret:
        config.app_secret = current.app_secret
    feishu_store().save(config)
    database.add_audit("feishu.config_updated", target_id=config.app_id, detail={"brand": config.brand, "base_url": config.resolved_base_url})
    return feishu_store().public()


@app.post("/api/admin/feishu/check", dependencies=[Depends(require_admin)])
def check_feishu() -> dict[str, Any]:
    try:
        with FeishuOpenAPIClient(feishu_store().load()) as client:
            spaces = client.list_spaces()
        return {"ok": True, "spaces": len(spaces), "message": f"机器人连接正常，可访问 {len(spaces)} 个知识空间"}
    except FeishuAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/feishu/spaces", dependencies=[Depends(require_admin)])
def feishu_spaces() -> list[dict[str, Any]]:
    try:
        with FeishuOpenAPIClient(feishu_store().load()) as client:
            return client.list_spaces()
    except FeishuAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/feishu/spaces/{space_id}/nodes", dependencies=[Depends(require_admin)])
def feishu_nodes(space_id: str, parent_node_token: str = "", recursive: bool = False, limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    try:
        with FeishuOpenAPIClient(feishu_store().load()) as client:
            if recursive:
                entries = list(client.iter_nodes(space_id, parent_node_token))[:limit]
                return [{**node, "path": path, "syncable": node.get("obj_type") == "docx" and bool(node.get("obj_token"))} for node, path in entries]
            return [{**node, "path": [str(node.get("title") or "")], "syncable": node.get("obj_type") == "docx" and bool(node.get("obj_token"))} for node in client.list_nodes(space_id, parent_node_token)[:limit]]
    except FeishuAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/feishu/import", dependencies=[Depends(require_admin)])
def import_from_feishu_bot(request: FeishuBotImportRequest, database: Database = Depends(get_database)) -> dict[str, Any]:
    try:
        with FeishuOpenAPIClient(feishu_store().load()) as client:
            blocks = client.list_document_blocks(request.document_id)
    except FeishuAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    conversion = FeishuConversionRequest(
        payload={"code": 0, "data": {"items": blocks}}, document_id=request.document_id,
        revision=request.revision, title=request.title, space_id=request.space_id, path=request.path,
        source_url=request.source_url, permissions=request.permissions,
    )
    return persist_feishu_request(conversion, database, kind="feishu_bot_import")


@app.post("/api/admin/feishu/sync", dependencies=[Depends(require_admin)])
def sync_feishu_space(request: FeishuSpaceSyncRequest, database: Database = Depends(get_database)) -> dict[str, Any]:
    imported: list[dict[str, Any]] = []
    skipped = 0
    failed: list[dict[str, str]] = []
    try:
        with FeishuOpenAPIClient(feishu_store().load()) as client:
            entries = client.iter_nodes(request.space_id, request.parent_node_token) if request.recursive else ((node, [str(node.get("title") or "")]) for node in client.list_nodes(request.space_id, request.parent_node_token))
            for node, path in entries:
                if len(imported) + len(failed) >= request.limit:
                    break
                if node.get("obj_type") != "docx" or not node.get("obj_token"):
                    skipped += 1
                    continue
                document_id = str(node["obj_token"])
                try:
                    blocks = client.list_document_blocks(document_id)
                    source_url = f"{request.source_url_base.rstrip('/')}/wiki/{node.get('node_token')}" if request.source_url_base else ""
                    conversion = FeishuConversionRequest(payload={"code": 0, "data": {"items": blocks}}, document_id=document_id, revision=str(node.get("obj_edit_time") or node.get("updated_at") or "latest"), title=str(node.get("title") or ""), space_id=request.space_id, path=path, source_url=source_url, permissions=request.permissions)
                    imported.append(persist_feishu_request(conversion, database, kind="feishu_space_sync"))
                except (FeishuAPIError, HTTPException) as exc:
                    failed.append({"document_id": document_id, "error": str(getattr(exc, "detail", exc))})
    except FeishuAPIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": not failed, "space_id": request.space_id, "imported": len(imported), "skipped": skipped, "failed": failed, "documents": [item["document"] for item in imported]}


@app.get("/api/admin/documents", dependencies=[Depends(require_admin)])
def documents(
    query: str = "", status: str = "", space_id: str = "",
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    database: Database = Depends(get_database),
) -> dict[str, Any]:
    return database.list_documents(query=query, status=status, space_id=space_id, limit=limit, offset=offset)


@app.get("/api/admin/documents/{document_id:path}", dependencies=[Depends(require_admin)])
def document_detail(document_id: str, database: Database = Depends(get_database)) -> dict[str, Any]:
    document = database.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/api/admin/documents/{document_id:path}/archive", dependencies=[Depends(require_admin)])
def archive_document(document_id: str, database: Database = Depends(get_database)) -> dict[str, bool]:
    if not database.archive_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    database.add_audit("document.archived", target_id=document_id)
    return {"archived": True}


@app.get("/api/admin/jobs", dependencies=[Depends(require_admin)])
def jobs(limit: int = Query(default=50, ge=1, le=200), database: Database = Depends(get_database)) -> list[dict[str, Any]]:
    return database.list_jobs(limit=limit)


@app.get("/api/admin/assets", dependencies=[Depends(require_admin)])
def assets(status: str = "", limit: int = Query(default=100, ge=1, le=500), database: Database = Depends(get_database)) -> list[dict[str, Any]]:
    return database.list_assets(status=status, limit=limit)


@app.get("/api/admin/audit", dependencies=[Depends(require_admin)])
def audit(limit: int = Query(default=100, ge=1, le=500), database: Database = Depends(get_database)) -> list[dict[str, Any]]:
    return database.list_audit(limit=limit)


@app.get("/api/admin/schema", dependencies=[Depends(require_admin)])
def schema() -> dict[str, Any]:
    return json.loads(schema_path().read_text(encoding="utf-8"))


@app.get("/api/admin/runtime", dependencies=[Depends(require_admin)])
def runtime() -> dict[str, Any]:
    return {
        "data_directory": str(data_dir()),
        "database": str(data_dir() / "okd.db"),
        "schema": str(schema_path()),
        "admin_token_configured": bool(os.getenv("OKD_ADMIN_TOKEN", "").strip()),
        "version": app.version,
    }


def mount_admin() -> None:
    configured = os.getenv("OKD_WEB_DIST", "").strip()
    if not configured:
        return
    web_dist = Path(configured).expanduser().resolve()
    if not (web_dist / "index.html").is_file():
        raise RuntimeError(f"OKD_WEB_DIST does not contain index.html: {web_dist}")
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="admin")


mount_admin()


def main() -> None:
    import uvicorn

    uvicorn.run("open_knowledge_document.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
