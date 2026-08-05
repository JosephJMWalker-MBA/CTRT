# ADR-0049: Current revocation-checkpoint witness conflicts require authorized adjudication

- Status: Accepted
- Date: 2026-08-04
- Scope: Phase 1A synthetic current conflict-adjudicator authority chain

## Context

PR #45 introduced the exact immutable `1.23.0` named-witness population over the `1.22.0` checkpoint protecting the current conflict-adjudicator credential revocation ledger.

That layer answers:

> What did each required named witness report about the exact immutable `1.22.0` checkpoint head?

Its canonical population records three matching observations and executes. Its governance rule is deliberately fail-closed: one required conflicting observation causes witness abstention even when every other required witness reports the declared head.

A valid conflict is evidence, not structural corruption. It must remain inspectable without being converted into a majority, confidence score, reputation adjustment, or retrospective rewrite. Operational continuation therefore requires a separate authority claim.

## Decision

Add a compact `1.24.0` adjudication-bound successor over the exact immutable `1.23.0` witness predecessor.

The successor preserves:

- the exact `1.22.0` checkpoint predecessor and head;
- the exact accepted `1.23.0` witness registry and policy;
- unchanged alpha and beta observations;
- one new immutable gamma observation reporting an alternate head;
- the conflicting required-population outcome as `abstain`;
- an accepted conflict-adjudicator registry;
- an accepted fail-closed adjudication policy;
- one immutable adjudication record containing exact fork evidence, preserved dissent, rationale, status, and selected head;
- unchanged ordered content IDs.

The provider-neutral adjudicator-checkpoint witness-conflict grammar remains authoritative for witness validation, authority validation, fork reconstruction, dissent preservation, resolution status, selected-head restrictions, and decision semantics.

The context adapter adds only exact `1.22.0` and `1.23.0` binding, compact `1.24.0` parsing, publication chronology, and manifest-last persistence.

## Fixed graph

### Conflicting gamma observation

```text
checkpoint-witness-attestation:attestation.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma.conflict.v0.1.0
sha256:914deff79eae3b553c1ff068ac72840e19dd9bd1ebbb38b8c3f664afb666cce9
```

Gamma reports an alternate head while preserving the expected head as the exact independently verified `1.22.0` checkpoint:

```text
expected = sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
observed = sha256:9999999999999999999999999999999999999999999999999999999999999999
```

### Conflict-adjudicator registry

```text
registry.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicators@0.1.0
sha256:aa657368aa10e3b24c45f550ecb7a897bca900ce34fda72038076370aa196f54
```

Registered authority:

```text
adjudicator.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Role:

```text
witness_conflict_adjudicator
```

### Adjudication policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication@0.1.0
sha256:1df94869e96a2ea024bb50b571a0579637d9e300a91bb20c091c5c0326dc6a6f
```

The policy requires:

```text
abstain_on_pending = true
abstain_on_unresolved = true
resolution_must_select_declared_head = true
forbid_vote_aggregation = true
```

### Adjudication record

```text
witness-conflict-adjudication:adjudication.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma-conflict.v0.1.0
sha256:0dd962ff196b63672cf595a8c0d160683f45518962848494490f80a3e1fc62ee
```

The record preserves gamma's exact alternate observation as both fork evidence and dissent. It selects only the exact checkpoint head already independently verified by `1.22.0`.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.24.0
sha256:a98bcdc6c6c146de7d688ea708285f8d4b82bd93a8486ac5e37e76bf3acaa5fb
```

## Semantic separation

Canonical resolved execution preserves four distinct claims:

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
canonical 1.23.0 witnesses  = execute
```

Adjudication execution does not make witnesses agree, erase gamma's observation, prove the selected checkpoint externally true, alter the underlying revocation ledger, or authorize the adjudicator through a credential claim.

Pending or unresolved adjudication does not invalidate the immutable conflict evidence. It withholds authorization to enter the exact PR #45 lifecycle.

## Execution order

```text
1.24.0 evidence loading
  -> conflicting 1.24.0 witness validation
  -> conflicting witness decision persistence
  -> authorized adjudication validation
  -> adjudication decision persistence
  -> adjudication abstention or exact 1.23.0 plan derivation
  -> unchanged PR #45 witness lifecycle
  -> outer finalization
```

The experiment run ID, experiment identity, version, content order, and all inherited evidence remain unchanged across the `1.24.0 -> 1.23.0` boundary.

## Outcomes

### Resolved

```text
conflicting witness = abstain
resolution          = resolved
adjudication        = execute
PR #45              = invoked with canonical 1.23.0 population
```

### Pending or unresolved

```text
conflicting witness = abstain
resolution          = pending | unresolved
adjudication        = abstain
PR #45              = not invoked
terminal outcome    = abstain
```

### Resolved with later revocation abstention

```text
adjudication                              = execute
canonical current revocation-checkpoint witness = execute
current conflict-adjudicator revocation  = abstain
terminal outcome                         = abstain
```

No later result rewrites the earlier witness conflict or adjudication execution.

## Structural failures

The boundary fails structurally for predecessor substitution, content-order drift, registry or policy drift, observation-population drift, witness identity-revision substitution, fork-evidence mismatch, dissent mismatch, authority identity or role mismatch, alternate selected-head resolution, invalid chronology, run-identity mismatch, stored-artifact drift, or noncanonical serialization.

Pending and unresolved statuses are governed abstentions rather than structural failures.

## Consequences

### Positive

- disagreement remains immutable and separately inspectable;
- operational resolution becomes an explicit authority claim;
- the original witness abstention is never rewritten;
- a resolved decision may continue only through the canonical `1.23.0` population;
- pending and unresolved authority states fail closed;
- the existing provider-neutral adjudication grammar is reused.

### Costs

- the authority chain gains another compact successor and outer lifecycle;
- real-chain tests must preserve and exercise the complete PR #30 through PR #45 graph;
- chronology must distinguish conflict observation, witness evaluation, adjudication evaluation, canonical witness reevaluation, delegated completion, and outer completion.

## Trust boundary

This layer does not establish legal or real-world identity, cryptographic authorship, signatures, private-key possession, trusted external time, witness or adjudicator independence, competence, honesty, or correctness, checkpoint or ledger completeness, absence of alternate histories, global uniqueness, public availability, correctness of the selected head, majority support, quorum, consensus, confidence, reputation, analytical accuracy, deployment, or an aggregate CTRT score.

## Deferred work

The next bounded successor may attest a credential for the exact new adjudicator identity revision and `witness_conflict_adjudicator` role.

Such a layer must preserve the complete `1.24.0` conflict, original witness abstention, fork evidence, dissent, rationale, selected head, adjudication record, exact `1.23.0` predecessor, exact `1.22.0` checkpoint report and head, and every inherited artifact unchanged.
