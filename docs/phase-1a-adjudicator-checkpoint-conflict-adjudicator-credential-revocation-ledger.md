# Phase 1A: Checkpoint-conflict adjudicator credential revocation ledger

## Purpose

This layer adds append-only, time-relative status history to the issuer-bound credential used by the adjudicator who may resolve an adjudicator-checkpoint witness conflict.

It answers one bounded question:

> What was the effective operational status of the exact credential at the declared evaluation time, according to the exact frozen event ledger?

It does not decide whether the adjudicator was correct. It does not alter the original checkpoint-witness abstention, fork evidence, dissent, selected checkpoint head, rationale, credential, or adjudication record.

## Fixed synthetic graph

### Credential

```text
adjudicator.synthetic.adjudicator-checkpoint-fork
synthetic-adjudicator-checkpoint-conflict-adjudicator@0.1.0
witness_conflict_adjudicator
```

### Revocation policy

```text
policy.synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-revocation@0.1.0
```

The accepted policy requires:

- exact attestation issuer authority;
- monotonic effective time;
- linear supersession;
- explicit abstention for `suspended` and `revoked` status.

### Event

```text
event.synthetic.adjudicator-checkpoint-fork.suspension.v0.1.0
```

The event is recorded during 2026 but becomes effective at:

```text
2027-01-01T00:00:00Z
```

Before that boundary, the exact event remains visible but does not alter the credential's effective status. At and after the boundary, the effective status becomes `suspended` and the run abstains before downstream work.

### Ledger

```text
ledger.synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-revocations@0.1.0
```

The frozen ledger binds the exact:

- `1.5.0` credential-bound corpus;
- credential issuer registry revision;
- revocation policy revision;
- ordered event references.

## Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-bound@1.5.0
sha256:8f058e8d82fa3b44bdd727cb33fd580abe3c21273a44a95db4390c3ad18ff890
```

Successor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-bound@1.6.0
sha256:d8c50b7a6ef0250df9bd2b2cc4830aadb45bdf4b8c7ec6696b8e316124822123
```

The `1.6.0` artifact is a compact successor manifest. It does not copy the complete predecessor graph. It binds the immutable `1.5.0` corpus, the revocation policy, the ledger, and the exact content order.

Publication is manifest-last:

1. policy;
2. events;
3. ledger;
4. `1.6.0` manifest.

## As-of evaluation

For each credential, the decision preserves:

- the immutable credential reference;
- base credential status;
- effective as-of status;
- every applied event ID;
- the event currently controlling effective status;
- explicit abstention reasons.

Example before suspension:

```text
base_status = active
effective_status = active
applied_event_ids = []
outcome = execute
```

Example at the suspension boundary:

```text
base_status = active
effective_status = suspended
applied_event_ids = [event.synthetic.adjudicator-checkpoint-fork.suspension.v0.1.0]
outcome = abstain
```

The original credential remains `active` in both cases because it records the issuance claim. The ledger decision records later operational history.

## Execution lifecycle

`RevocationGatedAdjudicatorCheckpointConflictExperimentRunner` performs:

1. exact `1.6.0` plan, manifest, policy, ledger, content-order, run-ID, and timestamp preflight;
2. storage-backed loading of the compact manifest, policy, ledger, events, credential, issuer, and adjudication evidence;
3. structural validation of issuer authority, credential binding, event order, and linear supersession;
4. as-of status evaluation;
5. run-specific revocation-decision persistence and reread verification;
6. terminal revocation abstention or explicit scoped delegation;
7. final-manifest persistence;
8. complete storage-backed reread verification.

Run-specific decision artifact:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-decision
```

Terminal artifacts:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-abstention
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-completion
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-terminal-abstention
```

## Explicit nested-plan delegation

The outer runner receives a frozen plan bound to `1.6.0` because the revocation decision depends on the new policy and ledger.

When the effective status permits execution, it derives a nested plan bound to the exact immutable `1.5.0` predecessor and invokes the unchanged credentialed checkpoint-conflict runner.

```text
outer plan:
  corpus = 1.6.0
  purpose = revocation evaluation and finalization

nested plan:
  corpus = 1.5.0
  purpose = unchanged ADR-0030 credential and downstream execution
```

The experiment identity, version, content IDs, content order, candidates, analyzers, and execution windows remain identical. The transition is explicit in code and covered by lifecycle tests.

## Terminal behavior

### Revocation outcome: `execute`

The outer runner delegates the unchanged PR #27 lifecycle and mirrors its independently preserved outcomes:

- credential decision;
- original adjudicator-checkpoint witness abstention;
- authorized conflict-adjudication decision;
- earlier adjudicator and reviewer governance outcomes;
- final analysis outcome.

### Revocation outcome: `abstain`

The outer runner persists the revocation decision and a terminal abstention manifest.

It must not create or report:

- a PR #27 credential decision;
- checkpoint-witness evaluation;
- conflict adjudication;
- earlier adjudicator governance;
- reviewer governance;
- analyzer execution.

Every downstream outcome field remains null.

## Structural failure versus governed abstention

Structural failures include exact-reference, issuer, credential, policy, ledger, event-population, order, supersession, persistence, and reread defects.

Governed abstention is reserved for a structurally valid graph whose as-of effective status is policy-ineligible.

This distinction prevents malformed evidence from being represented as an ordinary negative decision.

## Schemas

This slice reuses the established generic schemas for:

- adjudicator credential revocation policy;
- adjudicator credential revocation event;
- adjudicator credential revocation ledger;
- adjudicator credential revocation decision.

It adds context-specific schemas for:

- the compact `1.6.0` revocation-bound corpus;
- the revocation-gated checkpoint-conflict final manifest.

The final schema requires every downstream field to be null when revocation abstains.

## Privacy boundary

The artifacts contain only stable pseudonymous IDs, immutable revisions, roles, artifact references, statuses, timestamps, reason text, and declared governance outcomes.

They contain no private identity data, signatures, keys, certificate chains, reputation scores, vote counts, quorum, consensus percentages, model output, dataset, or aggregate CTRT score.

## Trust boundary

`verified` means that the declared immutable graph and execution lifecycle were reconstructed and validated under the accepted contracts.

It does not establish real-world identity, issuer trustworthiness, cryptographic authorship, trusted time, complete event disclosure, adjudicator correctness, witness truthfulness, global checkpoint uniqueness, or analytical accuracy.

See [ADR-0031](adr/0031-checkpoint-conflict-adjudicator-credentials-require-append-only-revocation-history.md).
