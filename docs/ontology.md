# Provisional CTRT Measurement Ontology

**Status:** Draft for operational-definition work  
**Important:** Inclusion here does not mean a construct is validated, measurable by available models, or eligible for aggregation.

## 1. Why an ontology is required

A model label is not automatically a valid content dimension. CTRT must define the construct independently of any particular analyzer, then evaluate whether available instruments measure that construct reliably.

The ontology therefore separates:

- the **construct** being investigated;
- the **observable indicators** that may support it;
- the **instrument output** produced by a model;
- the **normalization** used for comparison;
- the **interpretation** communicated to a user;
- the **judgment or action** that remains outside the measurement itself.

## 2. Measurement unit

The primary unit is a **content item**: a bounded body of text with preserved source and extraction provenance.

A content item may be segmented into evidence spans. Segment-level outputs may be summarized at item level only through a declared aggregation method.

CTRT must not assume that an item-level average adequately represents content containing sharp internal variation.

## 3. Candidate Phase 1 dimensions

### 3.1 Sentiment valence

**Provisional definition:** The degree to which expressed language is conventionally associated with positive, neutral, or negative evaluation.

**Not equivalent to:** moral quality, truthfulness, toxicity, emotional intensity, author intent, or reader impact.

**Candidate representation:**

- raw class probabilities;
- normalized valence from `-1.0` to `+1.0`;
- neutrality or ambiguity estimate;
- evidence spans;
- instrument and calibration metadata.

**Known complications:** mixed sentiment, negation, irony, quotation, domain-specific vocabulary, and target-dependent sentiment.

### 3.2 Emotion profile

**Provisional definition:** The distribution of language patterns associated with a declared emotion taxonomy.

**Candidate labels:** joy, anger, fear, sadness, disgust, surprise, and neutral.

**Not equivalent to:** the actual internal state of the creator or audience.

**Requirements:** Every result must identify the taxonomy. Scores from incompatible taxonomies may not be treated as directly interchangeable.

**Known complications:** multiple simultaneous emotions, rhetorical performance, fictional narration, quotation, cultural variation, and low-taxonomy coverage.

### 3.3 Emotional intensity

**Provisional definition:** The apparent strength or activation of emotional expression, independent of whether the expression is positive or negative.

**Not equivalent to:** extremism, toxicity, importance, urgency, or harm.

**Candidate representation:** normalized `0.0` to `1.0`, accompanied by the method used to derive it.

**Open question:** Whether intensity should be independently measured or derived from emotion-distribution and linguistic features.

### 3.4 Toxicity indicators

**Provisional definition:** Instrument-detected language patterns associated with categories such as hostility, insult, threat, harassment, obscenity, or identity attack.

**Not equivalent to:** offensiveness to every audience, policy violation, illegality, falsity, or moral condemnation.

**Requirements:** Preserve category-level outputs. A single toxicity number may summarize but may not replace them.

**Known complications:** identity-term false positives, reclaimed language, counterspeech, quotation, academic discussion, satire, dialect, and threats described rather than issued.

### 3.5 Linguistic hostility

**Provisional definition:** Directly adversarial or antagonistic expression toward an identifiable or implied target.

**Reason for separation:** Toxicity models may combine hostility with obscenity or identity language. CTRT should test whether hostility is independently useful and measurable.

**Status:** Candidate; operational definition incomplete.

### 3.6 Epistemic certainty

**Provisional definition:** The degree of certainty, qualification, or evidential caution expressed in propositions.

**Candidate indicators:** hedging, modal verbs, categorical claims, explicit uncertainty, source attribution, and confidence language.

**Not equivalent to:** factual accuracy or actual knowledge.

**Status:** Candidate for later instrument research.

### 3.7 Urgency and pressure

**Provisional definition:** Linguistic signals encouraging immediate attention or action.

**Candidate indicators:** deadlines, scarcity, imperative language, consequence framing, repeated calls to act, and time pressure.

**Not equivalent to:** manipulation; legitimate emergency communication may be highly urgent.

**Status:** Candidate for later instrument research.

## 4. Composite concepts that must not be prematurely scored

### 4.1 Tone

“Tone” is an interpretive umbrella, not presently a single operational dimension. It may depend on valence, emotion, intensity, certainty, hostility, urgency, empathy, humor, formality, rhetorical posture, and context.

During early phases, CTRT may present a **tone profile** composed of separately defined measurements. It must not imply that sentiment alone is tone.

### 4.2 Manipulation

Manipulation involves context, intent, power, omission, audience vulnerability, and strategy. Surface-language signals may support a limited claim such as “high pressure” or “fear appeal,” but CTRT must not infer manipulative intent without a separately validated method and suitable evidence.

### 4.3 Sensationalism

Sensationalism may involve headline-body relationships, novelty framing, exaggeration, uncertainty suppression, image choice, and publication context. Text-only emotional intensity is insufficient to establish it.

### 4.4 Overall CTRT rating

No overall rating is currently defined. Any future aggregate must state its purpose and demonstrate that combining dimensions adds useful information rather than hiding meaningful distinctions.

## 5. Dimension eligibility record

Before a dimension can enter an experimental CTRT report, it should have:

- a stable identifier and version;
- a plain-language name;
- an operational definition;
- explicit inclusions and exclusions;
- unit and level of analysis;
- expected output structure;
- known confounds and failure modes;
- candidate instruments;
- normalization rules, if any;
- validation evidence requirements;
- aggregation eligibility status;
- explanation constraints.

## 6. Provisional status vocabulary

- **Proposed:** named but not operationally defined.
- **Defined:** operational definition accepted for testing.
- **Instrumented:** at least one analyzer can produce a contract-compliant output.
- **Evaluated:** tested under the current benchmark protocol.
- **Validated for domain:** meets declared criteria for a specified domain and use.
- **Deferred:** intentionally excluded from the active phase.
- **Rejected:** evidence indicates that the construct or available measurement approach is unsuitable.

Validation is always bounded by domain, language, corpus, version, and intended use.
