# ADR-0010: Require Candidate Eligibility and Canonical Artifact Identity

- **Status:** Accepted for Phase 1A
- **Date:** 2026-08-02
- **Decision scope:** Candidate execution authorization and machine-readable artifact identity

## Context

Frozen experiment plans and append-only run records identify registry, protocol, corpus, instrument, environment, result, and comparison artifacts by version and hash. Those references are meaningful only if CTRT defines:

1. which exact registry state authorizes an instrument to execute; and
2. how machine-readable artifacts are serialized before their hashes are computed.

Without an eligibility gate, a plan could name a candidate that is merely proposed, deferred, license-blocked, unpinned, outside the declared dimension, or represented by an analyzer identity the registry never approved.

Without deterministic serialization, semantically identical records could receive different hashes because of mapping order or formatting, while unsupported values such as non-finite numbers could enter supposedly canonical artifacts.

## Decision

### Exact registry authorization

Every experiment plan must identify one candidate-registry artifact by:

- registry ID;
- registry version;
- canonical SHA-256 hash.

The supplied registry must match all three values exactly and must have lifecycle status `accepted`.

Registry inclusion alone never authorizes execution.

### Instrument-level eligibility

Each planned `InstrumentRevision` must declare:

- candidate ID;
- analyzer ID;
- CTRT dimension ID;
- exact implementation revision;
- adapter version;
- configuration hash.

Before execution, the matching candidate record must:

- exist in the exact registry snapshot;
- declare capability type `analyzer`;
- have disposition `eligible_for_evaluation`, `evaluated`, or `selected_for_domain`;
- have license review `provisionally_verified` or `verified`;
- explicitly authorize the analyzer ID;
- declare the planned dimension;
- require immutable revision pinning;
- contain a non-null pinned revision equal to the planned implementation revision.

A `pending` or `blocked` license review does not authorize execution.

### Eligibility artifact

A successful eligibility decision becomes an immutable, canonically serialized artifact containing:

- experiment ID and version;
- exact candidate-registry reference;
- authorized candidate IDs;
- authorized analyzer IDs.

Every experiment run record must reference the eligibility artifact for its exact plan version.

### Canonical JSON profile

Phase 1A defines `ctrt-canonical-json@0.1.0` for machine-readable artifact identity.

The profile uses:

- UTF-8 JSON;
- no byte-order mark;
- no trailing newline;
- lexicographically sorted object keys;
- compact separators;
- JSON strings with non-ASCII characters preserved as UTF-8;
- enum values represented by their declared string values;
- dataclasses represented by their declared fields;
- tuples and lists represented as JSON arrays;
- finite JSON numbers only;
- negative zero normalized to `0.0`.

The profile rejects:

- non-string mapping keys;
- sets and frozensets;
- bytes and bytearrays;
- NaN and infinity;
- unsupported runtime objects.

This is a CTRT project canonicalization profile. It does not claim full RFC 8785 compatibility.

### Content-derived hashes only

The canonical artifact pipeline serializes and hashes:

1. the frozen experiment plan;
2. the candidate eligibility report;
3. the execution environment;
4. each immutable analyzer result;
5. the comparison record;
6. the final experiment run record.

Run records are built from those computed hashes. Placeholder or caller-invented hashes are not used by the canonical pipeline.

### Synthetic authorization boundary

A separate accepted registry authorizes only the two deterministic first-party fixture analyzers.

The initial real-candidate registry remains non-executable. Its entries do not yet combine accepted registry status, explicit analyzer authorization, sufficient license review, and exact pinned implementation revisions.

## Consequences

### Positive

- A plan cannot silently execute a different candidate revision from the one reviewed.
- Candidate lifecycle, license, identity, and dimension boundaries become executable gates.
- Identical supported records produce identical artifact hashes.
- Result and comparison references are tied to actual serialized content.
- The synthetic workbench can test the full governance path without approving real models.

### Costs

- Registry changes alter the canonical registry hash and require a new plan version or amendment.
- Every executable analyzer identity must be explicitly listed in the registry.
- Canonicalization-profile changes require a new profile version and migration strategy.
- Persistent artifact storage remains necessary before large experiment runs.

## Rejected alternatives

### Trust candidate status alone

Rejected because `eligible_for_evaluation` does not identify an analyzer adapter, dimension, configuration, license state, or immutable revision.

### Hash ordinary pretty-printed JSON

Rejected because whitespace and key ordering would make artifact identity dependent on incidental formatting.

### Allow pending license review for execution

Rejected because CTRT should not download or execute a candidate until its use is at least provisionally reviewed.

### Add real candidates to the accepted synthetic registry

Rejected because fixture authorization must not imply that real models have passed revision, license, or domain review.

### Claim RFC 8785 compliance

Rejected because the initial profile intentionally defines only the subset CTRT currently needs and has tested.

## Review trigger

Revisit when CTRT introduces persistent artifact storage, signed manifests, cross-language implementations, distributed workers, or the first real candidate adapter.
