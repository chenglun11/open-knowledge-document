"""Convert Feishu/Lark Docx blocks into an Open Knowledge Document.

The converter is deliberately pure: it performs no network requests and never
downloads assets. Callers are expected to persist the source response first,
then pass the decoded JSON and snapshot reference into this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping


# Feishu block type numbers are retained as a compatibility aid. Payload keys
# remain the primary discriminator so future API additions degrade safely.
BLOCK_TYPE_NAMES = {
    1: "page",
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
    14: "code",
    15: "quote",
    17: "todo",
    19: "callout",
    22: "divider",
    23: "file",
    27: "image",
    31: "table",
    32: "table_cell",
    34: "quote_container",
}

TEXT_PAYLOADS = {
    "text",
    "bullet",
    "ordered",
    "code",
    "quote",
    "todo",
}
HEADING_PAYLOADS = {f"heading{i}" for i in range(1, 10)}
STRUCTURAL_PAYLOADS = {"page", "table", "table_cell", "quote_container", "callout"}
MEDIA_PAYLOADS = {"image", "file"}


@dataclass
class ConversionContext:
    snapshot_ref: str
    warnings: list[str] = field(default_factory=list)
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


def convert_feishu_blocks(
    payload: Mapping[str, Any] | list[Mapping[str, Any]],
    *,
    document_id: str,
    revision: str | int,
    title: str = "",
    space_id: str = "",
    path: Iterable[str] = (),
    source_url: str = "",
    snapshot_ref: str = "",
    snapshot_sha256: str = "",
    permissions: Mapping[str, Any] | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Convert a Feishu block-list response to an OKD 0.1 document.

    Accepted inputs are a raw block list, ``{"items": [...]}``, or the OpenAPI
    response shape ``{"data": {"items": [...]}}``.
    """

    if not document_id.strip():
        raise ValueError("document_id must not be blank")

    blocks = _extract_blocks(payload)
    snapshot_ref = snapshot_ref or f"snapshots/feishu/{document_id}/{revision}.json"
    snapshot_sha256 = snapshot_sha256 or _canonical_sha256(payload)
    context = ConversionContext(snapshot_ref=snapshot_ref)

    by_id: dict[str, Mapping[str, Any]] = {}
    ordered_ids: list[str] = []
    for index, block in enumerate(blocks):
        block_id = str(block.get("block_id") or f"anonymous-{index}")
        if block_id in by_id:
            context.warn(f"duplicate block_id preserved once: {block_id}")
            continue
        by_id[block_id] = block
        ordered_ids.append(block_id)

    referenced_children = {
        str(child_id)
        for block in blocks
        for child_id in _child_ids(block)
        if str(child_id)
    }
    root_ids = [
        block_id
        for block_id in ordered_ids
        if block_id not in referenced_children and _payload_name(by_id[block_id]) == "page"
    ]
    if not root_ids:
        root_ids = [block_id for block_id in ordered_ids if block_id not in referenced_children]
    if not root_ids:
        root_ids = ordered_ids[:1]

    converted_roots = [
        _convert_block(by_id[block_id], by_id=by_id, context=context, ancestors=())
        for block_id in root_ids
    ]
    content: list[dict[str, Any]] = []
    for node in converted_roots:
        if node.get("type") == "doc":
            content.extend(node.get("content") or [])
        else:
            content.append(node)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metadata: dict[str, Any] = {
        "title": title,
        "path": [str(part) for part in path],
        "status": "active",
    }
    if created_at:
        metadata["created_at"] = created_at
    if updated_at:
        metadata["updated_at"] = updated_at

    source: dict[str, Any] = {
        "type": "feishu",
        "document_id": document_id,
        "revision": revision,
    }
    if space_id:
        source["space_id"] = space_id
    if source_url:
        source["url"] = source_url

    return {
        "schema_version": "0.1.0",
        "id": f"feishu:{space_id}:{document_id}" if space_id else f"feishu:{document_id}",
        "source": source,
        "metadata": metadata,
        "permissions": dict(permissions or {"visibility": "unknown"}),
        "document": {"type": "doc", "content": content},
        "assets": list(context.assets.values()),
        "source_snapshot": {
            "format": "feishu-docx-blocks-v1",
            "storage_ref": snapshot_ref,
            "sha256": snapshot_sha256,
        },
        "conversion": {
            "converter": "feishu-blocks-to-okd",
            "converter_version": "0.1.0",
            "converted_at": now,
            "warnings": context.warnings,
        },
    }


def _extract_blocks(
    payload: Mapping[str, Any] | list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        blocks = payload
    elif isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, Mapping) and isinstance(data.get("items"), list):
            blocks = data["items"]
        elif isinstance(payload.get("items"), list):
            blocks = payload["items"]
        elif isinstance(payload.get("blocks"), list):
            blocks = payload["blocks"]
        else:
            raise ValueError("Feishu payload must contain a block list in data.items, items, or blocks")
    else:
        raise TypeError("Feishu payload must be an object or block list")

    if not all(isinstance(block, Mapping) for block in blocks):
        raise ValueError("every Feishu block must be an object")
    return list(blocks)


