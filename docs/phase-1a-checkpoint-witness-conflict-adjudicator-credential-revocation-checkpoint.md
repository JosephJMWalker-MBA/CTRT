# Phase 1A: Current adjudicator credential revocation checkpoint

## Purpose

This layer checkpoints the exact frozen `1.16.0` revocation ledger for the credential that authorizes the adjudicator resolving the current checkpoint-witness disagreement.

It answers one bounded question:

> Which exact immutable revocation-ledger head did the governed execution rely upon before evaluating current credential status?

It does not decide credential status, validate the credential, resolve the disagreement, or judge the truth of any content.

## Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.16.0
sha256:3336b30372595557d45d50ee56707cfc00a2420e53209d097a0d9e3d78a9648f
```

Successor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.17.0
sha256:e801447e9d897baa442effd11f2a1d059624e05d7286ad7ec2bc3761e328849d
```

The successor contains only exact references, unchanged content IDs, frozen status, and its publication timestamp.

## Fixed checkpoint graph

Checkpoint policy:

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:ce8fe8e454f9563a613eaeac66b528bf3e2800076e5f47cb0f2a91d11f9daf7f
```

Genesis checkpoint:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:245efb3279bc1b10c5ffafa337665a947a8dd86e9693590cccf09a6021d829a2
```

Frozen log:

```text
log.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:45e9330da82ddf1295a07cd0f763c1447a9cbfccc716b20f590d94113409aa24
```

The checkpoint covers this exact ordered event population:

```text
adjudicator-credential-revocation-event:event.synthetic.witness-conflict-adjudicator-checkpoint-fork.suspension.v0.1.0
sha256:48e7bb0fc45f50c25ba8eb0782f27ce421c01ae7a1d2ac64bdd65e08cb8f1e27
```

Population hash:

```text
sha256:f5a6ad7173450c58ef5d0695886eced35a79afbe55df0bf29b72a1807ad5aefc
```

## Canonical chronology

```text
2026-08-03T19:57:38Z  1.16.0 revocation successor published
2026-08-03T19:57:39Z  checkpoint policy created
2026-08-03T19:57:41Z  genesis checkpoint published
2026-08-03T19:57:43Z  checkpoint log frozen
2026-08-03T19:57:44Z  1.17.0 checkpoint successor published
2026-08-03T19:57:45Z  current checkpoint verified
2026-08-03T19:57:46Z  delegated current revocation evaluated
2026-08-03T19:57:47Z  current credential evaluated
2026-08-03T19:57:48Z  current checkpoint witnesses evaluated
2026-08-03T19:57:49Z  current disagreement adjudication evaluated
```

The run-specific downstream times move later than the canonical PR #38 example. No immutable predecessor timestamp, event, credential, decision, disagreement record, fork evidence, dissent, or selected head is modified.

## Checkpoint invariants

The generic checkpoint grammar enforces:

- accepted checkpoint policy;
- exact ordered event references;
- contiguous sequence numbers beginning at zero;
- no predecessor at genesis;
- exact immediate-predecessor references after genesis;
- prefix-only event-population extension;
- nondecreasing event counts;
- strictly increasing publication time;
- exact checkpoint canonical hashes;
- frozen-log head equality with the final checkpoint;
- exact ledger and event-population coverage.

The current adapter additionally requires:

```text
1.17.0.created_at
  <= current_checkpoint_verified_at
  <= current_revocation_evaluated_at
```

## Manifest-last publication

Storage order is:

1. accepted checkpoint policy;
2. immutable checkpoints in exact sequence order;
3. frozen checkpoint log;
4. compact `1.17.0` successor manifest;
5. exact-hash reread of policy, checkpoints, log, successor, predecessor, ledger, and event population.

The predecessor is verified but never rewritten.

## Contract adapter

Module:

```text
src/ctrt/checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints.py
```

Primary successor type:

```text
CheckpointBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
```

Public operations:

```text
load_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_evidence
validate_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoints
persist_checkpoint_bound_checkpoint_witness_conflict_adjudicator_credential_revocation_corpus
```

## Checkpoint-gated runner

Module:

```text
src/ctrt/checkpoint_gated_checkpoint_witness_conflict_adjudication_runner.py
```

Runner:

```text
CheckpointGatedCheckpointWitnessConflictAdjudicationExperimentRunner
```

