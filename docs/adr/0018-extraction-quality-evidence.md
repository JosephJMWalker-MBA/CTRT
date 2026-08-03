# ADR-0018: Extraction quality requires independent evidence

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 1A — Content Analysis Workbench

## Context

ADR-0017 authorizes extraction methods through a frozen registry. That gate proves that a declared method, immutable revision, source type, mapping kind, license state, and configuration were permitted to participate in an experiment.

Authorization does not prove that a particular extraction was complete or faithful. A licensed, pinned, eligible method can still produce a damaged, incomplete, ambiguous, or incorrectly reviewed output.

CTRT therefore needs an evidence layer between method eligibility and downstream analyzer execution.

## Decision

Every executable quality-bound extraction corpus must reference:

- one exact accepted extraction-quality policy;
- one immutable quality assessment for each content item;
- the exact source, extraction, and canonical-content artifacts evaluated by that assessment.

Quality evidence is evaluated before any analyzer runs.

### Evidence types remain separate

Each assessment preserves:

- deterministic automated checks with exact check IDs and revisions;
- reviewer observations with reviewer role, finding, notes, and evidence references;
- unresolved uncertainties;
- explicit issues;
- one extraction-quality status;
- one independent abstention decision with reason codes.

Automated checks do not substitute for reviewer observations. Reviewer confirmation does not erase failed automated checks. Uncertainty is retained rather than converted into a scalar score.

### Quality states

The initial vocabulary remains the existing structured extraction-quality vocabulary:

- `clean`;
- `partial`;
- `degraded`;
- `failed`.

`clean` is a strict state. It may not contain issues, unresolved uncertainty, failed automated checks, reviewer concerns, or abstention.

Non-clean states require explicit issues. `failed` requires abstention and the reason `extraction-quality-failed`.

### Frozen policy

The quality policy identifies:

- required automated check IDs and revisions;
- minimum reviewer-observation count;
- quality states that require abstention.

The initial synthetic policy requires exact coordinate coverage, source/output byte equality, one reviewer observation, and mandatory abstention for failed quality.

### Append-only corpus evolution

The method-bound synthetic corpus `0.2.0` remains unchanged.

A new quality-bound version `0.3.0` contains the same source, extraction, content, and method-registry bindings plus:

- the exact quality-policy reference;
- one exact quality-assessment reference per content entry.

Ingestion writes source, content, extraction, assessment, and policy artifacts before appending the quality-bound corpus manifest last. Partial evidence artifacts may remain valid after failure, but no corpus manifest falsely claims a complete quality population.

### Two verified terminal outcomes

`QualityGatedExtractionExperimentRunner` can return two verified outcomes.

#### Execute

When every assessment satisfies the policy and no assessment abstains, the runner:

1. persists a run-specific quality decision;
2. delegates the existing method-eligible extraction lifecycle unchanged;
3. links the eligible-extraction completion into a final quality-gated completion;
4. rereads and re-verifies the complete chain.

#### Abstain

When valid evidence contains an explicit abstention, the runner:

1. persists the quality decision;
2. does not invoke any analyzer;
3. creates no governed session, experiment completion, extraction-bound completion, or eligible-extraction completion;
4. writes and re-verifies a final quality-abstention artifact.

A verified abstention is a successful governance outcome, not an execution failure.

### Run-specific decisions

The detailed quality-decision artifact is identified by the experiment-run ID:

```text
<experiment-run-id>:extraction-quality-decision
```

This prevents separate executions of the same frozen plan from colliding when their evaluation timestamps differ. A deterministic plan-level index remains available for discovery without replacing the run-specific evidence.

### Verification does not imply accuracy

A verified quality outcome proves that:

- the exact policy and assessment artifacts were bound and reverified;
- required evidence was present;
- uncertainty and abstention were preserved;
- the selected execute-or-abstain lifecycle completed with intact artifacts.

It does not prove:

- real-world extraction accuracy;
- reviewer correctness;
- analyzer success or agreement;
- calibration;
- content quality;
- an aggregate CTRT score.

## Consequences

### Positive

- Method authorization can no longer masquerade as extraction accuracy.
- Automated and human evidence remain independently inspectable.
- Unresolved uncertainty can stop execution without being hidden or forced into a number.
- Abstention becomes a durable, verified result.
- Downstream analyzers cannot run before the quality gate completes.
- Prior frozen corpus versions remain unchanged.

### Costs and limits

- The initial policy does not adjudicate conflicting reviewers.
- Reviewer identity and authorization are not yet governed.
- No probabilistic extraction-quality score is defined.
- The synthetic checks validate architecture, not a real extractor.
- The local store still lacks signatures, access control, deletion policy, and remote durability.

## Rejected alternatives

### Treat method eligibility as sufficient evidence

Rejected because authorization concerns permission and reproducibility, not whether one output is accurate.

### Emit one scalar extraction confidence

Rejected because it would collapse automated failures, reviewer findings, uncertainty, and policy decisions into an opaque number.

### Treat abstention as an exception

Rejected because abstention is an intentional governed outcome that should be persisted and reviewed like execution completion.

### Run analyzers and attach quality evidence afterward

Rejected because low-quality or uncertain extraction must be able to prevent downstream measurement entirely.

### Rewrite corpus version `0.2.0`

Rejected because frozen research artifacts evolve by new versions, not silent mutation.
