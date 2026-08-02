# CTRT Constitution

**Status:** Draft 0.1  
**Applies to:** All CTRT specifications, software, datasets, experiments, reports, and integrations

## Preamble

Content Tone & Revenue Transparency (CTRT) exists to make characteristics of digital content more inspectable. It is intended to help people and institutions make informed decisions without assigning the system authority to decide what speech should exist, who is morally worthy, or what another person must consume.

CTRT therefore treats measurement as a governed practice. Scores must remain traceable to defined dimensions, source evidence, instruments, transformations, uncertainty, disagreement, and known limitations.

This Constitution governs the project before implementation convenience, model performance, commercial pressure, or persuasive presentation.

## Article I — Purpose and authority

1. CTRT measures characteristics of content items.
2. CTRT does not determine whether content should exist.
3. CTRT does not infer the moral worth, intent, identity, or character of a creator or consumer from a content score.
4. CTRT outputs are decision-support information, not commands.
5. No aggregate rating may be presented as objective truth independent of its specification, evidence, instruments, and version.

## Article II — Separation of responsibilities

CTRT separates the following responsibilities:

- **Extraction:** obtaining and delimiting content;
- **Measurement:** producing dimension-level observations with declared instruments;
- **Normalization:** transforming heterogeneous outputs into a common representation;
- **Aggregation:** combining eligible measurements according to a versioned method;
- **Explanation:** communicating results without modifying canonical measurements;
- **Evaluation:** testing reliability, validity, calibration, bias, and robustness;
- **Stewardship:** approving specifications, datasets, releases, and consequential changes.

No component may silently assume the authority of another.

## Article III — Operational definition before scoring

1. A dimension must be operationally defined before it can contribute to a CTRT score.
2. Every definition must state what is included, excluded, observable, and unresolved.
3. Labels that conceal multiple constructs must be decomposed or explicitly marked provisional.
4. “Tone” is not treated as synonymous with sentiment, emotion, toxicity, or intensity.
5. A dimension may remain unscored when available instruments do not validly measure it.

## Article IV — Evidence and provenance

Every canonical measurement must preserve or reference:

- the analyzed content or a stable content hash;
- the exact input span;
- source and extraction provenance;
- analyzer name, provider, model identifier, and version;
- configuration and normalization method;
- raw output and normalized output;
- processing timestamp and duration;
- warnings, errors, and applicability limits.

Normalized values may supplement raw outputs but may not replace them.

## Article V — Modularity and replaceability

1. An analyzer is a replaceable instrument, not the definition of a dimension.
2. Provider-specific behavior must remain behind provider-neutral contracts.
3. Replacing an analyzer must not require redesigning unrelated pipeline stages.
4. Multiple analyzers may measure the same dimension concurrently.
5. Model selection must be justified through evaluation rather than popularity or convenience alone.

## Article VI — Disagreement and uncertainty

1. Disagreement among instruments is evidence and must not be hidden.
2. Missing, conflicting, or out-of-domain results may reduce confidence or prevent aggregation.
3. Model-reported confidence is not equivalent to system reliability.
4. CTRT confidence must distinguish, where possible:
   - instrument confidence;
   - inter-instrument agreement;
   - empirical calibration;
   - domain applicability;
   - extraction quality;
   - aggregate confidence.
5. The system must be able to abstain.

## Article VII — Aggregation

1. Aggregation logic must be isolated, versioned, documented, and reproducible.
2. Every aggregate must expose its contributing measurements, exclusions, transformations, and weights.
3. An aggregate may not imply that unlike dimensions are interchangeable merely because they share a numeric range.
4. No overall CTRT rating is considered validated until evaluated against a declared protocol and corpus.
5. Aggregate labels must not exceed the precision supported by their evidence.

## Article VIII — Explainability fidelity

1. Explanations must be grounded in canonical measurements and cited evidence spans.
2. Explanations may not invent causes, motives, intent, or unsupported psychological claims.
3. Rule-based or generative explanations must disclose their method and version.
4. A generative model may communicate measurements but may not originate, alter, or overwrite canonical scores.
5. Explanations must communicate material disagreement, uncertainty, and known limitations.

## Article IX — Evaluation and falsifiability

CTRT claims must be testable. Evaluation must include, where applicable:

- repeatability;
- inter-instrument agreement;
- agreement with human annotations;
- calibration;
- perturbation stability;
- domain robustness;
- extraction robustness;
- subgroup and identity-term bias analysis;
- quoted-speech, satire, dialect, and reclaimed-language tests;
- explanation fidelity.

Negative results, regressions, and known failure modes are part of the project record.

## Article X — Non-consequential status by default

1. Experimental outputs must be clearly marked as unvalidated.
2. CTRT measurements may not be used for automatic censorship, punishment, eligibility, employment, credit, housing, legal judgment, or other high-impact determinations without a separately approved governance framework.
3. Integrations must not remove constitutional disclosures for the sake of interface simplicity.
4. Human review does not cure an invalid instrument; the validity of both instrument and process must be examined.

## Article XI — Versioning and change control

1. Constitutions, ontologies, schemas, normalization methods, aggregation methods, benchmark datasets, and released model bundles must be versioned.
2. Material changes require an Architecture Decision Record or equivalent public rationale.
3. Historical results must remain interpretable under the specification that produced them.
4. Reprocessing under a new specification creates a new analysis record; it does not rewrite the historical record.
5. Canonical research artifacts should be append-only after publication, except for clearly recorded corrections.

## Article XII — Scope discipline

Phase 0 is limited to constitutional design, ontology, contracts, schemas, synthetic fixtures, and evaluation protocol.

Until the Phase 0 exit criteria are accepted, the project will not:

- claim a validated CTRT score;
- tune an aggregate against anecdotal examples;
- deploy a consequential classifier;
- infer producer profiles or revenue relationships;
- begin platform filtering or enforcement;
- conceal unresolved definitions behind implementation progress.

## Amendment standard

This Constitution may be amended when evidence, experience, or clearer reasoning reveals a defect. Amendments must identify:

1. the problem being corrected;
2. the affected principle or requirement;
3. the evidence or reasoning supporting the change;
4. anticipated consequences and risks;
5. the new version and effective date.

Convenience alone is not sufficient reason to weaken traceability, uncertainty disclosure, separation of responsibilities, or the distinction between measurement and judgment.
