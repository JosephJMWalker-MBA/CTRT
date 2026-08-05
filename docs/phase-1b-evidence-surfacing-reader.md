# Phase 1B Evidence-Surfacing Reader

## Purpose

The first Phase 1B capability turns an existing verified stored-content experiment into a human-readable evidence view without introducing a new analyzer, aggregate, verdict, recommendation, or canonical research artifact.

It asks one bounded question:

> Can CTRT present the exact verified evidence graph to a person without changing what the graph means?

The implementation is intentionally downstream of the Phase 1A constitutional kernel. It reads and re-verifies existing artifacts; it does not authorize execution, alter measurements, resolve disagreement, or publish a simplified replacement record.

## Input boundary

The reader accepts:

```python
VerifiedStoredContentExperimentReceipt
FileSystemArtifactStore
```

The stored-content receipt is the first suitable presentation boundary because it links:

- exact canonical content artifacts containing the analyzed UTF-8 text;
- exact ordered content identity;
- per-content verified execution receipts;
- persisted session-receipt references;
- verified experiment bundles;
- experiment, corpus-bound, and stored-content completion markers.

A basic `VerifiedExecutionReceipt` is not sufficient for quoting evidence because it does not itself contain the canonical text bytes. The reader never accepts caller-supplied text as the source of an evidence excerpt.

## Verification sequence

`build_stored_content_evidence_view` performs the following sequence:

1. require a verified stored-content receipt;
2. require its content order to match the nested verified experiment receipt;
3. re-read the stored-content completion marker by exact ID and hash;
4. re-read the corpus-bound completion marker by exact ID and hash;
5. re-read the experiment completion marker by exact ID and hash;
6. re-read each canonical content artifact and reconstruct its exact text and metadata;
7. compare each reconstructed content reference and ordered content ID with the receipt;
8. re-read each persisted session receipt and compare its canonical bytes with the supplied receipt object;
9. load each experiment bundle through the existing bundle loader;
10. re-verify the manifest and every referenced member;
11. require contiguous ordered result roles;
12. require analyzer identity, result status, content identity, extraction identity, and comparison order to match the verified receipt;
13. quote evidence spans only from the reverified canonical content text; and
14. derive the noncanonical presentation view.

Any identity, ordering, payload, hash, target, extraction, status, or receipt drift fails before a view is returned.

## Presentation model

The top-level presentation type is:

```python
StoredContentEvidenceView
```

It contains one ordered `ContentEvidenceView` per content item. Each content view includes:

- exact stored text;
- content hash, language, source type, source URI, and extraction identity;
- run, session, and lifecycle identity;
- one `InstrumentEvidenceView` per immutable analyzer result;
- one separate `ComparisonEvidenceView`; and
- all supporting immutable artifact references.

### Instrument evidence

Each instrument view preserves:

- result status;
- analyzer, provider, instrument, adapter, taxonomy, dimension, and version identity;
- normalized instrument-level measurements and declared bounds;
- exact evidence-span coordinates and excerpts;
- evidence-support method identity;
- raw output and declared execution configuration;
- instrument probability when present;
- calibration state;
- domain applicability and reasons;
- extraction quality and issues;
- system abstention and reasons;
- ambiguity handling and preserved uncertainty;
- warnings and errors; and
- the immutable result artifact reference.

No confidence dimensions are combined.

### Comparison evidence

The comparison view remains distinct from the instrument results. It preserves:

- comparison status;
- participating result and analyzer order;
- agreement or disagreement state;
- abstention state and reasons;
- preserved material disagreements;
- declared limitations;
- complete structured comparison confidence JSON; and
- the immutable comparison artifact reference.

`score_combination_permitted` must remain `false`.

## Markdown renderer

`render_evidence_view_markdown` produces a deterministic Markdown document intended for review and interface prototyping.

The renderer shows:

- exact quoted content;
- plain headings for provenance, measurements, evidence, confidence dimensions, comparison, limitations, and immutable references;
- explicit lifecycle and abstention states; and
- interpretation notices at the end.

The renderer does not attempt to decide what the user should do with the content.

## Interpretation notices

Every `StoredContentEvidenceView` contains the exact notices defined by `PRESENTATION_NOTICES`:

1. the view is derived and canonical stored artifacts remain controlling;
2. verified describes lifecycle and evidence integrity, not analytical success; and
3. the view produces no overall CTRT score, content verdict, publish recommendation, or production-readiness claim.

These notices are part of the presentation contract rather than optional interface copy.

## Demonstrated fixture outcomes

The test lifecycle uses the exact linked three-item synthetic corpus.

### Content 001 — preserved disagreement

```text
The launch was good, but the support was bad.
```

The first-signal analyzer returns `+1.0` from the exact excerpt `good`. The last-signal analyzer returns `-1.0` from the exact excerpt `bad`. Both results remain successful. The separate comparison records strong disagreement, forbids score combination, and abstains.

### Content 002 — fixture agreement

```text
The launch was good and the support was good.
```

Both analyzers return their own successful `+1.0` measurement. The comparison records agreement and completes. The reader still does not synthesize an overall experiment score or recommendation.

### Content 003 — no-signal abstention

```text
The report contains no fixture vocabulary.
```

Both analyzers abstain without normalized measurements. The comparison also abstains. The experiment and evidence view may remain verified because verification describes lifecycle integrity, not analytical success.

## Failure tests

The bounded test module proves that:

- changed content bytes fail read-time SHA-256 verification before presentation;
- a caller-modified session receipt fails comparison with the persisted canonical receipt;
- reordered content references fail the exact ordered-content boundary;
- result and comparison evidence remain tied to the canonical content and verified session identities; and
- the public module surface remains limited to the evidence reader and renderer contracts.

The existing constitutional and mechanism-specific suite remains unchanged and continues to run in full.

## Explicit non-goals

This slice does not add:

- a web, desktop, mobile, or command-line application;
- a creator-preflight decision flow;
- a parental or educational monitoring system;
- ambient content collection;
- user accounts, consent records, access control, or privacy policy;
- a real analyzer or extraction engine;
- model-selection evidence;
- statistical evaluation;
- a new canonical presentation artifact;
- an overall CTRT score;
- scalar confidence;
- a safe/unsafe or good/bad verdict;
- a publish, block, restrict, or enforcement recommendation; or
- production deployment.

## Follow-on interface work

The same view can support two later plain-language doors without changing canonical measurements:

```text
Check before I publish
Understand this content
```

Those interfaces may progressively explain technical evidence, but they must not suppress disagreement, provenance, abstention, limitations, or immutable references for the sake of apparent simplicity.

The next bounded capability should turn this verified evidence view into a creator-preflight interaction while preserving the creator as the decision-maker.
