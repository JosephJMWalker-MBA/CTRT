# ADR-0059: Surface verified evidence before adding real analyzers

- **Status:** Accepted
- **Date:** 2026-08-05
- **Decision scope:** First Phase 1B application-shell capability
- **Related:** Constitution Articles II, IV, VI, VIII, and X; ADR-0007; ADR-0012; ADR-0015; ADR-0057; ADR-0058

## Context

Phase 1A closed the synthetic governance architecture, published the technical report, and established a constitutional regression gate. The next project risk is no longer missing governance machinery. It is building a simpler interface that accidentally discards the evidence and distinctions the machinery was created to preserve.

Two intended human workflows now guide Phase 1B:

1. a creator inspects content before deciding whether to publish; and
2. a person seeks to understand explicitly submitted content without delegating discernment to a hidden verdict.

Neither workflow should begin by adding more analyzers. The first implementation step should prove that existing verified evidence can be made readable without creating an overall score, scalar confidence summary, content verdict, publish recommendation, or production-readiness claim.

A basic `VerifiedExecutionReceipt` is not sufficient for quoted evidence because its bundle verifies analyzer results but does not itself preserve the canonical content text. The later stored-content lifecycle does preserve exact content artifacts and the verified per-content session receipts that analyzed them.

## Decision

Phase 1B begins with a derived evidence reader over:

```text
VerifiedStoredContentExperimentReceipt
+ FileSystemArtifactStore
```

The reader SHALL:

1. require a verified stored-content receipt;
2. re-read the stored-content, corpus-bound, and experiment completion markers;
3. re-read each canonical content artifact by exact ID and hash;
4. re-read each persisted session receipt and compare it with the supplied receipt object;
5. reconstruct and re-verify each experiment bundle and all of its members;
6. require result, analyzer, status, content, extraction, and comparison order to match the verified receipts exactly;
7. quote evidence spans only from the reverified canonical content text;
8. preserve analyzer identity, taxonomy, raw output, normalized instrument measurements, structured confidence dimensions, warnings, errors, disagreement, abstention, limitations, and immutable artifact references;
9. render a deterministic human-readable Markdown view; and
10. state that canonical artifacts remain controlling.

The resulting `StoredContentEvidenceView` is a presentation model. It is not appended to the canonical artifact store and does not become a new measurement, completion marker, or governance authority.

## Interpretation boundary

The reader may display:

- exact stored content;
- instrument-level normalized measurements;
- exact evidence excerpts and coordinates;
- analyzer, model, adapter, taxonomy, and dimension identity;
- applicability, extraction quality, calibration state, abstention, ambiguity, warnings, and limitations;
- comparison-level agreement and disagreement; and
- lifecycle and artifact references.

The reader may not create:

- an overall CTRT score;
- an overall sentiment or tone judgment;
- scalar or aggregate confidence;
- a `safe`, `unsafe`, `good`, or `bad` content verdict;
- a publish or restriction recommendation;
- a creator or audience profile;
- a claim of accuracy, model selection, or production readiness; or
- a replacement for any canonical artifact.

`verified` remains a statement about lifecycle and evidence integrity. It does not imply that analyzers agreed or produced a measurement.

## Why stored-content evidence is the first boundary

A caller-supplied string is not sufficient for a trustworthy evidence view. The interface must not quote text merely because it has the same content ID as a receipt. The exact text bytes must be loaded from the immutable content reference already bound to the verified lifecycle.

This decision therefore starts with the `0.2.0` stored-content path rather than the earlier single-session path. Later Phase 1B views may target the stricter extraction-manifest and quality-governed lifecycles, but they must retain the same rule: presentation quotes only reverified canonical content.

## Consequences

### Positive

- Phase 1B begins by making completed evidence useful to a person.
- Exact excerpts are sourced from stored content rather than caller trust.
- Presentation remains downstream of the constitutional kernel.
- The same view model can later support creator preflight and content-understanding interfaces.
- Usability work can proceed before real-candidate admission.
- The first application layer exercises disagreement and abstention rather than hiding them.

### Costs

- The view reader repeats intentional read-time verification and is not a cheap formatter.
- The first renderer is Markdown rather than a web or desktop interface.
- The view exposes technical identity and provenance that later interfaces must progressively explain without suppressing.
- The current reader targets the stored-content lifecycle and not every later Phase 1A receipt type.

## Rejected alternatives

### Add a real analyzer first

Rejected. A new analyzer would increase the amount of evidence without proving the project can present existing evidence faithfully.

### Build a creator-facing score card

Rejected. A compact score or recommendation would collapse the exact distinctions Phase 1A proved.

### Accept caller-supplied text beside a session receipt

Rejected. The basic receipt does not bind the caller's supplied bytes strongly enough for quoted evidence.

### Persist the human-readable view as a new canonical artifact

Rejected for this slice. The presentation is derived and may evolve. Its immutable references identify the canonical records that remain controlling.

### Begin with ambient parental monitoring

Rejected. Phase 1B begins with explicitly submitted or already governed content. Passive monitoring, consent, access control, child privacy, and restriction authority require separate human and governance decisions.

## Follow-on sequence

After this reader is accepted, bounded work may proceed to:

1. a plain-language creator-preflight presentation using the same derived view;
2. an explicitly submitted content-understanding presentation;
3. a real user interface that surfaces, rather than replaces, the evidence graph;
4. controlled admission of one pinned real analyzer; and
5. empirical evaluation under frozen protocols.

Aggregation remains out of scope until the measurement and evaluation evidence earns a separate constitutional decision.
