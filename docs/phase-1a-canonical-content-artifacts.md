# Phase 1A: Canonical Content Artifacts

This slice makes the synthetic experiment reproducible from CTRT's own append-only storage rather than from caller-supplied text.

## Components

### `CanonicalContentSnapshot`

One immutable analyzer input containing:

- deterministic artifact ID;
- content ID;
- exact text;
- exact UTF-8 text hash;
- language;
- source type;
- source URI;
- extraction reference;
- canonical payload and artifact hash.

`CanonicalContentSnapshot.from_content_item()` creates the record during ingestion. `CanonicalContentSnapshot.from_artifact()` parses and verifies a stored record. `to_content_item()` reconstructs the provider-neutral analyzer input.

### Linked corpus manifest

`docs/corpora/synthetic-three-items.v0.2.0.json` is a new frozen corpus version. Every entry includes a complete canonical artifact reference.

The previous `0.1.0` manifest is retained unchanged. It remains valid for the earlier caller-bound flow but is intentionally ineligible for storage-backed execution.

### `persist_canonical_corpus`

The ingestion helper:

1. verifies plan, corpus, content order, text hashes, and metadata;
2. builds each content artifact;
3. confirms each artifact reference matches the frozen manifest;
4. appends content artifacts;
5. appends the corpus manifest last;
6. reloads and reconstructs the full corpus from storage.

Identical repeats are idempotent. An artifact mismatch prevents publication of the linked manifest.

### `load_canonical_corpus`

The loader requires a fully linked manifest and:

1. verifies the stored manifest by ID, hash, and canonical payload;
2. retrieves every content artifact by the frozen reference;
3. parses and verifies canonical JSON;
4. recomputes the exact UTF-8 text hash;
5. checks all metadata against the manifest entry;
6. returns ordered reconstructed `ContentItem` records.

### `StoredContentExperimentRunner`

The runner accepts only:

- a frozen plan;
- exact candidate registry;
- linked corpus manifest;
- execution environment;
- ordered `StoredContentExecutionWindow` records;
- experiment-run ID.

An execution window contains a content ID and timestamps, not text or content metadata.

After loading the inputs, the runner delegates to `CorpusBoundExperimentRunner`. Its final completion marker links:

- the exact corpus manifest;
- every canonical content artifact;
- the verified corpus-bound completion;
- the complete storage-backed verification checklist.

## Hash model

### Text hash

```text
sha256(exact UTF-8 text bytes)
```

This is stored as `content_hash`.

### Canonical content artifact hash

```text
sha256(ctrt-canonical-json(full content record))
```

This identifies text plus metadata. It is frozen in the corpus manifest's `content_artifact_ref`.

## Failure behavior

### Before linked-manifest publication

Text, metadata, or reference mismatch prevents the corpus manifest from being written. Valid content artifacts written before a later failure remain append-only but do not constitute a completed corpus.

### Before experiment execution

A missing, corrupted, noncanonical, or mismatched stored content artifact fails in `content-loading`. No experiment completion is created.

### During delegated execution

Previously verified session receipts remain preserved. No stored-content completion marker is created unless the whole corpus-bound lifecycle succeeds.

### During final completion

Persistence or reread failure returns no verified stored-content receipt. The final marker may exist after a reread failure, but the caller receives an explicit verification error rather than success.

## Schemas

- `schemas/canonical-content-artifact.schema.json`
- `schemas/corpus-manifest.schema.json`
- `schemas/stored-content-experiment-completion.schema.json`

## Synthetic fixtures

- `docs/corpora/content/synthetic-content-001.json`
- `docs/corpora/content/synthetic-content-002.json`
- `docs/corpora/content/synthetic-content-003.json`
- `docs/corpora/synthetic-three-items.v0.2.0.json`

These fixtures are deterministic architecture tests. They are not a research corpus and make no claim about instrument quality.

## Explicit limits

This slice does not add:

- arbitrary extraction manifests;
- source-document binaries;
- licensing or consent records;
- encryption or access control;
- retention and deletion policy;
- remote storage or signatures;
- real model or dataset execution;
- aggregate scoring;
- API or frontend surfaces.
