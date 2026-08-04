# Phase 1A: Checkpoint-fork adjudicator credential revocation ledger

## Purpose

This slice adds append-only status history for the exact credential introduced by `1.15.0`.

It answers one bounded operational question:

> According to the exact accepted policy and exact frozen issuer-authored ledger, what was the effective status of the exact credential at the declared evaluation time?

It does not alter the credential, the checkpoint-witness disagreement, the adjudication, the selected checkpoint head, fork evidence, dissent, or any inherited artifact.

## Immutable predecessor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-bound@1.15.0
sha256:feb13271bed910f480e5ae0af730e4b68ff8636a7172a3f6b4a0c3bd0d51b542
```

The predecessor binds the exact credential:

```text
artifact_id = adjudicator-credential:credential.synthetic.witness-conflict-adjudicator-checkpoint-fork.v0.1.0
hash = sha256:e992110c0dadc3990406485d6b666977f68d74b78417b477ea255875fc3a7c0d
adjudicator_id = adjudicator.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
identity_revision = synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
status = active
```

The credential remains byte-for-byte immutable.

## Fixed revocation graph

### Policy

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation@0.1.0
sha256:62e4d678b71d9d8ee5a106f5207aa4f12d5551d9723b8a8e20dd03e858d695fb
```

Policy requirements:

```text
accepted lifecycle
permitted effects = active, suspended, revoked
exact attestation issuer required
monotonic effective time required
linear supersession required
abstain on suspended or revoked
```

### Future-effective event

```text
adjudicator-credential-revocation-event:event.synthetic.witness-conflict-adjudicator-checkpoint-fork.suspension.v0.1.0
sha256:48e7bb0fc45f50c25ba8eb0782f27ce421c01ae7a1d2ac64bdd65e08cb8f1e27
```

```text
recorded_at  = 2026-08-03T19:57:36Z
effective_at = 2027-01-01T00:00:00Z
effect       = suspended
supersedes   = null
```

The event is bound to the exact credential reference, adjudicator ID, issuer ID, and issuer revision.

### Frozen ledger

```text
ledger.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0
sha256:ba7522216035bc532100cd9cf3727c4a8d83cd27f0e4c51ee050d161abe3d3c3
```

The ledger binds:

- exact `1.15.0` credential corpus;
- exact issuer registry;
- exact revocation policy;
- exact ordered event population;
- frozen publication time.

### Successor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.16.0
sha256:3336b30372595557d45d50ee56707cfc00a2420e53209d097a0d9e3d78a9648f
```

The compact successor contains only:

- its own identity and version;
- frozen status;
- unchanged ordered content IDs;
- exact predecessor reference;
- exact policy reference;
- exact ledger reference;
- publication timestamp.

It does not duplicate inherited evidence.

## Contract module

```text
src/ctrt/checkpoint_witness_conflict_adjudicator_credential_revocation_ledger.py
```

Primary type:

```text
RevocationBoundCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
```

Public operations:

```text
load_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence
validate_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger
persist_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus
```

The context adapter delegates event, policy, ledger, status derivation, authority binding, and decision semantics to the established provider-neutral adjudicator credential revocation contract.

It adds only:

- exact `1.15.0` predecessor binding;
- compact `1.16.0` manifest parsing;
- exact unchanged content ordering;
- stricter historical-recording chronology;
- context-specific manifest-last storage entry points.

## Historical-recording boundary

The adapter requires:

```text
policy.created_at
  <= each event.recorded_at
  <= ledger.created_at
  <= 1.16.0.created_at
  <= revocation_evaluated_at
