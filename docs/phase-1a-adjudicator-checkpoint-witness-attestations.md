# Phase 1A: Adjudicator checkpoint witness attestations

This layer records what named synthetic witnesses claim to have observed about the exact adjudicator credential revocation checkpoint head.

It does **not** vote on checkpoint truth. The witness layer asks:

> Did every policy-required named witness report the exact independently verified checkpoint head?

The checkpoint layer separately asks:

> Is this exact ordered ledger state the valid head of this exact prefix-proof chain?

The downstream revocation layer separately asks:

> What operational adjudicator credential status follows from the bound event history at the declared evaluation time?

## Artifact graph

The fixed synthetic graph adds:

```text
registry.synthetic-adjudicator-checkpoint-witnesses@0.1.0
    ↓
policy.synthetic-adjudicator-checkpoint-witnesses@0.1.0
    ↓
three named checkpoint-witness attestations
    ↓
corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound@1.3.0
```

The successor corpus binds the exact predecessor:

```text
corpus.synthetic-three-items.adjudicator-revocation-checkpoint-bound@1.2.0
sha256:152eab38e3b72a2d8293ec88202fed3adaaf969df22e160b7a9f12983580d257
```

Every fixed attestation binds the exact checkpoint log:

```text
log.synthetic-witness-conflict-adjudicator-revocation-checkpoints@0.1.0
sha256:4b940c395da7a18c4e337f424f642c39839f373e685fe31fd037c3981b694a43
```

and the exact checkpoint head:

```text
adjudicator-credential-revocation-checkpoint:
checkpoint.synthetic.witness-conflict-adjudicator-revocations.0000
sha256:4034f2202a16a95902b535e38330d71358e5485ded645c4c649cccb1967c5e45
```

## Witness identities

The registry contains three stable pseudonymous witnesses:

```text
witness.synthetic.adjudicator-alpha
witness.synthetic.adjudicator-beta
witness.synthetic.adjudicator-gamma
```

Each identity has the immutable revision:

```text
synthetic-adjudicator-checkpoint-witness@0.1.0
```

and the role:

```text
checkpoint_observer
```

The registry contains no names, email addresses, phone numbers, government identifiers, biometric data, or private credential payloads.

## Policy invariants

The accepted witness policy requires:

1. the exact accepted witness registry;
2. every registry witness in exact registry order;
3. exactly one attestation per required witness;
4. abstention on any conflicting head;
5. prohibition of vote aggregation.

A larger matching group cannot override one conflicting observation.

## Attestation invariants

Every accepted attestation must bind:

- the exact witness ID and identity revision;
- the `checkpoint_observer` role through the registry;
- the exact `1.2.0` predecessor corpus;
- the exact checkpoint log;
- the exact expected checkpoint head;
- the exact observed checkpoint head;
- an observation kind derived from reference equality;
- an observation time at or after checkpoint publication;
- a receipt time at or before witness evaluation;
- a non-empty note.

`matches_head` is valid only when expected and observed references are exactly equal. Any difference requires `conflicting_head`.

## Publication lifecycle

`persist_witness_bound_adjudicator_checkpoint_corpus` publishes in dependency order:

1. re-read and verify the `1.2.0` predecessor corpus;
2. verify unchanged checkpoint policy, log, and head bindings;
3. validate the complete witness population;
4. append the accepted witness registry;
5. append the accepted witness policy;
6. append attestations in exact required witness order;
7. append the `1.3.0` successor corpus last;
8. reload the complete stored witness graph by hash.

No predecessor artifact is modified.

## Execution lifecycle

`AdjudicatorCheckpointWitnessExperimentRunner` performs:

1. exact plan, corpus, registry, policy, content-order, and timestamp preflight;
2. storage-backed witness and checkpoint evidence loading;
3. complete checkpoint-chain reverification;
4. run-specific checkpoint-verification report persistence;
5. exact named-witness validation;
6. run-specific witness-decision persistence;
7. either governed witness abstention or delegation to the unchanged checkpoint runner;
8. final witness-gated manifest persistence;
9. complete storage-backed reverification.

Run-specific evidence artifacts:

```text
<run>:adjudicator-credential-revocation-checkpoint-verification
<run>:adjudicator-checkpoint-witness-decision
```

Terminal artifacts:

```text
<run>:adjudicator-checkpoint-witness-abstention
<run>:adjudicator-checkpoint-witness-completion
<run>:adjudicator-checkpoint-witness-terminal-abstention
```

## No-majority conflict behavior

The failure matrix includes this exact population:

```text
alpha → matches_head
beta  → matches_head
gamma → conflicting_head
```

The result is:

```text
adjudicator_checkpoint_witness_outcome = abstain
terminal_outcome = abstain
```

No adjudicator revocation, adjudicator credential, earlier witness adjudication, reviewer governance, or analyzer execution follows.

The system does not claim gamma is correct. It preserves all three observations and declines to proceed while the required evidence conflicts.

## Outcome separation

The final artifact preserves distinct fields for:

```text
adjudicator_checkpoint_witness_outcome
adjudicator_revocation_outcome
adjudicator_credential_outcome
reviewer_checkpoint_witness_outcome
adjudication_outcome
reviewer_revocation_outcome
terminal_outcome
```

A clean witness outcome may still be followed by downstream revocation abstention. That later abstention does not erase successful checkpoint or witness verification.

## Structural failures

No verified witness final is produced for:

- missing or tampered witness artifacts;
- registry, policy, corpus, log, or head drift;
- substituted witness identity revision;
- a non-observer role;
- missing, duplicate, extra, or reordered attestations;
- an expected head different from the independently verified head;
- an observation kind inconsistent with exact references;
- observation before checkpoint publication;
- receipt after evaluation;
- predecessor corpus substitution;
- final persistence or storage reverification failure.

A structurally valid conflicting-head observation is different: it produces a verified governed abstention.

## Privacy and constitutional boundary

Witness artifacts contain only pseudonymous identifiers, immutable revisions, exact artifact references, observation classifications, timestamps, and notes.

They contain no vote totals, quorum thresholds, consensus percentages, trust scores, ranks, confidence scores, or aggregate CTRT scores.

`verified` means the exact frozen witness graph satisfies the declared identity, reference, ordering, timestamp, and abstention rules. It does not establish real identity, independence, honesty, competence, signatures, trusted time, global publication, universal completeness, which witness is correct, checkpoint uniqueness, adjudication correctness, or content quality.

## Intentionally excluded

- signatures, keys, and certificate chains;
- real identity or independence verification;
- witness reputation or scoring;
- quorum, majority vote, or consensus percentage;
- automatic conflict adjudication;
- live witness or transparency networks;
- external timestamp authorities;
- real witnesses, models, datasets, APIs, frontend, or deployment.

Authorized adjudication of adjudicator-checkpoint witness conflicts is the next bounded governance layer, not part of this one.