Execution stages:

1. exact frozen-plan, successor, predecessor, policy, log, head, run identity, and chronology preflight;
2. storage-backed checkpoint evidence loading;
3. sequence, ancestry, prefix, publication, ledger, and event-population validation;
4. run-specific checkpoint-verification report persistence;
5. exact plan narrowing from `1.17.0` to `1.16.0`;
6. unchanged PR #38 execution under the same experiment run ID;
7. outer final persistence;
8. storage-backed verification of the final, successor, predecessor, policy, log, checkpoints, report, and PR #38 final.

## Explicit scope narrowing

```text
1.17.0 plan -> current checkpoint verification and outer finalization
1.16.0 plan -> unchanged current revocation lifecycle
1.15.0 plan -> unchanged current credential lifecycle
1.14.0 plan -> unchanged current disagreement adjudication lifecycle
1.13.0 plan -> unchanged current named-witness lifecycle
1.12.0 plan -> unchanged inherited checkpoint lifecycle
1.11.0 plan -> unchanged inherited revocation lifecycle
1.10.0 plan -> unchanged inherited credential lifecycle
1.9.0 plan  -> unchanged inherited adjudication lifecycle
```

Only the corpus reference and identical ordered content IDs change between scopes.

## Run-specific artifacts

Checkpoint verification report:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-verification
```

Successful completion:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-completion
```

Verified checkpoint followed by downstream abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-terminal-abstention
```

## Outcome matrix

### Checkpoint verified; all governed layers execute

```text
current checkpoint             = verified
current revocation             = execute
current credential             = execute
current checkpoint witness     = abstain
current resolution status      = resolved
current conflict adjudication  = execute
predecessor witness            = execute
inherited revocation           = execute
inherited credential           = execute
inherited checkpoint witness   = execute
inherited resolution status    = not_required
inherited adjudication         = execute
terminal outcome               = execute
```

### Checkpoint verified; current suspension effective

```text
current checkpoint             = verified
current revocation             = abstain
all current downstream claims  = null
terminal outcome               = abstain
```

### Checkpoint verified; inherited suspension effective

```text
current checkpoint             = verified
current revocation             = execute
current credential             = execute
current checkpoint witness     = abstain
current resolution status      = resolved
current conflict adjudication  = execute
predecessor witness            = execute
inherited revocation           = abstain
remaining inherited claims     = null
terminal outcome               = abstain
```

### Checkpoint structurally invalid

```text
checkpoint report              = not persisted
PR #38                         = not invoked
all revocation/downstream      = absent
result                         = structural failure
```

## Tests

Contract tests establish:

- exact policy, checkpoint, log, and successor hashes;
- closed policy, checkpoint, log, and successor schemas;
- exact `1.16.0` predecessor binding;
- exact one-event population coverage;
- omitted-event rejection;
- checkpoint verification before revocation evaluation;
- manifest-last deterministic reconstruction;
- unsupported confidence-field rejection.

Real-chain tests establish:

- a valid checkpoint delegates exact PR #38;
- the exact same experiment run ID crosses the `1.17.0 -> 1.16.0` boundary;
- current suspension leaves checkpoint status verified and visible;
- inherited suspension leaves the current checkpoint and current revocation results distinct;
- invalid outer chronology fails before delegation;
- execution and terminal abstention satisfy one closed final schema.

## Review checklist

1. Does the genesis checkpoint bind the exact `1.16.0` corpus, ledger, and complete ordered event population?
2. Is the event-population hash derived from the exact stored references in order?
3. Does the frozen log declare its final checkpoint as its head?
4. Does `1.17.0` bind the exact predecessor, policy, log, and head without duplicating inherited evidence?
5. Must checkpoint verification occur before current revocation evaluation?
6. Is the checkpoint report persisted before PR #38 executes?
7. Does checkpoint structural failure prevent every downstream artifact?
8. Do current and inherited revocation outcomes remain independent?
9. Are completeness, global uniqueness, identity, authorship, trusted time, consensus, and correctness excluded?

## Deferred successor

The next layer may add immutable named-witness observations over the exact `1.17.0` checkpoint head. It must not rewrite the checkpoint report, current revocation decision, current credential graph, disagreement record, fork evidence, dissent, selected head, or any inherited artifact.
