# ADR-0050: Current revocation-checkpoint witness-conflict adjudicators require exact issuer-bound credentials

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A
- Successor corpus: `1.25.0`
- Exact predecessor: `1.24.0`

## Context

ADR-0049 established a bounded authorized adjudication over a preserved conflict in the exact required witness population observing the current revocation-checkpoint head.

That layer established that:

- the exact `1.23.0` witness population conflicted;
- the original witness decision remained `abstain`;
- an accepted adjudicator registry named one exact adjudicator identity revision;
- the registry assigned the `witness_conflict_adjudicator` role;
- an accepted adjudication policy required fail-closed pending and unresolved states;
- a resolved adjudication selected only the exact head independently verified by `1.22.0`;
- gamma's alternate observation remained immutable fork evidence and preserved dissent;
- the unchanged `1.23.0` lifecycle could execute only after the separate adjudication decision executed.

The accepted adjudicator registry is necessary but not sufficient to answer a narrower provenance question:

> Did an accepted issuer attest that the exact adjudicator identity revision was authorized for the exact role at the evaluation time?

Registry membership alone does not establish who asserted the authorization, which credential type was used, whether the issuer was accepted and active, whether the credential was active, whether the validity window included the evaluation time, or whether the credential authorized the exact role rather than a neighboring role.

The credential layer must not alter the adjudication record, decide whether the selected head was correct, erase dissent, or collapse credential eligibility into adjudication correctness.

## Decision

Add one immutable issuer-bound credential layer over the exact `1.24.0` adjudication corpus.

The `1.25.0` successor binds:

1. the exact immutable `1.24.0` predecessor;
2. the exact accepted conflict-adjudicator registry from `1.24.0`;
3. one accepted credential-issuer registry;
4. one accepted credential policy;
5. one immutable credential attestation for the exact adjudicator identity revision;
6. the exact `witness_conflict_adjudicator` role;
7. a validity interval and credential status;
8. the unchanged `1.24.0` adjudication reference.

The credential decision is persisted separately from every adjudication and witness decision.

Only a credential decision of `execute` may narrow the frozen plan from exact `1.25.0` to exact `1.24.0` under the same experiment run ID.

## Exact predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.24.0
sha256:a98bcdc6c6c146de7d688ea708285f8d4b82bd93a8486ac5e37e76bf3acaa5fb
```

The predecessor carries the complete preserved conflict, original witness abstention, fork evidence, dissent, selected head, rationale, adjudication record, exact `1.23.0` predecessor, exact `1.22.0` checkpoint head, and every inherited artifact.

None of that evidence is rewritten.

## Exact adjudicator identity

```text
adjudicator.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Required role:

```text
witness_conflict_adjudicator
```

## Issuer-bound credential graph

The accepted issuer registry contains one active issuer:

```text
issuer.synthetic.current-revocation-checkpoint-witness-conflict-governance
```

Issuer revision:

```text
synthetic-current-revocation-checkpoint-witness-conflict-governance@0.1.0
```

Credential type:

```text
ctrt.current-revocation-checkpoint-witness-conflict-adjudicator-role
```

The policy requires:

- exact adjudicator-registry binding;
- exact issuer-registry binding;
- exact credential-type binding;
- exact role matching;
- abstention when not yet valid;
- abstention when expired;
- abstention when suspended;
- abstention when revoked.

## Credential decision rule

```text
accepted active issuer
+ exact identity revision
+ exact role
+ active credential
+ valid_from <= evaluated_at < valid_until
= credential execute
```

Any governed invalidity state produces credential `abstain` without changing the adjudication record.

Structural identity, registry, policy, reference, or serialization mismatches fail the boundary rather than becoming governed abstentions.

## Outcome matrix

### Active exact credential

```text
new credential outcome = execute
exact 1.24.0 lifecycle = invoked
all prior outcomes      = preserved separately
```

### Not yet valid

```text
new credential outcome = abstain
reason                 = credential-not-yet-valid
all PR #46 outcomes     = null
terminal outcome        = abstain
```

### Expired

```text
new credential outcome = abstain
reason                 = credential-expired
all PR #46 outcomes     = null
terminal outcome        = abstain
```

### Suspended or revoked

```text
new credential outcome = abstain
reason                 = credential-status:suspended | credential-status:revoked
all PR #46 outcomes     = null
terminal outcome        = abstain
```

### Inactive issuer

```text
new credential outcome = abstain
reason                 = credential-issuer-inactive
all PR #46 outcomes     = null
terminal outcome        = abstain
```

## Execution order

```text
load exact 1.25.0 credential graph
  -> validate exact credential evidence
  -> persist credential decision
  -> credential abstention or exact 1.24.0 plan derivation
  -> unchanged PR #46 lifecycle
  -> outer finalization
  -> full storage reread
```

The credential decision is stored before any PR #46 execution.

## Invariants

1. The `1.25.0` predecessor reference equals the exact `1.24.0` reference.
2. Ordered content IDs remain unchanged.
3. The adjudicator registry equals the exact registry preserved by `1.24.0`.
4. Credential entries cover the exact adjudicator population in registry order.
5. Each credential entry binds one exact adjudicator ID and identity revision.
6. Each credential reference resolves to canonical immutable bytes.
7. The credential policy binds the exact issuer and adjudicator registries.
8. The attested role equals the registry role exactly.
9. The credential type equals the policy credential type exactly.
10. The issuer is present, revision-matched, authorized for the credential type, and active.
11. The validity window is half-open: `valid_from <= evaluated_at < valid_until`.
12. Credential abstention cannot claim downstream outcomes or a PR #46 final.
13. Credential execution narrows only the corpus reference under the same run ID.
14. The final manifest is written last and then reread.

## Structural failures

The layer fails closed for:

- predecessor substitution;
- content-order drift;
- adjudicator-registry drift;
- issuer-registry drift;
- credential-policy drift;
- credential-population drift;
- adjudicator ID substitution;
- identity-revision substitution;
- role substitution;
- credential-type substitution;
- issuer revision substitution;
- credential-reference drift;
- adjudication-reference drift;
- invalid chronology;
- run-identity mismatch;
- stored-artifact drift;
- noncanonical serialization.

These are not converted into credential abstentions.

## Trust boundary

This layer does not establish:

- legal or real-world identity;
- cryptographic authorship;
- signatures or private-key possession;
- trusted external time;
- issuer independence, competence, honesty, or correctness;
- adjudicator independence, competence, honesty, or correctness;
- correctness of the selected checkpoint head;
- completeness of the checkpoint or revocation ledger;
- absence of alternate histories;
- majority support, quorum, consensus, confidence, reputation, or trust scores;
- analytical accuracy;
- deployment;
- an aggregate CTRT score.

It establishes only that the accepted evidence graph contains an issuer-bound credential for the exact registered identity revision and role, and that the credential was eligible under the accepted policy at the evaluation time.

## Consequences

Positive consequences:

- registry membership and issuer authorization remain separate claims;
- identity revision and role are exact rather than inferred;
- credential eligibility remains separate from adjudication correctness;
- expiration and suspension can stop execution without rewriting history;
- every delegated result remains independently inspectable.

Costs:

- the final record grows by another explicit outcome and evidence boundary;
- callers must preserve chronology across one additional plan scope;
- future credential revocation requires a separate append-only layer.

## Deferred work

A later bounded layer may add an append-only revocation ledger for this exact `1.25.0` credential.

That layer must preserve the issuer registry, policy, credential attestation, credential decision, complete `1.24.0` adjudication graph, exact `1.23.0` witness predecessor, exact `1.22.0` checkpoint head, and every inherited artifact unchanged.
