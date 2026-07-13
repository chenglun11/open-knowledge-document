"""HTTP API used by the OKD Workbench frontend."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from open_knowledge_document.converters.feishu import convert_feishu_blocks


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


app = FastAPI(
    title="Open Knowledge Document Workbench API",
    version="0.1.0",
    description="Offline-friendly conversion API for exploring OKD documents.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "schema_version": "0.1.0", "converter_version": "0.1.0"}


@app.post("/api/convert/feishu")
def convert_feishu(request: FeishuConversionRequest) -> dict[str, Any]:
    try:
        return convert_feishu_blocks(
            request.payload,
            document_id=request.document_id,
            revision=request.revision,
            title=request.title,
            space_id=request.space_id,
            path=request.path,
            source_url=request.source_url,
            snapshot_ref=request.snapshot_ref,
            permissions=request.permissions,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("open_knowledge_document.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
