# ADR-0003: Treat Disagreement and Abstention as First-Class Results

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

When multiple instruments analyze the same content, their outputs may conflict. A conventional pipeline often averages the conflict away or selects the most convenient result. Instruments may also receive content outside their evaluated domain or lack sufficient context.

## Decision

CTRT will represent disagreement and abstention explicitly.

- Every analyzer result has a status: `success`, `partial`, `abstained`, or `failed`.
- Instrument-level results remain available after aggregation.
- Agreement metrics are separate from model-reported confidence.
- Aggregators may exclude a result only through a declared rule and must record the exclusion.
- The analysis report may remain partial or abstain from an aggregate when disagreement, applicability, extraction quality, or missing evidence crosses a declared boundary.

## Consequences

- Users may receive uncertainty rather than a simple answer.
- Aggregate logic becomes more conservative and more auditable.
- Benchmarking must evaluate disagreement patterns rather than accuracy alone.
- Explanations must communicate material conflict.
- The system avoids converting ambiguity into false precision.
