# ADR-0042: Current adjudicator revocation ledgers require immutable checkpoints

- Status: Accepted
- Date: 2026-08-04
- Scope: Phase 1A synthetic checkpoint-fork adjudicator authority chain

## Context

PR #38 introduced an append-only revocation ledger for the exact credential that authorizes the adjudicator resolving the current checkpoint-witness disagreement.

That layer can answer:

> What was the effective status of the exact credential at the declared evaluation time according to the exact frozen issuer-authored history?

It does not, by itself, identify which immutable ledger head a governed execution relied upon.

A ledger can remain immutable while later checkpoints identify different published heads. Execution therefore needs a separate provenance statement that binds the exact corpus, exact ledger, complete ordered event population, and exact checkpoint chain before the revocation decision is evaluated.

## Decision

Add a compact `1.17.0` successor over the immutable `1.16.0` revocation corpus.

The successor binds:

- the exact immutable `1.16.0` predecessor;
- one accepted checkpoint policy;
- one frozen ordered checkpoint log;
- the exact final checkpoint head;
- unchanged ordered content IDs;
- one publication timestamp.

The generic adjudicator-credential revocation checkpoint grammar remains authoritative for policy, checkpoint, log, sequence, ancestry, prefix, event-population, verification-report, and storage behavior.

The context adapter adds only:

- exact `1.16.0` type and hash binding;
- context-specific compact-manifest parsing;
- verification no later than current revocation evaluation;
- manifest-last publication through the current authority chain.

## Fixed graph

### Checkpoint policy

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:ce8fe8e454f9563a613eaeac66b528bf3e2800076e5f47cb0f2a91d11f9daf7f
```

The policy requires exact event order, prefix-only extension, contiguous sequence numbers, and monotonic checkpoint publication time.

### Genesis checkpoint

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:245efb3279bc1b10c5ffafa337665a947a8dd86e9693590cccf09a6021d829a2
```

The checkpoint binds:

```text
sequence_number = 0
predecessor_checkpoint_ref = null
event_count = 1
event_population_hash = sha256:f5a6ad7173450c58ef5d0695886eced35a79afbe55df0bf29b72a1807ad5aefc
published_at = 2026-08-03T19:57:41Z
```

The covered population is the exact future-effective suspension event frozen into the `1.16.0` ledger.

### Frozen checkpoint log

```text
log.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:45e9330da82ddf1295a07cd0f763c1447a9cbfccc716b20f590d94113409aa24
```

Its declared head equals its final checkpoint.

### Successor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.17.0
sha256:e801447e9d897baa442effd11f2a1d059624e05d7286ad7ec2bc3761e328849d
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
8. log head equality with the final checkpoint;
9. exact equality among the protected revocation corpus, frozen ledger, ordered event population, and declared checkpoint head;
10. checkpoint verification no later than current revocation evaluation.

A malformed chain is a structural failure. It is not a governed abstention because the system cannot establish which evidence head it is evaluating.

## Execution order

```text
1.17.0 checkpoint validation
  -> checkpoint verification report persistence
  -> exact 1.16.0 plan derivation
  -> unchanged PR #38 current revocation lifecycle
  -> outer checkpoint finalization
```

The experiment run ID, experiment identity, version, parameters, content order, and all inherited evidence remain unchanged.

## Independent claims

This layer preserves separately:

```text
checkpoint status            -> whether the exact ledger head is structurally verified
current revocation outcome   -> whether current append-only status history permits credential evaluation
current credential outcome   -> whether current authority is issuer-authorized and valid
current witness outcome      -> what current named witnesses reported
current adjudication outcome -> what current accepted authority selected
inherited outcomes           -> every lower checkpoint, revocation, credential, witness, and adjudication result
terminal outcome             -> whether the complete governed lifecycle executed
```

No later result rewrites an earlier evidentiary claim.

## Consequences

### Positive

- governed execution identifies the exact ledger head it relied upon;
- ledger provenance is inspectable independently from effective credential status;
- a verified checkpoint remains visible when current or inherited revocation later abstains;
- structural checkpoint failure prevents every downstream decision;
- future checkpoint extensions can prove prefix continuity without rewriting the original ledger or event;
- provider-neutral checkpoint semantics are reused rather than forked.

### Costs

- the authority chain adds another compact successor and outer lifecycle;
- real-chain tests require the complete PR #30 through PR #38 evidence graph;
- run chronology must distinguish checkpoint publication, verification, revocation evaluation, and later downstream completion.

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

The next bounded successor may add immutable named-witness observations over the exact `1.17.0` checkpoint head. Such a layer must preserve the checkpoint report, `1.16.0` revocation decision, `1.15.0` credential graph, `1.14.0` disagreement and adjudication record, fork evidence, dissent, selected head, and every inherited artifact unchanged.
