# Phase 1A: Checkpoint-conflict adjudicator revocation checkpoint witness conflict adjudication

## Purpose

This implementation adds authorized conflict adjudication over the exact named-witness evidence introduced by PR #30.

The layer answers one bounded question:

> Did the exact accepted adjudicator and policy resolve the preserved witness conflict by selecting the independently verified checkpoint head?

It does not replace the witness result. It preserves the original witness decision, every observation, every conflicting fork, and every dissent while producing a separate adjudication outcome.

## Position in the governance chain

```text
1.7.0 checkpoint-bound corpus
    |
    v
1.8.0 named-witness-bound corpus
    |
    v
1.9.0 witness-conflict-adjudication-bound corpus
```

The operational flow is:

```text
1.9.0 plan
    -> load exact adjudication graph
    -> revalidate exact PR #30 witness receipt
    -> validate and persist adjudication decision
    -> abstain OR execute exact lower checkpoint lifecycle
    -> persist and reverify final
```

The scope transition is explicit:

```text
1.9.0 plan -> adjudication validation and outer finalization
1.8.0 receipt -> immutable witness result and evidence
1.7.0 plan -> lower checkpoint lifecycle after authorization
```

## Fixed canonical artifacts

### `1.8.0` predecessor

```text
artifact_id:
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-bound

artifact_version:
1.8.0

artifact_hash:
sha256:3d48f367ce1b1101dd7044bb846da42786e3eb9af55c6de7d9bc9e5545f2479a
```

The predecessor contains the three immutable matching witness attestations introduced by PR #30.

### Conflict-adjudicator registry

```text
registry_id:
registry.synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-witness-conflict-adjudicators

registry_version:
0.1.0

artifact_hash:
sha256:44e1bad4db6061c3dc37b8b33fb673958e51ba3c84388ea2a9ec32bf54cd1fde
```

The fixed registry contains one stable pseudonymous record:

```text
adjudicator_id:
adjudicator.synthetic.checkpoint-conflict-revocation-checkpoint-witness-conflict

identity_revision:
synthetic-checkpoint-conflict-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

role:
witness_conflict_adjudicator
```

The registry declares an identity revision and role. It does not establish legal identity, competence, independence, or credential validity.

### Adjudication policy

```text
policy_id:
policy.synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-witness-conflict-adjudication

policy_version:
0.1.0

artifact_hash:
sha256:19a81edbcc0eff61c0f197edf4fd21bfa83aae332329f51957135e8462294400
```

The policy requires:

- the exact accepted adjudicator registry;
- the exact ordered adjudicator population;
- abstention while a case is pending;
- abstention when a case remains unresolved;
- selection of the declared independently verified checkpoint head for resolution;
- no vote aggregation.

### Canonical adjudication record

```text
artifact_id:
witness-conflict-adjudication:adjudication.synthetic.checkpoint-conflict-revocation-checkpoint-witnesses.v0.1.0

artifact_hash:
sha256:70eb3e037fe9bd308a44890c1caa2fbcf8d0b39ab407357b885d68eacd9f2fab

status:
not_required
```

The canonical witness graph contains no conflict. The record therefore preserves:

```text
adjudicator_id = null
selected_head_ref = null
fork_evidence = []
preserved_dissent = []
```

It does not manufacture an adjudication decision when all required witnesses already match.

### `1.9.0` successor

```text
artifact_id:
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound

artifact_version:
1.9.0

artifact_hash:
sha256:080d41cf305eaf28c120fb20359c4d01392409351af2bae350c8400cdb9b5d43
```

The compact successor binds:

- the exact `1.8.0` predecessor;
- the exact witness registry, policy, and ordered attestations already preserved by that predecessor;
- the exact conflict-adjudicator registry;
- the exact adjudication policy;
- the exact adjudication record;
- the unchanged content IDs and order.

## Publication order

The fixed graph is published append-only and manifest-last:

1. conflict-adjudicator registry;
2. adjudication policy;
3. adjudication record;
4. `1.9.0` manifest.

The manifest is not available until every referenced authority and decision artifact has been stored and hash-verified.

No prior artifact is modified.

## Contract modules

### Concise context contract

```text
src/ctrt/checkpoint_conflict_witness_adjudication.py
```

Public contracts:

