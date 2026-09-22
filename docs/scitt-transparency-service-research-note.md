# SCITT Transparency Service — Research Note

**Status:** infrastructure prior art only; not an accepted CTRT architecture decision  
**Date:** 2026-09-22

## Why this matters

CTRT already has:

- canonical serialization;
- content-derived SHA-256 identities;
- append-only local artifact storage;
- immutable artifact-ID bindings;
- verified bundle manifests;
- read-time reverification;
- governed execution receipts.

ADR-0011 explicitly deferred signatures, remote durability, and distributed verification.

IETF RFC 9943, *An Architecture for Trustworthy and Transparent Digital Supply Chains* (SCITT), is now relevant prior art for those deferred concerns:

- https://www.rfc-editor.org/rfc/rfc9943.html

## SCITT pattern

At a high level:

```text
signed statement
      ↓
registration policy
      ↓
transparency service
      ↓
append-only / verifiable registration
      ↓
receipt
      ↓
independent relying-party verification
```

This overlaps CTRT's future need to make experiment/evidence records independently verifiable across process or host boundaries.

## Mapping to CTRT

A possible future mapping is:

```text
CTRT canonical artifact / bundle manifest
      ↓
issuer signature
      ↓
SCITT-compatible signed statement
      ↓
registration policy
      ↓
transparency service
      ↓
receipt stored alongside CTRT evidence
```

Potential candidates for registration include:

- frozen experiment plans;
- candidate-eligibility decisions;
- execution receipts;
- experiment-completion manifests;
- human-reference freeze records;
- result-bearing evaluation manifests.

## Boundary: registration is not semantic truth

A SCITT receipt can help establish that a signed statement was registered under a declared policy and is independently verifiable.

It does **not** establish:

```text
registered
!= accurate
!= calibrated
!= valid measurement
!= authorized for a domain
!= selected for production
!= suitable for consequential use
```

CTRT's existing candidate eligibility, calibration, disagreement, abstention, evidence-quality, and human-reference rules remain separate.

## Why CTRT should investigate before inventing more infrastructure

The local Phase 1A artifact store was intentionally minimal. That was the correct boundary for proving append-only persistence invariants.

Now that a standards-track transparency architecture exists, CTRT should not casually invent bespoke machinery for:

- signed statement registration;
- independent inclusion receipts;
- transparency-service verification;
- multi-party receipt checking.

Those functions should first be evaluated against SCITT.

## What SCITT does not replace

SCITT does not replace:

- CTRT canonicalization;
- analyzer/candidate registries;
- dimension eligibility;
- extraction provenance;
- structured confidence;
- human-reference methodology;
- disagreement preservation;
- governed execution policy;
- CTRT's distinction between evidence and interpretation.

It is best understood as a potential **transport/registration/verifiability substrate** around selected CTRT artifacts.

## Best next research question

Can one existing CTRT completion manifest be wrapped as a SCITT-compatible signed statement and independently receipt-verified **without changing the manifest's canonical bytes or weakening CTRT's current evidence semantics**?

That should be explored as a bounded interoperability spike before any new distributed provenance infrastructure is designed.
