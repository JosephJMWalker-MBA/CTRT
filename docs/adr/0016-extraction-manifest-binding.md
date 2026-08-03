# ADR-0016: Extraction manifests replace implicit content-item provenance

- **Status:** Accepted
- **Date:** 2026-08-02
- **Phase:** 1A — Content Analysis Workbench

## Context

ADR-0015 made canonical analyzer inputs reproducible by storing exact text and metadata before execution. Those records still used the temporary extraction identity:

```text
content-item:<content-id>
```

That convention identified the output but did not explain how the canonical text was produced from a source artifact. It could not preserve extractor identity, implementation revision, configuration, or source-to-canonical coordinates.

Reliable extraction evaluation requires the extraction step to become an inspectable immutable artifact rather than an implicit label.

## Decision

CTRT will introduce a separate extraction-backed corpus path containing three immutable artifacts for every content item:

1. a source artifact;
2. an extracted-content artifact;
3. an extraction manifest linking the two.

The frozen extraction corpus references all three artifacts by exact ID and SHA-256 hash.

### Source artifacts

A source artifact records:

- source ID;
- exact source text for the dependency-free synthetic fixture;
- SHA-256 of the exact UTF-8 source bytes;
- source type;
- source URI, including explicit `null`;
- canonical artifact identity.

This phase does not claim to preserve arbitrary source binaries, page images, audio, or licensing evidence.

### Extraction identity

An extraction artifact ID derives from:

- content ID;
- exact source artifact reference;
- extraction method ID;
- immutable method revision;
- canonical configuration hash;
- expected canonical text hash.

Changing any of these inputs creates a different extraction identity.

### Extracted-content identity

The extracted-content artifact records the exact canonical text, language, source metadata, and extraction artifact ID.

Its artifact ID derives from:

- content ID;
- canonical text hash;
- extraction identity.

The same text produced by a different extraction process therefore remains distinguishable.

### Coordinate mapping

Every extraction manifest includes ordered half-open source and canonical coordinate spans.

The initial mapping vocabulary contains only:

```text
exact
```

Exact spans must:

- begin at zero;
- be contiguous and ordered in both coordinate spaces;
- preserve span length;
- map identical source and canonical text slices;
- cover the complete source and canonical text.

Normalization, omission, reordering, OCR geometry, many-to-one mapping, and uncertain coordinates remain deferred until explicit mapping kinds and validation semantics are adopted.

### Persistence order

Extraction corpus ingestion writes artifacts in this order:

1. source artifact;
2. extracted-content artifact;
3. extraction manifest;
4. frozen extraction corpus manifest last.

Partial artifacts may remain valid after failure, but no corpus manifest claims a complete extraction corpus until every graph member has been stored and reverified.

### Execution

`ExtractionBoundExperimentRunner` accepts only:

- the frozen plan;
- candidate registry;
- frozen extraction corpus manifest;
- execution environment;
- ordered content IDs and timestamps.

It reloads and verifies the entire source-extraction-content graph, reconstructs `ContentItem` values from stored extracted-content artifacts, and delegates the existing governed multi-content runner.

A final extraction-bound completion artifact links:

- the exact source artifacts;
- extraction manifests;
- extracted-content artifacts;
- frozen extraction corpus;
- verified experiment completion.

### No analytical aggregation

A verified extraction-bound completion proves provenance and lifecycle integrity. It does not imply analyzer success, agreement, non-abstention, extraction accuracy on real documents, or an aggregate CTRT score.

## Consequences

### Positive

- Extraction provenance becomes inspectable and immutable.
- Method or configuration drift changes artifact identity.
- Identical canonical text from different extraction processes remains distinguishable.
- Source-to-canonical coordinates are preserved explicitly.
- Execution no longer depends on caller-supplied text.
- Legacy corpus and content artifacts remain unchanged.

### Costs and limits

- Only exact identity mappings are currently executable.
- Synthetic source artifacts contain text rather than source-document binaries.
- No real OCR, HTML parser, transcript engine, or document extractor runs.
- Extraction quality is not yet benchmarked.
- Remote durability, signatures, access control, retention, and licensing remain unresolved.

## Rejected alternatives

### Continue using `content-item:<content-id>`

Rejected because it hides the extraction method and source relationship.

### Put extraction metadata only in the corpus manifest

Rejected because extraction records should be independently addressable, reusable, and verifiable.

### Treat equal output text as equal extraction provenance

Rejected because different methods, revisions, configurations, or sources may produce identical text while carrying materially different provenance.

### Add normalization mappings now

Rejected because mapping semantics must be explicit and testable rather than inferred.
