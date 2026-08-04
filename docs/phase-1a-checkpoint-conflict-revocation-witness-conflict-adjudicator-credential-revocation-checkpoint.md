# Phase 1A — Witness-conflict adjudicator credential revocation checkpoint

This bounded layer checkpoints the exact frozen `1.11.0` revocation ledger before that ledger may authorize the credential lifecycle.

It asks only:

> Does the exact immutable checkpoint chain bind the exact `1.11.0` revocation corpus, frozen ledger, and complete ordered event population before revocation evaluation?

Checkpoint verification is a provenance claim. It does not determine the credential's effective status, authorize the adjudicator, resolve the witness evidence, or establish that the ledger contains every real-world event.

## Fixed graph

```text
1.11.0 revocation-bound corpus
  → accepted checkpoint policy
  → immutable genesis checkpoint
  → frozen checkpoint log
  → manifest-last 1.12.0 checkpoint-bound corpus
```

### Checkpoint policy

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:55ac4a95e1ad0e1052a4300ad25a90c215d74663efca60d2dca8196524b4878c
```

The accepted policy requires exact event order, prefix-only extension, contiguous sequence numbers, and monotonic publication time.

### Genesis checkpoint

```text
adjudicator-credential-revocation-checkpoint:
checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.0000
sha256:350d6550bbe969457fde6f556505e2b6ef270f4d1cedd296c6a835505ed37359
```

The checkpoint binds:

- sequence number `0`;
- no predecessor checkpoint;
- the exact immutable `1.11.0` corpus;
- the exact frozen PR #33 revocation ledger;
- the exact ordered future-effective suspension-event reference;
- event count `1`;
- deterministic event-population hash `sha256:8af8962c65284cd62a35be38f2cea90989a30fc1d268c69db11226017031c97e`;
- publication at `2026-08-03T19:54:51Z`.

### Frozen checkpoint log

```text
log.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:829e5900a8977de21d9d2a939fe48d2efc504541592fcfefe93f9c60c2759e47
```

The log contains one checkpoint and declares that same checkpoint as its exact head.

### Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-bound@1.11.0
sha256:33b05c3429a0d8f58bb12a4ad497c1c885a4e23386fc80fa017f8cbe9ccaf280
```

Successor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.12.0
sha256:3fdaa55c2fb1ab14aaca5482093ff6415f6835483f0c2b2e3bd6a758af40a096
```

The compact `1.12.0` manifest binds the exact predecessor, policy, log, head, and unchanged ordered content population. It does not duplicate or rewrite the inherited credential, issuer, revocation, adjudication, witness, dissent, checkpoint, reviewer, or analytical evidence.

## Chronology

```text
2026-08-03T19:54:48Z  1.11.0 predecessor published
2026-08-03T19:54:49Z  checkpoint policy created
2026-08-03T19:54:51Z  genesis checkpoint published
2026-08-03T19:54:53Z  checkpoint log frozen
2026-08-03T19:54:54Z  1.12.0 successor published
2026-08-03T19:54:55Z  checkpoint verified
2026-08-03T19:54:56Z  delegated revocation evaluated
2026-08-03T19:55:00Z  credential evaluated
2026-08-03T19:55:30Z  adjudication evaluated
2026-08-03T19:56:00Z  adjudication lifecycle completed
2026-08-03T19:56:30Z  credential lifecycle completed
2026-08-03T19:56:45Z  revocation lifecycle completed
2026-08-03T19:57:00Z  checkpoint lifecycle completed
```

The run-specific revocation evaluation moves one second later than the canonical PR #33 example. This preserves the same active as-of result while ensuring the checkpoint is published and verified before the operational decision it governs. The immutable `1.11.0` evidence remains unchanged.

## Checkpoint invariants

The reused generic checkpoint grammar requires:

1. sequence numbers contiguous from zero;
2. genesis with no predecessor;
3. each later checkpoint bound to its immediate predecessor;
4. exact ordered-prefix preservation of prior event populations;
5. nondecreasing event counts;
6. strictly increasing publication times;
7. verification at or after publication;
8. frozen-log head equality with the final checkpoint;
9. exact equality among checkpoint corpus, current ledger, event order, and head.

The context adapter adds:

```text
checkpoint_verified_at <= revocation_evaluated_at
```

A structurally invalid checkpoint produces no revocation outcome.

## Manifest-last publication

Persistence order is:

1. accepted checkpoint policy;
2. immutable checkpoint population in sequence order;
3. frozen checkpoint log;
4. compact `1.12.0` successor manifest;
5. exact-hash reread of the complete graph.

The predecessor and every inherited artifact remain immutable.

## Contract adapter

The public contract module is:

```text
src/ctrt/checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints.py
```

Primary successor type:

```text
CheckpointBoundCheckpointConflictWitnessAdjudicatorCredentialRevocationCorpusSnapshot
```

Public operations:

```text
load_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoint_evidence
validate_checkpoint_conflict_witness_adjudicator_credential_revocation_checkpoints
persist_checkpoint_bound_checkpoint_conflict_witness_adjudicator_credential_revocation_corpus
```

The adapter reuses the generic checkpoint policy, checkpoint, log, verification-report, stored-evidence, validation, and persistence contracts. It adds only exact `1.11.0` authority binding and the pre-revocation verification boundary.

## Checkpoint-gated runner

The outer runner is:

```text
src/ctrt/checkpoint_gated_checkpoint_conflict_witness_adjudication_runner.py
```

`CheckpointGatedCheckpointConflictWitnessAdjudicationExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, content-order, policy, log, head, run, and chronology preflight;
2. storage-backed loading and hash verification of the complete `1.12.0` checkpoint graph;
3. sequence, ancestry, prefix, chronology, ledger-head, and event-population validation;
4. run-specific checkpoint-verification persistence and reread verification;
5. exact plan narrowing from `1.12.0` to the immutable `1.11.0` predecessor;
6. invocation of the unchanged PR #33 runner;
7. outer final-manifest persistence;
8. storage-backed reread of the final, successor, policy, log, checkpoints, verification report, and delegated PR #33 final.

