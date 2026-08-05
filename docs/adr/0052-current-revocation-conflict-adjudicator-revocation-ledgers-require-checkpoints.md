# ADR-0052: Current revocation-checkpoint conflict-adjudicator revocation ledgers require immutable checkpoints

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0051 added an append-only `1.26.0` revocation ledger for the exact
`1.25.0` conflict-adjudicator credential. That layer preserves credential
issuance separately from later operational status and evaluates the frozen
issuer-authored history as of a declared time.

A frozen ledger is still only a document claiming an ordered event population.
Without a separately published checkpoint, later readers cannot distinguish the
accepted ledger head from a substituted ledger carrying another event order,
another event population, or another head.

The checkpoint must not reinterpret the credential, adjudication, witness
conflict, selected checkpoint head, or any inherited artifact. It may establish
only the exact ledger head that was checkpointed.

## Decision

CTRT will publish a compact `1.27.0` checkpoint layer over the exact immutable
`1.26.0` revocation graph.

The layer will:

1. preserve `1.26.0` unchanged as the checkpoint predecessor;
2. bind an accepted checkpoint policy;
3. bind every checkpoint to the exact revocation corpus and exact ledger;
4. preserve the exact ordered event prefix;
5. require contiguous checkpoint sequence numbers;
6. require prefix extension and monotonic publication time;
7. publish a frozen checkpoint log with one exact head;
8. publish the `1.27.0` successor manifest last;
9. verify the checkpoint before evaluating revocation status;
10. persist the checkpoint verification report before PR #48;
11. narrow the plan from exact `1.27.0` to exact `1.26.0` under the same run ID;
12. preserve the checkpoint result and every PR #48 result separately;
13. treat checkpoint drift as structural failure rather than governed
    abstention.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.26.0
sha256:05c322ff072be8b63868d7b8aad77aa69752ce92eef5e66ab88d169156e515f8
```

The predecessor preserves the exact issuer registry, credential policy,
credential attestation, revocation policy, future-effective suspension event,
frozen ledger, complete adjudication graph, original witness conflict, selected
`1.22.0` head, dissent, fork evidence, and every inherited artifact.

## Fixed checkpoint graph

```text
checkpoint policy = sha256:330a38347de9c667b784e04f8dc58e219066d482f9370b0ccb06c2191aa4139f
event population  = sha256:85d78e0e0cd731cf45fad9ad3ddf6f702e6c2b790f8f999a097dd38e90af68e4
genesis checkpoint = sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12
frozen log         = sha256:c3a20a2895b80e4cba990842dc9229984fa03399040ba4192dd90f1b4ff42670
successor 1.27.0   = sha256:e3e288981f17b308bf5f844cd84633b2e79c67103f6c31b6f13dc89fca672e21
```

## Exact covered head

```text
revocation corpus:
  corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.26.0

revocation ledger:
  ledger.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0

ordered event population:
  event.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator.suspension.v0.1.0
```

The checkpoint records the event even though its suspension effect begins later.
Checkpoint publication and event effectiveness remain independent claims.

## Publication order

1. accepted checkpoint policy;
2. immutable checkpoint records;
3. frozen checkpoint log;
4. compact `1.27.0` successor manifest;
5. exact-hash reread of predecessor, policy, checkpoints, log, ledger, and
   ordered events.

Required chronology is:

```text
1.26.0 published
<= checkpoint policy published
<= checkpoint published
<= checkpoint log frozen
<= 1.27.0 published
<= checkpoint verified
<= revocation evaluated
<= PR #48 completed
<= outer completion
```

## Execution order

```text
load exact 1.27.0 checkpoint graph
  -> verify exact 1.26.0 ledger head and ordered event prefix
  -> persist checkpoint verification report
  -> derive exact 1.26.0 plan under the same run ID
  -> execute unchanged PR #48
  -> preserve every delegated result separately
  -> outer finalization
  -> complete storage reread
```

## Failure semantics

Structural failures include predecessor substitution, content-order drift,
checkpoint policy or log substitution, checkpoint payload drift, ledger
substitution, event-reference or event-order drift, noncontiguous sequence,
broken prefix extension, publication chronology drift, verification after
revocation evaluation, run-identity mismatch, stored-artifact drift, and
noncanonical serialization.

A valid `suspended` or `revoked` status remains a governed abstention in PR #48.
The checkpoint layer itself does not convert structural checkpoint failure into
an abstention artifact.

## Trust boundary

This layer does not establish ledger completeness, absence of alternate
histories, trusted external time, cryptographic authorship, legal identity,
issuer or adjudicator independence or correctness, selected-head truth,
consensus, confidence, reputation, analytical accuracy, deployment, or an
aggregate CTRT score.

It establishes only that the accepted immutable checkpoint graph covers the
exact ordered event prefix and exact ledger head used by `1.26.0`.

## Consequences

Positive consequences:

- the accepted revocation head becomes independently identifiable;
- event ordering remains reconstructable;
- checkpoint verification precedes revocation evaluation;
- later abstention cannot rewrite checkpoint evidence;
- every delegated result remains separately inspectable.

Costs:

- a checkpoint policy, checkpoint record, frozen log, report, and successor are
  required;
- a checkpoint proves only the accepted head, not global completeness;
- long authority-specific names remain necessary.

## Intentionally deferred

A later bounded layer may add named independent witnesses over this exact
`1.27.0` checkpoint head. It must preserve the complete `1.27.0` checkpoint
graph, the complete `1.26.0` revocation graph, and every inherited artifact
unchanged.
