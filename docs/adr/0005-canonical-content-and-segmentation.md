# ADR-0005: Canonical Content and Segmentation

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

Whole-item scores can conceal sharp internal variation. A long article may contain calm reporting, a quoted threat, hostile commentary, and a conciliatory conclusion. Conversely, isolated sentence analysis can remove the context needed to distinguish quotation, counterspeech, satire, or reported speech.

CTRT therefore needs both item-level and segment-level analysis without allowing preprocessing or chunking to become invisible.

## Decision

### Canonical content

The extracted content item is the canonical analyzed text. Its exact text and content hash must be preserved before segmentation or model-specific preprocessing.

### Coordinate system

All canonical spans use zero-based, half-open Unicode code-point offsets into the preserved content text:

`[start, end)`

Evidence and segments must be recoverable from these offsets. A future implementation may additionally preserve byte or tokenizer offsets, but those may not replace canonical text coordinates.

### Segmentation manifest

Every segmentation is a versioned derivative described by a segmentation manifest containing:

- the canonical content identifier;
- segmentation method and version;
- configuration;
- ordered segment identifiers;
- start and end offsets;
- segment text hashes;
- whether overlap is permitted;
- whether the segments claim complete coverage;
- warnings and known limitations.

No component may silently split, truncate, summarize, or rewrite text.

### Segment-level analysis

A segment-level result must identify both its segment and parent content item. Its evidence spans remain expressible in canonical content coordinates.

Analyzers may require different window sizes, but model-specific windows must be recorded as preprocessing artifacts rather than treated as the only segmentation truth.

### Item-level summaries

An item-level summary derived from segment results is a separate, versioned transformation. It must declare:

- the included segments;
- handling of overlap and gaps;
- weighting method;
- treatment of peaks and outliers;
- missing, failed, or abstained segment results;
- the transformation version.

A mean may not be presented as a complete account when it materially conceals local variation.

### Truncation

Undeclared truncation is prohibited. When an instrument cannot process the complete applicable unit, the result must be partial, abstained, or accompanied by an explicit warning and preserved truncation record.

## Rationale

This structure protects two truths at once:

1. context matters; and
2. local variation matters.

Preserving canonical text coordinates allows CTRT to compare whole-item, paragraph, sentence, and overlapping-window experiments without losing provenance or rewriting the source record.

## Consequences

- Content extraction must finish before segmentation begins.
- Segment boundaries are evidence-bearing data and must be reproducible.
- Multiple segmentation manifests may coexist for one content item.
- Reports must identify which segmentation and summary method produced each derived item-level value.
- Evidence spans may not be fabricated from a segment label when the analyzer provides no genuine local attribution.
- The benchmark protocol must test isolated segments against surrounding context.

## Rejected alternatives

### Whole-item analysis only

Rejected because averages and single classifications can conceal meaningful internal shifts.

### Sentence analysis only

Rejected because sentence boundaries do not preserve sufficient context for many rhetorical and toxicity distinctions.

### Let each model chunk text internally without recording it

Rejected because model comparison would then confound instrument behavior with invisible preprocessing differences.

### Store segment text without offsets

Rejected because duplicated text can drift from the canonical source and cannot reliably support cross-method comparison.

## Revisit conditions

Revisit when multilingual normalization, multimodal content, tokenizer alignment, or streaming content requires additional coordinate systems. Canonical preserved-text coordinates must remain available even if supplementary coordinate systems are added.
