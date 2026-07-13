"""Command-line interface for Open Knowledge Document."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from open_knowledge_document.converters.feishu import convert_feishu_blocks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okd")
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert-feishu", help="convert a saved Feishu block response")
    convert.add_argument("--input", required=True, type=Path)
    convert.add_argument("--output", required=True, type=Path)
    convert.add_argument("--document-id", required=True)
    convert.add_argument("--revision", required=True)
    convert.add_argument("--title", default="")
    convert.add_argument("--space-id", default="")
    convert.add_argument("--path", action="append", default=[])
    convert.add_argument("--source-url", default="")
    convert.add_argument("--visibility", choices=["public", "organization", "restricted", "unknown"], default="unknown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "convert-feishu":
        raise AssertionError(f"unhandled command: {args.command}")

    raw_bytes = args.input.read_bytes()
    payload = json.loads(raw_bytes)
    result = convert_feishu_blocks(
        payload,
        document_id=args.document_id,
        revision=args.revision,
        title=args.title,
        space_id=args.space_id,
        path=args.path,
        source_url=args.source_url,
        snapshot_ref=str(args.input),
        snapshot_sha256=sha256(raw_bytes).hexdigest(),
        permissions={"visibility": args.visibility},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