## Explicit scope transition

```text
1.12.0 plan → checkpoint validation, report persistence, outer finalization
1.11.0 plan → unchanged PR #33 revocation lifecycle
1.10.0 plan → unchanged credential lifecycle
1.9.0 plan  → unchanged adjudication lifecycle
1.8.0 receipt → preserved witness evidence
1.7.0 scope → lower checkpoint lifecycle
```

Only the corpus reference is narrowed. Experiment identity, version, content IDs, content order, governance evidence, and lower execution arguments remain unchanged.

## Run-specific artifacts

Checkpoint verification report:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-verification
```

Successful delegated execution:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-completion
```

Valid checkpoint followed by a downstream abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-terminal-abstention
```

## Outcome separation

Checkpoint status and downstream outcomes answer different questions:

```text
checkpoint status     → whether the exact frozen ledger head is structurally verified
revocation outcome    → whether the event history permits credential evaluation then
credential outcome    → whether the adjudicator is issuer-authorized then
witness outcome       → what the required named witnesses reported
adjudication outcome  → what accepted adjudication authority selected
terminal outcome      → whether the complete governed lifecycle executed
```

No later result rewrites an earlier one.

### Valid checkpoint and active revocation

```text
checkpoint status     = verified
revocation outcome    = execute
credential outcome    = execute
checkpoint witness outcome = execute
resolution status     = not_required
adjudication outcome  = execute
terminal outcome      = execute
```

### Valid checkpoint and effective suspension

```text
checkpoint status     = verified
revocation outcome    = abstain
credential outcome    = null
checkpoint witness outcome = null
resolution status     = null
adjudication outcome  = null
terminal outcome      = abstain
```

Checkpoint evidence remains visible even though PR #33 correctly stops before credential execution.

### Invalid checkpoint

No checkpoint receipt or revocation outcome is produced. PR #33 is not invoked.

## Test coverage

Contract and storage tests prove:

- canonical policy, checkpoint, log, and successor hashes;
- generic policy, checkpoint, and log schemas;
- the closed `1.12.0` successor schema;
- exact `1.11.0` predecessor and content-order binding;
- exact single-event coverage;
- omission rejection;
- verification no later than revocation evaluation;
- manifest-last persistence and deterministic reconstruction;
- rejection of unsupported confidence fields.

Stored lifecycle tests use real lower PR #30–#33 evidence to prove:

1. a valid checkpoint delegates the exact PR #33 lifecycle;
2. a valid checkpoint remains independently verified when the future suspension becomes effective and PR #33 abstains;
3. invalid checkpoint chronology stops before a PR #33 run-specific revocation decision;
4. the outer final satisfies its closed schema;
5. every new contract and runner symbol is available from the package public API.

## Privacy and trust boundary

Artifacts contain stable pseudonymous IDs, immutable revisions, exact artifact references, ordered populations, deterministic hashes, sequence metadata, timestamps, statuses, and separate governance outcomes.

Verification does not establish:

- legal or real-world adjudicator, witness, or issuer identity;
- cryptographic authorship or private-key possession;
- trusted external time;
- issuer trustworthiness, legal authority, independence, or competence;
- event completeness beyond the exact frozen ledger;
- absence of undisclosed events or alternate checkpoint chains;
- global checkpoint uniqueness or public availability;
- witness truthfulness, independence, or correctness;
- adjudicator competence, independence, honesty, or correctness;
- adjudication correctness;
- majority support, quorum, consensus, confidence, or reputation;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred layers

Named witnesses over the exact `1.12.0` checkpoint head are the next bounded layer. Witness-conflict adjudication, credentials and revocation for that authority, signatures, keys, identity providers, trusted external timestamp services, and live transparency infrastructure remain separate future layers.
