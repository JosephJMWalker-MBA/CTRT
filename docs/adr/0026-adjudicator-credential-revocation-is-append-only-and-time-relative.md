# ADR-0026: Adjudicator credential revocation is append-only and time-relative

- Status: Accepted
- Date: 2026-08-03

## Context

CTRT already binds a witness-conflict adjudicator identity revision and role to an immutable issuer attestation. That attestation is historical evidence: it records what an issuer asserted when the credential was created.

Operational permission may change later. Suspending, revoking, or reinstating authority by editing the original attestation would destroy the distinction between the original assertion and later governance action. Editing the witness-conflict adjudication would be worse: it would retroactively rewrite fork evidence, rationale, selected head, and preserved dissent.

The system therefore needs a separate status-history layer.

## Decision

Adjudicator credential status changes are represented as immutable events in a frozen ordered ledger.

Each event binds:

- the exact credential attestation reference;
- the pseudonymous adjudicator ID;
- the exact issuer ID and revision;
- an explicit effect: `active`, `suspended`, or `revoked`;
- a recording timestamp;
- an effective timestamp;
- a reason;
- the immediately preceding event it supersedes, when one exists.

The original credential and witness-conflict adjudication remain unchanged.

Status is evaluated deterministically as of an explicit experiment timestamp. Events effective after that timestamp remain visible but do not yet change permission.

For each credential, events form one linear chain in ledger order:

1. the first event supersedes nothing;
2. every later event names the immediately prior event;
3. effective timestamps never move backward;
4. all earlier events remain preserved after supersession.

A later `active` event may reinstate permission after suspension or revocation, but it does not erase the earlier event.

A structurally valid ledger state of `suspended` or `revoked` creates a governed abstention before adjudicator credential evaluation, witness adjudication, or analyzer execution.

Structural provenance failures—such as an unknown credential, substituted issuer revision, broken chain, reordered population, or hash mismatch—produce no verified terminal receipt.

## Consequences

### Positive

- The original credential remains inspectable.
- The original adjudication, fork evidence, rationale, and dissent remain inspectable.
- Experiments can reproduce status at a declared historical time.
- Future-effective actions can be published before becoming operational.
- Reinstatement preserves the complete suspension or revocation history.
- Inactive authority stops execution before downstream work.
- Recording time and effective time remain distinct claims.

### Costs

- The ledger is larger than a mutable status field.
- Every consumer must evaluate the ordered event history.
- A frozen ledger proves only the exact supplied event population, not universal completeness.
- Later events require a new ledger and successor corpus artifact.

## Non-claims

A verified adjudicator revocation decision does not establish:

- the adjudicator's legal or real-world identity;
- the issuer's trustworthiness;
- cryptographic authorship;
- trusted external time;
- that every relevant event was disclosed;
- that the adjudication was correct;
- that the selected checkpoint head is globally unique;
- extraction, review, or analyzer accuracy;
- content quality;
- consensus;
- an aggregate CTRT score.

## Rejected alternatives

### Mutate the credential status

Rejected because it erases the original issuer assertion and prevents historical reproduction.

### Mutate or invalidate the adjudication artifact

Rejected because credential permission and adjudication evidence are separate claims. Later status changes must not rewrite preserved fork evidence or dissent.

### Use current wall-clock time implicitly

Rejected because ambient time makes experiments irreproducible. Evaluation requires an explicit timestamp.

### Treat recording time as effective time

Rejected because governance actions may be announced before or after their operational effective time.

### Use event counts or issuer votes

Rejected because status is derived from exact authorized event succession, not aggregation or consensus.

### Query a live revocation service

Deferred. This phase evaluates a frozen append-only artifact graph only.

## Follow-up

A later bounded layer may publish immutable checkpoints over the adjudicator revocation ledger to detect omission, reordering, and rollback between ledger versions without altering this event model.
