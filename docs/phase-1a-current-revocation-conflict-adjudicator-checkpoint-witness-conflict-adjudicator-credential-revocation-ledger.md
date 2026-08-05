# Phase 1A: Current conflict-adjudicator credential revocation ledger

## Purpose

This layer adds append-only status history to the exact issuer-bound
credential introduced by `1.30.0`.

It asks only:

> At a supplied evaluation timestamp, does the exact frozen ordered ledger
> leave the exact credential active under the accepted revocation policy?

## Inputs

The runner requires the exact:

- frozen `1.31.0` revocation-bound corpus;
- frozen `1.30.0` credential corpus;
- frozen `1.29.0` adjudication corpus;
- conflict-adjudicator registry;
- credential issuer registry;
- credential policy;
- credential attestation;
- conflict-adjudication policy and adjudication record;
- revocation policy;
- revocation ledger;
- ordered revocation events;
- frozen experiment plan; and
- experiment run ID and ordered lifecycle timestamps.

## Fixed evidence

```text
revocation policy
  policy.synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation@0.1.0

event
  event.synthetic.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator.suspension.v0.1.0

ledger
  ledger.synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0

successor
  corpus.synthetic-three-items.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.31.0
```

## As-of evaluation

The credential begins with its immutable attested base status. Ordered events
whose `effective_at` timestamp is less than or equal to the evaluation
timestamp are applied according to linear supersession.

The fixed suspension is recorded before ledger freeze but becomes effective
only at:

```text
2027-02-01T00:00:00Z
```

Therefore:

```text
2027-01-31T23:59:59Z -> execute; effective status active
2027-02-01T00:00:00Z -> abstain; effective status suspended
```

## Execution path

### Active as-of status

```text
validate 1.31.0
  -> load and reverify revocation evidence
  -> load and reverify 1.30.0 credential evidence
  -> evaluate status as active
  -> persist revocation decision
  -> derive exact 1.30.0 plan
  -> execute PR #52 unchanged
  -> persist and reverify outer final
```

### Suspended or revoked as-of status

```text
validate 1.31.0
  -> load and reverify all evidence
  -> evaluate status as suspended or revoked
  -> persist revocation abstention decision
  -> do not call PR #52
  -> leave all 28 delegated outcome fields null
  -> persist and reverify terminal abstention
```

## Plan narrowing

Only the corpus reference and matching content list narrow:

```text
1.31.0 plan -> revocation evaluation and outer finalization
1.30.0 plan -> unchanged PR #52 credential lifecycle
1.29.0 plan -> unchanged PR #51 adjudication lifecycle
```

The experiment run ID and ordered content IDs remain unchanged.

## Stored runtime artifacts

A successful outer run stores:

- the revocation decision;
- the optional exact PR #52 receipt/final;
- the outer final marker; and
- references to the exact policy, ledger, events, credential predecessor, and
  adjudication.

The final marker is written last and then reread from storage.

## Tests

The layer verifies:

- exact fixed hashes and schemas;
- exact `1.31.0 -> 1.30.0` ancestry;
- active status before the event boundary;
- suspended abstention at the exact boundary;
- issuer substitution as structural failure;
- event recording after ledger freeze as structural failure;
- deterministic manifest-last reconstruction;
- exact PR #52 delegation under the same run ID;
- no PR #52 final after revocation abstention;
- preservation of a later inherited abstention;
- chronology failure before any runtime decision; and
- exact public exports.

## Non-goals

The layer does not provide a network revocation service, mutable credential
record, certificate authority, distributed consensus protocol, identity proof,
reputation system, confidence score, aggregate trust score, or legal
determination.
