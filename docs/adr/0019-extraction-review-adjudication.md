# ADR-0019: Extraction review disagreement is adjudicated without voting

- **Status:** Accepted
- **Date:** 2026-08-02
- **Phase:** 1A — Content Analysis Workbench

## Context

ADR-0018 introduced independent extraction-quality evidence and a governed quality gate. Reviewer observations were preserved separately from automated checks, but reviewer identity was represented only as a free-form role string. The system could retain an observation without proving which registered reviewer made it, whether that reviewer was authorized for the stated role, how contradictory observations related to one another, or whether disagreement had been resolved.

A research-grade record must preserve disagreement rather than flatten it into a reviewer count, consensus percentage, or majority verdict.

## Decision

CTRT will add an append-only review-adjudication layer before the existing quality gate.

### Reviewer identities and roles are registry-bound

A frozen reviewer registry identifies each reviewer by:

- stable reviewer ID;
- immutable identity revision;
- authorized roles;
- active or inactive status.

The initial synthetic registry authorizes primary reviewer, secondary reviewer, and adjudicator roles. Registry membership proves only that CTRT authorized the identity record used in this experiment. External identity proofing, credentials, employment status, and human identity verification remain out of scope.

### Review policy forbids majority voting

A frozen review-adjudication policy declares:

- the minimum number of distinct reviewers;
- required reviewer roles;
- the role authorized to adjudicate;
- adjudication states that require abstention;
- whether dissent must remain preserved;
- whether majority voting is forbidden.

The initial policy requires distinct primary and secondary reviewers, requires an authorized adjudicator for resolved conflict, abstains on pending or unresolved conflict, preserves dissent, and explicitly forbids majority-vote adjudication.

Reviewer counts do not determine the outcome. Two confirming observations do not erase one issue or uncertain observation.

### Contradictions are explicit artifacts

Every review observation preserves:

- stable observation ID;
- reviewer ID and role;
- review-question ID;
- finding;
- notes;
- evidence references;
- observation timestamp.

When observations addressing the same question contain different findings, a conflict record must identify the observations and describe the disagreement. Contradictory findings without a declared conflict fail validation.

### Adjudication states remain distinct

The initial states are:

- `not_required` — no declared conflict exists;
- `pending` — conflict awaits adjudication;
- `resolved` — an authorized adjudicator has supplied a resolution;
- `unresolved` — conflict remains unresolved after review.

Pending and unresolved states must trigger review abstention. A resolved state may permit execution only when an active registry-authorized adjudicator is named and resolution notes are preserved.

### Dissent survives resolution

Resolution does not delete, rewrite, or outvote a dissenting observation. A preserved dissent record identifies the dissenting reviewer, supporting observation IDs, position, and rationale.

A resolved record may therefore permit execution while still preserving material dissent for later inspection.

### Review-bound corpora evolve append-only

The existing quality-bound corpus `0.3.0` remains unchanged. A new `0.4.0` corpus binds:

- the existing extraction and quality graph;
- one exact reviewer-registry reference;
- one exact review-policy reference;
- one immutable review-adjudication artifact per content item.

All source, extraction, content, quality, reviewer, policy, and adjudication artifacts are written and verified before the review-bound corpus manifest is written last.

### Review has a governed execute-or-abstain boundary

`AdjudicatedExtractionExperimentRunner` evaluates review evidence before invoking the existing quality gate.

If review evidence abstains:

- no quality-gated runner is invoked;
- no analyzer executes;
- no governed session or experiment-completion artifact is created;
- a review-adjudication abstention artifact is written and reverified.

If review evidence permits execution, the existing quality gate runs unchanged. The final review-adjudicated marker links the exact review corpus, reviewer registry, policy, adjudication records, run-specific review decision, quality decision, and quality-gated final artifact.

### Review outcome and terminal outcome remain separate

A review decision may permit execution while the downstream quality gate independently abstains. The final marker therefore preserves both:

- `review_outcome` — whether review adjudication permitted the quality gate;
- `terminal_outcome` — whether the complete upstream chain executed or abstained.

Neither field is an extraction-accuracy score or content verdict.

## Consequences

### Positive

- Reviewer identity and role are inspectable and registry-bound.
- Contradictory findings cannot disappear into a consensus summary.
- Pending and unresolved disagreements fail closed before analysis.
- Authorized adjudication can resolve a conflict without deleting dissent.
- Review abstention becomes a verified governance outcome rather than an execution error.
- The final provenance chain distinguishes review permission from downstream quality outcome.

### Costs and limits

- The registry does not externally verify human identity or credentials.
- The initial role vocabulary is intentionally small.
- Conflict declaration remains authored rather than automatically inferred across arbitrary semantic claims.
- Adjudicator competence, independence, and conflicts of interest remain unresolved.
- The local artifact store still lacks signatures, access control, remote durability, and deletion policy.
- No real reviewers, source documents, extractors, or models are introduced.

## Rejected alternatives

### Majority vote

Rejected because reviewer counts suppress minority evidence and transform disagreement into an unsupported scalar decision rule.

### Consensus percentage

Rejected because it implies calibrated confidence without a validated basis and hides the substance of dissent.

### Delete dissent after adjudication

Rejected because resolution is a governance action, not proof that the dissenting observation was meaningless or incorrect.

### Let unresolved review proceed with a warning

Rejected because analyzer outputs would then appear downstream despite a known unresolved upstream provenance dispute.

### Merge review observations into the quality assessment

Rejected because assessment evidence, reviewer identity, conflict declaration, and adjudication are distinct responsibilities with different lifecycle semantics.