def _convert_block(
    block: Mapping[str, Any],
    *,
    by_id: Mapping[str, Mapping[str, Any]],
    context: ConversionContext,
    ancestors: tuple[str, ...],
) -> dict[str, Any]:
    block_id = str(block.get("block_id") or "")
    if block_id and block_id in ancestors:
        context.warn(f"cycle detected at block {block_id}")
        return _unsupported_node(block, context=context, reason="cycle")

    payload_name = _payload_name(block)
    payload = block.get(payload_name)
    payload = payload if isinstance(payload, Mapping) else {}
    next_ancestors = (*ancestors, block_id) if block_id else ancestors
    children = [
        _convert_block(by_id[child_id], by_id=by_id, context=context, ancestors=next_ancestors)
        for child_id in _child_ids(block)
        if child_id in by_id
    ]
    missing_children = [child_id for child_id in _child_ids(block) if child_id not in by_id]
    for child_id in missing_children:
        context.warn(f"block {block_id or '<unknown>'} references missing child {child_id}")

    if payload_name == "page":
        return {"id": block_id, "type": "doc", "content": children}

    if payload_name in HEADING_PAYLOADS:
        level = int(payload_name.removeprefix("heading"))
        return _text_node(block_id, "heading", payload, attrs={"level": level}, children=children, context=context)

    if payload_name == "text":
        return _text_node(block_id, "paragraph", payload, children=children, context=context)
    if payload_name in {"bullet", "ordered", "todo"}:
        attrs: dict[str, Any] = {"kind": payload_name}
        if payload_name == "todo" and "style" in payload:
            attrs["style"] = payload["style"]
        return _text_node(block_id, "list_item", payload, attrs=attrs, children=children, context=context)
    if payload_name == "code":
        attrs = {}
        style = payload.get("style")
        if isinstance(style, Mapping) and style.get("language") is not None:
            attrs["language"] = str(style["language"])
        return _text_node(block_id, "code_block", payload, attrs=attrs, children=children, context=context)
    if payload_name == "quote":
        paragraph = _text_node(block_id, "paragraph", payload, context=context)
        return {"id": block_id, "type": "blockquote", "content": [paragraph, *children]}
    if payload_name == "divider":
        return {"id": block_id, "type": "divider"}
    if payload_name == "quote_container":
        return {"id": block_id, "type": "blockquote", "content": children}
    if payload_name == "callout":
        return {
            "id": block_id,
            "type": "callout",
            "attrs": _safe_attrs(payload, exclude={"elements"}),
            "content": [*_rich_text(payload, block_id=block_id, context=context), *children],
        }
    if payload_name == "table":
        attrs = _safe_attrs(payload, exclude={"cells"})
        return {"id": block_id, "type": "table", "attrs": attrs, "content": children}
    if payload_name == "table_cell":
        return {"id": block_id, "type": "table_cell", "content": children}
    if payload_name in MEDIA_PAYLOADS:
        return _media_node(block_id, payload_name, payload, context=context)

    context.warn(f"unsupported Feishu block type {payload_name!r} at {block_id or '<unknown>'}")
    return _unsupported_node(block, context=context, reason="unsupported_block", children=children)


