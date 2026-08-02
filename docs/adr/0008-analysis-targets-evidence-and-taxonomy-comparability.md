# ADR-0008: Analysis Targets, Evidence Provenance, and Taxonomy Comparability

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02
- **Decision scope:** Canonical measurement and Workbench comparison contracts

## Context

The Phase 0 foundation already preserves canonical content, segmentation, analyzer identity, confidence vectors, disagreement, and abstention. Three remaining ambiguities could still permit misleading Workbench output:

1. a result could identify its parent content without identifying whether the analyzer received the whole item or one segment;
2. an evidence span could be displayed without distinguishing native model evidence from post-hoc attribution or deterministic derivation;
3. outputs from incompatible taxonomies could be placed beside one another and normalized as though their labels were equivalent.

Extraction quality also existed in the confidence vector, but a result did not yet carry a machine-readable link to the upstream extraction or canonical-input record from which that quality was inherited.

## Decision

### Explicit analysis target

Every `ModelResult` must identify an `analysis_target` containing:

- target kind: complete content item or segment;
- canonical content identifier;
- zero-based, half-open canonical start and end offsets;
- upstream extraction or canonical-input reference;
- segmentation manifest and segment identifiers when the target is a segment;
- canonical coordinate-system identity.

A segment target must name both its segmentation manifest and segment. A complete-item target may not name either.

The result-level `content_id` must equal the target's `content_id`. Evidence spans must fall entirely within the target coordinates.

### Extraction inheritance

The analysis target carries the upstream `extraction_ref`. The result confidence vector must carry the same reference in `extraction_quality.evidence_ref`.

This equality is enforced by the Python contract. JSON records require both references, and Workbench assembly must reject mismatches during deserialization or contract validation.

Failed extraction continues to force system abstention under ADR-0006. Partial or degraded extraction remains visible in the confidence vector and report limitations.

For direct raw-text input, the reference may identify the canonical input record rather than an extractor execution, but it may not be absent.

### Evidence provenance

Every result must include an `evidence_support` declaration with one of four states:

- `provided-native` — local evidence is emitted by the analyzer or its declared adapter;
- `provided-post-hoc` — evidence is produced by a separate attribution method;
- `provided-deterministic` — evidence is produced by a versioned deterministic rule;
- `unavailable` — the result has no valid local evidence.

Post-hoc and deterministic evidence must identify the method and version. Native evidence relies on the analyzer and adapter identity already stored in the result. Unavailable evidence may not contain evidence spans. Any provided-evidence state requires at least one span.

Post-hoc attribution is evidence about an attribution method, not proof that the analyzer used the highlighted text causally.

### Taxonomy comparison

Comparing two analyzer outputs requires a versioned taxonomy-comparison record. The allowed relationships are:

- `identical`;
- `compatible-mapping`;
- `partial-overlap`;
- `incompatible`;
- `unassessed`.

Partial, incompatible, and unassessed relationships require side-by-side presentation. Compatible and partial mappings must name a mapping method and version. Partial overlap must record information loss.

No taxonomy-comparison record may permit score combination during Phase 0. A mapping supports inspectable comparison only; it does not make the original taxonomies identical.

Reports must carry their taxonomy-comparison records, and each dimension summary must identify the comparison records it relies upon. A single-taxonomy summary may use an empty comparison list.

## Consequences

- Whole-item and segment results become distinguishable without inspecting configuration fields.
- Extraction limitations are linked to a specific upstream record rather than copied as free text.
- Evidence-free analyzers remain usable, but the absence of local evidence is explicit.
- Post-hoc explanations cannot silently masquerade as native model evidence.
- The Workbench can display incompatible models without falsely normalizing them.
- Future mappings remain replaceable and auditable through method identity and versioning.

## Rejected alternatives

### Infer the target from evidence-span coordinates

Rejected because empty evidence and whole-item outputs would remain ambiguous.

### Treat all highlighted spans as equivalent evidence

Rejected because model-native evidence, deterministic matching, and post-hoc attribution carry different epistemic meaning.

### Normalize every taxonomy to a universal label set

Rejected because such normalization would hide information loss and convert the proposed universal taxonomy into an unvalidated authority.

### Store extraction quality only as a report limitation

Rejected because downstream results must retain a direct, machine-readable link to the input-quality evidence that constrained them.

## Revisit conditions

Revisit when multimodal evidence, token-level causal methods, multilingual normalization, or a validated purpose-specific taxonomy mapping requires additional provenance or coordinate systems. The canonical text target, evidence origin, information-loss record, and no-silent-equivalence rules remain controlling.
