# TRACE (Chang & Chang 2026) — Commitment-Evidence Prior Art Note

**Status:** research prior art only; no CTRT architecture or authorization change  
**Date:** 2026-09-23

> Naming note: this document refers to the external paper **TRACE: Typed Reasoning And Commitment Evidence** by Edward Y. Chang and Emily J. Chang. It is unrelated to the separate repository `JosephJMWalker-MBA/TRACE`, despite the naming overlap.

## Source

- Chang, E. Y. & Chang, E. J. (2026), *TRACE: An Operational Reasoning Schema for Auditable Agentic Commitments*, arXiv:2607.12480  
  https://arxiv.org/abs/2607.12480

## Why it matters to CTRT

The paper proposes:

- a typed, versioned `TraceRecord`;
- a reference writer procedure;
- measurement gates;
- append-only revision;
- consumer contracts for memory, planning, temporal regret, and verdict reuse;
- an operating discipline summarized as **no durable state change without a record**;
- a benchmark protocol for evaluating the usefulness of those records to downstream consumers.

Its search-and-rescue vignette is especially relevant because the record can defer commitment, request a bounded additional observation, append the new evidence, and reconsider the branch.

The paper explicitly presents this as a schema/contract contribution; the closed-loop vignette is illustrative rather than an empirical performance result.

## CTRT comparison

CTRT already preserves a related but differently scoped lifecycle:

```text
frozen plan
→ exact eligibility
→ canonical inputs
→ execution
→ structured result
→ disagreement / abstention
→ append-only artifacts
→ verified receipt
→ later evaluation
```

The external TRACE proposal adds useful pressure around a different boundary:

```text
evidence currently available
→ commitment gate
→ COMMIT | DEFER
→ bounded additional observation when needed
→ append-only revision
→ downstream consumer contract
```

This is highly compatible with CTRT's existing rule that evidence, measurement, confidence, abstention, and authorization remain distinct.

## What CTRT should inherit or test

Potentially reusable ideas:

- explicit `COMMIT | DEFER`-style commitment state rather than forcing every execution to end in a substantive verdict;
- consumer contracts that say what a record guarantees and what downstream systems must preserve;
- append-only evidence revision rather than silent replacement;
- benchmark design that tests whether richer records improve downstream decisions;
- bounded additional-observation requests as a first-class response to insufficient evidence.

## What TRACE does not replace

The external TRACE paper does not by itself replace CTRT's:

- candidate eligibility;
- dimension eligibility;
- extraction provenance and quality;
- structured confidence;
- taxonomy identity;
- candidate-to-human-reference evaluation;
- constitutional product-door boundaries;
- separation of research eligibility from domain selection and production authorization.

A `TraceRecord` can be a useful commitment-evidence object without becoming a CTRT measurement contract.

## Strongest comparison experiment

Encode one bounded CTRT research decision in both representations:

1. native CTRT artifacts and receipt;
2. an external TRACE-style `TraceRecord`.

Then compare losslessly representable information across:

- exact input identity;
- evidence provenance;
- uncertainty;
- abstention/defer semantics;
- authority/eligibility;
- revision history;
- downstream-use constraints;
- additional-observation requests;
- independently verifiable completion.

The objective should not be to make CTRT win. If TRACE represents the necessary commitment lifecycle more simply, CTRT should inherit that machinery.

## Best next question

> Can CTRT adopt a generic commitment/defer + consumer-contract layer from TRACE without duplicating or weakening CTRT's existing measurement, provenance, and authorization semantics?

Do not answer that by terminology comparison alone; use an executable schema crosswalk or synthetic reference case.
