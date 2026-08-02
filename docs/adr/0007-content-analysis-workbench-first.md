# ADR-0007: Build the Content Analysis Workbench Before a CTRT Scoring Product

- **Status:** Proposed
- **Date:** 2026-08-02
- **Decision scope:** Phase 1 architecture and first executable deliverable

## Context

Open-source sentiment, emotion, toxicity, extraction, and transcript technologies already address parts of the CTRT problem. Choosing one implementation per category before comparative evaluation would convert untested assumptions into architecture.

A direct request to “build the CTRT analyzer” would also invite premature decisions about:

- which models are authoritative;
- how incompatible taxonomies are normalized;
- whether model probabilities are calibrated;
- how extraction defects affect downstream measurements;
- how disagreement is represented;
- whether a combined score is useful at all.

The Phase 0 Constitution instead requires provider neutrality, preserved raw outputs, visible disagreement, explicit uncertainty, versioned operational definitions, and reproducible evaluation.

## Decision

The first executable Phase 1 deliverable will be a **Content Analysis Workbench**, not a user-facing CTRT scoring product.

The workbench will:

1. register candidate technologies without treating them as selected;
2. run multiple eligible instruments against the same canonical content;
3. preserve exact versions, configurations, taxonomies, raw outputs, normalized outputs, confidence vectors, timings, warnings, failures, and resource observations;
4. compare results side by side without silently averaging disagreement;
5. store repeatable experiment and benchmark records;
6. evaluate extraction technologies separately from downstream analyzers;
7. support abstention and partial results as valid outcomes;
8. produce evidence for later model-selection records.

No overall CTRT score or scalar tone rating will be produced by the initial workbench.

## Provider abstraction

CTRT will retain the generic provider-neutral `Analyzer` contract keyed by `dimension_id`.

It will **not** create separate `SentimentProvider`, `EmotionProvider`, and `ToxicityProvider` interfaces unless a demonstrated technical requirement emerges. Dimension-specific interfaces would duplicate the existing abstraction and encourage model categories to harden into architecture.

Extraction and transcript acquisition are upstream capabilities and require contracts distinct from semantic analyzers because their outputs, failure modes, provenance, and evaluation methods differ.

## Candidate technologies

Named technologies belong in a versioned candidate registry. Inclusion means only:

> This technology is sufficiently relevant to justify evaluation under a declared protocol.

Inclusion does not mean endorsement, selection, compatibility, calibration, production readiness, or licensing approval.

Every candidate must receive a recorded evaluation disposition:

- proposed;
- eligible for evaluation;
- deferred;
- rejected before execution;
- evaluated;
- selected for a declared domain;
- not selected.

## Selection boundary

A technology may be selected only through a versioned model-selection record that states:

- the CTRT dimension or extraction task;
- domain and language boundaries;
- candidate alternatives;
- corpus and protocol versions;
- accuracy or agreement evidence;
- calibration evidence or its absence;
- latency and resource measurements;
- deployment and licensing constraints;
- known failure modes;
- replacement triggers.

“Best model” is not a valid conclusion without a specified construct, domain, corpus, metric, and use.

## Consequences

### Positive

- Architecture follows evidence rather than model popularity.
- Candidate models can be replaced without redesigning CTRT.
- Negative results and disagreement become research assets.
- The system can explain why a technology was selected.
- Extraction quality remains visible as an upstream dependency.
- The workbench itself becomes a reusable research instrument.

### Costs

- The first user-facing score is delayed.
- The project must maintain candidate, experiment, and selection records.
- Side-by-side comparison requires careful taxonomy handling.
- Evaluation design becomes part of the product rather than an informal development step.

## Rejected alternatives

### Build one analyzer stack immediately

Rejected because it would encode unvalidated model and normalization choices before comparison.

### Create one provider interface per analysis category

Rejected for Phase 1 because the generic `Analyzer` contract already expresses replaceability through `dimension_id`, analyzer identity, and taxonomy identity.

### Select models from published benchmark claims alone

Rejected because published metrics may use domains, taxonomies, preprocessing, and datasets that do not match CTRT’s intended use.

### Produce a provisional overall rating during workbench development

Rejected because it would bias evaluation toward confirming an aggregation method that has not yet earned eligibility.

## Review trigger

Revisit this decision only after the workbench has produced enough comparative evidence to support at least one domain-bounded instrument selection record.