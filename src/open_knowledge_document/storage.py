"""Durable SQLite storage for the OKD administration service."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_document_id TEXT NOT NULL,
                    space_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    path_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    visibility TEXT NOT NULL DEFAULT 'unknown',
                    revision TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    asset_count INTEGER NOT NULL DEFAULT 0,
                    snapshot_ref TEXT NOT NULL DEFAULT '',
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_type, source_document_id, space_id)
                );

                CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_documents_space ON documents(space_id, status);

                CREATE TABLE IF NOT EXISTS assets (
                    document_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    source_asset_id TEXT NOT NULL DEFAULT '',
                    media_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    filename TEXT NOT NULL DEFAULT '',
                    storage_ref TEXT NOT NULL DEFAULT '',
                    download_status TEXT NOT NULL DEFAULT 'pending',
                    sha256 TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(document_id, id),
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(download_status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT '',
                    source_document_id TEXT NOT NULL DEFAULT '',
                    document_id TEXT NOT NULL DEFAULT '',
                    processed INTEGER NOT NULL DEFAULT 0,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_started ON jobs(started_at DESC);

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'admin',
                    target_id TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
                """
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_document(self, document: Mapping[str, Any]) -> None:
        now = utc_now()
        metadata = document.get("metadata") if isinstance(document.get("metadata"), Mapping) else {}
        source = document.get("source") if isinstance(document.get("source"), Mapping) else {}
        permissions = document.get("permissions") if isinstance(document.get("permissions"), Mapping) else {}
        conversion = document.get("conversion") if isinstance(document.get("conversion"), Mapping) else {}
        snapshot = document.get("source_snapshot") if isinstance(document.get("source_snapshot"), Mapping) else {}
        warnings = conversion.get("warnings") if isinstance(conversion.get("warnings"), list) else []
        assets = document.get("assets") if isinstance(document.get("assets"), list) else []
        document_id = str(document["id"])
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, source_type, source_document_id, space_id, title, path_json,
                    status, visibility, revision, content_hash, warning_count,
                    asset_count, snapshot_ref, document_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_type=excluded.source_type,
                    source_document_id=excluded.source_document_id,
                    space_id=excluded.space_id,
                    title=excluded.title,
                    path_json=excluded.path_json,
                    status=excluded.status,
                    visibility=excluded.visibility,
                    revision=excluded.revision,
                    content_hash=excluded.content_hash,
                    warning_count=excluded.warning_count,
                    asset_count=excluded.asset_count,
                    snapshot_ref=excluded.snapshot_ref,
                    document_json=excluded.document_json,
                    updated_at=excluded.updated_at
                """,
                (
                    document_id,
                    str(source.get("type") or "unknown"),
                    str(source.get("document_id") or ""),
                    str(source.get("space_id") or ""),
                    str(metadata.get("title") or ""),
                    json.dumps(metadata.get("path") or [], ensure_ascii=False),
                    str(metadata.get("status") or "active"),
                    str(permissions.get("visibility") or "unknown"),
                    str(source.get("revision") or ""),
                    content_hash,
                    len(warnings),
                    len(assets),
                    str(snapshot.get("storage_ref") or ""),
                    encoded,
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM assets WHERE document_id = ?", (document_id,))
            for asset in assets:
                if not isinstance(asset, Mapping):
                    continue
                connection.execute(
                    """
                    INSERT INTO assets (
                        document_id, id, source_asset_id, media_type, filename,
                        storage_ref, download_status, sha256, size, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        str(asset.get("id") or ""),
                        str(asset.get("source_asset_id") or ""),
                        str(asset.get("media_type") or "application/octet-stream"),
                        str(asset.get("filename") or ""),
                        str(asset.get("storage_ref") or ""),
                        str(asset.get("download_status") or "pending"),
                        str(asset.get("sha256") or ""),
                        int(asset.get("size") or 0),
                        now,
                    ),
                )

    def list_documents(
        self,
        *,
        query: str = "",
        status: str = "",
        space_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        values: list[Any] = []
        if query:
            conditions.append("(title LIKE ? OR id LIKE ? OR source_document_id LIKE ?)")
            wildcard = f"%{query}%"
            values.extend([wildcard, wildcard, wildcard])
        if status:
            conditions.append("status = ?")
            values.append(status)
        if space_id:
            conditions.append("space_id = ?")
            values.append(space_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connection() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM documents {where}", values).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT id, source_type, source_document_id, space_id, title, path_json,
                       status, visibility, revision, content_hash, warning_count,
                       asset_count, snapshot_ref, created_at, updated_at
                FROM documents {where}
                ORDER BY updated_at DESC LIMIT ? OFFSET ?
                """,
                [*values, max(1, min(limit, 200)), max(0, offset)],
            ).fetchall()
        return {"items": [self._document_summary(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT document_json FROM documents WHERE id = ?", (document_id,)).fetchone()
        return json.loads(row["document_json"]) if row else None

    def archive_document(self, document_id: str) -> bool:
        with self.connection() as connection:
            row = connection.execute("SELECT document_json FROM documents WHERE id = ?", (document_id,)).fetchone()
            if not row:
                return False
            document = json.loads(row["document_json"])
            document.setdefault("metadata", {})["status"] = "archived"
            encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            connection.execute(
                "UPDATE documents SET status='archived', document_json=?, updated_at=? WHERE id=?",
                (encoded, utc_now(), document_id),
            )
        return True

    def create_job(self, job: Mapping[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (id, kind, status, source_type, source_document_id, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(job["id"]), str(job["kind"]), str(job["status"]),
                    str(job.get("source_type") or ""), str(job.get("source_document_id") or ""),
                    str(job.get("started_at") or utc_now()),
                ),
            )

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        document_id: str = "",
        processed: int = 0,
        warning_count: int = 0,
        error: str = "",
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE jobs SET status=?, document_id=?, processed=?, warning_count=?,
                                error=?, completed_at=? WHERE id=?
                """,
                (status, document_id, processed, warning_count, error, utc_now(), job_id),
            )

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_assets(self, *, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        where = "WHERE download_status = ?" if status else ""
        values: list[Any] = [status] if status else []
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM assets {where} ORDER BY updated_at DESC LIMIT ?",
                [*values, max(1, min(limit, 500))],
            ).fetchall()
        return [dict(row) for row in rows]

    def add_audit(
        self,
        event_type: str,
        *,
        actor: str = "admin",
        target_id: str = "",
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO audit_events (event_type, actor, target_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_type, actor, target_id, json.dumps(detail or {}, ensure_ascii=False), utc_now()),
            )

    def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json"))
            items.append(item)
        return items

    def overview(self) -> dict[str, Any]:
        with self.connection() as connection:
            document_count = int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            active_count = int(connection.execute("SELECT COUNT(*) FROM documents WHERE status='active'").fetchone()[0])
            warning_count = int(connection.execute("SELECT COALESCE(SUM(warning_count), 0) FROM documents").fetchone()[0])
            asset_count = int(connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
            pending_assets = int(connection.execute("SELECT COUNT(*) FROM assets WHERE download_status='pending'").fetchone()[0])
            failed_jobs = int(connection.execute("SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0])
            spaces = [
                dict(row)
                for row in connection.execute(
                    "SELECT space_id, COUNT(*) AS documents FROM documents GROUP BY space_id ORDER BY documents DESC LIMIT 12"
                ).fetchall()
            ]
        return {
            "documents": document_count,
            "active_documents": active_count,
            "warnings": warning_count,
            "assets": asset_count,
            "pending_assets": pending_assets,
            "failed_jobs": failed_jobs,
            "spaces": spaces,
            "recent_jobs": self.list_jobs(limit=8),
            "recent_documents": self.list_documents(limit=8)["items"],
        }

    @staticmethod
    def _document_summary(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["path"] = json.loads(item.pop("path_json"))
        return item
