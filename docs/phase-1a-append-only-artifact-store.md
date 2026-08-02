# Phase 1A: Append-only canonical artifact store

## Purpose

This slice persists the canonical experiment artifacts introduced by ADR-0010 without adding a database, remote service, model dependency, or production deployment.

It proves that CTRT can retain canonical bytes by immutable identity, retrieve them later, detect tampering, and distinguish a complete experiment bundle from a partial set of writes.

## Storage layout

```text
<store-root>/
  blobs/
    sha256/
      <payload-digest>
  ids/
    sha256/
      <sha256-of-artifact-id>.json
```

Blob filenames are derived only from validated hashes. Artifact IDs never become filesystem paths.

Each ID-index record contains:

- artifact ID;
- canonical artifact hash;
- canonicalization version;
- media type.

## Append behavior

`FileSystemArtifactStore.append()` accepts a `CanonicalArtifact`.

- A new hash writes one content-addressed blob.
- A new artifact ID writes one immutable ID-index record.
- Repeating the exact artifact is idempotent.
- Reusing an artifact ID with a different hash fails.
- Finding different bytes under an existing hash fails as collision or corruption.
- No update or delete operation exists.

Exclusive file creation prevents normal writers from overwriting existing paths.

## Read behavior

`get(artifact_id, expected_hash=...)`:

1. resolves the immutable ID index;
2. verifies the requested ID;
3. optionally verifies the expected hash;
4. reads the content-addressed blob;
5. recomputes SHA-256;
6. reconstructs a validated `CanonicalArtifact`.

`read_payload(artifact_hash)` provides hash-addressed retrieval with the same digest verification.

## Experiment bundle persistence

`persist_experiment_bundle()` stores these artifacts independently and in dependency order:

1. plan;
2. candidate-eligibility report;
3. execution environment;
4. ordered analyzer results;
5. comparison;
6. run record.

It then creates and stores a canonical bundle manifest with role-bound references. The manifest is written last.

Required roles are:

- `plan`;
- `candidate-eligibility`;
- `environment`;
- `result:0` and at least one additional result;
- `comparison`;
- `run-record`.

`verify_experiment_bundle()` re-verifies the manifest and every referenced artifact by ID and expected hash.

## Failure semantics

The store raises explicit failures for:

- missing IDs or hashes;
- artifact-ID replacement attempts;
- unreadable or malformed index records;
- unexpected hashes;
- corrupted or tampered blobs;
- ID-index key collisions;
- incomplete or inconsistent bundle manifests.

An interrupted bundle write may leave valid unreferenced artifacts. Those bytes are not treated as a complete experiment because no verified bundle manifest exists.

## Tests

The executable tests cover:

- canonical round-trip persistence;
- idempotent repeat writes;
- append-only ID conflict rejection;
- explicit missing-artifact failures;
- read-time detection of tampered bytes;
- complete synthetic experiment-bundle persistence;
- bundle-member corruption detection;
- bundle-manifest schema validity.

## Scope boundary

This implementation does not provide:

- database transactions;
- remote storage;
- multi-host consistency;
- signatures or worker attestation;
- authentication or authorization;
- deletion or garbage collection;
- retention, backup, or disaster recovery;
- real candidate execution.

The store validates the persistence architecture only.