def _text_node(
    block_id: str,
    node_type: str,
    payload: Mapping[str, Any],
    *,
    attrs: Mapping[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
    context: ConversionContext,
) -> dict[str, Any]:
    node: dict[str, Any] = {"id": block_id, "type": node_type}
    if attrs:
        node["attrs"] = dict(attrs)
    content = _rich_text(payload, block_id=block_id, context=context)
    content.extend(children or [])
    if content:
        node["content"] = content
    return node


def _rich_text(
    payload: Mapping[str, Any],
    *,
    block_id: str,
    context: ConversionContext,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    elements = payload.get("elements")
    if not isinstance(elements, list):
        return output

    for index, element in enumerate(elements):
        if not isinstance(element, Mapping):
            context.warn(f"non-object inline element at {block_id}:{index}")
            continue
        text_run = element.get("text_run")
        if isinstance(text_run, Mapping):
            text_node: dict[str, Any] = {"type": "text", "text": str(text_run.get("content") or "")}
            marks = _text_marks(text_run.get("text_element_style"))
            if marks:
                text_node["marks"] = marks
            output.append(text_node)
            continue

        equation = element.get("equation")
        if isinstance(equation, Mapping):
            output.append({"type": "equation", "attrs": {"content": str(equation.get("content") or "")}})
            continue

        mention_user = element.get("mention_user")
        if isinstance(mention_user, Mapping):
            node = {
                "type": "mention_user",
                "attrs": {"user_id": str(mention_user.get("user_id") or "")},
            }
            marks = _text_marks(mention_user.get("text_element_style"))
            if marks:
                node["marks"] = marks
            output.append(node)
            continue

        mention_doc = element.get("mention_doc")
        if isinstance(mention_doc, Mapping):
            node = {
                "type": "mention_document",
                "attrs": {
                    "token": str(mention_doc.get("token") or ""),
                    "object_type": mention_doc.get("obj_type"),
                    "url": str(mention_doc.get("url") or ""),
                },
            }
            marks = _text_marks(mention_doc.get("text_element_style"))
            if marks:
                node["marks"] = marks
            output.append(node)
            continue

        reminder = element.get("reminder")
        if isinstance(reminder, Mapping):
            output.append({"type": "reminder", "attrs": _safe_attrs(reminder)})
            continue

        inline_file = element.get("file")
        if isinstance(inline_file, Mapping):
            output.append({"type": "inline_file", "attrs": _safe_attrs(inline_file)})
            continue

        inline_type = next((key for key in element if key not in {"text_run", "equation"}), "unknown")
        context.warn(f"unsupported inline element {inline_type!r} at {block_id}:{index}")
        output.append(
            {
                "type": "unsupported_inline",
                "attrs": {"source_type": inline_type, "source": _json_safe(element)},
                "source_payload_ref": f"{context.snapshot_ref}#block={block_id}&element={index}",
            }
        )
    return output


def _text_marks(style: Any) -> list[dict[str, Any]]:
    if not isinstance(style, Mapping):
        return []
    marks: list[dict[str, Any]] = []
    for source_name, target_name in (
        ("bold", "bold"),
        ("italic", "italic"),
        ("underline", "underline"),
        ("strikethrough", "strike"),
        ("inline_code", "code"),
    ):
        if style.get(source_name):
            marks.append({"type": target_name})
    link = style.get("link")
    if isinstance(link, Mapping) and link.get("url"):
        marks.append({"type": "link", "attrs": {"href": str(link["url"])}})
    if style.get("text_color") is not None:
        marks.append({"type": "color", "attrs": {"value": style["text_color"]}})
    return marks


def _media_node(
    block_id: str,
    payload_name: str,
    payload: Mapping[str, Any],
    *,
    context: ConversionContext,
) -> dict[str, Any]:
    source_asset_id = str(payload.get("token") or payload.get("file_token") or block_id)
    asset_id = f"feishu:{source_asset_id}"
    media_type = "application/octet-stream" if payload_name == "file" else "image/*"
    asset = {
        "id": asset_id,
        "media_type": media_type,
        "filename": str(payload.get("name") or ""),
        "size": int(payload.get("size") or 0),
        "storage_ref": f"pending://feishu/{source_asset_id}",
        "source_asset_id": source_asset_id,
        "download_status": "pending",
    }
    context.assets.setdefault(asset_id, asset)
    attrs: dict[str, Any] = {"asset_id": asset_id}
    for key in ("width", "height", "name", "view_type"):
        if key in payload:
            attrs[key] = _json_safe(payload[key])
    return {"id": block_id, "type": payload_name, "attrs": attrs}


def _unsupported_node(
    block: Mapping[str, Any],
    *,
    context: ConversionContext,
    reason: str,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    block_id = str(block.get("block_id") or "")
    node: dict[str, Any] = {
        "id": block_id,
        "type": "unsupported",
        "attrs": {
            "reason": reason,
            "source_type": _payload_name(block),
            "source_block_type": block.get("block_type"),
        },
        "source_payload_ref": f"{context.snapshot_ref}#block={block_id}",
    }
    if children:
        node["content"] = children
    return node


def _payload_name(block: Mapping[str, Any]) -> str:
    numeric_name = BLOCK_TYPE_NAMES.get(block.get("block_type"))
    candidates = [
        key
        for key, value in block.items()
        if key not in {"block_id", "block_type", "parent_id", "children"} and isinstance(value, Mapping)
    ]
    if numeric_name and numeric_name in block:
        return numeric_name
    known_payloads = HEADING_PAYLOADS | TEXT_PAYLOADS | STRUCTURAL_PAYLOADS | MEDIA_PAYLOADS | {"divider"}
    for name in sorted(known_payloads):
        if name in block:
            return name
    if numeric_name:
        return numeric_name
    return candidates[0] if candidates else f"block_type_{block.get('block_type', 'unknown')}"


def _child_ids(block: Mapping[str, Any]) -> list[str]:
    children = block.get("children")
    child_ids = [str(child) for child in children if str(child)] if isinstance(children, list) else []
    payload_name = _payload_name(block)
    payload = block.get(payload_name)
    if payload_name == "table" and isinstance(payload, Mapping) and isinstance(payload.get("cells"), list):
        for cell in payload["cells"]:
            cell_id = str(cell)
            if cell_id and cell_id not in child_ids:
                child_ids.append(cell_id)
    return child_ids


def _safe_attrs(payload: Mapping[str, Any], *, exclude: set[str] | None = None) -> dict[str, Any]:
    return {str(key): _json_safe(value) for key, value in payload.items() if key not in (exclude or set())}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
