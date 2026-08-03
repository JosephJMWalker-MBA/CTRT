# Phase 1A Extraction Quality Evidence

This slice adds an independent quality gate between extraction-method eligibility and analyzer execution.

It remains dependency-free and synthetic. No OCR engine, parser, transcription system, extraction model, or external service is installed or executed.

## Why this layer exists

The existing method registry answers whether a declared extraction method revision was authorized.

It does not answer whether a particular extracted result is complete, faithful, or sufficiently reviewed. This layer preserves that second question as its own evidence and lifecycle.

## Artifact graph

The quality-bound corpus references the existing source, extraction, and extracted-content artifacts plus:

- one accepted `ExtractionQualityPolicySnapshot`;
- one `ExtractionQualityAssessmentSnapshot` for every content item.

Each assessment binds the exact source, extraction, and content artifact references it evaluated.

## Quality policy

The policy freezes:

- required automated check IDs;
- required check revisions;
- minimum reviewer-observation count;
- quality statuses that require abstention.

The synthetic policy requires:

1. `exact-coordinate-coverage@0.1.0`;
2. `source-output-byte-equality@0.1.0`;
3. at least one reviewer observation;
4. abstention when quality is `failed`.

## Assessment contract

Each assessment contains four independent evidence surfaces.

### Automated checks

Each check records:

- check ID and revision;
- `passed`, `failed`, or `not_applicable`;
- explanatory details;
- evidence references.

### Reviewer observations

Each observation records:

- stable observation ID;
- reviewer role;
- `confirmed`, `issue`, or `uncertain`;
- notes;
- evidence references.

### Uncertainty and issues

Uncertainties retain unresolved questions with stable IDs, descriptions, and evidence references. Issues are explicit descriptive strings. Neither is converted into scalar confidence.

### Abstention

`SystemAbstention` remains independent from the quality status. Policy-required abstention and reviewer-triggered abstention are both preserved with explicit reason codes.

## Quality consistency rules

A `clean` assessment may not contain:

- issues;
- unresolved uncertainty;
- failed automated checks;
- reviewer findings of `issue` or `uncertain`;
- abstention.

A non-clean assessment requires at least one issue.

A `failed` assessment must abstain and include:

```text
extraction-quality-failed
```

When a policy requires abstention for a status, the assessment must also include:

```text
quality-status:<status>
```

## Manifest-last ingestion

`persist_quality_bound_corpus` performs the following sequence:

1. validate the frozen plan, corpus, policy, and assessment population;
2. verify every source-extraction-content graph;
3. append source artifacts;
4. append extracted-content artifacts;
5. append extraction manifests;
6. append quality assessments;
7. append the quality policy;
8. append the quality-bound corpus manifest last;
9. reread the policy and every assessment.

The local store is append-only, not transactional. Valid partial artifacts may remain after failure, but the final corpus manifest is the completion marker.

## Quality decision

`validate_extraction_quality_evidence` returns an `ExtractionQualityDecisionReport` only after:

- the plan references the exact quality-bound corpus;
- content order matches exactly;
- the corpus references the exact accepted policy;
- each assessment reference matches its corpus entry;
- source, extraction, and content references match;
- required automated checks match exactly and in order;
- reviewer minimums are satisfied;
- policy-required abstention reasons are present.

The report preserves every content item's status, issues, uncertainty IDs, and abstention decision.

## Governed execution

`QualityGatedExtractionExperimentRunner` first loads and validates the quality evidence. It then writes a run-specific decision artifact:

```text
<experiment-run-id>:extraction-quality-decision
```

### Execute outcome

When no assessment abstains:

- the existing `EligibleExtractionExperimentRunner` runs unchanged;
- one final `quality-gated-completion` links the policy, assessments, decision, and eligible-extraction completion;
- the entire chain is reread and reverified.

### Abstain outcome

When any valid assessment abstains:

- no analyzer is invoked;
- no governed session or experiment completion is created;
- one final `quality-abstention` artifact links the policy, assessments, and decision;
- the abstention artifact is reread and reverified.

Both outcomes return `VerifiedQualityGatedExtractionReceipt`. The outcome field remains explicitly `execute` or `abstain`.

## Failure boundaries

Failures are identified as:

- `preflight`;
- `quality-loading`;
- `quality-validation`;
- `decision-persistence`;
- `experiment-execution`;
- `final-persistence`;
- `verification`.

A later analyzer failure may leave the valid quality decision and earlier verified session receipts intact, but no quality-gated completion is written.

## Synthetic fixtures

The frozen `0.3.0` corpus contains three clean identity extractions. Every fixture:

- passes both deterministic checks;
- has one confirming reviewer observation;
- preserves no uncertainty;
- reports no issue;
- does not abstain.

Tests construct altered append-only assessment and corpus versions to exercise uncertainty, failed checks, missing review evidence, and abstention without mutating the accepted fixtures.

## Schemas

- [`extraction-quality-policy.schema.json`](../schemas/extraction-quality-policy.schema.json)
- [`extraction-quality-assessment.schema.json`](../schemas/extraction-quality-assessment.schema.json)
- [`quality-bound-extraction-corpus.schema.json`](../schemas/quality-bound-extraction-corpus.schema.json)
- [`extraction-quality-decision.schema.json`](../schemas/extraction-quality-decision.schema.json)
- [`quality-gated-extraction-final.schema.json`](../schemas/quality-gated-extraction-final.schema.json)

## Explicit limits

This slice does not provide:

- real extraction-quality measurement;
- reviewer identity governance;
- conflict adjudication;
- probabilistic or scalar extraction confidence;
- real source documents or datasets;
- retries, scheduling, parallel workers, API, frontend, or deployment;
- aggregate CTRT scoring.

`verified` means the declared policy, evidence, decision, and selected lifecycle completed with intact artifacts. It does not mean the extraction was objectively accurate.
