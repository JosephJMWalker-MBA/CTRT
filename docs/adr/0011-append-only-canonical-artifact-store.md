# ADR-0011: Append-only canonical artifact store

**Status:** Accepted  
**Date:** 2026-08-02  
**Deciders:** CTRT project stewardship

## Context

ADR-0010 established deterministic canonical serialization and content-derived SHA-256 identities for governed experiment artifacts. Those identities are insufficient if the bytes are kept only in memory, silently replaced, or returned without verification.

Phase 1A needs a minimal persistence boundary before any real candidate can execute. The boundary must preserve canonical bytes, reject mutation, expose corruption, and prove when every member of an experiment bundle has been written. It must not prematurely introduce a database, distributed object store, API service, or production deployment architecture.

## Decision

CTRT will provide a dependency-free local filesystem artifact store with two append-only structures:

1. **Content-addressed blobs** keyed by the lowercase SHA-256 digest of canonical bytes.
2. **Artifact-ID indexes** keyed by a SHA-256 digest of the artifact ID and containing the exact artifact ID, artifact hash, canonicalization version, and media type.

The following invariants apply:

- one artifact ID may reference exactly one artifact hash;
- storing the same artifact ID, hash, metadata, and bytes again is idempotent;
- attempting to assign different bytes or a different hash to an existing artifact ID is rejected;
- an existing blob whose bytes differ from the requested payload is treated as collision or corruption;
- every retrieval recomputes SHA-256 before returning bytes;
- expected hashes may be supplied at retrieval and must match the stored ID index;
- store operations expose no update or delete method;
- filenames are derived from hashes rather than untrusted artifact IDs.

Writes use exclusive file creation. The blob is written before the ID index. An interrupted operation may leave an unreferenced blob, but it cannot make an artifact ID point to partially written or different bytes.

## Complete experiment bundles

A complete synthetic experiment bundle contains:

- frozen plan;
- candidate-eligibility decision;
- execution environment;
- at least two analyzer results;
- comparison;
- run record.

Each member is stored independently. A canonical `ExperimentBundleManifest` is written **last** and acts as the completion marker. Its role-bound references identify every required artifact by ID and hash.

A bundle is considered complete only when:

1. its manifest is present and hash-valid;
2. the manifest bytes match the expected canonical manifest;
3. every referenced artifact can be retrieved by ID and expected hash;
4. every referenced blob passes SHA-256 verification.

Partially persisted artifacts remain valid append-only artifacts, but they do not constitute a complete experiment bundle without a verified manifest.

## Canonical scope

The store accepts `CanonicalArtifact` instances produced under `ctrt-canonical-json@0.1.0` with media type `application/json`.

This decision does not claim:

- database transactions;
- rollback of partial bundle writes;
- process or host attestation;
- cryptographic signatures;
- distributed consistency;
- remote durability;
- backup or retention policy;
- authorization or access control.

Those concerns require separate decisions before production use.

## Consequences

### Positive

- canonical bytes survive beyond one Python process;
- silent artifact replacement is structurally rejected;
- corruption is detected during ordinary reads, not only during audits;
- complete experiment bundles have an explicit machine-readable completion marker;
- storage remains dependency-free and local for Phase 1A;
- later database or object-store adapters can implement the same invariants.

### Costs and limitations

- bundle persistence is not an all-or-nothing transaction;
- interrupted writes may leave unreferenced content-addressed blobs;
- concurrent writers rely on exclusive filesystem creation and subsequent verification;
- local filesystem durability depends on the host and its backup practices;
- no garbage collection is provided because deletion policy has not been authorized.

## Rejected alternatives

### Mutable files named directly from artifact IDs

Rejected because IDs may contain unsafe path characters and mutable paths permit silent replacement.

### One monolithic bundle file

Rejected because individual artifacts must remain independently identifiable, retrievable, and verifiable.

### Database or cloud object storage now

Deferred because Phase 1A needs to prove storage invariants before selecting infrastructure.

### Treating successful writes as sufficient without read verification

Rejected because disk corruption, manual tampering, and hash/index mismatch must remain observable.

## Follow-on work

After this decision is implemented and validated, the next bounded work should define an experiment execution session that performs preflight checks, runs the synthetic workbench, persists the canonical bundle, and returns only after the bundle manifest re-verifies. Real candidate adapters remain out of scope.
