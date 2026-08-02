# Dimension Eligibility Registry

This directory contains the canonical Phase 0 governance record for each candidate CTRT dimension.

A dimension record answers a question that model documentation cannot answer:

> Is this construct sufficiently defined, bounded, and testable to appear in an experimental CTRT report?

## Current decisions

| Dimension | Status | Experimental report | Overall rating |
|---|---|---:|---:|
| Sentiment valence | Defined | Eligible | No |
| Emotion profile | Defined | Eligible | No |
| Toxicity indicators | Defined | Eligible | No |
| Emotional intensity | Proposed | Ineligible | No |

These are construct decisions, not model-selection decisions. No analyzer is approved merely because its claimed task matches an eligible dimension.

## Eligibility sequence

A candidate analyzer may enter a later experiment only when:

1. the dimension record is `eligible_experimental`;
2. the analyzer's `dimension_id` exactly matches the record;
3. the dimension status is at least `defined` and is not deferred or rejected;
4. the expected output structure is determined;
5. the dimension may appear as a profile component;
6. the analyzer satisfies the record's instrument requirements;
7. its output conforms to the model-result contract;
8. its use is registered in a pre-execution experiment manifest.

Passing this gate does not establish accuracy, calibration, or domain validity. Those claims require the research protocol and benchmark evidence.

## Tone profile

“Tone” is presently a presentation label for a transparent profile. It is not a canonical scalar measurement. A first experimental profile may display sentiment valence, an emotion distribution, and category-level toxicity indicators without collapsing them into one score.

## Emotional intensity

Emotional intensity is blocked because the project has not established whether it should be independently measured, derived from emotion outputs, or represented as a multi-feature activation profile. Existing model confidence values must not be relabeled as intensity.

## Versioning

Each filename includes the dimension ID and semantic version. A change to the operational meaning, claim scope, output structure, or eligibility decision requires a new version and a supporting ADR or resolution record. Historical records must remain available.

## Machine-readable contract

Records follow [`schemas/dimension-eligibility.schema.json`](../../schemas/dimension-eligibility.schema.json). The dependency-free gate in [`src/ctrt/eligibility.py`](../../src/ctrt/eligibility.py) enforces the current constitutional invariants.
