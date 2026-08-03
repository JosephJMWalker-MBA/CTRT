# Phase 1A: Extraction Review Adjudication

This slice adds identity-bound human review and explicit disagreement handling before the existing extraction-quality gate.

It does not establish reviewer correctness, external identity proof, extraction accuracy, or content quality.

## Artifact graph

The review-bound path extends the existing source and quality graph:

```text
source artifact
  ↓
extraction manifest
  ↓
extracted-content artifact
  ↓
quality assessment
  ↓
review adjudication
```

The frozen review-bound corpus additionally references:

- the extraction-method registry;
- the extraction-quality policy;
- the reviewer registry;
- the review-adjudication policy;
- one quality assessment and one review-adjudication artifact per content item.

The corpus manifest is written last.

## Reviewer registry

`ReviewerRegistrySnapshot` parses and canonically identifies reviewer records containing:

- `reviewer_id`;
- `identity_revision`;
- authorized `roles`;
- `active` status.

The synthetic registry contains separate primary reviewer, secondary reviewer, and adjudicator identities.

The registry is an execution authorization artifact. It is not an external credential or identity-verification service.

## Review policy

`ReviewAdjudicationPolicySnapshot` freezes:

- minimum distinct reviewers;
- required roles;
- authorized adjudicator role;
- states that require abstention;
- mandatory dissent preservation;
- prohibition of majority-vote adjudication.

The initial policy requires two distinct reviewers occupying primary and secondary roles. Pending and unresolved conflicts abstain.

## Review observations

`ReviewerObservationRecord` preserves one position with:

- stable observation ID;
- reviewer ID;
- reviewer role;
- review-question ID;
- `confirmed`, `issue`, or `uncertain` finding;
- notes;
- evidence references;
- observation timestamp.

Reviewer identity and role are checked against the frozen registry.

## Conflict records

`ReviewConflictRecord` explicitly connects observations that disagree.

A conflict contains:

- stable conflict ID;
- conflict kind;
- at least two observation IDs;
- description.

The validator groups observations by review question. When a question contains multiple findings, the disagreement must be represented by a conflict record. Reviewer counts do not resolve the conflict.

## Adjudication states

`ReviewAdjudicationSnapshot` supports:

- `not_required`;
- `pending`;
- `resolved`;
- `unresolved`.

`not_required` permits no conflict state.

`pending` and `unresolved` require declared unresolved conflicts and explicit abstention.

`resolved` requires:

- at least one declared conflict;
- no unresolved conflict IDs;
- an active authorized adjudicator;
- resolution notes;
- no review-level abstention.

## Preserved dissent

`PreservedDissent` retains:

- dissent ID;
- reviewer ID;
- observation IDs belonging to that reviewer;
- position;
- rationale;
- explicit `preserved: true` marker.

A resolved adjudication can therefore permit execution without claiming unanimous agreement.

## Decision report

`validate_review_adjudication_evidence` produces a `ReviewAdjudicationDecisionReport` that preserves, for each content item:

- adjudication status;
- distinct reviewer IDs;
- reviewer roles;
- conflict IDs;
- unresolved conflict IDs;
- dissent IDs;
- abstention state.

The report intentionally contains no:

- vote totals;
- majority result;
- consensus percentage;
- scalar confidence;
- aggregate quality score.

## Governed runner

`AdjudicatedExtractionExperimentRunner` evaluates the review layer before calling `QualityGatedExtractionExperimentRunner`.

### Preflight

The runner verifies:

- frozen experiment plan;
- exact review-bound corpus reference;
- exact content order;
- exact reviewer-registry reference;
- exact review-policy reference;
- ordered execution windows;
- review and quality evaluation timestamps.

### Evidence loading

The runner rereads and hash-verifies:

- review-bound corpus;
- reviewer registry;
- review policy;
- every review-adjudication artifact;
- quality policy and every quality assessment.

### Review decision

The run-specific decision is stored as:

```text
<experiment-run-id>:review-adjudication-decision
```

A stable plan-level index remains available for discovery.

The quality decision is also preserved for the same run, even when review abstention prevents the quality runner from executing.

### Review abstention

When review outcome is `abstain`:

- the quality-gated runner is not invoked;
- no analyzer executes;
- no governed session, experiment completion, or quality-gated final is created;
- the final artifact is:

```text
<experiment-run-id>:review-adjudication-abstention
```

### Review-permitted execution

When review outcome is `execute`, the existing quality-gated runner executes unchanged.

The quality gate can still independently abstain. The review layer therefore preserves both review outcome and terminal outcome.

Successful full execution writes:

```text
<experiment-run-id>:review-adjudicated-completion
```

## Failure semantics

Failures are reported at explicit stages:

- `preflight`;
- `evidence-loading`;
- `review-validation`;
- `decision-persistence`;
- `quality-gate`;
- `final-persistence`;
- `verification`.

If later analyzer execution fails, the run-specific review decision, quality decision, and earlier verified content receipts remain valid append-only evidence. No final review-adjudicated completion is written.

## Synthetic test cases

The test suite verifies:

- clean two-reviewer execution;
- exact schema validation;
- idempotent ingestion and execution;
- unresolved conflict abstention before analyzers;
- two confirmations cannot outvote one issue finding;
- resolved conflict can execute while dissent remains preserved;
- contradictory findings require a conflict record;
- an unauthorized adjudicator cannot resolve conflict;
- vote-count fields are rejected by both schema and parser;
- missing adjudication artifacts fail before decision;
- later analyzer failure preserves decisions and earlier receipts;
- final persistence failure returns no verified receipt;
- stored adjudication evidence reconstructs exactly.

## Current exclusions

This slice does not add:

- real reviewer accounts or identity proofing;
- credential issuers or signatures;
- automatic reviewer assignment;
- conflict-of-interest checks;
- automatic semantic conflict detection;
- reviewer performance scores;
- majority voting or consensus percentages;
- real extraction engines, models, or datasets;
- API, frontend, deployment, retries, or distributed workers.
