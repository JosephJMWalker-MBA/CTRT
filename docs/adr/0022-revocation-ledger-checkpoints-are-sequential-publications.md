# ADR-0022: Revocation ledger checkpoints are immutable sequential publications

- Status: Accepted
- Date: 2026-08-03

## Context

ADR-0021 established immutable credential-revocation events and deterministic status evaluation from one frozen ordered ledger. That proves what a particular ledger artifact contains, but it does not by itself preserve an inspectable sequence of published ledger states.

Without explicit checkpoints, a later publisher could present a shorter ledger, reorder earlier events, omit an event from a later view, or substitute a different head without leaving a first-class canonical record of the discontinuity.

CTRT needs a bounded integrity layer that detects these changes before revocation-gated execution. This layer must remain dependency-free and must not claim the guarantees of a cryptographically signed or globally witnessed transparency service.

## Decision

CTRT will represent revocation-ledger publication continuity with immutable sequential checkpoint artifacts.

A checkpoint binds:

- one exact revocation-bound predecessor corpus;
- one exact revocation-ledger reference;
- the complete ordered event-reference population visible at publication;
- an explicit event count;
- a hash of that ordered event population;
- a zero-based sequence number;
- the immediately preceding checkpoint reference, or `null` for genesis;
- a publication timestamp.

A frozen checkpoint log binds an accepted checkpoint policy, the complete ordered checkpoint population, and one exact head checkpoint.

The checkpoint-bound corpus is a distinct append-only successor artifact. Version `0.7.0` retains the complete prior governance graph and adds exact references to:

- the `0.6.0` revocation-bound predecessor corpus;
- the checkpoint policy;
- the frozen checkpoint log;
- the head checkpoint.

## Required validation

Before downstream revocation evaluation, CTRT must verify:

1. the experiment plan exactly matches the checkpoint-bound corpus;
2. the checkpoint policy is accepted;
3. the checkpoint log is frozen and bound to that policy;
4. the stored checkpoint population exactly matches the log;
5. checkpoint sequence numbers are contiguous from zero;
6. the genesis checkpoint has no predecessor;
7. each later checkpoint names its immediate predecessor;
8. each later ordered event population contains the prior population as an exact prefix;
9. event counts never decrease;
10. checkpoint publication times strictly increase;
11. no checkpoint is evaluated before its publication time;
12. the log head is the final checkpoint;
13. the head binds the exact `0.6.0` predecessor corpus;
14. the head binds the exact current revocation ledger;
15. the head event references, order, and count exactly match that ledger.

Omission, reordering, rollback, sequence gaps, broken predecessor links, future publication, or a stale/substituted head are structural failures. They do not produce a governed abstention because there is no valid checkpoint proof to authorize the downstream lifecycle.

## Execution boundary

After successful validation, CTRT persists and reverifies a run-specific checkpoint-verification report before invoking the existing revocation-gated runner.

A valid checkpoint chain does not force execution. The downstream revocation ledger may still produce a governed abstention, and later credential, review, quality, or analyzer boundaries remain independent.

The final checkpoint-gated artifact therefore preserves:

- the checkpoint-verification evidence;
- the downstream revocation outcome;
- the ultimate terminal outcome;
- the exact downstream revocation final reference.

If downstream execution later fails, the already-persisted checkpoint-verification report and any earlier verified content receipts remain append-only evidence. No checkpoint-gated completion is created.

## Consequences

### Positive

- Published ledger states become explicit canonical artifacts.
- Omission, reordering, and rollback within the supplied checkpoint chain are detectable.
- A stale checkpoint head cannot authorize a newer ledger.
- Historical publication states remain inspectable rather than overwritten.
- Revocation status and publication continuity remain separate claims.
- Existing revocation, credential, review, quality, and analysis semantics remain unchanged.

### Costs

- Each ledger publication adds checkpoint and log artifacts.
- Corpus evolution adds another explicit proof layer and artifact identity.
- A publisher must preserve and supply the complete checkpoint chain under evaluation.
- Validation remains linear in the number of checkpoints and event references.

## Trust boundary and non-claims

A verified checkpoint chain means that the exact supplied policy, corpus, log, checkpoints, predecessor links, ordered event populations, timestamps, and current ledger relationship were checked and reverified from append-only storage.

It does **not** establish:

- that every real revocation event was disclosed;
- that no unpublished checkpoint or conflicting fork exists;
- that the publisher is honest;
- that any independent party observed the checkpoint;
- external timestamp authority;
- cryptographic signature authenticity;
- public transparency-log inclusion;
- global consistency across observers;
- reviewer identity, competence, or correctness;
- extraction or analyzer accuracy;
- content quality or an aggregate CTRT score.

## Intentionally excluded

- digital signatures and key management;
- Merkle trees and inclusion proofs;
- live transparency services;
- witness gossip or fork reconciliation;
- network publication and polling;
- multiple competing checkpoint authorities;
- private identity attributes;
- real reviewers, models, extractors, or datasets.

## Alternatives considered

### Treat the ledger hash as the checkpoint

Rejected. A single ledger hash identifies one state but does not express predecessor continuity or prove that later states preserve earlier ordered populations.

### Mutate one latest-checkpoint record

Rejected. Mutation would erase publication history and violate CTRT's append-only governance model.

### Convert checkpoint failure into abstention

Rejected. Abstention is a valid governed result. A broken checkpoint chain is invalid provenance and must fail structurally.

### Implement a cryptographic transparency log now

Deferred. Signatures, key rotation, Merkle proofs, witnesses, and fork detection require a substantially larger trust and operational model than this bounded dependency-free phase.
