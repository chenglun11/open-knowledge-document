# Open Knowledge Document

Open Knowledge Document (OKD) is an open, vendor-neutral document envelope and
conversion toolkit for knowledge systems.

The project is intended to sit between a source system such as Feishu/Lark and
downstream systems such as BookStack, Docmost, search engines, or AI agents.
It keeps source snapshots and assets recoverable while exposing a normalized,
versioned document representation.

> Status: v0.2 administration preview. The schema is not stable and must be
> validated against a representative real-world document corpus before v1.0.

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

## Administration panel

The repository includes a Vue 3 administration panel based on the
vue-pure-admin technology stack (Vite, TypeScript and Element Plus). It
provides administrator authentication, Feishu bot configuration, wiki space
browsing, document and whole-space imports, document inventory, jobs, assets,
schema inspection, audit logs and runtime settings.

Start the local conversion API:

```bash
python -m pip install -e ".[validation,workbench]"
okd-api
```

In a second terminal, start the frontend:

```bash
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Raw block JSON remains available under the
advanced debug switch, but the normal import path uses a Feishu/Lark bot.

### Feishu bot setup

Create a custom Feishu app and enable bot access. Grant it read access to the
Wiki and Docx APIs, including `wiki:space:read` (or the broader Wiki read
permission) and `docx:document:readonly`. The app must also be added as a
member or administrator of each knowledge space it should read; API scopes
alone do not grant access to document resources.

In **飞书导入**, enter the App ID and App Secret, save them, and run the
connection check. Secrets are stored only in `/data/feishu-config.json` with
mode `0600` and are never returned to the browser. The panel then lists spaces
and their recursive node trees. Importing a document fetches all pages from
`/docx/v1/documents/{document_id}/blocks`, saves the source snapshot, validates
the OKD result, and commits it to SQLite.

Images and files are registered with `download_status=pending`. Their binary
download worker and object-storage adapter are intentionally a separate next
stage; enable `drive:drive:readonly` when that worker is added.

### Docker

Build and run the complete Workbench and API on one port:

```bash
docker compose up --build -d
```

Then open `http://127.0.0.1:8080` and log in with the value of
`OKD_ADMIN_TOKEN` (the local Compose default is `change-me-local`). Override
the host port with `OKD_PORT=8090`. The runtime container runs as a non-root
user and serves both the compiled frontend and `/api/*` endpoints. SQLite,
source snapshots and the encrypted-at-rest responsibility of the host are
persisted in the `okd-data` Docker volume.

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
