# ADR-0027: Adjudicator revocation checkpoints are prefix proofs

- Status: Accepted
- Date: 2026-08-03

## Context

ADR-0026 represents adjudicator credential status changes as immutable events in a frozen ordered ledger. That preserves the credential, adjudication, fork evidence, rationale, and dissent while permitting deterministic status evaluation at a declared time.

A single frozen ledger proves only its own supplied event population. Across later ledger versions, a consumer also needs to detect omission, reordering, stale heads, and rollback without mutating prior ledgers or introducing a live transparency service.

## Decision

CTRT publishes immutable sequential checkpoints over adjudicator credential revocation ledger states.

Each checkpoint binds:

- the exact revocation-bound predecessor corpus;
- the exact adjudicator revocation ledger;
- the complete ordered event reference population;
- the event count;
- a canonical hash of that ordered population;
- a contiguous sequence number;
- the immediately preceding checkpoint, except at genesis;
- an explicit publication timestamp.

A frozen checkpoint log binds the exact ordered checkpoint population and identifies its final member as the head.

Checkpoint validation requires:

1. sequence numbers contiguous from zero;
2. genesis with no predecessor;
3. every later checkpoint naming the immediately prior checkpoint;
4. every later event population preserving the complete earlier population as an ordered prefix;
5. event counts never decreasing;
6. publication timestamps strictly increasing;
7. no checkpoint verified before publication;
8. the log head matching the current adjudicator revocation ledger exactly.

A checkpoint defect is a structural provenance failure. It produces no verified checkpoint terminal receipt and prevents revocation evaluation.

A valid checkpoint does not determine credential status. It authorizes delegation to the unchanged adjudicator revocation layer, which independently produces execute or governed abstain.

## Consequences

### Positive

- Earlier checkpoint and ledger artifacts remain immutable.
- Omission, reordering, stale heads, and rollback are detectable within the frozen graph.
- The exact event order is inspectable, not represented by a count alone.
- Checkpoint verification is persisted before revocation evaluation.
- Revocation, credential, witness, adjudication, reviewer-revocation, and terminal outcomes remain separate.
- A downstream abstention does not erase successful checkpoint verification.

### Costs

- Every ledger publication adds a checkpoint artifact and a successor log/corpus.
- Consumers must load and verify the complete checkpoint chain.
- Prefix proof size grows with history unless a later compaction design is adopted.
- Publication time remains an artifact claim rather than trusted external time.

## Non-claims

A verified adjudicator revocation checkpoint does not establish:

- cryptographic authorship or signature validity;
- trusted external time;
- public or global publication;
- universal event completeness;
- that no undisclosed alternate checkpoint chain exists;
- issuer trustworthiness;
- credential truthfulness;
- adjudicator identity;
- adjudication correctness;
- checkpoint-head uniqueness outside the frozen graph;
- extraction, review, or analyzer accuracy;
- content quality;
- consensus, confidence, or an aggregate CTRT score.

## Rejected alternatives

### Store only the latest ledger hash

Rejected because a latest hash cannot prove ordered prefix preservation or identify omitted prior events.

### Permit checkpoint replacement

Rejected because replacement destroys the history needed to detect rollback.

### Compare event counts only

Rejected because equal counts may conceal substitution or reordering.

### Accept any earlier checkpoint as the head

Rejected because a stale head can authorize evaluation against an obsolete ledger state.

### Treat checkpoint verification as revocation status

Rejected because publication integrity and operational permission are separate claims.

### Add signatures or a live transparency service now

Deferred. This bounded layer proves consistency inside an immutable artifact graph only.

## Follow-up

A later layer may bind independent witness attestations to adjudicator revocation checkpoint heads, preserving witness disagreement and abstaining on unresolved head conflicts without modifying this checkpoint chain.
