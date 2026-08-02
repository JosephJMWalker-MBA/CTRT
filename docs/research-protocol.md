# CTRT Model Evaluation Research Protocol

**Status:** Phase 0 design document  
**Execution:** Deferred until the constitutional foundation is accepted and Label Lens reaches its completion boundary

## 1. Research objective

Evaluate whether combinations of interchangeable content-analysis instruments can produce measurements that are useful, explainable, repeatable, calibrated, and appropriately bounded by uncertainty.

The protocol does not begin by assuming that a named model, label taxonomy, or aggregate score is valid.

## 2. Core research questions

1. Which proposed CTRT dimensions can be operationally defined with sufficient clarity for annotation and testing?
2. Which candidate instruments measure those dimensions most reliably within declared domains?
3. Where do instruments disagree, and what does that disagreement reveal?
4. Do normalized outputs preserve meaningful information from raw model outputs?
5. Can explanations remain faithful to measurements, evidence, uncertainty, and disagreement?
6. Does an aggregate representation add practical value without hiding distinctions?

## 3. Pre-registration record

Before an experiment runs, preserve:

- experiment identifier and version;
- research question and hypotheses;
- included dimensions and operational definitions;
- candidate instruments and exact versions;
- corpus version and inclusion rules;
- annotation protocol;
- metrics and acceptance thresholds;
- planned exclusions;
- normalization and aggregation methods;
- random seeds and execution configuration;
- known conflicts of interest;
- stopping conditions.

Changes after execution begins must be recorded as amendments rather than silently replacing the original plan.

## 4. Corpus design

The benchmark corpus should be versioned, licensed or otherwise lawfully usable, and stratified across content types that create distinct measurement challenges.

Candidate strata include:

- straight news reporting;
- opinion and commentary;
- social-media posts;
- advertisements and calls to action;
- product reviews;
- political rhetoric;
- religious discourse;
- humor and satire;
- fiction and dialogue;
- educational and academic writing;
- quoted hostile or toxic language;
- counterspeech and condemnation of abuse;
- dialect and informal speech;
- mixed-emotion and mixed-valence passages.

The corpus must include ordinary low-intensity material, not only dramatic examples.

## 5. Annotation protocol

### 5.1 Annotator preparation

Annotators receive:

- the operational definition for each dimension;
- inclusions and exclusions;
- positive, negative, ambiguous, and abstention examples;
- instructions not to infer author identity, intent, or moral worth;
- a method for recording uncertainty and missing context.

### 5.2 Independent annotation

At least two annotators independently label each eligible item. High-ambiguity dimensions may require three or more.

### 5.3 Adjudication

Disagreement is preserved before adjudication. An adjudicated label supplements the independent labels and does not erase them.

### 5.4 Human-reference limitations

Human agreement is not treated as infallible ground truth. Low agreement may reveal an unclear construct, insufficient context, poor instructions, or genuinely plural interpretation.

## 6. Instrument execution

Each candidate analyzer receives the same canonical content representation for a given comparison unless the experiment explicitly tests preprocessing differences.

Preserve:

- raw input hash;
- preprocessed input;
- model and tokenizer versions;
- configuration;
- hardware and software environment where material;
- raw response;
- normalized response;
- processing time;
- warnings and failures.

Repeated runs are required for any nondeterministic component.

## 7. Evaluation dimensions

### 7.1 Contract compliance

Can the instrument return the required identity, raw output, normalized output, evidence, timing, warnings, and applicability metadata?

### 7.2 Reliability and repeatability

- identical-input repeatability;
- run-to-run variance;
- version-to-version stability;
- extraction-to-analysis consistency.

### 7.3 Agreement

- agreement with independent human annotations;
- agreement with adjudicated references;
- inter-instrument agreement;
- class- and domain-specific disagreement.

Metrics must fit the output type and may include accuracy, macro-F1, correlation, Krippendorff’s alpha, Cohen’s kappa, or distributional distance.

### 7.4 Calibration

Determine whether reported probabilities or confidence values correspond to observed reliability. Evaluate calibration separately by domain and class when sample size permits.

### 7.5 Perturbation stability

Test changes that should preserve meaning, including:

- punctuation changes;
- whitespace and casing;
- benign paraphrase;
- reordered independent sentences;
- removal of irrelevant boilerplate.

Also test meaning-changing perturbations such as negation, target substitution, or threat reversal to verify appropriate sensitivity.

### 7.6 Context sensitivity

Compare isolated sentences with their surrounding passage. Evaluate quotation, reported speech, fictional dialogue, headline-body relationships, and counterspeech.

### 7.7 Domain robustness

Report performance per corpus stratum. Strong aggregate performance may not conceal failure in a meaningful domain.

### 7.8 Bias and confounding

Test identity terms, names, dialect, reclaimed language, minority religious vocabulary, quoted slurs, academic description, and other contexts known to produce spurious toxicity or sentiment signals.

### 7.9 Explanation fidelity

Every explanatory claim must be traceable to:

- a canonical measurement;
- a declared interpretation rule;
- one or more evidence spans, when applicable;
- the applicable uncertainty and disagreement state.

Human reviewers should judge whether an explanation accurately communicates the measurements without adding unsupported intent, causation, or value judgment.

## 8. Model selection record

A selected instrument must have a public rationale containing:

- the dimension and domain for which it is selected;
- alternatives tested;
- benchmark results;
- known failure modes;
- latency and resource considerations;
- license and distribution constraints;
- rejected alternatives and reasons;
- conditions that would trigger replacement or reevaluation.

No instrument is “best” without a specified dimension, domain, metric, and use.

## 9. Aggregate experiments

Aggregate scoring begins only after component measurements are evaluated.

Each candidate aggregate must be compared against a non-aggregate presentation to test whether it improves:

- user comprehension;
- decision usefulness;
- consistency of interpretation;
- explanation quality;

while not reducing:

- visibility of disagreement;
- uncertainty awareness;
- dimension-level distinctions;
- traceability.

A simpler profile is preferred when an aggregate adds false precision.

## 10. Failure and abstention

The system should abstain or return a partial report when:

- extraction quality is inadequate;
- content is outside an instrument’s evaluated domain;
- required model outputs are missing;
- disagreement exceeds a declared boundary;
- confidence is uncalibrated or materially low;
- the construct cannot be responsibly inferred from available context.

Abstention is a valid result, not an implementation failure.

## 11. Publication standard

Published findings should include the protocol version, corpus version, code commit, instrument versions, complete metrics, negative results, limitations, and enough configuration detail to support reproduction.

Claims must remain bounded to the domains and uses actually tested.
