# Phase 1A: Revocation Ledger Checkpoints

## Purpose

This slice adds an inspectable publication-continuity layer above CTRT's immutable credential-revocation ledger.

The revocation ledger answers:

> What ordered credential-status event history is being evaluated as of this experiment timestamp?

The checkpoint layer answers a different question:

> Does the supplied sequence of published ledger states preserve its predecessor chain and ordered event history without omission, reordering, or rollback?

A successful checkpoint verification does not determine credential status and does not authorize an analyzer by itself. It permits the existing revocation-gated lifecycle to evaluate the ledger, after which all downstream governance boundaries remain independent.

## Canonical artifacts

### Checkpoint policy

`CredentialRevocationCheckpointPolicySnapshot` freezes the required publication rules:

- exact event order;
- prefix extension;
- contiguous sequence numbers;
- strictly increasing publication times.

The initial accepted synthetic policy requires all four rules.

### Ledger checkpoint

`CredentialRevocationLedgerCheckpointSnapshot` binds:

- artifact and checkpoint identity;
- zero-based sequence number;
- exact revocation-bound corpus reference;
- exact revocation-ledger reference;
- complete ordered event references;
- event count;
- ordered event-population hash;
- immediate predecessor checkpoint, or `null` at genesis;
- publication timestamp.

The ordered population hash is derived from the canonical JSON representation of the exact event-reference sequence. It is not a Merkle root and provides no inclusion-proof mechanism.

### Checkpoint log

`CredentialRevocationCheckpointLogSnapshot` freezes:

- the exact checkpoint policy;
- the complete ordered checkpoint-reference population;
- the exact head checkpoint;
- the log publication timestamp.

The head must be the final checkpoint reference.

### Checkpoint-bound corpus

`CheckpointBoundRevocationCorpusSnapshot` wraps the existing revocation-bound corpus with exact references to:

- its `0.6.0` predecessor;
- the checkpoint policy;
- the checkpoint log;
- the checkpoint head.

The synthetic successor uses a distinct identity:

```text
corpus.synthetic-three-items.checkpoint-bound@0.7.0
```

This allows `0.6.0` and `0.7.0` to coexist in the append-only store.

### Verification report

`CredentialRevocationCheckpointVerificationReport` records:

- experiment identity and version;
- checkpoint-bound corpus, policy, and log references;
- exact head checkpoint reference;
- checkpoint count;
- head sequence number;
- head event count and ordered population hash;
- verification timestamp.

The detailed run-specific report is persisted at:

```text
<experiment-run-id>:credential-revocation-checkpoint-verification
```

A deterministic plan-level index is also written for discovery.

## Publication order

`persist_checkpoint_bound_corpus` writes artifacts in this order:

1. checkpoint policy;
2. each checkpoint in log order;
3. checkpoint log;
4. checkpoint-bound corpus manifest last.

The manifest cannot claim a complete checkpoint graph until every referenced policy, checkpoint, and log artifact has already been persisted and reverified.

## Validation algorithm

`validate_credential_revocation_checkpoints` performs the following checks.

### Corpus and lifecycle binding

- the experiment plan is frozen;
- plan corpus and content order match `0.7.0` exactly;
- corpus policy, log, and head references match supplied artifacts;
- policy is accepted;
- log is frozen and bound to the exact policy;
- supplied checkpoint population exactly matches the log.

### Sequential continuity

For checkpoint position `n`:

- `sequence_number` must equal `n`;
- checkpoint zero must have no predecessor;
- every later checkpoint must name checkpoint `n - 1` exactly;
- publication time must be later than its predecessor;
- publication may not occur after the verification timestamp.

### Ordered prefix preservation

For every adjacent pair, the later checkpoint's first `previous.event_count` event references must equal the complete previous event-reference tuple.

This catches:

- deletion of a previously published event;
- insertion before or within the prior population;
- reordering of prior events;
- substitution of a prior reference;
- event-count rollback.

New events may only appear after the complete prior ordered prefix.

### Current-head binding

The final checkpoint must:

