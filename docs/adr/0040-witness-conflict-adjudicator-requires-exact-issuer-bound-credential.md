# ADR-0040: Witness-conflict adjudicator requires an exact issuer-bound credential

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0039 preserved an exact checkpoint-witness disagreement and authorized a governed response through a separately recorded conflict adjudication.

The `1.14.0` graph therefore contains three distinct facts:

```text
checkpoint witness outcome = abstain
resolution status          = resolved
adjudication outcome       = execute
```

That graph binds a pseudonymous adjudicator identity revision and the role `witness_conflict_adjudicator`, but it does not establish that an accepted issuer authorized that exact identity revision to perform that role during the adjudication interval.

Treating registry membership as credential evidence would collapse two separate governance claims:

1. the registry recognizes an adjudicator identity and role;
2. an accepted issuer issued a current credential authorizing that exact identity revision and role.

The second claim requires its own immutable evidence and fail-closed decision.

## Decision

CTRT will publish an append-only `1.15.0` credential layer over the exact immutable `1.14.0` disagreement and adjudication graph.

The layer will:

1. preserve `1.14.0` unchanged as the credential predecessor;
2. bind an accepted synthetic credential-issuer registry;
3. bind an accepted credential policy to the exact `1.14.0` conflict-adjudicator registry;
4. require an exact credential type;
5. require the exact pseudonymous adjudicator ID and identity revision used by the adjudication record;
6. require the exact role `witness_conflict_adjudicator`;
7. evaluate the half-open interval `valid_from <= evaluated_at < valid_until`;
8. abstain on not-yet-valid, expired, suspended, or revoked credential state;
9. treat identity, issuer, type, role, subject-reference, policy, or manifest drift as structural failure;
10. publish issuer registry, policy, and credential before the compact `1.15.0` manifest;
11. persist the run-specific credential decision before any predecessor execution;
12. invoke the unchanged PR #36 lifecycle only when the current credential outcome is `execute`;
13. narrow only the corpus reference and unchanged ordered content population from `1.15.0` to `1.14.0` during delegation;
14. preserve current credential, witness, adjudication, predecessor, revocation, inherited credential, inherited witness, inherited adjudication, and terminal outcomes separately.

## Fixed graph

```text
1.14.0 preserved disagreement and adjudication
  → accepted credential issuer registry
  → accepted exact-role credential policy
  → immutable credential for the exact adjudicator identity revision
  → 1.15.0 credential-bound successor
```

Fixed hashes:

```text
issuer registry   = sha256:6d6f0690afa8d0d3817e5d64e15654487e469c00abb7e215be5f22e323f07a15
credential policy = sha256:b25e1aea19f4d5865fdce15a3f2739e7b45d4e028c1bbfd346d0a20cdfe66adf
credential        = sha256:e992110c0dadc3990406485d6b666977f68d74b78417b477ea255875fc3a7c0d
1.15.0 successor  = sha256:feb13271bed910f480e5ae0af730e4b68ff8636a7172a3f6b4a0c3bd0d51b542
```

The credential authorizes:

```text
adjudicator_id = adjudicator.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
identity_revision = synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
```

## Semantic separation

The canonical path preserves all three predecessor claims and adds a fourth:

```text
checkpoint witness outcome = abstain
resolution status          = resolved
adjudication outcome       = execute
credential outcome         = execute
```

Credential execution does not make the witnesses agree, erase fork evidence or dissent, validate the selected checkpoint as externally true, or prove the adjudicator's reasoning correct.

## Delegation

```text
1.15.0 plan → current credential decision and outer finalization
1.14.0 plan → unchanged PR #36 lifecycle after credential execution
```

A current credential abstention is terminal for this layer. The credential decision remains stored, and PR #36 is not invoked.

## Chronology

```text
2026-08-03T19:57:21Z  1.14.0 predecessor published
2026-08-03T19:57:30Z  credential issuer registry created
2026-08-03T19:57:31Z  credential policy created
2026-08-03T19:57:32Z  credential issued
2026-08-03T19:57:33Z  credential becomes valid
2026-08-03T19:57:34Z  1.15.0 successor published
2026-08-03T19:57:35Z  canonical credential evaluation
```

The credential expires at the half-open boundary `2027-08-03T19:57:33Z`; evaluation at that instant abstains.

## Consequences

The system can distinguish:

- preserved witness disagreement;
- authorized conflict adjudication;
- issuer-bound role authorization for the exact adjudicator identity revision;
- later revocation evidence for that credential;
- every inherited governance and terminal outcome.

No later outcome rewrites an earlier claim.

This ADR does **not** establish credential non-revocation. The credential document's current status field is evaluated as supplied evidence, but an append-only revocation ledger, revocation events, and their independent evaluation remain a later bounded layer.

It also does not establish legal identity, real-world issuer identity, cryptographic authorship, private-key possession, trusted external time, issuer or adjudicator independence, competence, honesty, correctness, checkpoint truth, global uniqueness, public availability, majority support, quorum, consensus, confidence, reputation, content accuracy, model accuracy, deployment, or an aggregate CTRT score.
