# ADR-0015: Canonical content artifacts are stored before execution

- **Status:** Accepted
- **Date:** 2026-08-02
- **Phase:** 1A — Content Analysis Workbench

## Context

ADR-0014 bound a frozen experiment plan to an ordered corpus manifest containing each content ID, exact UTF-8 text hash, language, source type, and extraction identity. That gate proved that caller-supplied content matched the frozen corpus before execution.

The experiment still depended on the caller to resupply the original text and metadata at run time. A plan and corpus manifest could identify the intended inputs without preserving the actual analyzer input bytes inside CTRT's append-only artifact store.

Reproducible execution requires the system to preserve and later reconstruct those inputs itself.

## Decision

CTRT will represent every executable content item as an immutable canonical JSON artifact containing:

- a deterministic artifact ID;
- content ID;
- exact canonical text;
- SHA-256 of the exact UTF-8 text bytes;
- language;
- source type;
- source URI, including explicit `null`;
- extraction identity.

The artifact ID derives from the content ID and exact text hash:

```text
canonical-content:<content-id>:<text-sha256-digest>
```

The corpus manifest links each content entry to the expected canonical artifact ID and canonical artifact hash.

### Two hashes remain distinct

`content_hash` identifies only the exact UTF-8 text bytes presented to analyzers.

`artifact_hash` identifies the full canonical JSON record, including text and bound metadata.

Neither hash substitutes for the other. A text-preserving metadata change keeps the text hash but changes the artifact hash. A text change changes both the text-derived artifact ID and the artifact hash.

### Manifest evolution is append-only

The existing unlinked synthetic corpus `0.1.0` remains unchanged.

A new linked corpus version `0.2.0` references the canonical content artifacts. Legacy unlinked manifests remain parseable and usable by earlier corpus-binding logic, but they cannot authorize storage-backed execution.

### Ingestion completion boundary

Canonical corpus ingestion performs these steps in order:

1. verify the frozen plan and corpus binding against supplied content;
2. construct and verify each canonical content artifact;
3. append each content artifact independently;
4. append the linked corpus manifest last;
5. reread the manifest and every referenced content artifact;
6. reconstruct the ordered `ContentItem` population from storage.

If ingestion fails before step 4, independently written content artifacts may remain as valid append-only records, but no linked corpus manifest claims that the corpus is complete.

### Storage-backed execution boundary

`StoredContentExperimentRunner` does not accept content text or metadata.

Its request contains only:

- the exact ordered content IDs;
- externally recorded start and completion timestamps.

Before execution it:

1. verifies the frozen plan, candidate registry, linked corpus manifest, and ordered execution windows;
2. loads every content artifact by the ID and hash frozen in the corpus manifest;
3. verifies canonical JSON, text hash, metadata, and extraction identity;
4. reconstructs each `ContentItem` from storage;
5. delegates the existing corpus-bound experiment lifecycle;
6. writes a final stored-content completion marker linking all content artifacts to the verified corpus-bound completion;
7. rereads and re-verifies the complete chain.

### Completion does not aggregate measurements

A verified stored-content completion proves:

- exact stored inputs were linked by the frozen corpus manifest;
- those inputs were reverified and reconstructed;
- the corpus-bound experiment lifecycle completed;
- the final provenance artifacts reverified.

It does not imply:

- analyzer success;
- instrument agreement;
- non-abstention;
- accuracy or calibration;
- favorable content quality;
- an aggregate CTRT score.

## Consequences

### Positive

- Experiments no longer rely on callers to resupply original text bytes.
- Text identity and metadata identity remain independently inspectable.
- Corpus manifests can prove the exact stored inputs they authorize.
- Repeated execution can reconstruct identical provider-neutral inputs.
- Legacy frozen manifests remain preserved rather than silently rewritten.
- Partial content artifacts do not falsely declare a complete corpus.

### Costs and limits

- The local filesystem store is still not a transactional database.
- Canonical content records may contain sensitive or licensed text; access control and retention policy remain unresolved.
- The current extraction identity remains limited to `content-item:<content-id>`.
- Exact UTF-8 bytes are authoritative; no Unicode normalization policy is introduced.
- Source documents, licensing evidence, signatures, remote durability, and deletion policy remain out of scope.

## Rejected alternatives

### Continue accepting caller-supplied content at execution time

Rejected because the stored experiment record would remain dependent on external bytes that CTRT could not independently reconstruct.

### Store only text blobs

Rejected because language, source identity, URI, and extraction identity are part of the reproducible analyzer input contract.

### Use the text hash as the full artifact hash

Rejected because it would hide metadata changes and collapse two different provenance questions into one identifier.

### Rewrite the existing `0.1.0` corpus manifest

Rejected because frozen research artifacts are append-only. The linked corpus is a new version.

### Embed all content text directly in the corpus manifest

Rejected because independent content artifacts provide reusable content addressing, isolated integrity checks, and clearer manifest completion semantics.
