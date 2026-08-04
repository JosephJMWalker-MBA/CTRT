# ADR-0037: Checkpoint-conflict witness adjudicator revocation ledgers require immutable checkpoints

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0036 added append-only, time-relative status history for the exact credential authorizing checkpoint-conflict witness adjudication. That layer can reconstruct the credential's effective status at a declared time without editing the credential.

The remaining provenance question is narrower:

> Which exact frozen ledger head and ordered event population did the revocation decision rely upon?

A ledger hash alone identifies one artifact, but execution should also preserve an immutable publication boundary with explicit sequence, ancestry, ordered-event coverage, and a declared head.

## Decision

CTRT will publish an immutable checkpoint chain over the exact `1.11.0` revocation ledger before revocation evaluation.

The layer will:

1. reuse the generic adjudicator credential revocation checkpoint grammar;
2. bind the exact `1.11.0` revocation corpus and frozen ledger;
3. bind the complete ordered event-reference population and deterministic population hash;
4. require contiguous sequence numbers beginning at zero;
5. require no predecessor at genesis and exact immediate predecessors thereafter;
6. require prefix-only extension of event populations;
7. require monotonic checkpoint publication time;
8. freeze an ordered checkpoint log whose final member is its declared head;
9. publish a compact manifest-last `1.12.0` successor;
10. verify and persist the checkpoint report before delegating the unchanged `1.11.0` revocation lifecycle;
11. require checkpoint verification no later than revocation evaluation;
12. preserve checkpoint verification when a later revocation, credential, adjudication, witness, reviewer, or analyzer layer abstains.

## Fixed graph

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
  → checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.0000
  → log.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
  → corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.12.0
```

The genesis checkpoint covers the exact single-event `1.11.0` ledger and has no predecessor.

## Chronology

```text
2026-08-03T19:54:48Z  1.11.0 predecessor published
2026-08-03T19:54:49Z  checkpoint policy created
2026-08-03T19:54:51Z  genesis checkpoint published
2026-08-03T19:54:53Z  checkpoint log frozen
2026-08-03T19:54:54Z  1.12.0 successor published
2026-08-03T19:54:55Z  checkpoint verified
2026-08-03T19:54:56Z  delegated revocation evaluated
```

The revocation evaluation is intentionally one second later than the canonical PR #33 example. The immutable `1.11.0` evidence is unchanged, the future suspension remains unapplied, and the checkpoint now precedes the operational decision it governs.

## Consequences

Checkpoint success and revocation status remain separate claims. A valid checkpoint may be followed by revocation execution or governed abstention. An invalid checkpoint is structural failure and prevents revocation evaluation entirely.

This ADR does not add named checkpoint witnesses, witness conflict adjudication, signatures, keys, trusted external time, public transparency infrastructure, majority logic, confidence, reputation, or consensus.
