# Open Questions

These questions are intentionally unresolved. Phase 0 should answer or explicitly defer them before model implementation begins.

## P1 — Construct definition

1. **What does CTRT mean by “tone”?** Is it only a user-facing profile composed of independent dimensions, or is there a defensible operational construct that can be measured directly?
2. **Which dimensions are essential to the first useful report?** Sentiment, emotion, intensity, and toxicity are candidates, but inclusion must follow a user need and validation plan.
3. **Should emotional intensity be independently measured or derived?** Derivation may improve consistency but can import the assumptions of the emotion taxonomy.
4. **What is the target of a measurement?** Whole-item averages may conceal local hostility, quoted threats, or shifts between calm reporting and emotionally charged passages.
5. **Which constructs require context beyond text?** Sensationalism, manipulation, revenue incentive, irony, and author intent may be invalid as text-only claims.

## P1 — Confidence and disagreement

6. **What should “overall confidence” mean?** Model probability, calibration, inter-model agreement, domain applicability, extraction quality, and corpus representativeness are distinct.
7. **When must CTRT abstain?** Thresholds are needed for inadequate extraction, unsupported language, unknown domain, missing context, and material analyzer conflict.
8. **How should incompatible taxonomies be compared?** Emotion labels and toxicity categories cannot be merged merely because their values fall between zero and one.

## P1 — Evidence and explanation

9. **What evidence must each analyzer return?** Some models provide only item-level probabilities; others can support token- or span-level evidence. CTRT must distinguish evidence from post-hoc attribution.
10. **How will explanation fidelity be tested?** A readable explanation is insufficient if it adds intent, causation, or certainty not present in the canonical measurements.
11. **Can a rule-based explanation cover the initial reports?** If so, the project may defer a generative explanation layer and reduce a source of unsupported synthesis.

## P2 — Corpus and annotation

12. **What is the smallest benchmark corpus that can reveal meaningful failure modes?** It must include ordinary content, ambiguity, quotation, counterspeech, satire, dialect, identity terms, and domain shifts.
13. **What does annotator disagreement mean for each construct?** It may indicate poor instructions, missing context, a weak construct, or genuine interpretive plurality.
14. **What content can be legally and reproducibly redistributed?** Licensing and provenance requirements may shape the benchmark before model selection does.
15. **Should Phase 1 begin with English only?** A clear language boundary is preferable to implied multilingual validity.

## P2 — Aggregation and usefulness

16. **Who is the first intended reader of a CTRT report?** Researchers, parents, advertisers, publishers, and individual users may need different presentations without changing the canonical measurements.
17. **What decision becomes better because CTRT exists?** The answer should govern report design and prevent score creation for its own sake.
18. **What information would an overall rating add?** It must outperform a transparent dimension profile without encouraging false precision.
19. **Should an aggregate be universal or purpose-specific?** A universal number may be conceptually incoherent when users value dimensions differently.

## P2 — Project identity and future boundary

20. **Does one standard adequately contain both content measurement and revenue transparency?** They may ultimately require interoperable but separate evidence systems.
21. **What remains constitutional across future integrations?** Browser extensions, parent controls, advertiser tools, and platform APIs must not strip provenance, uncertainty, or measurement/judgment separation.
22. **Who has authority to amend the ontology and validation thresholds?** Open governance must be designed before external adoption creates pressure to optimize definitions for stakeholders.

## Resolution record

When a question is resolved, preserve:

- the decision;
- supporting evidence or reasoning;
- rejected alternatives;
- remaining uncertainty;
- the document, ADR, schema, or protocol changed as a result.
