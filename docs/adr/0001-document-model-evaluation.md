# ADR 0001: Evaluate the normalized document body model

- Status: Proposed
- Date: 2026-07-13

## Context

The first source is Feishu/Lark, while initial consumers include BookStack,
Meilisearch, and AI retrieval. Source documents may contain rich text, tables,
tasks, images, attachments, code, diagrams, embeds, and source-specific blocks.

Choosing a downstream product's storage format would introduce a new form of
vendor lock-in. Choosing Markdown as canonical would lose information that it
cannot represent. The normalized model therefore needs an extensible tree,
stable schema versioning, and an explicit escape hatch for unsupported blocks.

## Candidates

1. ProseMirror-compatible JSON
2. Portable Text
3. Pandoc AST
4. OKD-native block JSON with CommonMark/GFM projections

## Evaluation corpus

Use synthetic or sanitized representatives of:

- technical proposals
- product specifications
- test reports
- nested lists and task lists
- wide and merged tables
- code blocks
- image-heavy pages
- attachments
- diagrams and embedded objects
- internal links
- moved, deleted, and permission-restricted documents

No private production document may be committed to this repository.

## Scoring criteria

| Criterion | Weight |
| --- | ---: |
| Round-trip fidelity | 25% |
| Unknown-block preservation | 15% |
| Markdown and HTML export | 15% |
| BookStack adapter complexity | 10% |
| Python implementation complexity | 10% |
| Schema stability and migrations | 10% |
| License and ecosystem openness | 10% |
| Storage size and processing cost | 5% |

## Required invariants

- Conversion errors must never delete the last successful representation.
- Unknown blocks must retain a source payload reference.
- Assets must use stable IDs and cryptographic hashes.
- Derived formats are replaceable projections, not canonical state.
- Every stored document declares its schema version and source revision.
- A source snapshot must be sufficient to rerun normalization offline.

## Decision

Pending evaluation. The draft schema uses a small generic block tree only to
enable fixtures and validation; it is not a v1 commitment.
