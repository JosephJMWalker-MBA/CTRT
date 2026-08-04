# ADR-0041: Checkpoint-fork adjudicator credentials require append-only revocation history

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0040 added an exact issuer-bound credential for the pseudonymous adjudicator that resolved the checkpoint-witness conflict preserved by `1.14.0`.

The canonical `1.15.0` credential answers a narrow authorization question:

> Did an accepted issuer issue a structurally valid credential for the exact adjudicator identity revision and `witness_conflict_adjudicator` role at the declared time?

That claim is insufficient for later execution. A credential may be valid within its declared interval while a later issuer-authored status event independently suspends or revokes it. Editing the credential would destroy the original authorization evidence and collapse two different claims:

```text
credential validity -> what the credential declared
revocation status   -> what later append-only status history made effective
```

## Decision

CTRT will publish an append-only `1.16.0` revocation layer over the exact immutable `1.15.0` credential graph.

The layer will:

1. preserve `1.15.0` unchanged as the exact predecessor;
2. bind an accepted fail-closed revocation policy;
3. represent status changes only as immutable issuer-authored events;
4. bind each event to the exact credential, adjudicator, issuer, and issuer revision;
5. distinguish `recorded_at` from `effective_at`;
6. require monotonic effective time and linear supersession;
7. publish a frozen ledger with exact ordered event references;
8. bind the ledger to the exact `1.15.0` corpus, issuer registry, and revocation policy;
9. publish policy, events, and ledger before the compact `1.16.0` manifest;
10. require all recorded history used by a decision to exist before ledger freeze and successor publication;
11. derive effective status deterministically as of the declared evaluation time;
12. preserve the credential's original base status unchanged;
13. persist the run-specific revocation decision before any `1.15.0` credential evaluation;
14. terminate before PR #37 when effective status is `suspended` or `revoked`;
15. invoke the exact unchanged PR #37 lifecycle only after revocation outcome `execute`;
16. preserve current revocation, current credential, witness, adjudication, inherited revocation, inherited credential, and terminal outcomes independently.

## Fixed graph

```text
exact 1.15.0 credential graph
  -> accepted revocation policy
  -> immutable future-effective suspension event
  -> frozen ordered revocation ledger
  -> compact 1.16.0 revocation-bound successor
```

The canonical event is recorded before publication but becomes effective later:

```text
recorded_at  = 2026-08-03T19:57:36Z
effective_at = 2027-01-01T00:00:00Z
effect       = suspended
```

Before the effective boundary, the event is visible but does not change status.

## Recorded time versus effective time

Every status event carries two independent timestamps:

```text
recorded_at  -> when the event entered the frozen issuer-authored history
effective_at -> when the already-recorded event changes effective status
```

A future-effective event is valid and inspectable before it applies.

A future-recorded event may not be imported retroactively into an earlier decision. The context boundary requires:

```text
policy.created_at
  <= event.recorded_at
  <= ledger.created_at
  <= successor.created_at
  <= revocation_evaluated_at
  <= credential_evaluated_at
```

## Canonical chronology

```text
2026-08-03T19:57:30Z  credential issuer registry created
2026-08-03T19:57:31Z  credential policy created
2026-08-03T19:57:32Z  credential issued
2026-08-03T19:57:33Z  credential validity begins
2026-08-03T19:57:34Z  1.15.0 credential successor published
2026-08-03T19:57:35Z  revocation policy created
2026-08-03T19:57:36Z  future suspension recorded
2026-08-03T19:57:37Z  revocation ledger frozen
2026-08-03T19:57:38Z  1.16.0 revocation successor published
2026-08-03T19:57:39Z  revocation status evaluated
2026-08-03T19:57:40Z  credential evaluated
```

The suspension becomes effective at:

```text
2027-01-01T00:00:00Z
```

## As-of status semantics

Before the effective boundary:

```text
base_status       = active
effective_status  = active
applied_event_ids = []
revocation_outcome = execute
```

At the effective boundary:

```text
base_status       = active
effective_status  = suspended
applied_event_ids = [event.synthetic.witness-conflict-adjudicator-checkpoint-fork.suspension.v0.1.0]
revocation_outcome = abstain
```

The credential bytes do not change.

## Semantic separation

A complete canonical execution can preserve all of these facts simultaneously:

```text
current revocation outcome          = execute
current credential outcome          = execute
current checkpoint witness outcome  = abstain
current resolution status           = resolved
current adjudication outcome        = execute
predecessor witness outcome         = execute
inherited revocation outcome        = execute
inherited credential outcome        = execute
inherited checkpoint witness        = execute
inherited resolution status         = not_required
inherited adjudication outcome       = execute
terminal outcome                    = execute
```

An effective current suspension instead yields:

```text
current revocation outcome = abstain
all downstream outcomes    = null
terminal outcome           = abstain
```

No later result rewrites an earlier claim.

## Delegation

```text
1.16.0 plan -> current revocation validation, decision persistence, outer finalization
1.15.0 plan -> unchanged PR #37 credential lifecycle after revocation execution
1.14.0 plan -> unchanged PR #36 disagreement and adjudication lifecycle
1.13.0 plan -> unchanged PR #35 named-witness lifecycle
1.12.0 plan -> unchanged PR #34 checkpoint lifecycle
1.11.0 plan -> unchanged inherited revocation lifecycle
```

Only the corpus reference and identical ordered content IDs are narrowed.

## Consequences

The system can distinguish:

- what the credential originally declared;
- which status events were present in the exact frozen ledger;
- when those events were recorded;
- when those events became effective;
- the resulting as-of revocation outcome;
- every later credential, witness, adjudication, and terminal outcome.

This layer does not establish:

- completeness of the frozen ledger beyond its exact event population;
- absence of undisclosed events or alternate ledgers;
- global ledger uniqueness or public availability;
- legal or real-world adjudicator or issuer identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- issuer, adjudicator, or witness independence, competence, honesty, or correctness;
- adjudication correctness or external truth of the selected checkpoint;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, analyzer, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

The bounded successor should checkpoint the exact frozen `1.16.0` revocation ledger so later execution can prove which ledger head it relied upon without modifying any prior artifact.
