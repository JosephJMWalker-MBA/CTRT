# Phase 1A: Adjudicator credential revocation checkpoints

This layer proves that the adjudicator revocation ledger evaluated by an experiment is the exact head of a frozen, contiguous, prefix-extending checkpoint history.

It does **not** reinterpret the revocation ledger. Checkpoint verification answers:

> Is this exact ordered ledger state the valid head of this exact checkpoint chain?

The downstream revocation layer separately answers:

> What operational credential status follows from this exact event history at the declared evaluation time?

## Artifact graph

The fixed synthetic graph adds:

```text
policy.synthetic-witness-conflict-adjudicator-revocation-checkpoints@0.1.0
    ↓
adjudicator-credential-revocation-checkpoint:
checkpoint.synthetic.witness-conflict-adjudicator-revocations.0000
    ↓
log.synthetic-witness-conflict-adjudicator-revocation-checkpoints@0.1.0
    ↓
corpus.synthetic-three-items.adjudicator-revocation-checkpoint-bound@1.2.0
```

The genesis checkpoint binds the exact predecessor:

```text
corpus.synthetic-three-items.adjudicator-credential-revocation-bound@1.1.0
sha256:0cc4d77649e2d240e719ed98f618f968ba884289663eaf07fd375241ca7e20ab
```

It also binds the exact adjudicator revocation ledger and its one ordered future-effective suspension event.

## Checkpoint invariants

Every accepted chain must satisfy all of the following:

1. Sequence numbers begin at zero and are contiguous.
2. Genesis has no predecessor.
3. Every later checkpoint names the immediately prior checkpoint.
4. Every later event population preserves the earlier population as an exact ordered prefix.
5. Event counts never decrease.
6. Publication timestamps strictly increase.
7. Verification never predates publication.
8. The frozen log head is its final checkpoint.
9. The corpus head, log head, final checkpoint, current ledger, and exact event order all agree.

A mismatch is a structural failure, not a governed abstention.

## Publication lifecycle

`persist_checkpoint_bound_adjudicator_revocation_corpus` publishes in dependency order:

1. re-read and verify the `1.1.0` predecessor corpus;
2. validate the complete checkpoint chain;
3. append the accepted checkpoint policy;
4. append checkpoints in exact sequence order;
5. append the frozen checkpoint log;
6. append the `1.2.0` successor corpus last;
7. reload the complete stored graph by hash.

The predecessor corpus, revocation ledger, credential, adjudication, checkpoint-witness evidence, rationale, selected head, and preserved dissent are not modified.

## Execution lifecycle

`CheckpointGatedAdjudicatorRevocationExperimentRunner` performs:

1. exact plan, corpus, policy, log, head, content-order, and timestamp preflight;
2. storage-backed policy, log, checkpoint, and corpus loading;
3. checkpoint-chain and current-ledger validation;
4. run-specific checkpoint-verification report persistence;
5. delegation to the unchanged adjudicator revocation runner;
6. final checkpoint-gated manifest persistence;
7. complete storage-backed reverification.

Run-specific verification artifact:

```text
<run>:adjudicator-credential-revocation-checkpoint-verification
```

Terminal artifacts:

```text
<run>:adjudicator-revocation-checkpoint-completion
<run>:adjudicator-revocation-checkpoint-terminal-abstention
```

## Outcome separation

The final receipt preserves:

```text
adjudicator_revocation_outcome
adjudicator_credential_outcome
witness_outcome
adjudication_outcome
reviewer_revocation_outcome
terminal_outcome
```

Checkpoint success remains visible when the revocation ledger later produces a governed abstention. A checkpoint never converts an abstention into execution and never overwrites downstream evidence.

## Fixed temporal example

The genesis checkpoint is published at:

```text
2026-08-03T14:51:00Z
```

The bound suspension event becomes effective at:

```text
2027-01-01T00:00:00Z
```

Therefore the same valid checkpoint chain permits the revocation layer to produce:

```text
2026-08-03T14:00:00Z → revocation status active → execute
2027-01-01T00:00:00Z → revocation status suspended → abstain
```

The checkpoint result is unchanged in both runs because the published ledger state is unchanged. Only the explicit revocation evaluation time changes.

## Structural failures

No verified checkpoint final is produced for:

- missing or tampered checkpoint artifacts;
- policy, log, corpus, or head hash drift;
- non-contiguous sequence numbers;
- a predecessor on genesis;
- a later checkpoint that skips its immediate predecessor;
- event omission, substitution, or reordering;
- decreasing event counts;
- non-increasing publication time;
- verification before publication;
- a stale head;
- a head that does not exactly match the current ledger.

## Privacy and constitutional boundary

Checkpoint artifacts contain only immutable artifact references, sequence metadata, ordered population hashes, and timestamps. They contain no real names, contact information, private identity data, trust scores, ranks, votes, consensus percentages, confidence scores, or aggregate CTRT scores.

`verified` means the exact frozen graph satisfies the declared checkpoint invariants. It does not establish signatures, trusted time, global publication, universal completeness, issuer trust, real identity, credential truth, adjudication correctness, or content quality.

## Intentionally excluded

- signatures, keys, and certificate chains;
- live transparency or revocation services;
- external timestamp authorities;
- global checkpoint discovery;
- independent adjudicator-checkpoint witnesses;
- witness quorum or voting;
- real identities, adjudicators, issuers, models, datasets, APIs, frontend, or deployment.

Independent witness attestations over checkpoint heads are the next bounded governance layer, not part of this one.
