# Phase 1A: Current revocation-checkpoint conflict-adjudicator revocation checkpoint

## Bounded question

> Does the exact accepted immutable checkpoint cover the exact ordered event
> prefix and exact `1.26.0` revocation-ledger head before revocation evaluation?

This layer does not decide whether the underlying adjudication is correct. It
does not establish global ledger completeness. It verifies one exact immutable
checkpoint graph and then delegates unchanged to PR #48.

## Immutable inputs

- predecessor `1.26.0`:
  `sha256:05c322ff072be8b63868d7b8aad77aa69752ce92eef5e66ab88d169156e515f8`
- checkpoint policy:
  `sha256:330a38347de9c667b784e04f8dc58e219066d482f9370b0ccb06c2191aa4139f`
- ordered event population:
  `sha256:85d78e0e0cd731cf45fad9ad3ddf6f702e6c2b790f8f999a097dd38e90af68e4`
- genesis checkpoint:
  `sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12`
- frozen checkpoint log:
  `sha256:c3a20a2895b80e4cba990842dc9229984fa03399040ba4192dd90f1b4ff42670`
- successor `1.27.0`:
  `sha256:e3e288981f17b308bf5f844cd84633b2e79c67103f6c31b6f13dc89fca672e21`

## Files

- candidate checkpoint policy;
- genesis checkpoint;
- frozen checkpoint log;
- compact `synthetic-corpus.v1.27.0.json`;
- closed successor schema;
- typed checkpoint adapter;
- checkpoint-gated runner;
- closed final schema;
- contract, lifecycle, and public API tests;
- ADR-0052.

## Publication chronology

```text
1.26.0 successor             2026-08-03T19:58:45Z
checkpoint policy            2026-08-03T19:58:47Z
genesis checkpoint           2026-08-03T19:58:49Z
checkpoint log frozen        2026-08-03T19:58:51Z
1.27.0 successor             2026-08-03T19:58:52Z
checkpoint verification      2026-08-03T19:58:53Z or later
revocation evaluation        after checkpoint verification
```

The future-effective suspension remains visible in the event prefix but does
not become effective until `2027-02-01T00:00:00Z`.

## Runtime contract

1. preflight exact plan, predecessor, policy, log, head, run ID, and chronology;
2. storage-load exact checkpoint evidence;
3. verify contiguous chain and exact ordered event prefix;
4. persist the checkpoint report;
5. narrow only the corpus reference from `1.27.0` to `1.26.0`;
6. invoke PR #48 unchanged under the same experiment run ID;
7. preserve every PR #48 and inherited outcome separately;
8. finalize and reread every referenced artifact.

## Outcome preservation

Checkpoint verification has no scalar score and no vote. Successful
verification permits the unchanged PR #48 lifecycle.

Before the suspension boundary, the delegated revocation layer may execute.
At or after the suspension boundary, PR #48 may abstain. In both cases, the
checkpoint remains verified and the delegated terminal result remains separate.

Checkpoint mismatch, missing evidence, chronology drift, or storage drift is a
structural failure. It does not produce a governed checkpoint abstention.

## Review invariants

- exact `1.26.0` predecessor;
- exact ledger reference;
- exact ordered event prefix;
- exact event-population hash;
- contiguous sequence beginning at zero;
- null predecessor for genesis;
- log head equals the final checkpoint;
- manifest-last deterministic reconstruction;
- report persistence before PR #48;
- exact `1.27.0 -> 1.26.0` plan narrowing;
- unchanged experiment run ID;
- no confidence, quorum, vote, or aggregate score;
- every delegated outcome remains separately inspectable.

## Explicit exclusions

The layer does not prove global completeness, external trusted time,
cryptographic authorship, real-world identity, independence, correctness,
consensus, reputation, confidence, deployment, or an aggregate CTRT score.
