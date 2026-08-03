# ADR-0032: Checkpoint-conflict adjudicator revocation ledgers require immutable checkpoints

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0031 introduced append-only, time-relative revocation history for the issuer-bound credential used by the adjudicator who may resolve an adjudicator-checkpoint witness conflict.

That ledger establishes which immutable events were declared and how they affect the credential at an explicit evaluation time. It does not independently establish that a verifier selected the intended frozen ledger head or that the head covers the complete ordered event population declared by that ledger revision.

A mutable pointer to a current head would weaken reconstruction. Re-reading the ledger alone would not preserve a publication sequence across later ledger revisions. The next bounded question is therefore:

> Does the exact immutable checkpoint chain prove that the exact `1.6.0` revocation corpus and frozen ledger head were published with complete ordered event coverage?

This question remains independent of whether every real-world event was disclosed, whether the issuer is trustworthy, whether the credentialed adjudicator was correct, or whether the checkpoint has external witnesses.

## Decision

CTRT will bind the checkpoint-conflict adjudicator credential revocation ledger to an immutable, ordered checkpoint chain.

The layer will:

1. reuse the established generic adjudicator credential revocation checkpoint policy, checkpoint, log, verification report, and continuity contracts;
2. bind each checkpoint to the exact revocation corpus, exact frozen ledger revision, and exact ordered event references;
3. require contiguous sequence numbers beginning at zero;
4. require each non-genesis checkpoint to reference its immediate predecessor;
5. require every later checkpoint to preserve the complete prior event prefix without omission or reordering;
6. require monotonically increasing publication time;
7. require the frozen checkpoint-log head to equal the exact current ledger event population;
8. persist a run-specific checkpoint verification report before the ADR-0031 revocation runner may execute;
9. preserve checkpoint verification separately from the later revocation, credential, witness, adjudication, reviewer, and analyzer outcomes;
10. fail closed on missing, altered, stale, future-dated, or structurally inconsistent checkpoint evidence.

The initial synthetic chain contains one genesis checkpoint. That checkpoint covers the exact single-event ledger introduced by ADR-0031.

## Successor-manifest boundary

The new corpus is a compact manifest:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-bound@1.7.0
```

It binds:

- the exact canonical `1.6.0` revocation-bound predecessor;
- the exact accepted checkpoint policy;
- the exact frozen checkpoint log;
- the exact checkpoint head;
- the unchanged ordered content population.

The outer checkpoint decision is evaluated against a frozen plan bound to `1.7.0`.

After successful checkpoint verification, the runner derives a narrowly scoped nested plan bound to the exact immutable `1.6.0` predecessor and invokes the unchanged ADR-0031 runner:

```text
1.7.0 plan -> checkpoint verification and outer finalization
1.6.0 derived plan -> unchanged revocation and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidates, analyzers, execution windows, and all prior governance evidence remain unchanged. Only the corpus reference is explicitly narrowed to the predecessor required by the delegated runner.

## Checkpoint semantics

A checkpoint is a claim about publication continuity and exact ledger coverage. It is not a second revocation decision.

The genesis checkpoint records:

- sequence number `0`;
- no predecessor checkpoint;
- the exact `1.6.0` revocation corpus reference;
- the exact frozen ledger reference;
- the exact ordered event references;
- event count and deterministic event-population hash;
- an explicit publication timestamp.

A verified checkpoint proves that the declared immutable graph satisfies the accepted continuity rules. It does not prove external observation or completeness beyond the declared graph.

## Failure boundaries

Structural failure includes:

- plan or content-order drift;
- substituted checkpoint policy, log, head, ledger, corpus, or artifact references;
- non-contiguous sequence numbers;
- an invalid genesis predecessor;
- a missing immediate predecessor;
- event omission, rollback, or reordering;
- a stale ledger reference;
- a checkpoint head that does not equal the current ledger population;
- non-increasing publication time;
- verification before publication;
- missing or altered stored artifacts;
- report, final-manifest, or reread failure.

Checkpoint verification has no ordinary abstention outcome. A structurally invalid checkpoint graph is an error. Once checkpoint verification succeeds, the delegated ADR-0031 runner may still produce governed revocation abstention when the credential's as-of status is `suspended` or `revoked`.

## Append-only publication order

Publication is manifest-last:

1. checkpoint policy;
2. immutable checkpoints;
3. frozen checkpoint log;
4. compact `1.7.0` successor manifest.

No `1.6.0` or earlier artifact is edited.

## Consequences

### Positive

- the exact ledger head and its ordered event coverage become independently inspectable;
- later checkpoints can preserve prior event prefixes without rewriting history;
- checkpoint verification occurs before the revocation decision can affect execution;
- a valid checkpoint remains visible even when the later revocation decision produces terminal abstention;
- generic checkpoint semantics are reused rather than forked;
- the `1.7.0`/`1.6.0` delegation boundary is explicit and testable.

### Costs

- callers must carry checkpoint policy, log, population, head, and verification time;
- the outer runner must preserve another exact plan scope;
- checkpoint publication adds artifacts without establishing external witness agreement;
- JSON timestamps and publisher claims are not cryptographic or externally trusted time.

## Non-claims

Verification does not establish:

- legal or real-world identity;
- issuer or checkpoint-publisher trustworthiness;
- cryptographic authorship;
- trusted external time;
- complete real-world event disclosure;
- external observation of the checkpoint;
- checkpoint consensus, quorum, majority support, or reputation;
- adjudicator honesty, independence, competence, or correctness;
- which witness was truthful;
- global uniqueness of the checkpoint head;
- content, extraction, model, or analyzer accuracy;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may add attestations from declared witnesses over the exact `1.7.0` checkpoint head. Witness conflicts, signatures, keys, certificate chains, identity providers, external transparency services, and consensus mechanisms remain separate future decisions.