- equal the log and corpus head reference;
- bind the exact `0.6.0` predecessor corpus;
- bind the exact current revocation ledger;
- contain exactly the ledger's ordered event references;
- contain the same event count.

A valid historical chain with a stale head therefore cannot authorize a newer or different ledger.

## Structural failure versus downstream abstention

Checkpoint invalidity is structural failure. Examples include:

- sequence gaps;
- broken predecessor references;
- non-increasing publication timestamps;
- future-dated checkpoints;
- omitted or reordered event references;
- count rollback;
- substituted policy, log, checkpoint, corpus, or hash;
- a head that differs from the current ledger;
- missing stored checkpoint evidence.

No checkpoint verification report or downstream revocation decision should be treated as a verified outcome when these conditions occur.

After successful checkpoint verification, the existing revocation runner may independently return:

- execution permission; or
- governed abstention because a credential is effectively suspended or revoked.

Later credential, review, quality, and analyzer boundaries remain unchanged.

## Runner stages

`CheckpointGatedRevocationExperimentRunner` exposes precise fail-closed stages:

1. `preflight`
2. `checkpoint-loading`
3. `checkpoint-validation`
4. `report-persistence`
5. `revocation-execution`
6. `final-persistence`
7. `verification`

The checkpoint verification report is persisted before downstream revocation execution begins.

If downstream execution fails after some content receipts have been verified, the error preserves those completed content IDs. The checkpoint report remains append-only evidence, but no checkpoint-gated final artifact is created.

## Terminal artifacts

A terminal execution produces:

```text
<experiment-run-id>:revocation-checkpoint-completion
```

A valid checkpoint chain followed by a downstream governed abstention produces:

```text
<experiment-run-id>:revocation-checkpoint-terminal-abstention
```

The latter is not a checkpoint abstention. It means checkpoint verification succeeded and a later revocation or governance boundary abstained.

Both terminal forms preserve:

- checkpoint corpus, policy, and log references;
- the full checkpoint-reference population;
- checkpoint head;
- run-specific verification report;
- downstream revocation final reference;
- revocation outcome and ultimate terminal outcome.

## Fixed synthetic graph

The repository fixture contains:

- one accepted checkpoint policy;
- one genesis checkpoint at sequence zero;
- one frozen checkpoint log;
- one `0.7.0` checkpoint-bound corpus.

The genesis checkpoint commits to the one-event synthetic revocation ledger from ADR-0021. The tests additionally construct multi-checkpoint graphs to verify prefix extension and predecessor behavior.

## Tested failure paths

The executable suite covers:

- clean checkpoint verification and analyzer execution;
- valid checkpoint verification followed by revocation abstention;
- idempotent persistence and execution;
- exact storage reconstruction;
- sequence gaps;
- broken immediate-predecessor links;
- omitted prior events;
- reordered prior events;
- event-count rollback;
- future publication timestamps;
- checkpoint head mismatch with the current ledger;
- unknown fields rejected by schema and parser;
- missing stored checkpoint artifacts;
- downstream analyzer failure with preserved checkpoint report and partial progress;
- final checkpoint-gated persistence failure with prior verified artifacts retained.

## Trust boundary

`verified` means the supplied append-only artifacts form the exact internally consistent checkpoint chain required by the frozen policy and that its head matches the supplied current revocation ledger.

It does not mean:

- the ledger contains every real event;
- the log contains every checkpoint ever published;
- no conflicting checkpoint fork exists;
- an independent witness observed the checkpoints;
- publication timestamps come from a trusted external authority;
- the artifacts carry valid digital signatures;
- the publisher or issuer is trustworthy;
- reviewer credentials or judgments are correct;
- extraction or analyzer results are accurate;
- content is good, bad, safe, unsafe, or worthy of an aggregate score.

## Intentionally deferred

- digital signatures and key rotation;
- Merkle inclusion and consistency proofs;
- public or live transparency services;
- witness attestations;
- gossip and fork reconciliation;
- network retrieval or monitoring;
- real identity providers, reviewers, extractors, models, or datasets.
