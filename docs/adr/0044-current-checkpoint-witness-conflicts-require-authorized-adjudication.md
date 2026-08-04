# ADR-0044: Current checkpoint witness conflicts require authorized adjudication

- Status: Accepted
- Date: 2026-08-04
- Scope: Phase 1A synthetic governance chain

## Context

PR #40 binds a required named-witness population to the exact immutable `1.17.0` checkpoint head. Its policy is deliberately fail-closed:

```text
match + match + match    -> execute
match + match + conflict -> abstain
```

A valid conflicting observation is not malformed evidence. It is an immutable report from a required witness that differs from the declared checkpoint head. The witness layer must preserve that report and abstain without allowing the other required witnesses to outvote it.

Operational work may still need a governed way to proceed after such an abstention. That continuation cannot be represented as a revised witness decision. Doing so would erase the historical fact that the required witness population conflicted.

## Decision

CTRT will represent conflict resolution as a new, append-only adjudication layer over the exact preserved `1.18.0` observation population.

The `1.19.0` layer must preserve separately:

1. the exact `1.18.0` predecessor;
2. every original witness attestation in required order;
3. the original witness decision of `abstain`;
4. the exact fork evidence;
5. the dissenting observed head;
6. the accepted adjudicator registry;
7. the accepted adjudication policy;
8. the adjudication record and rationale;
9. the adjudication decision;
10. any later delegated lifecycle outcomes.

A resolved adjudication may select only the exact checkpoint head independently verified by the immutable `1.17.0` checkpoint chain.

The selected head is an operational authorization claim. It does not change what any witness observed.

## Required behavior

### Resolved conflict

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome         = execute
```

After those three claims are persisted separately, the plan may narrow from exact `1.19.0` to exact `1.18.0` and invoke PR #40 unchanged under the same experiment run ID.

PR #40 then evaluates the canonical `1.18.0` witness population. Its result remains distinct from the original conflicting population and its adjudication.

### Pending conflict

```text
conflicting witness outcome = abstain
resolution status           = pending
adjudication outcome         = abstain
```

The witness and adjudication decisions are persisted. PR #40 is not invoked.

### Unresolved conflict

```text
conflicting witness outcome = abstain
resolution status           = unresolved
adjudication outcome         = abstain
```

Fork evidence and dissent remain visible. PR #40 is not invoked.

## No-majority rule

The adjudication layer may not infer authorization from witness counts.

Two matching witnesses do not defeat one required conflict. The accepted adjudicator acts under an explicit policy and must provide a separately stored decision and rationale.

The layer must not introduce:

- majority voting;
- weighted voting;
- quorum;
- consensus claims;
- confidence scores;
- reputation scores;
- witness ranking;
- trust aggregation.

## Exact authority binding

The adjudication record must bind:

- the exact `1.18.0` predecessor reference;
- the exact witness registry and policy;
- the exact ordered attestation population;
- the accepted adjudicator registry;
- the accepted adjudication policy;
- the exact independently verified checkpoint head;
- the exact conflicting observed head;
- the exact fork-evidence attestation;
- the preserved dissent entry;
- the adjudicator identity revision;
- the decision timestamp and rationale.

Any drift is structural failure rather than governed abstention.

## Publication order

The append-only publication order is:

1. accepted adjudicator registry;
2. accepted adjudication policy;
3. immutable conflicting attestation;
4. immutable adjudication record;
5. compact `1.19.0` successor manifest;
6. exact-hash reread of the complete graph.

The `1.18.0` predecessor is verified but never rewritten.

## Lifecycle order

The governed runtime order is:

```text
conflicting witness validation
-> conflicting witness decision persistence
-> adjudication validation
-> adjudication decision persistence
-> optional exact PR #40 execution
-> outer final persistence
-> complete storage reverification
```

No PR #40 artifact may exist when adjudication is pending or unresolved.

## Independent claims

The final record keeps these claims distinct:

- conflicting current witness outcome;
- current resolution status;
- current adjudication outcome;
- canonical `1.18.0` witness outcome after authorized resolution;
- current revocation outcome;
- current credential outcome;
- lower checkpoint-witness and adjudication outcomes;
- every inherited outcome;
- terminal outcome.

A later revocation abstention does not rewrite the earlier adjudication execution. A later successful execution does not rewrite the original witness abstention.

## Trust boundary

This decision does not establish:

- legal or real-world adjudicator identity;
- cryptographic authorship or signature validity;
- private-key possession;
- trusted external time;
- adjudicator independence, competence, honesty, or correctness;
- witness independence, competence, honesty, or correctness;
- checkpoint or ledger completeness;
- absence of undisclosed events or alternate checkpoint chains;
- global uniqueness or public availability;
- external truth of either observed head;
- majority support, consensus, confidence, reputation, or trust;
- analytical accuracy, deployment readiness, or an aggregate CTRT score.

## Consequences

### Positive

- Original disagreement remains auditable.
- Operational resolution is explicit and attributable.
- Pending and unresolved states fail closed.
- Later governance layers can credential and revoke the new adjudicator without modifying this decision.
- The system distinguishes evidence from authorization.

### Costs

- The artifact graph grows by another immutable layer.
- Runtime receipts carry more independent outcomes.
- Reviewers must distinguish the conflicting witness population from the canonical population evaluated after resolution.
- The new adjudicator authority requires its own future credential, revocation, checkpoint, and witness governance.

## Follow-on boundary

The next bounded layer may attest a credential for the exact adjudicator identity revision and `witness_conflict_adjudicator` role introduced here.

That layer must preserve the complete `1.19.0` conflict, abstention, fork evidence, dissent, selected head, rationale, and adjudication result unchanged.
