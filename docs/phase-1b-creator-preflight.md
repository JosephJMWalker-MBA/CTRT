# Phase 1B Creator Preflight

## Purpose

Creator preflight is CTRT's first plain-language interaction.

It helps a creator inspect a verified content-analysis evidence graph before publication without turning that evidence into a score, verdict, approval, or recommendation.

The workflow is:

```text
exact stored draft
  -> governed synthetic analysis
  -> verified evidence view
  -> creator preflight
  -> creator decides
```

The preflight is an application-shell projection. It does not modify the Phase 1A constitutional kernel or write a new canonical artifact.

## Input

The builder accepts:

```python
CreatorPreflightRequest
VerifiedStoredContentExperimentReceipt
FileSystemArtifactStore
```

A request contains:

- one exact `content_id` already present in the verified stored-content experiment;
- the creator's intended message;
- an optional intended audience; and
- zero or more creator concerns.

Creator intent, audience, and concerns are labeled as user-provided context. They are not treated as verified evidence and are not persisted by this layer.

## Verification boundary

`build_creator_preflight` first calls `build_stored_content_evidence_view`.

That means preflight does not trust:

- caller-supplied content text;
- caller-modified receipt fields;
- unverified result objects;
- unverified evidence excerpts; or
- a simplified summary detached from stored artifacts.

The evidence reader rechecks:

1. stored-content lifecycle status;
2. ordered content identity;
3. stored-content, corpus-bound, and experiment completion markers;
4. canonical content artifacts by exact ID and hash;
5. stored session receipts against the supplied receipt objects;
6. every bundle manifest and referenced member;
7. analyzer order and result statuses;
8. analysis target and extraction identity;
9. comparison identity and ordering; and
10. evidence excerpts against exact stored text.

Only after that sequence succeeds may creator preflight select one exact content item.

## Output contract

`CreatorPreflightView` contains:

- the exact verified content evidence;
- creator-provided context;
- plain-language observations;
- deterministic reflection questions;
- exact completion references;
- neutral creator-controlled actions; and
- fixed interpretation notices.

Every observation and prompt carries immutable artifact references supporting why it appears.

## Plain-language observations

The initial observation categories are:

### Lifecycle

Explains that the evidence graph verified while explicitly denying that verification implies analytical correctness.

### Instrument record

For each analyzer, reports only what its immutable result contains:

- status;
- normalized measurement and declared bounds, when present;
- exact quoted evidence spans, when present;
- abstention reasons; or
- preserved errors.

### Comparison record

Reports the separate comparison status, agreement state, abstention reasons, and the fact that score combination was not permitted.

### Uncertainty

Surfaces nonvalidated calibration, non-in-domain applicability, extraction-quality issues, and preserved ambiguity without collapsing them into one confidence number.

### Limitation

Preserves the exact comparison limitations rather than hiding them beneath a simplified conclusion.

## Reflection prompts

Prompts are deterministic and condition-driven.

Every preflight asks:

- whether the evidence matches the creator's intended message; and
- what context is present in the creator's mind but absent from the exact stored text.

Additional prompts appear for:

- intended audience;
- creator concerns;
- highlighted evidence spans;
- material disagreement;
- instrument agreement;
- instrument abstention;
- comparison abstention;
- nonvalidated calibration;
- applicability outside or short of an in-domain declaration;
- non-clean extraction;
- preserved uncertainty; and
- comparison limitations.

A prompt identifies a question worth human attention. It does not answer the question.

## Creator-controlled actions

The initial renderer displays four unranked actions:

```text
Publish as written.
Revise the draft and run preflight again.
Pause without publishing.
Seek feedback from a person who understands the context.
```

The system does not choose among them.

## Markdown interaction

`render_creator_preflight_markdown` renders:

1. the exact stored draft;
2. creator-provided context;
3. plain-language evidence observations;
4. reflection questions as a checklist;
5. creator-controlled actions as a checklist;
6. interpretation notices; and
7. immutable evidence references.

The renderer intentionally omits the evidence view's full raw-output and configuration detail. Those details remain available in the underlying `ContentEvidenceView` and the full technical evidence renderer.

This is presentation prioritization, not evidence deletion.

## Demonstrated fixture behaviors

### Material disagreement

For:

```text
The launch was good, but the support was bad.
```

creator preflight preserves:

- first-signal valence `+1.0` with exact excerpt `good`;
- last-signal valence `-1.0` with exact excerpt `bad`;
- material disagreement;
- comparison abstention;
- unknown calibration;
- fixture limitations; and
- reflection questions about context, disagreement, highlighted wording, and uncertainty.

It does not recommend revision.

### Agreement

For:

```text
The launch was good and the support was good.
```

creator preflight preserves both independent analyzer results and records comparison agreement.

It asks whether the shared measured signal is intentional. It does not treat agreement as approval.

### No signal

For:

```text
The report contains no fixture vocabulary.
```

both analyzers abstain without invented measurements.

Creator preflight asks what should be inspected manually rather than treating missing output as proof that no relevant signal exists.

## Explicit exclusions

This slice does not add:

- an API or graphical interface;
- free-form conversational generation;
- automatic rewrite suggestions;
- a publish-readiness score;
- overall tone or sentiment;
- safe or unsafe classification;
- creator or audience profiling;
- ambient monitoring;
- a real analyzer;
- a real extractor;
- empirical accuracy or calibration claims;
- canonical persistence of creator context or preflight views;
- production deployment; or
- another governance layer.

## Tests

The bounded suite proves:

- disagreement, agreement, and no-signal abstention produce different reflection prompts while preserving the same constitutional boundary;
- exact evidence excerpts and per-analyzer values remain visible;
- the Markdown renderer leaves the final action with the creator;
- unknown content IDs fail without guessing;
- caller-modified receipts fail before preflight;
- tampered canonical content fails read-time hash verification;
- creator context rejects empty or duplicate values; and
- the module exports only the bounded creator-preflight surface.

## Next bounded step

After this layer is accepted, the next implementation should be a minimal local interaction surface that accepts a creator's draft and context, runs only the already-authorized synthetic workflow, and displays this preflight view.

That interface must remain a demonstration until controlled real-candidate admission and empirical evaluation provide analyzers with meaningful declared domains.
