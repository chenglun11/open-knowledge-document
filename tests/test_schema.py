from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from open_knowledge_document.converters.feishu import convert_feishu_blocks


ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas" / "open-knowledge-document-v0.1.schema.json").read_text()
        )
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_public_example_matches_schema(self) -> None:
        document = json.loads((ROOT / "examples" / "minimal-document.json").read_text())
        self.validator.validate(document)

    def test_feishu_converter_output_matches_schema(self) -> None:
        payload = {
            "items": [
                {"block_id": "page", "block_type": 1, "page": {}, "children": ["text"]},
                {
                    "block_id": "text",
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": "Schema validated"}}]},
                },
            ]
        }
        document = convert_feishu_blocks(
            payload,
            document_id="doc-schema",
            revision=1,
            title="Schema test",
        )
        self.validator.validate(document)


if __name__ == "__main__":
    unittest.main()
