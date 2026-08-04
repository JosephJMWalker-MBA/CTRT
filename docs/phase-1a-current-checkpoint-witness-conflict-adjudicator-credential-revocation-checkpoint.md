# Phase 1A: Current conflict-adjudicator revocation checkpoint

## Purpose

This bounded layer adds immutable checkpoint provenance above the exact `1.21.0` append-only revocation ledger introduced by PR #43.

It asks only:

> Which exact frozen `1.21.0` revocation-ledger head did governed execution rely upon before evaluating the current conflict-adjudicator credential status?

It does not change credential issuance, append-only revocation status, the preserved checkpoint-witness conflict, the original witness abstention, fork evidence, dissent, selected head, rationale, adjudication, or any inherited outcome.

## Exact predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.21.0
sha256:b6a3065ffb517dda9fb498404021371f7d5b320af144842c3f7d2453c99ace1e
```

The predecessor binds the exact frozen revocation ledger:

```text
ledger.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0
sha256:38345155c8550fa4d5bdb16b786039c5aac6904071862ec09a770e09f25d7960
```

The ledger contains the exact immutable future-effective suspension event:

```text
adjudicator-credential-revocation-event:event.synthetic.current-checkpoint-witness-conflict-adjudicator.suspension.v0.1.0
sha256:86fe5a56df406791385c432080c36cdc84620686a359d7edfd155ed41d3ec720
```

## Fixed checkpoint graph

### Policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:61a61e18a82575ed5163f2ecc3cc0123f342583e3bbc60fa364d27082e3dadec
```

The accepted policy requires:

- exact event order;
- prefix-only extension;
- contiguous checkpoint sequence numbers;
- monotonic checkpoint publication time.

### Genesis checkpoint

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
```

```text
sequence_number = 0
predecessor_checkpoint_ref = null
event_count = 1
event_population_hash = sha256:620fed6d90310f7cbc73a704cd73350a15125763d59881648dca44305f9eeb8f
published_at = 2026-08-03T19:58:18Z
```

### Frozen log

```text
log.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:5f9dde79fcffcafd0372229262b5e6cd9fdc148ff63750134f6467d77497b48b
```

The log contains the exact genesis checkpoint and declares it as the head.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.22.0
sha256:3ef12c528781ddec9976323b8a23670f3592839ce2145afed60cda39170c0304
```

The successor is compact. It contains only exact references, the unchanged ordered content IDs, frozen status, and its publication timestamp.

## Canonical chronology

```text
2026-08-03T19:58:15Z  1.21.0 revocation successor published
2026-08-03T19:58:16Z  checkpoint policy created
2026-08-03T19:58:18Z  genesis checkpoint published
2026-08-03T19:58:20Z  checkpoint log frozen
2026-08-03T19:58:21Z  1.22.0 checkpoint successor published
2026-08-03T19:58:22Z  checkpoint verified
2026-08-03T19:58:23Z  current conflict-adjudicator revocation evaluated
```

The outer boundary requires:

```text
1.22.0.created_at
  <= current_checkpoint_verified_at
  <= current_conflict_adjudicator_revocation_evaluated_at
  <= PR #43 completion
  <= outer completion
```

## Manifest-last publication

Publication order is:

1. accepted checkpoint policy;
2. immutable checkpoints in exact sequence order;
3. frozen checkpoint log;
4. compact `1.22.0` successor manifest;
5. exact-hash reread of the successor, exact `1.21.0` predecessor, policy, log, checkpoint head, frozen ledger, and ordered event population.

The exact `1.21.0` predecessor is verified but never rewritten.

## Contract adapter

```text
src/ctrt/current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints.py
```

Primary type:

```text
CheckpointBoundCurrentCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
```

Public operations:

```text
load_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence
validate_current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints
persist_current_checkpoint_witness_conflict_adjudicator_revocation_checkpoint_corpus
```

The adapter delegates policy, sequence, ancestry, ordered-prefix, event-population, log-head, verification-report, and storage behavior to the provider-neutral adjudicator-credential revocation checkpoint grammar. It adds only exact `1.21.0` binding, compact `1.22.0` parsing, context chronology, and manifest-last persistence.

## Checkpoint-gated runner

```text
src/ctrt/checkpoint_gated_current_checkpoint_witness_conflict_runner.py
```

