from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from open_knowledge_document.cli import main
from open_knowledge_document.converters.feishu import convert_feishu_blocks


class FeishuConverterTests(unittest.TestCase):
    def test_converts_common_blocks_marks_assets_and_unknown_blocks(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "block_id": "page-1",
                        "block_type": 1,
                        "page": {},
                        "children": ["heading-1", "text-1", "image-1", "unknown-1"],
                    },
                    {
                        "block_id": "heading-1",
                        "block_type": 3,
                        "heading1": {
                            "elements": [{"text_run": {"content": "Architecture"}}]
                        },
                    },
                    {
                        "block_id": "text-1",
                        "block_type": 2,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": "Open model",
                                        "text_element_style": {
                                            "bold": True,
                                            "link": {"url": "https://example.invalid"},
                                        },
                                    }
                                }
                            ]
                        },
                    },
                    {
                        "block_id": "image-1",
                        "block_type": 27,
                        "image": {"token": "img-token", "width": 800, "height": 600},
                    },
                    {
                        "block_id": "unknown-1",
                        "block_type": 999,
                        "future_widget": {"value": "preserved in raw snapshot"},
                    },
                ]
            },
        }

        result = convert_feishu_blocks(
            payload,
            document_id="doc-1",
            revision=7,
            title="Synthetic document",
            space_id="space-1",
            snapshot_ref="snapshots/doc-1/7.json",
        )

        self.assertEqual(result["schema_version"], "0.1.0")
        self.assertEqual(result["id"], "feishu:space-1:doc-1")
        nodes = result["document"]["content"]
        self.assertEqual([node["type"] for node in nodes], ["heading", "paragraph", "image", "unsupported"])
        self.assertEqual(nodes[0]["attrs"]["level"], 1)
        self.assertEqual(nodes[1]["content"][0]["marks"][0], {"type": "bold"})
        self.assertEqual(nodes[1]["content"][0]["marks"][1]["attrs"]["href"], "https://example.invalid")
        self.assertEqual(nodes[2]["attrs"]["asset_id"], "feishu:img-token")
        self.assertEqual(result["assets"][0]["download_status"], "pending")
        self.assertEqual(nodes[3]["source_payload_ref"], "snapshots/doc-1/7.json#block=unknown-1")
        self.assertTrue(result["conversion"]["warnings"])

    def test_preserves_nested_table_cells(self) -> None:
        payload = {
            "items": [
                {"block_id": "page", "block_type": 1, "page": {}, "children": ["table"]},
                {
                    "block_id": "table",
                    "block_type": 31,
                    "table": {"cells": ["cell"], "property": {"row_size": 1, "column_size": 1}},
                },
                {"block_id": "cell", "block_type": 32, "table_cell": {}, "children": ["text"]},
                {
                    "block_id": "text",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "Cell value"}}]},
                },
            ]
        }

        result = convert_feishu_blocks(payload, document_id="doc", revision="1")
        table = result["document"]["content"][0]
        self.assertEqual(table["type"], "table")
        self.assertEqual(table["content"][0]["type"], "table_cell")
        self.assertEqual(table["content"][0]["content"][0]["type"], "paragraph")

    def test_rejects_missing_block_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "block list"):
            convert_feishu_blocks({}, document_id="doc", revision="1")

    def test_cli_converts_saved_snapshot_and_hashes_exact_bytes(self) -> None:
        payload = {
            "items": [
                {"block_id": "page", "block_type": 1, "page": {}, "children": ["text"]},
                {
                    "block_id": "text",
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {"mention_user": {"user_id": "user-1"}},
                            {
                                "mention_doc": {
                                    "token": "doc-2",
                                    "obj_type": 22,
                                    "url": "https://example.invalid/doc-2",
                                }
                            },
                        ]
                    },
                },
            ]
        }
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "snapshot.json"
            output_path = Path(directory) / "document.okd.json"
            input_path.write_bytes(raw)

            exit_code = main(
                [
                    "convert-feishu",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--document-id",
                    "doc-1",
                    "--revision",
                    "9",
                ]
            )

            result = json.loads(output_path.read_text())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["source_snapshot"]["sha256"], sha256(raw).hexdigest())
            inline_nodes = result["document"]["content"][0]["content"]
            self.assertEqual(inline_nodes[0]["type"], "mention_user")
            self.assertEqual(inline_nodes[1]["type"], "mention_document")


if __name__ == "__main__":
    unittest.main()
