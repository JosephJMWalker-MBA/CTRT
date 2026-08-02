# Phase 1A Synthetic Workbench Slice

## Purpose

This slice is the first executable proof of the accepted Content Analysis Workbench architecture. It validates orchestration and record-preservation behavior without downloading models, assembling a benchmark corpus, or making claims about real-world measurement quality.

## What it proves

The dependency-free workbench can:

- register interchangeable analyzers by stable identity;
- select multiple analyzers for one declared dimension;
- run them against the same complete canonical content target;
- preserve one immutable `ModelResult` per analyzer;
- preserve raw output, normalized output, evidence provenance, structured confidence, warnings, and configuration;
- compare analyzer taxonomies without permitting score combination;
- surface material disagreement separately from the original results;
- abstain at the comparison level without rewriting successful analyzer results;
- preserve analyzer abstentions and failures as valid research outcomes.

## Synthetic analyzers

Two deterministic fixtures are included:

1. `synthetic.sentiment.first-signal` selects the first exact `good` or `bad` token.
2. `synthetic.sentiment.last-signal` selects the last exact `good` or `bad` token.

Both expose the same synthetic three-class taxonomy. They are intentionally simplistic and are not candidate production instruments.

For the fixture content:

> The launch was good, but the support was bad.

The first-signal fixture emits positive valence and the last-signal fixture emits negative valence. Both analyzer results remain successful and immutable. The comparison records strong disagreement and abstains.

## Comparison behavior

The initial comparison protocol is deliberately narrow:

- equal normalized valence values produce `agreement`;
- differing values with the same sign produce `partial-disagreement`;
- opposite signs produce `strong-disagreement`;
- any missing, failed, or abstained result produces agreement-level `abstain`.

Strong disagreement and agreement-level abstention trigger report-level system abstention under the accepted confidence contract.

No instrument probabilities are aggregated. No taxonomy scores are combined. No overall CTRT score is produced.

## Boundary

This slice does not establish:

- analyzer accuracy;
- calibration;
- empirical agreement thresholds;
- taxonomy mapping validity;
- benchmark suitability;
- production readiness;
- user-facing scoring behavior.

Its only claim is architectural: CTRT can execute multiple instruments, preserve their records, and represent disagreement without silently resolving it.

## Next step after acceptance

The next workbench increment should define versioned experiment and execution-environment records before any real candidate is downloaded or evaluated. Real model execution remains deferred while Label Lens is the active priority.
