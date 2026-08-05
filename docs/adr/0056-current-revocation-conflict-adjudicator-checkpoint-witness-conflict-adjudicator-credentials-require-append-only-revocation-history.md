# ADR-0056: Current conflict-adjudicator credentials require append-only revocation history

## Status

Accepted.

## Context

The frozen `1.30.0` corpus binds one issuer-bound credential to the exact
adjudicator identity revision and `witness_conflict_adjudicator` role used by
the immutable `1.29.0` conflict adjudication.

That credential is itself immutable. Its stored `status: active` field records
the attestation state when issued; it must not be edited later to represent a
suspension or revocation. Replacing the credential would erase the distinction
between:

- what the issuer originally attested;
- what later status event was recorded;
- when that event became operationally effective; and
- what status was used by a particular experiment run.

A deterministic append-only status history is therefore required before the
`1.30.0` lifecycle can execute.

## Decision

Introduce a compact frozen `1.31.0` successor that binds:

1. the exact immutable `1.30.0` credential corpus;
2. one accepted revocation policy;
3. one ordered frozen revocation ledger; and
4. the exact immutable event records named by that ledger.

The bounded question is:

> At the evaluation timestamp, does the exact ordered append-only ledger leave
> the exact `1.30.0` credential active under the exact accepted policy?

No credential, adjudication, witness, checkpoint, revocation, fork-evidence, or
dissent record inherited from `1.30.0` is modified.

## Exact graph

```text
predecessor 1.30.0 = sha256:a9ece983cac8c81dee0bfd61df4cd396ea03eb1df339c0ef6cc43e0604b39209
revocation policy = sha256:de02d6e7c97ce0a10ce677fd1ac780b8e6d649b3af785b452ea801ac5ef65a5c
suspension event  = sha256:fdb64b1bb3ecade16236f3031578d599f84edc114cd9852eb1ccb0fd3046ac8c
frozen ledger     = sha256:c5b57e6345dd16f4b37d98ab858a114dca0d43ee405843db84580a35b3396665
successor 1.31.0  = sha256:74b4ffaa1b3d4be26331f1543928526633c3adc3f820c47eed09a7bb9af7c0c1
```

## Event semantics

The fixed event records a future-effective suspension:

```text
recorded_at  = 2026-08-03T19:59:15Z
effective_at = 2027-02-01T00:00:00Z
effect       = suspended
```

The event is bound to the exact credential attestation, adjudicator ID, issuer
ID, and issuer revision.

Before the effective boundary, the event remains visible but does not change
the as-of status. At the exact effective boundary, the status becomes
`suspended` and the revocation gate returns governed abstention.

## Ordering and supersession

The policy requires:

- permitted effects limited to `active`, `suspended`, and `revoked`;
- exact attestation issuer authority;
- monotonic effective timestamps;
- linear supersession;
- explicit ordered event references; and
- governed abstention for `suspended` or `revoked` status.

No majority, quorum, consensus, confidence, reputation, trust score, or
aggregate status is computed.

## Chronology

```text
1.30.0 successor published  2026-08-03T19:59:13Z
revocation policy published 2026-08-03T19:59:14Z
event recorded              2026-08-03T19:59:15Z
ledger frozen               2026-08-03T19:59:16Z
1.31.0 successor published  2026-08-03T19:59:17Z
revocation evaluated        2026-08-03T19:59:18Z or later
PR #52 lifecycle            only after revocation execute
```

Every event must be recorded no earlier than policy publication and no later
than ledger freeze. The ledger must be frozen before the `1.31.0` successor is
published. Evaluation must occur after publication.

## Persistence order

The append-only publication order is:

```text
exact 1.30.0 predecessor
  -> revocation policy
  -> ordered event records
  -> frozen ledger
  -> compact 1.31.0 manifest last
```

The runtime order is:

```text
load exact 1.31.0 graph
  -> reverify exact 1.30.0 credential evidence
  -> evaluate ordered status history as of the supplied timestamp
  -> persist the revocation decision
  -> abstain or derive the exact 1.30.0 plan
  -> execute PR #52 unchanged under the same run ID
  -> preserve every delegated outcome separately
  -> persist the outer final marker
  -> reread and verify complete storage
```

## Outcome preservation

The final record preserves separately:

- the new current conflict-adjudicator credential revocation outcome;
- the PR #52 credential outcome;
- the four PR #51 conflict-resolution outcomes;
- all twenty-three inherited PR #50 and earlier outcome/status fields; and
- the terminal review outcome.

The new revocation result is not allowed to overwrite or summarize any
delegated result.

## Structural failure

The layer fails closed, without producing a governed abstention artifact, for:

- predecessor or content-order drift;
- revocation policy, ledger, event, credential, issuer, adjudicator, or
  adjudication substitution;
- missing, duplicate, reordered, or unreferenced event evidence;
- invalid issuer authority;
- non-monotonic effective time;
- non-linear supersession;
- event recording after ledger freeze;
- ledger or manifest chronology inversion;
- experiment run mismatch;
- stored-artifact or hash drift;
- noncanonical serialization; or
- closed-schema violation.

## Governed abstention

A structurally valid `suspended` or `revoked` as-of result is a governed
abstention. It persists the revocation decision and outer final marker, creates
no PR #52 runtime final, and leaves every downstream outcome field null.

## Trust boundary

This layer does not establish:

- real-world or legal identity;
- cryptographic authorship;
- issuer or adjudicator independence;
- issuer competence, honesty, or correctness;
- completeness or timeliness of the real-world revocation history;
- absence of omitted, delayed, or conflicting events;
- trusted external time;
- adjudication or witness correctness;
- checkpoint truth or ledger completeness beyond the stored graph;
- consensus, confidence, reputation, aggregate trust, analytical accuracy,
  deployment readiness, or a CTRT score.

It establishes only that the exact stored ordered event graph produced the
recorded deterministic as-of status under the exact accepted policy.

## Consequences

The original credential remains immutable and inspectable. Status changes are
represented as separate evidence. Experiment runs can reconstruct exactly which
events existed, which were operationally effective, and why execution proceeded
or abstained.

A later checkpoint may commit the exact frozen `1.31.0` ledger head. That
checkpoint must not reopen the credential or revocation decision, and further
governance layers must remain subject to an explicit finite completion
criterion rather than recurse indefinitely.