- `CheckpointConflictWitnessAdjudicationCorpusSnapshot`
- `ConflictAdjudicationError`
- `ConflictDecisionReport`
- `StoredConflictAdjudicationEvidence`
- `load_checkpoint_conflict_witness_adjudication_evidence`
- `persist_checkpoint_conflict_witness_adjudication_corpus`
- `validate_checkpoint_conflict_witness_adjudication`

The module adapts the established adjudicator-checkpoint witness-conflict grammar. It does not define a parallel state machine.

### Compatibility façade

```text
src/ctrt/adjudicator_checkpoint_conflict_credential_revocation_checkpoint_witness_conflict_adjudication.py
```

This long context-specific path is retained only as a compatibility façade. All implementation logic lives in the concise context module.

### Outer runner

```text
src/ctrt/adjudicated_checkpoint_conflict_revocation_witness_runner.py
```

Public runner contracts:

- `CheckpointExecutor`
- `CheckpointConflictWitnessAdjudicationRunnerStage`
- `CheckpointConflictWitnessAdjudicationRunnerStatus`
- `CheckpointConflictWitnessAdjudicationExperimentError`
- `CheckpointConflictWitnessAdjudicationFinalManifest`
- `VerifiedCheckpointConflictWitnessAdjudicationReceipt`
- `AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner`

## Adjudication states

### `not_required`

Required evidence:

```text
witness_outcome = execute
fork_evidence = empty
adjudication_status = not_required
```

Result:

```text
adjudication_outcome = execute
```

The outer runner reuses the exact lower checkpoint receipt already preserved inside the verified PR #30 witness receipt. It does not rerun the witness layer.

### `pending`

Required evidence:

```text
witness_outcome = abstain
fork_evidence = non-empty
adjudication_status = pending
selected_head_ref = null
```

Result:

```text
adjudication_outcome = abstain
checkpoint_receipt = null
terminal_outcome = abstain
```

No checkpoint executor is called.

### `unresolved`

Required evidence:

```text
witness_outcome = abstain
fork_evidence = non-empty
adjudicator identity and role = exact accepted registry record
adjudication_status = unresolved
selected_head_ref = null
```

Result:

```text
adjudication_outcome = abstain
checkpoint_receipt = null
terminal_outcome = abstain
```

Preserved dissent remains part of the decision report and stored adjudication record.

### `resolved`

Required evidence:

```text
witness_outcome = abstain
fork_evidence = exact conflicting observations
adjudicator identity and role = exact accepted registry record
adjudication_status = resolved
selected_head_ref = independently verified checkpoint head
preserved_dissent = retained
```

Result:

```text
adjudication_outcome = execute
```

Because PR #30 correctly stopped before checkpoint execution, a resolved case supplies an explicit `CheckpointExecutor`.

The executor receives:

```text
plan.corpus_ref = exact immutable 1.7.0 checkpoint predecessor
content_ids = unchanged ordered content population
experiment identity and version = unchanged
experiment_run_id = unchanged
```

The executor must return a verified lower checkpoint receipt with the same experiment scope.

## Original witness outcome is never rewritten

A resolved case intentionally produces two different valid outcomes:

```text
checkpoint_witness_outcome = abstain
adjudication_outcome = execute
```

These values answer different questions:

- witness outcome: did every required witness report the same checkpoint head?
- adjudication outcome: did accepted authority resolve the preserved conflict under policy?

The final and receipt preserve both values.

A later lower-layer abstention may also coexist:

```text
checkpoint_witness_outcome = abstain
adjudication_outcome = execute
revocation_outcome = abstain
terminal_outcome = abstain
```

No layer rewrites another layer's evidence or conclusion.

## Outer execution lifecycle

`AdjudicatedCheckpointConflictRevocationWitnessExperimentRunner` performs:

1. verify frozen `1.9.0` plan, content order, run ID, authority references, and chronology;
2. verify that the supplied PR #30 receipt binds the exact `1.8.0` predecessor and experiment scope;
3. load and hash-verify the complete stored adjudication graph;
4. revalidate the exact named-witness population and decision;
5. reread the stored witness decision and witness final;
6. validate adjudicator registry, policy, state, fork evidence, dissent, selected head, and chronology;
7. persist and reread the run-specific adjudication decision;
8. terminate on adjudication abstention, reuse an existing checkpoint receipt, or invoke the explicit lower checkpoint executor;
9. persist the final manifest;
10. reread the final, adjudication corpus, authority, decision, witness final, and delegated checkpoint final.

