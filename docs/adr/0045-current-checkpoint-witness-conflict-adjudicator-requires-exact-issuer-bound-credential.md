# ADR-0045: Current checkpoint-witness conflict adjudicator requires an exact issuer-bound credential

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0044 preserved the exact `1.18.0` checkpoint-witness disagreement and added a separately recorded `1.19.0` adjudication.

That graph contains three distinct claims:

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
```

The graph names a pseudonymous adjudicator identity revision and the role `witness_conflict_adjudicator`. Registry membership establishes that the accepted registry recognizes that identity and role. It does not establish that an accepted issuer authorized the exact identity revision to perform that role during the adjudication interval.

Collapsing registry recognition and credential authorization would erase an independently testable governance boundary.

## Decision

CTRT will publish an append-only `1.20.0` credential layer over the exact immutable `1.19.0` conflict and adjudication graph.

The layer will:

1. preserve `1.19.0` unchanged as the credential predecessor;
2. bind an accepted synthetic credential-issuer registry;
3. bind an accepted credential policy to the exact `1.19.0` conflict-adjudicator registry;
4. require the exact credential type `ctrt.current-checkpoint-witness-conflict-adjudicator-role`;
5. require the exact adjudicator ID and identity revision used by the immutable adjudication record;
6. require the exact role `witness_conflict_adjudicator`;
7. evaluate the half-open interval `valid_from <= evaluated_at < valid_until`;
8. abstain on not-yet-valid, expired, suspended, or revoked credential state;
9. treat predecessor, content-order, identity, issuer, type, role, subject-reference, policy, credential population, chronology, or storage drift as structural failure;
10. publish issuer registry, policy, and credential before the compact `1.20.0` manifest;
11. persist the run-specific credential decision before any `1.19.0` execution;
12. invoke the unchanged PR #41 lifecycle only when the current credential outcome is `execute`;
13. narrow only the corpus reference and unchanged ordered content population from `1.20.0` to `1.19.0` under the same experiment run ID;
14. preserve the credential decision and every PR #41 outcome separately.

## Fixed graph

```text
1.19.0 preserved conflict and adjudication
  → accepted credential issuer registry
  → accepted exact-role credential policy
  → immutable credential for the exact adjudicator identity revision
  → 1.20.0 credential-bound successor
```

Fixed hashes:

```text
issuer registry   = sha256:1c13ed78af7964464be460350c06ce32097e2e58c718c0f2b6a2d4fff6296fe8
credential policy = sha256:ef4953a1c33f07e4e31aab2b5a0f7784c99354b147286a9c45bdd24ecd899526
credential        = sha256:6c538f6ac902906ebbea7e59155e183fdaf8dd0ec37eb2848d1bd7f07433efa6
1.20.0 successor  = sha256:8cba471df7daa5664a87822fb8fad5a68b10b19422129ee266224f153ede5f20
```

The credential authorizes:

```text
adjudicator_id = adjudicator.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
identity_revision = synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
role = witness_conflict_adjudicator
```

## Semantic separation

Canonical execution preserves four independent claims:

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
credential outcome          = execute
```

Credential execution does not make witnesses agree, remove fork evidence or dissent, validate the adjudication rationale, prove the selected checkpoint externally true, or establish later non-revocation.

Credential abstention does not invalidate the immutable adjudication record. It only withholds authorization to execute that predecessor lifecycle through this new boundary.

## Delegation

```text
1.20.0 plan → current credential decision and outer finalization
1.19.0 plan → unchanged PR #41 lifecycle after credential execution
```

A credential abstention is terminal for this layer. The decision remains stored and PR #41 is not invoked.

## Chronology

```text
2026-08-03T19:58:00Z  1.19.0 predecessor published
2026-08-03T19:58:06Z  credential issuer registry created
2026-08-03T19:58:07Z  credential policy created
2026-08-03T19:58:08Z  credential issued
2026-08-03T19:58:09Z  credential becomes valid
2026-08-03T19:58:10Z  1.20.0 successor published
2026-08-03T19:58:11Z  canonical credential evaluation
```

The credential expires at the half-open boundary `2027-08-03T19:58:09Z`; evaluation at that instant abstains.

## Consequences

The system can distinguish:

- preserved witness disagreement;
- accepted operational adjudication;
- issuer-bound role authorization for the exact adjudicator identity revision;
- later append-only revocation evidence for that credential;
- every current, lower, inherited, and terminal result.

No later result rewrites an earlier claim.

This ADR does **not** establish append-only credential non-revocation. A later bounded layer may add a revocation policy, ledger, events, checkpoints, and witness evidence for this exact credential while preserving `1.20.0` unchanged.

It also does not establish legal or real-world identity, cryptographic authorship, signatures, private-key possession, trusted external time, issuer or adjudicator independence, competence, honesty, correctness, checkpoint truth, global uniqueness, public availability, majority support, quorum, consensus, confidence, reputation, content accuracy, model accuracy, deployment, or an aggregate CTRT score.
