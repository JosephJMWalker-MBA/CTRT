# ADR-0029: Adjudicator checkpoint witness conflicts require authorized resolution

- Status: Accepted
- Date: 2026-08-03

## Context

ADR-0028 adds immutable named witness observations above adjudicator credential revocation checkpoints. Every required witness is preserved individually, and one conflicting checkpoint-head observation produces a governed witness abstention regardless of how many other witnesses match.

That behavior protects CTRT from silently converting witness count into truth. It also creates a legitimate operational question: when the checkpoint chain has independently verified one declared head, but a structurally valid witness reports another head, may execution ever continue?

The witness layer cannot answer that question without contradicting its own purpose. Its job is to preserve observations and expose disagreement, not to adjudicate the disagreement.

## Decision

CTRT represents adjudicator-checkpoint witness conflict resolution as a separate immutable governance layer.

The original witness decision remains unchanged. If any required witness reports a conflicting head, the witness outcome remains `abstain` permanently.

A separate adjudication artifact binds:

- the exact witness-bound predecessor corpus;
- the exact witness registry and policy;
- the exact conflict-adjudicator registry and policy;
- the checkpoint head already verified by the checkpoint chain;
- every conflicting witness attestation;
- the expected and observed head references;
- the resolution status;
- the authorized adjudicator identity revision and role, when decided;
- the selected head, when resolved;
- preserved dissent;
- an explicit rationale and decision timestamp.

Resolution states are:

- `not_required` when every required witness matched;
- `pending` when conflict evidence exists but no authorized decision has been made;
- `resolved` when an authorized adjudicator permits the independently verified head to proceed;
- `unresolved` when an authorized adjudicator determines that the available evidence does not permit resolution.

A resolved adjudication may select only the checkpoint head already established by the independently verified checkpoint chain. It may not select the conflicting witness head, invent a third head, merge heads, or infer a winner from witness count.

Pending and unresolved adjudications produce governed terminal abstention before revocation, credential, reviewer-governance, or analyzer execution.

A resolved adjudication permits delegation to the unchanged adjudicator checkpoint runner. The original witness abstention, conflict evidence, rationale, and dissent remain separately inspectable in the final receipt.

## Consequences

### Positive

- Witness disagreement is never overwritten or reclassified as agreement.
- Authority and observation remain separate claims.
- Two matching witnesses cannot outvote one conflicting witness.
- Resolution requires an explicit authorized identity revision, role, rationale, and timestamp.
- The selected head remains constrained by independent checkpoint verification.
- Pending and unresolved cases fail closed.
- Downstream revocation or analytical abstention does not erase successful adjudication.
- The exact fork and dissent remain available for later audit or reconsideration.

### Costs

- The artifact graph gains an adjudicator registry, policy, adjudication record, decision report, successor corpus, and outer final receipt.
- A resolved case may execute the checkpoint runner after the witness runner has already persisted an abstention, creating intentionally separate records rather than one collapsed status.
- Consumers must distinguish observation, authorization, and downstream outcomes.
- Human or institutional authority remains an asserted synthetic role in this phase, not externally verified identity.

## Structural failure versus governed abstention

Structural failure includes:

- missing or tampered predecessor, registry, policy, attestation, adjudication, or corpus artifacts;
- stale hashes or mismatched artifact identities;
- an adjudication record not bound by the successor corpus;
- an unknown adjudicator;
- an adjudicator identity-revision or role mismatch;
- fork evidence that differs from the original witness observations;
- missing dissent in a resolved or unresolved case;
- a resolved selection that differs from the independently verified checkpoint head;
- a decision timestamp after the declared evaluation time;
- storage, final-persistence, or reread failure.

These defects produce no verified adjudication terminal receipt.

Structurally valid `pending` or `unresolved` adjudication produces governed abstention. Structurally valid `resolved` adjudication permits downstream execution while preserving the original witness abstention.

## Non-claims

A verified adjudicator-checkpoint witness adjudication does not establish:

- that the selected checkpoint head is globally unique;
- that the conflicting witness was mistaken or dishonest;
- that every relevant checkpoint or witness observation was disclosed;
- that no alternate checkpoint chain exists;
- legal or real-world adjudicator identity;
- adjudicator independence, competence, honesty, or correctness;
- cryptographic authorship or signature validity;
- trusted external time;
- public or global publication;
- universal event completeness;
- issuer trustworthiness;
- credential truthfulness;
- extraction, review, or analyzer accuracy;
- content quality;
- consensus, confidence, reputation, rank, or an aggregate CTRT score.

## Rejected alternatives

### Let matching witnesses outvote a conflict

Rejected because witness count is not evidence that one observation is true.

### Change the original witness outcome after resolution

Rejected because it would erase the historical fact that the required witnesses disagreed.

### Permit the adjudicator to select any observed head

Rejected because adjudication authority must not replace independent checkpoint-chain verification.

### Drop dissent after a resolved decision

Rejected because operational resolution does not make contrary evidence disappear.

### Treat every conflict as permanently terminal

Rejected because a separate, explicit, inspectable authority may legitimately govern whether a verified state is operationally usable.

### Add signatures, identity providers, or a live fork-resolution network now

Deferred. This bounded layer establishes immutable authorization and preserved disagreement inside the synthetic repository graph.

## Follow-up

The next bounded layer may bind the conflict adjudicator identity revision and role to immutable issuer credentials, validity windows, and revocation state without altering this adjudication record.
