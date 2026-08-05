# ADR-0055: The current revocation conflict-adjudicator checkpoint-witness adjudicator requires an exact issuer-bound credential

- Status: Accepted
- Date: 2026-08-03
- Scope: Phase 1A governance evidence
- Successor corpus: `1.30.0`
- Exact predecessor: `1.29.0`

## Context

ADR-0054 introduced an authorized adjudication over a preserved conflict in the exact `1.28.0` named-witness population.

That layer preserved the conflicting observation, fork evidence, dissent, adjudicator registry, adjudication policy, selected checkpoint head, and every delegated outcome. It established that a declared adjudicator record performed the operational resolution under an accepted policy.

It did not establish that the declared adjudicator identity revision held an accepted issuer-bound credential for the required role at evaluation time.

A registry entry alone states who the accepted policy names. It does not provide a separate issuer record, credential type, validity window, status, or exact subject binding.

## Decision

The exact `1.29.0` adjudication may execute only after an accepted issuer-bound credential gate evaluates the exact adjudicator identity revision and required role.

The credential layer is append-only. It does not alter the `1.29.0` adjudication, witness records, fork evidence, dissent, selected head, or any inherited artifact.

The layer binds exactly:

```text
adjudicator ID:
  adjudicator.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork

identity revision:
  synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

required role:
  witness_conflict_adjudicator
```

The accepted issuer record is:

```text
issuer ID:
  issuer.synthetic.current-revocation-conflict-adjudicator-checkpoint-witness-governance

issuer revision:
  synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-governance@0.1.0
```

The credential type is:

```text
ctrt.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-role
```

## Exact immutable graph

```text
issuer registry:
  sha256:764b0e77ee7b1dc2bea93b896402002c5b81b6a785d05b5ba4aafa8ee05fda8c

credential policy:
  sha256:a5074d6dab65673e899297bb3e1243dc013c88ba75d05845a1ad3b409c885a4a

credential attestation:
  sha256:26759637a9f3a4b8e8cc2996a071abdbb9f4cbccd7c0cf873344f7a48f4885b6

credential-bound successor `1.30.0`:
  sha256:a9ece983cac8c81dee0bfd61df4cd396ea03eb1df339c0ef6cc43e0604b39209
```

The exact predecessor remains:

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.29.0
sha256:7f764303de2ed1d57856403bd900d0690ebf18c37b40a944e29e0e9b27a70cc4
```

## Credential semantics

The credential is active and uses a half-open validity interval:

```text
valid_from <= evaluated_at < valid_until
```

Exact timestamps:

```text
issued_at  = 2026-08-03T19:59:11Z
valid_from = 2026-08-03T19:59:12Z
valid_until = 2027-08-03T19:59:12Z
```

The accepted policy produces governed abstention when the credential is not yet valid, expired, suspended, or revoked.

Identity revision, issuer, credential type, required role, subject reference, predecessor, and artifact substitution are structural failures rather than governed abstentions.

## Execution order

```text
load exact `1.30.0` credential graph
  -> verify exact `1.29.0` predecessor
  -> validate exact issuer-bound credential
  -> persist credential decision
  -> credential abstention or exact `1.29.0` plan derivation
  -> execute PR #51 unchanged under the same run ID
  -> preserve every PR #51 and inherited outcome separately
  -> persist outer final last
  -> reread the complete stored graph
```

The credential decision must exist before any PR #51 runtime artifact created by this outer layer.

## Outcome separation

The new credential outcome is not an aggregate status for the adjudication chain.

The final record preserves separately:

1. the new credential outcome;
2. the `1.29.0` conflicting witness outcome;
3. the `1.29.0` resolution status;
4. the `1.29.0` adjudication outcome;
5. the resolved canonical witness outcome;
6. all 23 PR #50 and inherited outcomes;
7. the terminal review outcome.

No confidence, score, vote, majority, quorum, reputation, or trust field is permitted.

## Governed abstention

A structurally valid credential may produce `abstain` when its validity or status requires it.

When the credential outcome is `abstain`:

```text
all PR #51 and inherited outcomes = null
PR #51 final reference            = null
terminal outcome                  = abstain
```

The credential decision and outer abstention final remain inspectable.

## Structural failure

The runner fails closed without manufacturing a governed abstention for:

- predecessor reference or content-order drift;
- adjudicator registry substitution;
- issuer registry substitution;
- credential policy substitution;
- credential attestation substitution or omission;
- duplicate credential subjects;
- adjudicator ID or identity-revision drift;
- subject-reference drift;
- credential-type or role drift;
- issuer ID or revision drift;
- adjudication substitution;
- chronology inversion;
- run-identity mismatch;
- noncanonical serialization;
- stored-artifact drift;
- closed-schema violation.

## Trust boundary

This decision does not establish:

- real-world or legal identity;
- cryptographic authorship or signature validity;
- issuer independence, competence, honesty, or correctness;
- adjudicator independence, competence, honesty, or correctness;
- witness independence or correctness;
- checkpoint truth or ledger completeness;
- absence of alternate histories;
- trusted external time;
- consensus, majority support, or quorum;
- confidence, reputation, or aggregate trust;
- analytical accuracy, deployment readiness, or a CTRT score.

It establishes only that the exact accepted issuer record attested that the exact declared adjudicator identity revision held the exact required role during the evaluated validity interval, and that this credential decision governed whether the unchanged `1.29.0` lifecycle could execute.

## Consequences

### Positive

- authority is no longer inferred solely from registry membership;
- issuer, subject, role, type, status, and validity are independently inspectable;
- expired or inactive authority produces explicit governed abstention;
- structural substitution remains distinguishable from a valid abstention;
- the entire adjudication and dissent graph remains immutable.

### Costs

- the governance graph gains another append-only evidence layer;
- runtime chronology and final records become larger;
- every delegated outcome must remain individually represented;
- credential lifecycle changes require separate append-only evidence rather than mutation.

## Deferred

A later bounded layer may attach append-only revocation history to this exact credential attestation.

Such a layer must preserve the complete `1.30.0` issuer, policy, credential, conflict, adjudication, fork-evidence, dissent, selected-head, and inherited outcome graph unchanged.
