# Phase 1A: Extraction Manifest Binding

This slice replaces the temporary `content-item:<content-id>` provenance convention with a complete immutable extraction graph.

## Artifact graph

For each content item:

```text
SourceArtifactSnapshot
        │
        ▼
ExtractionManifestSnapshot ─────► ExtractedContentSnapshot
        │                                  │
        └──────── coordinate map ──────────┘
```

The frozen `ExtractionCorpusManifestSnapshot` references all three artifacts by exact ID and SHA-256 hash.

## Synthetic method

The initial fixture declares:

- method ID: `synthetic.identity-text`;
- method revision: `ctrt-synthetic-identity-text@0.1.0`;
- configuration: UTF-8 identity extraction;
- mapping kind: `exact`.

No extractor is installed or executed. The records are fixed synthetic fixtures used to validate governance and provenance contracts.

## Two text-related hashes

The source artifact preserves a hash of exact source UTF-8 bytes.

The extracted-content artifact preserves a hash of exact canonical UTF-8 bytes.

The extraction manifest binds both through source and content artifact references. Equal text does not collapse source, method, configuration, or extraction identity.

## Coordinate requirements

The current exact mapping must:

1. start at source and canonical offset zero;
2. use half-open coordinates;
3. remain contiguous and ordered;
4. preserve span length;
5. map identical text slices;
6. cover both texts completely.

Any unsupported transformation fails closed.

## Ingestion

Use `persist_extracted_corpus` with:

- a frozen experiment plan;
- a frozen extraction corpus manifest;
- ordered source snapshots;
- ordered extraction snapshots;
- ordered extracted-content snapshots.

The function verifies every graph before writing the corpus manifest last.

## Reconstruction

`load_extracted_corpus`:

- reloads each artifact by ID and expected hash;
- verifies canonical JSON;
- rechecks source and canonical text hashes;
- rechecks method and configuration identity;
- rechecks coordinate coverage and exact slices;
- reconstructs provider-neutral `ContentItem` values.

## Execution

`ExtractionBoundExperimentRunner` receives no source or canonical text. Its execution windows contain only content IDs and timestamps.

The runner:

1. verifies the plan, candidate registry, corpus reference, and ordered scope;
2. loads the stored extraction graph;
3. reconstructs `ContentItem` inputs;
4. delegates `MultiContentExperimentRunner`;
5. writes an extraction-bound completion artifact;
6. rereads and reverifies the full chain.

## Failure semantics

- corpus or scope mismatch: `preflight`;
- missing, corrupted, or inconsistent graph: `extraction-loading`;
- governed session failure: `experiment-execution`;
- final marker write failure: `completion-persistence`;
- post-write mismatch: `verification`.

Earlier governed receipts remain append-only if a later content item fails. No extraction-bound completion is produced.

## Excluded

This slice does not add:

- OCR;
- HTML extraction;
- audio transcription;
- normalization mappings;
- source binaries;
- licensing evidence;
- model downloads;
- real datasets;
- aggregate scoring;
- API, frontend, or deployment.
