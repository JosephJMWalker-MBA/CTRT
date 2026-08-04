# ADR-0046: Current checkpoint-witness conflict-adjudicator credentials require append-only revocation history

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0045 added an issuer-bound credential for the exact adjudicator identity revision and `witness_conflict_adjudicator` role used by the immutable `1.19.0` conflict adjudication.

That `1.20.0` layer establishes a credential decision at a declared evaluation time. It does not establish that no later issuer-authored suspension or revocation exists.

Treating the credential document's embedded status as permanent would collapse two independently testable claims:

1. an accepted issuer issued a structurally valid credential;
2. the accepted append-only status history leaves that credential operational at a particular time.

A later status event must not rewrite the credential, adjudication, disagreement, or any inherited artifact.

## Decision

CTRT will publish an append-only `1.21.0` revocation layer over the exact immutable `1.20.0` credential graph.

The layer will:

1. preserve `1.20.0` unchanged as the revocation predecessor;
2. bind an accepted revocation policy;
3. require issuer-authored events for the exact credential, adjudicator, issuer, and issuer revision;
4. preserve event recording time separately from event effective time;
5. require monotonic effective time and linear supersession;
6. bind an ordered frozen event ledger to the exact `1.20.0` credential corpus and issuer registry;
7. evaluate effective status as of a declared time;
8. keep future-effective events visible without applying them early;
9. abstain when the effective status is `suspended` or `revoked`;
10. treat predecessor, authority, credential, event, order, supersession, chronology, ledger, or storage drift as structural failure;
11. publish policy, events, ledger, and compact `1.21.0` manifest in dependency order;
12. persist the run-specific revocation decision before any `1.20.0` execution;
13. invoke the unchanged PR #42 lifecycle only when the revocation outcome is `execute`;
14. narrow only the corpus reference and unchanged ordered content population from `1.21.0` to `1.20.0` under the same experiment run ID;
15. preserve the new revocation outcome and every PR #42 outcome separately.

## Fixed graph

```text
1.20.0 issuer-bound credential
  → accepted revocation policy
  → immutable future-effective suspension event
  → frozen ordered event ledger
  → 1.21.0 revocation-bound successor
```

Fixed hashes:

```text
revocation policy = sha256:04430a4444d931e9e7e1793c3d3e05bbb9f18912d0e5daa15224ea1c261181a8
future suspension = sha256:86fe5a56df406791385c432080c36cdc84620686a359d7edfd155ed41d3ec720
frozen ledger     = sha256:38345155c8550fa4d5bdb16b786039c5aac6904071862ec09a770e09f25d7960
1.21.0 successor  = sha256:b6a3065ffb517dda9fb498404021371f7d5b320af144842c3f7d2453c99ace1e
```

The event targets:

```text
credential = adjudicator-credential:credential.synthetic.current-checkpoint-witness-conflict-adjudicator.v0.1.0
adjudicator = adjudicator.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
issuer = issuer.synthetic.current-checkpoint-witness-conflict-governance
issuer revision = synthetic-current-checkpoint-witness-conflict-governance@0.1.0
effect = suspended
effective_at = 2027-01-01T00:00:00Z
```

## Semantic separation

Before the suspension boundary, canonical execution preserves five independent claims:

```text
conflicting witness outcome       = abstain
resolution status                 = resolved
adjudication outcome              = execute
credential outcome                = execute
credential revocation outcome     = execute
```

At the suspension boundary:

```text
credential revocation outcome     = abstain
all PR #42 runtime outcomes        = null
terminal outcome                  = abstain
```

The immutable credential and adjudication records remain present. Revocation abstention withholds execution through this new boundary; it does not erase or retroactively alter issuance or adjudication.

## Publication and chronology

```text
2026-08-03T19:58:10Z  1.20.0 credential predecessor published
2026-08-03T19:58:12Z  revocation policy created
2026-08-03T19:58:13Z  future suspension recorded
2026-08-03T19:58:14Z  event ledger frozen
2026-08-03T19:58:15Z  1.21.0 successor published
2026-08-03T19:58:16Z  canonical as-of evaluation
2027-01-01T00:00:00Z  suspension becomes effective
```

The event is part of the frozen history before its effect applies. Evaluation before the effective boundary returns `active`; evaluation at the boundary returns `suspended` and abstains.

## Delegation

```text
1.21.0 plan → current conflict-adjudicator revocation decision and outer finalization
1.20.0 plan → unchanged PR #42 lifecycle after revocation execution
```

A revocation abstention is terminal for this layer. The revocation decision remains stored and PR #42 is not invoked.

## Consequences

The system can distinguish:

- credential issuance;
- append-only status history;
- effective as-of status;
- preserved witness disagreement;
- authorized conflict adjudication;
- every current, lower, inherited, and terminal outcome.

No later result rewrites an earlier claim.

This ADR does not establish ledger completeness, trusted external time, cryptographic authorship, private-key possession, real-world identity, issuer independence, adjudicator competence, adjudication correctness, checkpoint truth, public availability, absence of undisclosed events, majority support, quorum, consensus, confidence, reputation, deployment, analytical accuracy, or an aggregate CTRT score.

A later bounded layer may checkpoint this exact revocation ledger while preserving `1.21.0` unchanged.