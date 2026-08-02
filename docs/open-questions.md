# Open Questions

This register preserves both unresolved questions and resolved questions that shaped constitutional decisions. A resolved item remains visible as historical provenance.

## Resolved — Initial profile

1. **What does CTRT mean by “tone”?** Resolved by [ADR-0004](adr/0004-initial-experimental-dimension-profile.md): during Phase 0, tone is a user-facing profile composed of separately identified measurements, not a directly measured scalar construct.
2. **Which dimensions are essential to the first useful report?** Resolved provisionally by ADR-0004: sentiment valence, emotion profile, and category-level toxicity indicators are eligible for experimental reporting. Eligibility does not approve any model.
3. **Should emotional intensity be independently measured or derived?** The design question remains open, but its immediate eligibility question is resolved: emotional intensity is excluded from the first experimental report until independent, derived, or hybrid measurement is explicitly decided and validated.

## Resolved — Confidence and abstention

7. **What should “overall confidence” mean?** Resolved by [ADR-0006](adr/0006-structured-confidence-and-abstention.md): Phase 0 defines no overall confidence scalar. Confidence is a vector containing instrument probability, calibration, applicability, extraction quality, agreement, abstention, and ambiguity preservation.
8. **When must CTRT abstain?** Partially resolved by ADR-0006. Out-of-domain applicability, failed extraction, strong inter-instrument disagreement, and agreement-level abstention independently force system abstention. Thresholds for borderline applicability, degraded extraction, low calibration evidence, and partial disagreement remain open and must be policy-specific.

## P1 — Construct definition

4. **What is the target of a measurement?** Whole-item averages may conceal local hostility, quoted threats, or shifts between calm reporting and emotionally charged passages.
5. **Which constructs require context beyond text?** Sensationalism, manipulation, revenue incentive, irony, and author intent may be invalid as text-only claims.
6. **What observable evidence distinguishes emotional intensity from urgency, hostility, and valence?** This must be answered before emotional intensity can become eligible.

## P1 — Confidence and disagreement

9. **How should incompatible taxonomies be compared?** Emotion labels and toxicity categories cannot be merged merely because their values fall between zero and one.
24. **Which policy-specific noncritical signals should trigger abstention?** Borderline applicability, degraded extraction, partial disagreement, and unvalidated calibration may justify abstention for some uses but not others.
25. **How should ambiguity-budget status be evaluated consistently?** Phase 0 defines the record and vocabulary but not yet an empirical threshold for `constrained` or `exceeded`.

## P1 — Evidence and explanation

10. **What evidence must each analyzer return?** Some models provide only item-level probabilities; others can support token- or span-level evidence. CTRT must distinguish evidence from post-hoc attribution.
11. **How will explanation fidelity be tested?** A readable explanation is insufficient if it adds intent, causation, certainty, calibration, or a scalar confidence value not present in the canonical measurements.
12. **Can a rule-based explanation cover the initial reports?** If so, the project may defer a generative explanation layer and reduce a source of unsupported synthesis.

## P2 — Corpus and annotation

13. **What is the smallest benchmark corpus that can reveal meaningful failure modes?** It must include ordinary content, ambiguity, quotation, counterspeech, satire, dialect, identity terms, and domain shifts.
14. **What does annotator disagreement mean for each construct?** It may indicate poor instructions, missing context, a weak construct, or genuine interpretive plurality.
15. **What content can be legally and reproducibly redistributed?** Licensing and provenance requirements may shape the benchmark before model selection does.
16. **Should Phase 1 begin with English only?** A clear language boundary is preferable to implied multilingual validity.

## P2 — Aggregation and usefulness

17. **Who is the first intended reader of a CTRT report?** Researchers, parents, advertisers, publishers, and individual users may need different presentations without changing the canonical measurements.
18. **What decision becomes better because CTRT exists?** The answer should govern report design and prevent score creation for its own sake.
19. **What information would an overall rating add?** It must outperform a transparent dimension profile without encouraging false precision.
20. **Should an aggregate be universal or purpose-specific?** A universal number may be conceptually incoherent when users value dimensions differently.

## P2 — Project identity and future boundary

21. **Does one standard adequately contain both content measurement and revenue transparency?** They may ultimately require interoperable but separate evidence systems.
22. **What remains constitutional across future integrations?** Browser extensions, parent controls, advertiser tools, and platform APIs must not strip provenance, uncertainty, or measurement/judgment separation.
23. **Who has authority to amend the ontology and validation thresholds?** Open governance must be designed before external adoption creates pressure to optimize definitions for stakeholders.

## Resolution record requirements

When a question is resolved, preserve:

- the decision;
- supporting evidence or reasoning;
- rejected alternatives;
- remaining uncertainty;
- the document, ADR, schema, or protocol changed as a result.