```

This prevents an event recorded after ledger freeze from being imported into an earlier historical decision.

`effective_at` is evaluated separately. A recorded future-effective event remains visible while the effective status stays active.

## Manifest-last persistence

Publication order is:

1. accepted revocation policy;
2. immutable events in exact ledger order;
3. frozen ledger;
4. compact `1.16.0` manifest;
5. exact-hash reread of the complete graph.

The predecessor is loaded and verified but never rewritten.

## As-of decision

Before `2027-01-01T00:00:00Z`:

```text
base_status        = active
effective_status   = active
applied_event_ids  = []
revocation_outcome = execute
```

At and after the effective boundary:

```text
base_status        = active
effective_status   = suspended
applied_event_ids  = [event.synthetic.witness-conflict-adjudicator-checkpoint-fork.suspension.v0.1.0]
revocation_outcome = abstain
```

The credential's own `status`, `revoked_at`, and `revocation_reason` remain unchanged.

## Revocation-gated runner

```text
src/ctrt/revocation_gated_checkpoint_witness_conflict_adjudication_runner.py
```

Primary runner:

```text
RevocationGatedCheckpointWitnessConflictAdjudicationExperimentRunner
```

Stages:

```text
preflight
evidence-loading
revocation-validation
decision-persistence
credential-execution
final-persistence
verification
```

The runner performs:

1. exact frozen-plan, successor, predecessor, policy, ledger, run identity, and chronology preflight;
2. storage-backed loading of the complete `1.16.0` graph;
3. storage-backed loading of the exact `1.15.0` credential authority graph;
4. deterministic as-of revocation validation;
5. run-specific revocation-decision persistence and reread verification;
6. terminal abstention when current revocation outcome is `abstain`;
7. exact `1.16.0 -> 1.15.0` plan narrowing only after revocation `execute`;
8. invocation of PR #37 unchanged;
9. outer final persistence;
10. exact-hash reread of successor, predecessor, policy, ledger, events, credential authority, adjudication, decision, and optional PR #37 final.

## Explicit execution scopes

```text
1.16.0 plan -> current revocation validation and outer finalization
1.15.0 plan -> unchanged PR #37 current credential lifecycle
1.14.0 plan -> unchanged PR #36 conflict adjudication lifecycle
1.13.0 plan -> unchanged PR #35 checkpoint-witness lifecycle
1.12.0 plan -> unchanged PR #34 checkpoint lifecycle
1.11.0 plan -> unchanged inherited credential-revocation lifecycle
1.10.0 plan -> unchanged inherited credential lifecycle
1.9.0 plan  -> unchanged inherited adjudication lifecycle
```

Only the corpus reference and identical ordered content IDs are narrowed. Experiment identity, version, parameters, run ID, and inherited evidence remain unchanged.

## Run-specific artifacts

Current revocation decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-decision
```

Terminal current revocation abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-abstention
```

Successful delegated completion:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-completion
```

Current revocation execution followed by a later independent abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-terminal-abstention
```

## Outcome matrix

### Current status active

```text
current revocation                   = execute
current credential                   = execute
current checkpoint witness           = abstain
current resolution                   = resolved
current adjudication                 = execute
predecessor witness                  = execute
inherited revocation                 = execute
inherited credential                 = execute
inherited checkpoint witness         = execute
inherited resolution                 = not_required
inherited adjudication               = execute
terminal                             = execute
```

### Current status suspended

```text
current revocation                   = abstain
all current credential/downstream    = null
terminal                             = abstain
```

The current revocation decision is stored. PR #37 is not invoked.

### Current status active; inherited status later suspended

```text
current revocation                   = execute
current credential                   = execute
current checkpoint witness           = abstain
current resolution                   = resolved
current adjudication                 = execute
predecessor witness                  = execute
inherited revocation                 = abstain
remaining inherited outcomes         = null
terminal                             = abstain
```

Both revocation outcomes remain separately inspectable.

## Structural failures

The boundary fails closed for:

- predecessor identity or hash drift;
- content-order drift;
- policy or ledger reference drift;
- credential, adjudicator, issuer, or issuer-revision substitution;
- event population or ordering drift;
- duplicate or non-linear event history;
- non-monotonic effective time;
- event recording after ledger freeze;
- evaluation before successor publication;
- revocation evaluation after credential evaluation;
- run-identity mismatch in inherited receipts;
- stored artifact or canonical serialization drift.

These failures do not become abstentions because they indicate malformed or substituted evidence rather than a governed negative outcome.

## Validation coverage

Contract tests prove:

- exact canonical hashes;
- closed policy, event, ledger, and successor schemas;
- exact `1.15.0` predecessor binding;
- active as-of status before the future event;
- suspended status at the effective boundary;
- immutable credential base status;
- explicit applied event IDs;
- issuer and content-order drift failure;
- manifest-last deterministic reconstruction;
- rejection of unsupported confidence fields.

Chronology tests prove:

- an event recorded after ledger freeze is rejected;
- an evaluation before `1.16.0` publication is rejected.

Stored lifecycle tests use the real PR #30 through PR #37 evidence chain and prove:

1. current active status delegates exact PR #37;
2. effective current suspension creates no PR #37 credential decision;
3. current revocation execution remains distinct from inherited suspension;
4. invalid outer chronology fails during preflight;
5. all inherited receipts share the exact outer experiment run ID;
6. execution and abstention paths satisfy one closed final schema.

## Trust boundary

This layer proves only the result derived from the exact declared policy, exact frozen ledger, exact event population, and exact evaluation time.

It does not prove:

- that the ledger contains every real-world event;
- that no alternate ledger exists;
- global uniqueness, public availability, or external publication;
- legal identity or authority;
- cryptographic authorship or key possession;
- trusted external time;
- honesty, independence, competence, or correctness of any issuer, adjudicator, or witness;
- adjudication correctness or external truth of the selected checkpoint;
- majority support, quorum, consensus, confidence, reputation, or trust;
- analyzer, extraction, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

## Bounded successor

The next layer should checkpoint the exact frozen `1.16.0` ledger. It must preserve the `1.16.0` decision, `1.15.0` credential graph, `1.14.0` disagreement and adjudication evidence, fork evidence, dissent, selected head, and every inherited artifact unchanged.