## Run-specific artifacts

Adjudication decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudication-decision
```

Terminal abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudication-abstention
```

Successful lower execution:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudication-completion
```

Authorized adjudication followed by later lower-layer abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudication-terminal-abstention
```

## Final manifest

The final schema is:

```text
schemas/adjudicated-checkpoint-conflict-revocation-witness-final.schema.json
```

It requires separate fields for:

- original checkpoint-witness outcome;
- conflict-resolution status;
- adjudication outcome;
- checkpoint-conflict adjudicator revocation and credential outcomes;
- earlier adjudicator and reviewer governance outcomes;
- terminal review outcome;
- adjudication corpus and authority references;
- preserved witness final;
- run-specific adjudication decision;
- optional lower checkpoint final;
- verified checks and completion time.

When adjudication abstains, every lower outcome and checkpoint-final reference must remain null.

When adjudication executes, a lower checkpoint final and revocation outcome must exist.

## Structural failure

The runner fails structurally for:

- a plan not frozen on the exact `1.9.0` corpus;
- content-order drift;
- run, experiment, or version mismatch;
- a PR #30 receipt bound to a different `1.8.0` graph;
- altered witness attestation population or order;
- altered stored witness decision or final;
- substituted adjudicator registry, policy, or adjudication record;
- an adjudication bound to a different witness predecessor;
- fork evidence that differs from the witness decision;
- unknown adjudicator ID;
- identity-revision or role drift;
- a resolved decision selecting a non-declared head;
- impossible timestamps;
- missing or altered stored artifacts;
- append, serialization, or reread failure;
- a delegated checkpoint receipt with different experiment scope.

Structural failure does not produce an adjudication outcome. It reports the exact runner stage.

## Governed abstention

Governed abstention occurs for:

- `pending` adjudication;
- `unresolved` adjudication;
- later revocation, credential, witness, adjudication, reviewer, or analysis abstention after an authorized `execute` decision.

A current adjudication abstention prevents the lower checkpoint executor from being invoked.

## Test coverage

Contract tests prove:

- fixed registry, policy, adjudication, and `1.9.0` schemas;
- deterministic canonical manifest hash;
- exact `1.8.0` predecessor binding;
- canonical `not_required` behavior;
- resolved conflict with original witness abstention, fork evidence, and dissent preserved;
- pending abstention;
- unresolved abstention with dissent preserved;
- manifest-last persistence and deterministic reconstruction;
- rejection of an unsupported confidence field.

Lifecycle tests use real stored PR #30 receipts to prove:

1. `not_required` preserves the witness `execute` decision and reuses the existing lower checkpoint receipt;
2. `pending` preserves witness abstention and never calls the checkpoint executor;
3. `unresolved` preserves witness abstention and terminates without a checkpoint receipt;
4. `resolved` preserves witness abstention, invokes the explicit lower checkpoint executor exactly once, and returns the independently verified lower outcome.

The lifecycle tests also exposed and retained an important integrity rule: every dynamic adjudication must bind the exact dynamically conflicted `1.8.0` predecessor, not the canonical all-match predecessor.

## Privacy and trust boundary

Stored artifacts contain:

- stable pseudonymous IDs;
- immutable identity revisions and roles;
- artifact references and hashes;
- preserved fork evidence and dissent;
- lifecycle state;
- rationale;
- timestamps;
- declared governance outcomes.

Verification does not establish:

- legal or real-world adjudicator identity;
- adjudicator credential validity or non-revocation;
- adjudicator competence, independence, honesty, or correctness;
- witness identity, independence, competence, or truthfulness;
- cryptographic authorship;
- trusted external time;
- public availability or global checkpoint uniqueness;
- which witness was correct;
- majority support, quorum, consensus, confidence, or reputation;
- complete real-world event disclosure;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred successor

The next bounded layer should bind the exact conflict adjudicator's pseudonymous identity revision and `witness_conflict_adjudicator` role to immutable issuer credentials, validity windows, and status.

That credential layer must not modify:

- the original PR #30 witness outcome;
- any matching or conflicting attestation;
- fork evidence;
- preserved dissent;
- adjudication rationale;
- selected checkpoint head;
- the `1.9.0` adjudication record.
