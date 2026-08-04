# ADR-0038: Witness-conflict adjudicator revocation checkpoints require named observations

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0037 added an immutable checkpoint chain over the exact `1.11.0` revocation ledger and published the compact `1.12.0` checkpoint-bound corpus.

That checkpoint proves a structural publication claim inside the frozen CTRT graph. It does not answer the narrower operational question:

> Did every policy-required named witness report the exact independently verifiable `1.12.0` checkpoint head?

Treating witness agreement as a vote or confidence score would collapse distinct observations into an unsupported aggregate. Omitting a conflicting observation would erase material evidence.

## Decision

CTRT will publish immutable named observations over the exact `1.12.0` checkpoint head before the checkpoint may authorize the inherited lifecycle.

The layer will:

1. reuse the generic adjudicator-checkpoint witness registry, policy, attestation, decision, and storage grammar;
2. bind an accepted ordered registry of three named synthetic checkpoint observers;
3. bind an accepted policy requiring that exact witness population and order;
4. preserve every observation as a separate immutable artifact;
5. bind each observation to the exact `1.12.0` corpus, checkpoint log, expected head, and observed head;
6. distinguish `matches_head` from `conflicting_head` without deriving confidence or reputation;
7. require observation and receipt chronology after checkpoint publication;
8. abstain when any required witness reports a conflicting head;
9. forbid vote aggregation, so two matches cannot outvote one conflict;
10. publish a compact manifest-last `1.13.0` successor;
11. independently reverify the exact `1.12.0` checkpoint before evaluating current observations;
12. persist the checkpoint report and witness decision as separate run-specific artifacts;
13. delegate the unchanged PR #34 checkpoint lifecycle only after current witness execution;
14. preserve the current witness decision when a later revocation, credential, inherited witness, adjudication, or terminal layer abstains.

## Fixed graph

```text
registry.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
  → policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
  → alpha observation
  → beta observation
  → gamma observation
  → corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.13.0
```

The canonical fixtures all report the exact `1.12.0` head. Conflicting observations are introduced only in tests and remain separately preserved.

## Decision rule

```text
match + match + match    → execute
match + match + conflict → abstain
```

No majority, quorum, consensus, confidence, reputation, or trust score is produced. The layer does not decide which conflicting witness is correct.

## Chronology

```text
2026-08-03T19:54:54Z  1.12.0 checkpoint corpus published
2026-08-03T19:54:55Z  witness registry created
2026-08-03T19:54:56Z  witness policy created
2026-08-03T19:54:57Z  alpha observed exact head
2026-08-03T19:54:59Z  beta observed exact head
2026-08-03T19:55:01Z  gamma observed exact head
2026-08-03T19:55:03Z  1.13.0 successor published
2026-08-03T19:55:04Z  checkpoint independently reverified
2026-08-03T19:55:05Z  current witness population evaluated
2026-08-03T19:55:06Z  delegated revocation evaluated
```

## Consequences

Checkpoint integrity, current witness observations, revocation status, credential authorization, inherited witness evidence, adjudication, and terminal execution remain separate claims. A unanimous current witness decision may be followed by downstream execution or downstream abstention. A current witness conflict prevents PR #34 delegation but does not invalidate or rewrite the checkpoint.

This ADR does not add conflict adjudication for the current observations, credentials or revocation history for a future conflict adjudicator, signatures, keys, trusted external time, public transparency infrastructure, real-world identity, majority logic, confidence, reputation, or consensus.
