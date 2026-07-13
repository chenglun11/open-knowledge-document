# Open Knowledge Document

Open Knowledge Document (OKD) is an open, vendor-neutral document envelope and
conversion toolkit for knowledge systems.

The project is intended to sit between a source system such as Feishu/Lark and
downstream systems such as BookStack, Docmost, search engines, or AI agents.
It keeps source snapshots and assets recoverable while exposing a normalized,
versioned document representation.

> Status: early design draft. The schema is not stable and must be validated
> against a representative real-world document corpus before v1.0.

## Design goals

- No dependency on a specific wiki, editor, or search engine.
- Loss-aware conversion: unsupported source blocks are preserved, never
  silently discarded.
- Reproducibility: derived Markdown, HTML, and plain text can be regenerated
  from a versioned source snapshot and normalized document.
- Portable assets: images and attachments are referenced by stable IDs and
  content hashes rather than expiring source URLs.
- Explicit provenance, revisions, permissions, and conversion warnings.
- A fully open specification and reference implementation.

## Non-goals

- Replacing the source system's collaborative editor.
- Bidirectional synchronization.
- Defining a rich-text editor implementation.
- Treating Markdown, HTML, BookStack, or Docmost storage as canonical.

## Proposed pipeline

```text
Source API
  -> immutable source snapshot
  -> Open Knowledge Document
       -> Markdown / HTML / plain text
       -> BookStack / Docmost
       -> search indexes / AI retrieval
```

## Repository layout

```text
schemas/       Draft JSON Schemas
examples/      Synthetic, non-sensitive examples
docs/adr/      Architecture decisions and model evaluation
src/           Reference converters and CLI
tests/         Conversion fixtures and behavior tests
```

## Feishu/Lark conversion

The first reference converter accepts a previously saved Docx block-list API
response. It performs no network access: persist the raw response first, then
convert it offline.

```bash
python -m open_knowledge_document.cli convert-feishu \
  --input snapshots/document-1.json \
  --output build/document-1.okd.json \
  --document-id document-1 \
  --revision 7 \
  --space-id space-1 \
  --title "Architecture proposal" \
  --path Engineering \
  --path Architecture
```

The converter currently handles paragraphs, headings, list items, code,
quotes, callouts, dividers, tables, images, and files. Unknown blocks and
inline elements are emitted as `unsupported` nodes with references back to the
source snapshot. Image and file records are emitted with `download_status` set
to `pending`; downloading and content hashing belong to the asset pipeline.

Run the test suite with:

```bash
python -m pip install -e ".[validation]"
python -m unittest discover -s tests -v
```

## Current decision process

The normalized body model is intentionally not frozen yet. The initial model
evaluation compares:

- ProseMirror-compatible JSON
- Portable Text
- Pandoc AST
- an OKD-native block tree with CommonMark/GFM projections

See [ADR 0001](docs/adr/0001-document-model-evaluation.md).

## License

Apache License 2.0.