`CheckpointGatedCurrentCheckpointWitnessConflictExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, policy, log, head, content-order, run-identity, and chronology preflight;
2. storage-backed loading of the complete checkpoint graph;
3. sequence, ancestry, prefix, publication, ledger, and event-population validation;
4. independent run-specific checkpoint-verification persistence;
5. exact plan narrowing from `1.22.0` to `1.21.0`;
6. unchanged PR #43 execution under the same experiment run ID;
7. outer final persistence;
8. storage-backed reread of the final, successor, predecessor, policy, log, checkpoints, verification report, and exact PR #43 final.

## Explicit scopes

```text
1.22.0 plan -> current conflict-adjudicator revocation checkpoint and outer finalization
1.21.0 plan -> unchanged PR #43 revocation lifecycle
1.20.0 plan -> unchanged conflict-adjudicator credential lifecycle
1.19.0 plan -> unchanged conflict and adjudication lifecycle
1.18.0 plan -> unchanged canonical current named-witness lifecycle
1.17.0 plan -> unchanged current checkpoint lifecycle
1.16.0 plan -> unchanged lower current credential-revocation lifecycle
```

Only the corpus reference and identical ordered content IDs narrow between layers.

## Independent outcomes

The final record preserves separately:

```text
current_conflict_adjudicator_revocation_outcome
current_conflict_adjudicator_credential_outcome
conflicting_witness_outcome
current_resolution_status
current_conflict_adjudication_outcome
resolved_current_witness_outcome
current_revocation_outcome
current_credential_outcome
lower_checkpoint_witness_outcome
lower_resolution_status
lower_conflict_adjudication_outcome
lower_predecessor_witness_outcome
inherited_revocation_outcome
inherited_credential_outcome
inherited_checkpoint_witness_outcome
inherited_resolution_status
inherited_adjudication_outcome
terminal_outcome
```

The checkpoint result is also preserved independently through the checkpoint verification report and exact head reference.

No later result rewrites an earlier evidentiary or authority claim.

## Outcome matrix

### Checkpoint verified; PR #43 executes

```text
checkpoint status                         = verified
current conflict-adjudicator revocation   = execute
current conflict-adjudicator credential   = execute
conflicting witness                       = abstain
current resolution                        = resolved
current conflict adjudication             = execute
terminal outcome                          = execute
```

### Checkpoint verified; PR #43 revocation abstains

```text
checkpoint status                         = verified
current conflict-adjudicator revocation   = abstain
all PR #42 outcomes                       = null
terminal outcome                          = abstain
```

The checkpoint report and exact head remain independently visible.

### Checkpoint structurally invalid

```text
checkpoint report                         = absent
PR #43                                    = not invoked
all revocation and downstream outcomes    = absent
result                                    = structural failure
```

## Run-specific artifacts

Checkpoint verification report:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-verification
```

Successful completion:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-completion
```

Verified checkpoint followed by governed abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-terminal-abstention
```

## Test coverage

Contract and storage tests prove:

- exact policy, checkpoint, log, predecessor, and successor hashes;
- closed policy, checkpoint, log, successor, and final schemas;
- exact `1.21.0` predecessor and unchanged content-order binding;
- exact complete one-event population coverage;
- omitted-event rejection;
- checkpoint verification no later than revocation evaluation;
- exact manifest-last reconstruction;
- unsupported-confidence rejection;
- public contract and runner API stability.

Stored lifecycle tests use a real PR #43 receipt from the complete authority chain and prove:

1. a verified checkpoint delegates the exact `1.21.0` plan under the same experiment run ID;
2. all PR #43 outcomes remain unchanged and separately preserved;
3. a verified checkpoint remains visible when PR #43 later abstains on effective suspension;
4. invalid outer chronology fails before delegation;
5. execution and terminal abstention satisfy one closed final schema.

## Structural failures

The boundary fails closed for predecessor, content-order, policy, log, checkpoint-head, sequence, ancestry, event omission, event substitution, event reordering, non-prefix extension, publication chronology, verification chronology, run identity, stored artifact, or canonical serialization drift.

A valid downstream revocation abstention remains a governed abstention rather than a checkpoint failure.

## Trust boundary

Checkpoint verification does not establish:

- ledger completeness beyond its exact frozen event population;
- absence of undisclosed events or alternate checkpoint chains;
- global checkpoint uniqueness or public availability;
- legal or real-world adjudicator, issuer, or witness identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- issuer, adjudicator, or witness independence, competence, honesty, or correctness;
- adjudication correctness or selected-checkpoint truth;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, analyzer, model, dataset, or content accuracy;
- deployment or an aggregate CTRT score.

## Intentionally deferred

The next bounded layer may add immutable named-witness observations over the exact `1.22.0` checkpoint head.

It must preserve the checkpoint report, complete `1.21.0` revocation graph, `1.20.0` credential, `1.19.0` disagreement and adjudication evidence, fork evidence, dissent, selected head, rationale, and every inherited artifact unchanged.