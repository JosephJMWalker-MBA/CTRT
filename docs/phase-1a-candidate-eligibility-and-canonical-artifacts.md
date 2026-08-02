# Phase 1A: Candidate Eligibility and Canonical Artifacts

## Purpose

This slice connects frozen experiment plans to exact candidate-registry authorization and content-derived artifact hashes.

It answers two questions before any real model adapter is introduced:

1. Does the exact registry snapshot authorize every planned instrument?
2. Can every machine-readable experiment artifact receive a deterministic identity derived from its content?

## Execution gate

A frozen plan is eligible only when its candidate-registry reference exactly matches the supplied registry's:

- registry ID;
- registry version;
- canonical SHA-256 hash.

The registry must be accepted.

For each planned instrument, CTRT checks:

- candidate existence;
- analyzer capability;
- executable candidate disposition;
- at least provisional license verification;
- explicit analyzer-ID authorization;
- declared CTRT dimension;
- mandatory revision pinning;
- exact agreement between the plan revision and registry pin.

All failures are preserved together in one eligibility error so reviewers can see every blocking reason.

## Dimension-bound revisions

`InstrumentRevision` now includes `dimension_id`.

This prevents a candidate approved for one construct from being reused silently for another. The dimension must appear in both:

- the frozen experiment plan's declared dimensions; and
- the candidate's registry record.

## Registry separation

The repository contains two distinct registry roles:

### Initial real-candidate registry

`docs/candidates/initial-registry.v0.1.0.json`

This remains a research inventory. It does not authorize execution because candidates are not yet fully pinned and explicitly connected to analyzer identities, and several license reviews remain pending.

### Accepted synthetic registry

`docs/candidates/synthetic-registry.v0.1.0.json`

This authorizes only:

- `synthetic.sentiment.first-signal`;
- `synthetic.sentiment.last-signal`.

Both are deterministic first-party fixtures. Their eligibility proves the governance path without implying any real model selection.

## Canonical JSON profile

`ctrt-canonical-json@0.1.0` deterministically converts supported Python contracts into compact UTF-8 JSON.

The serializer:

- sorts object keys;
- preserves Unicode as UTF-8;
- serializes enums by declared value;
- serializes dataclasses by fields;
- converts tuples to arrays;
- accepts finite JSON numbers only;
- normalizes negative zero;
- rejects unordered, binary, non-string-keyed, and unsupported values.

The canonical payload has no trailing newline.

## Artifact pipeline

`serialize_experiment_run` performs the complete sequence:

1. confirm the eligibility report belongs to the frozen plan;
2. serialize and hash the plan;
3. serialize and hash the eligibility report;
4. serialize and hash the execution environment;
5. serialize and hash each immutable analyzer result;
6. serialize and hash the comparison;
7. build the run record from those computed hashes;
8. serialize and hash the final run record.

The returned `ExperimentArtifactBundle` verifies that the run record references the exact result, comparison, and eligibility hashes in the bundle.

## Preserved boundaries

This implementation does not:

- download or execute any real candidate;
- accept the real-candidate registry for execution;
- construct a benchmark corpus;
- persist artifacts to a database or object store;
- sign or attest artifact hashes;
- claim cross-language canonicalization compatibility;
- produce an aggregate CTRT score.

## Validated failure cases

Tests reject:

- registry ID, version, or hash mismatch;
- draft or superseded registry use;
- proposed, deferred, rejected, or not-selected candidates;
- pending or blocked license review;
- missing analyzer authorization;
- undeclared dimensions;
- missing or mismatched revision pins;
- unsupported canonical values;
- non-finite numbers;
- inconsistent artifact-bundle hashes;
- run records without an eligibility reference.

## Next boundary

The next bounded step is persistent artifact storage and verification for the synthetic pipeline:

- write canonical artifacts without mutation;
- retrieve by ID and hash;
- verify bytes on read;
- reject replacement and hash collisions;
- export a complete experiment manifest.

Real candidate adapter work remains deferred until Label Lens permits the compute allocation and at least two candidates have accepted, pinned, license-reviewed registry entries.
