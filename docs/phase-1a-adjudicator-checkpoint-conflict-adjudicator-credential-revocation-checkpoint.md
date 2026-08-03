# Phase 1A: Checkpoint-conflict adjudicator credential revocation checkpoint

## Purpose

This layer checkpoints the exact frozen revocation-ledger head used to determine the operational status of the issuer-bound credential for the adjudicator who may resolve an adjudicator-checkpoint witness conflict.

It answers one bounded question:

> Does the exact immutable checkpoint chain prove that the exact `1.6.0` revocation corpus and frozen ledger head were published with complete ordered event coverage?

It does not decide whether the issuer disclosed every real-world event, whether the adjudicator was correct, whether a witness was truthful, or whether an external party observed the checkpoint.

## Fixed synthetic graph

### Revocation predecessor

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-bound@1.6.0
sha256:d8c50b7a6ef0250df9bd2b2cc4830aadb45bdf4b8c7ec6696b8e316124822123
```

### Checkpoint policy

```text
policy.synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:e041cbb0a189a389e5aa6d7902d7ad4a3808c7a921739f527a8c2487cbb14b41
```

The accepted policy requires:

- exact ordered event coverage;
- prefix extension without omission or reordering;
- contiguous checkpoint sequence numbers;
- monotonically increasing publication time.

### Genesis checkpoint

```text
checkpoint.synthetic.adjudicator-checkpoint-conflict-adjudicator-credential-revocations.0000
```

Stored artifact:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.adjudicator-checkpoint-conflict-adjudicator-credential-revocations.0000
sha256:ccf31947e678160514a5ac6f59eec7f3718c56e7800c973f23c0770895629422
```

The genesis checkpoint binds:

- the exact `1.6.0` revocation corpus;
- the exact frozen revocation ledger;
- the exact single ordered suspension event;
- event count `1`;
- deterministic event-population hash;
- sequence number `0`;
- no predecessor checkpoint;
- publication time `2026-08-03T19:25:30Z`.

### Checkpoint log

```text
log.synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:575a42f1c90435ab30e6c56c0b80aefc111ac44d89b1b9c7a401d6301aa4b2f2
```

The frozen log contains one checkpoint and identifies the genesis checkpoint as its exact head.

## Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-bound@1.6.0
sha256:d8c50b7a6ef0250df9bd2b2cc4830aadb45bdf4b8c7ec6696b8e316124822123
```

Successor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-bound@1.7.0
sha256:26311c6a5da00c7e6ea3986406be48ca8d3087ccf3f41f07c783cd8db88635fb
```

The `1.7.0` artifact is a compact successor manifest. It binds the immutable `1.6.0` predecessor, checkpoint policy, frozen checkpoint log, exact head checkpoint, and unchanged content order.

Publication is manifest-last:

1. checkpoint policy;
2. immutable checkpoints;
3. frozen checkpoint log;
4. `1.7.0` manifest.

## Checkpoint verification

Verification reconstructs the complete stored checkpoint population and confirms:

- the plan is frozen and bound to the exact `1.7.0` corpus;
- policy, log, and head references match the manifest;
- the checkpoint population exactly matches the frozen log;
- sequence numbers are contiguous from zero;
- genesis has no predecessor;
- later checkpoints, when present, name their immediate predecessors;
- later event populations preserve the complete prior prefix;
- publication time strictly increases;
- no checkpoint is verified before publication;
- the head binds the exact `1.6.0` predecessor and current ledger;
- the head event order and count equal the ledger event population.

The run-specific verification report records:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-verification
```

It is persisted and reread before the revocation runner may execute.

## Execution lifecycle

`CheckpointGatedAdjudicatorCheckpointConflictExperimentRunner` performs:

1. exact `1.7.0` plan, manifest, checkpoint policy, log, head, content-order, run-ID, and timestamp preflight;
2. storage-backed loading of the compact manifest, policy, log, and complete checkpoint population;
3. structural validation of sequence, predecessor continuity, prefix extension, chronology, and exact ledger-head coverage;
4. run-specific checkpoint-verification report persistence and reread verification;
5. explicit scoped delegation to the unchanged ADR-0031 revocation runner;
6. final-manifest persistence;
7. complete storage-backed reread verification.

Terminal artifacts are:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-completion
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-terminal-abstention
```

## Explicit nested-plan delegation

The outer runner receives a frozen plan bound to `1.7.0` because checkpoint verification depends on the new policy, log, and head.

After successful checkpoint verification, it derives a nested plan bound to the exact immutable `1.6.0` predecessor and invokes the unchanged revocation-gated checkpoint-conflict runner.

```text
outer plan:
  corpus = 1.7.0
  purpose = checkpoint verification and outer finalization

nested plan:
  corpus = 1.6.0
  purpose = unchanged ADR-0031 revocation and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidates, analyzers, execution windows, and all prior governance evidence remain identical.

## Terminal behavior

### Checkpoint valid; revocation outcome `execute`

The checkpoint report remains separately persisted. The outer runner delegates the unchanged ADR-0031 lifecycle and mirrors its independently preserved outcomes:

- revocation decision;
- checkpoint-conflict adjudicator credential decision;
- original adjudicator-checkpoint witness outcome;
- conflict-adjudication outcome;
- earlier adjudicator and reviewer governance outcomes;
- terminal analysis outcome.

### Checkpoint valid; revocation outcome `abstain`

The checkpoint remains verified and separately visible. The delegated revocation runner persists its terminal abstention without producing credential, witness, conflict-adjudication, reviewer, or analyzer work after the revocation boundary.

The checkpoint layer does not convert that governed abstention into structural failure.

### Checkpoint structurally invalid

The runner fails before invoking ADR-0031. No revocation decision or downstream work is permitted.

## Structural failures

Structural failures include:

- plan or content-order drift;
- substituted policy, log, head, corpus, ledger, or artifact references;
- non-contiguous sequence numbers;
- invalid genesis predecessor;
- missing immediate predecessor;
- event omission, rollback, or reordering;
- stale ledger reference;
- head mismatch with the current ledger population;
- non-increasing publication time;
- verification before publication;
- missing or altered stored artifacts;
- report, final-manifest, or reread failure.

Malformed checkpoint evidence is never represented as ordinary abstention.

## Schemas

This slice reuses the established generic schemas for:

- adjudicator credential revocation checkpoint policy;
- adjudicator credential revocation ledger checkpoint;
- adjudicator credential revocation checkpoint log;
- adjudicator credential revocation checkpoint verification report.

It adds context-specific schemas for:

- the compact `1.7.0` checkpoint-bound corpus;
- the checkpoint-gated checkpoint-conflict revocation final manifest.

## Privacy boundary

Artifacts contain stable pseudonymous IDs, immutable revisions, artifact references, event counts, deterministic hashes, timestamps, statuses, and declared governance outcomes only.

They contain no private identity data, signatures, keys, certificate chains, reputation scores, vote counts, quorum, consensus percentages, model output, dataset, or aggregate CTRT score.

## Trust boundary

`verified` means that the declared immutable checkpoint graph and execution lifecycle were reconstructed and validated under the accepted contracts.

It does not establish real-world identity, publisher trustworthiness, cryptographic authorship, trusted time, complete event disclosure, external checkpoint observation, adjudicator correctness, witness truthfulness, global head uniqueness, consensus, or analytical accuracy.

See [ADR-0032](adr/0032-checkpoint-conflict-adjudicator-revocation-ledgers-require-immutable-checkpoints.md).
