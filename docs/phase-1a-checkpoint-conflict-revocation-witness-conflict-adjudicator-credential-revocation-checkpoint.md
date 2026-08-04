# Phase 1A — Witness-conflict adjudicator credential revocation checkpoint

This bounded layer checkpoints the exact frozen `1.11.0` revocation ledger before that ledger may authorize the credential lifecycle.

It asks only:

> Does the exact immutable checkpoint chain bind the exact `1.11.0` revocation corpus, frozen ledger, and complete ordered event population before revocation evaluation?

The checkpoint does not establish complete real-world disclosure, issuer trustworthiness, cryptographic authorship, trusted external time, public availability, witness agreement, adjudicator competence, or adjudication correctness.

## Fixed graph

```text
1.11.0 revocation-bound corpus
  → accepted checkpoint policy
  → immutable genesis checkpoint
  → frozen checkpoint log
  → manifest-last 1.12.0 checkpoint-bound corpus
```

The genesis checkpoint binds the exact `1.11.0` corpus, frozen revocation ledger, and one ordered future-effective suspension event. It has sequence number zero and no predecessor checkpoint.

## Chronology

```text
2026-08-03T19:54:48Z  1.11.0 predecessor published
2026-08-03T19:54:49Z  checkpoint policy created
2026-08-03T19:54:51Z  genesis checkpoint published
2026-08-03T19:54:53Z  checkpoint log frozen
2026-08-03T19:54:54Z  1.12.0 successor published
2026-08-03T19:54:55Z  checkpoint verified
2026-08-03T19:54:56Z  delegated revocation evaluated
2026-08-03T19:55:00Z  credential evaluated
```

The later `19:54:56Z` revocation evaluation preserves the same active as-of result as PR #33 while ensuring checkpoint publication and verification precede the decision.

## Explicit scope transition

```text
1.12.0 plan → checkpoint validation, report persistence, outer finalization
1.11.0 plan → unchanged PR #33 revocation lifecycle
1.10.0 plan → unchanged credential lifecycle
1.9.0 plan  → unchanged adjudication lifecycle
1.8.0 receipt → preserved witness evidence
1.7.0 scope → lower checkpoint lifecycle
```

No predecessor artifact is modified.

## Deferred layers

Named witnesses over the exact `1.12.0` checkpoint head, conflict adjudication, credentials for that authority, signatures, keys, external timestamp services, and live transparency infrastructure remain separate future layers.
