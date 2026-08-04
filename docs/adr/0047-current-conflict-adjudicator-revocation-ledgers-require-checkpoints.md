# ADR-0047: Current conflict-adjudicator revocation ledgers require immutable checkpoints

- Status: Accepted
- Date: 2026-08-04
- Scope: Phase 1A synthetic current checkpoint-witness conflict authority chain

## Context

PR #43 introduced an append-only revocation ledger for the exact credential that authorizes the adjudicator resolving the preserved current checkpoint-witness conflict.

That layer answers:

> According to the exact accepted revocation policy and exact frozen issuer-authored event ledger, what was the effective status of the exact `1.20.0` credential at the declared evaluation time?

It does not, by itself, identify which immutable ledger head a governed execution relied upon.

The complete `1.21.0` graph preserves credential issuance, append-only status events, witness disagreement, witness abstention, fork evidence, dissent, selected head, rationale, adjudication, and every inherited outcome as separate claims. A further provenance boundary must preserve those claims while binding execution to one exact published ledger head.

## Decision

Add a compact `1.22.0` successor over the immutable `1.21.0` revocation corpus.

The successor binds:

- the exact immutable `1.21.0` predecessor;
- one accepted checkpoint policy;
- one frozen ordered checkpoint log;
- the exact final checkpoint head;
- unchanged ordered content IDs;
- one publication timestamp.

The provider-neutral adjudicator-credential revocation checkpoint grammar remains authoritative for policy, checkpoint, log, sequence, ancestry, prefix, event-population, verification-report, and storage behavior.

The context adapter adds only:

- exact `1.21.0` type and hash binding;
- context-specific compact-manifest parsing;
- verification no later than current conflict-adjudicator revocation evaluation;
- manifest-last publication through the existing authority chain.

## Fixed graph

### Checkpoint policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:61a61e18a82575ed5163f2ecc3cc0123f342583e3bbc60fa364d27082e3dadec
```

The policy requires exact event order, prefix-only extension, contiguous sequence numbers, and monotonic checkpoint publication time.

### Genesis checkpoint

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
```

The checkpoint binds:

```text
sequence_number = 0
predecessor_checkpoint_ref = null
event_count = 1
event_population_hash = sha256:620fed6d90310f7cbc73a704cd73350a15125763d59881648dca44305f9eeb8f
published_at = 2026-08-03T19:58:18Z
```

The covered population is the exact future-effective suspension event frozen into the `1.21.0` ledger.

### Frozen checkpoint log

```text
log.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:5f9dde79fcffcafd0372229262b5e6cd9fdc148ff63750134f6467d77497b48b
```

Its declared head equals its final checkpoint.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.22.0
sha256:3ef12c528781ddec9976323b8a23670f3592839ce2145afed60cda39170c0304
```

## Invariants

A valid checkpoint chain requires:

1. sequence numbers beginning at zero and remaining contiguous;
2. no predecessor at genesis;
3. exact immediate-predecessor binding after genesis;
4. exact preservation of every earlier ordered event prefix;
5. nondecreasing event counts;
6. strictly increasing publication timestamps;
7. checkpoint references matching canonical checkpoint bytes;
8. log-head equality with the final checkpoint;
9. exact equality among the protected `1.21.0` corpus, frozen ledger, ordered event population, and declared checkpoint head;
10. checkpoint verification no later than current conflict-adjudicator revocation evaluation.

A malformed chain is a structural failure. It is not a governed abstention because the system cannot establish which evidence head it is evaluating.

## Execution order

```text
1.22.0 checkpoint validation
  -> checkpoint verification report persistence
  -> exact 1.21.0 plan derivation
  -> unchanged PR #43 revocation lifecycle
  -> outer checkpoint finalization
```

The experiment run ID, experiment identity, version, parameters, content order, and all inherited evidence remain unchanged.

## Independent claims

This layer preserves separately:

```text
checkpoint status                          -> whether the exact 1.21.0 ledger head is structurally verified
current conflict-adjudicator revocation    -> whether append-only status history permits credential evaluation
current conflict-adjudicator credential    -> whether the resolving authority is issuer-authorized and valid
conflicting witness outcome                -> the preserved required-population abstention
current conflict adjudication              -> the accepted authority's separate resolution
current and inherited governance outcomes  -> every lower checkpoint, revocation, credential, witness, and adjudication result
terminal outcome                           -> whether the complete governed lifecycle executed
```

No later result rewrites an earlier evidentiary or authority claim.

## Consequences

### Positive

- governed execution identifies the exact `1.21.0` ledger head it relied upon;
- checkpoint provenance remains inspectable independently from credential status;
- a verified checkpoint remains visible when PR #43 later abstains on effective suspension;
- structural checkpoint failure prevents every PR #43 runtime artifact;
- future checkpoint extensions can prove prefix continuity without rewriting the original ledger or event;
- provider-neutral checkpoint semantics are reused rather than forked.

### Costs

- the authority chain adds another compact successor and outer lifecycle;
- real-chain tests require the complete PR #30 through PR #43 evidence graph;
- runtime chronology must distinguish checkpoint publication, verification, revocation evaluation, delegated completion, and outer completion.

## Trust boundary

Checkpoint verification does not establish:

- completeness of the issuer-authored ledger beyond its exact frozen population;
- absence of undisclosed events or alternate checkpoint chains;
- global checkpoint uniqueness or public availability;
- legal or real-world adjudicator, issuer, or witness identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- issuer, adjudicator, or witness independence, competence, honesty, or correctness;
- correctness of the disagreement resolution or selected checkpoint;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, analyzer, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

## Deferred work

The next bounded successor may add immutable named-witness observations over the exact `1.22.0` checkpoint head.

Such a layer must preserve the checkpoint report, the complete `1.21.0` revocation graph, the `1.20.0` credential, the `1.19.0` disagreement and adjudication record, fork evidence, dissent, selected head, rationale, and every inherited artifact unchanged.