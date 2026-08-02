# ADR-0006: Structured Confidence and Abstention

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

A scalar confidence value collapses several distinct questions:

- what probability an instrument reported;
- whether that probability is calibrated for the declared domain;
- whether the content is within the instrument's evaluated applicability boundary;
- whether extraction preserved the content needed for analysis;
- whether multiple instruments agree;
- whether the system should abstain;
- how much unresolved ambiguity the system deliberately preserves.

These signals are not interchangeable. A high model-reported probability cannot repair failed extraction, out-of-domain use, or material inter-instrument conflict.

## Decision

CTRT will represent confidence as a required, structured vector at both analyzer-result and report levels.

The vector contains:

1. instrument probability;
2. calibration state;
3. applicability state;
4. extraction quality;
5. inter-instrument agreement;
6. system abstention;
7. an ambiguity budget that records unresolved uncertainty without converting it into a scalar.

### Analyzer-result lifecycle

An immutable analyzer result records the vector available at execution time. Its agreement state is normally `single-instrument`. It must not be mutated after comparison with other analyzers.

### Report lifecycle

Report assembly creates a separate report-level confidence vector. It may enrich agreement, applicability, extraction, and abstention using a declared aggregation policy while preserving every original analyzer result.

### No silent aggregation

Phase 0 prohibits a single confidence percentage. Confidence signals may not be averaged, multiplied, weighted, or otherwise collapsed unless a future explicit, versioned method is accepted through the research protocol and recorded with the report.

Every aggregation policy must declare:

- which confidence signals it may read;
- which signals may trigger abstention;
- which outputs it is forbidden to create.

`scalar-confidence` is a required forbidden output during Phase 0.

### Critical abstention

The following states force system abstention independently of instrument probability:

- applicability is `out-of-domain`;
- extraction quality is `failed`;
- agreement is `strong-disagreement`;
- agreement evaluation itself returns `abstain`.

Borderline applicability, degraded extraction, unknown calibration, and partial disagreement remain visible and may trigger abstention under a more restrictive declared policy, but they are not automatically collapsed into a numerical penalty.

### Calibration

Calibration is `unknown` until the instrument has been evaluated under the CTRT research protocol for a declared domain. Model-reported probabilities are not treated as calibrated merely because they sum to one or are labeled confidence scores.

### Agreement

Agreement is only measured when at least two compatible analyzers participate. A single analyzer must report `single-instrument` with no invented agreement metric or value.

### Extraction inheritance

Extraction quality is upstream evidence. Partial or degraded extraction must appear in downstream limitations. Failed extraction forces abstention.

### Ambiguity budget

The ambiguity budget is descriptive, not numeric. It records uncertainty preserved, any forced resolutions introduced by a method, and whether unresolved ambiguity exceeds the method's declared ability to summarize faithfully.

### Explanation constraint

An explanation may summarize the vector in natural language. It may not invent a scalar confidence percentage, imply calibration that has not been demonstrated, or conceal a critical abstention signal.

## Consequences

- ModelResult records gain a required confidence vector.
- Report records surface a separate report-level confidence vector.
- Per-score confidence fields are removed from normalized measurements.
- Applicability moves from an unstructured string into the vector.
- Aggregation policies become explicit canonical records.
- Explanations must identify the confidence signals they summarize.
- Phase 0 reports preserve uncertainty rather than forcing false precision.
