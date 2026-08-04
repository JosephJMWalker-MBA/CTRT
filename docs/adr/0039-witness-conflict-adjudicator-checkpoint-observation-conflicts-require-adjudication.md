# ADR-0039: Witness-conflict adjudicator checkpoint observation conflicts require authorized adjudication

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0038 added an exact named-witness population over the immutable `1.12.0` checkpoint for the revocation history governing the credential of the adjudicator used in the prior witness-conflict case.

The canonical `1.13.0` population reports the declared checkpoint head uniformly. Its policy nevertheless defines a fail-closed rule for any required conflict:

```text
match + match + conflict → witness abstention
```

A witness abstention preserves disagreement but does not answer the narrower operational question:

> May execution continue after the exact conflicting observation has been preserved?

Counting observations cannot answer that question because the witness policy explicitly forbids vote aggregation. Replacing the conflicting observation, editing `1.13.0`, or converting the witness outcome from abstention to execution would destroy the evidence the governance layer exists to preserve.

## Decision

CTRT will publish an append-only `1.14.0` conflict-adjudication layer over the exact immutable `1.13.0` witness corpus.

The layer will:

1. preserve `1.13.0` unchanged as the adjudication predecessor;
2. introduce a new immutable gamma observation reporting an alternate checkpoint head;
3. retain the original alpha and beta observations unchanged;
4. evaluate the resulting exact witness population under the accepted `1.13.0` witness registry and policy;
5. preserve the witness outcome as `abstain`;
6. bind an accepted pseudonymous conflict-adjudicator registry;
7. bind an accepted fail-closed adjudication policy;
8. require pending and unresolved cases to abstain;
9. forbid vote aggregation;
10. require any resolved case to select only the independently verified declared checkpoint head;
11. require fork evidence to reconstruct every conflicting observation exactly;
12. preserve dissent after operational resolution;
13. publish one canonical `1.14.0` artifact serving as both the conflicting witness corpus and the adjudication-bound successor;
14. publish dependencies before the `1.14.0` manifest;
15. persist the run-specific witness decision and adjudication decision separately;
16. invoke the unchanged PR #35 lifecycle only after adjudication execution;
17. narrow only the corpus reference and unchanged content order from `1.14.0` to `1.13.0` during delegation;
18. preserve witness, adjudication, and every downstream outcome independently.

## Fixed graph

```text
1.13.0 all-matching witness corpus
  → gamma conflicting observation
  → accepted conflict-adjudicator registry
  → accepted conflict-adjudication policy
  → resolved adjudication with exact fork evidence and dissent
  → 1.14.0 adjudication-bound successor
```

The canonical resolved decision selects the exact checkpoint head already bound by `1.12.0`:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.0000
sha256:350d6550bbe969457fde6f556505e2b6ef270f4d1cedd296c6a835505ed37359
```

## Semantic separation

```text
checkpoint witness outcome = abstain
resolution status          = resolved
adjudication outcome       = execute
```

The adjudication authorizes a governed operational response to preserved disagreement. It does not make the witnesses agree, erase the alternate observation, determine that gamma was dishonest or mistaken, or strengthen the checkpoint into a claim of external truth.

## Delegation

```text
1.14.0 plan → conflicting witness decision, conflict adjudication, outer finalization
1.13.0 plan → unchanged PR #35 named-witness lifecycle after authorized resolution
```

Pending or unresolved adjudication produces terminal abstention before PR #35 is invoked.

## Chronology

```text
2026-08-03T19:57:15Z  canonical PR #35 witness lifecycle completed
2026-08-03T19:57:16Z  gamma observed alternate checkpoint head
2026-08-03T19:57:17Z  gamma observation received
2026-08-03T19:57:18Z  conflict-adjudicator registry created
2026-08-03T19:57:19Z  conflict-adjudication policy created
2026-08-03T19:57:20Z  canonical adjudication decided
2026-08-03T19:57:21Z  1.14.0 successor published
2026-08-03T19:57:22Z  conflicting witness population evaluated
2026-08-03T19:57:23Z  adjudication evaluated
```

A resolved run may then execute the exact `1.13.0` predecessor under new run-specific times while preserving all earlier artifacts.

## Consequences

The system can distinguish:

- an immutable witness disagreement;
- the status of an authorized adjudication process;
- the selected operational head;
- the unchanged predecessor witness result;
- later revocation, credential, inherited witness, inherited adjudication, and terminal outcomes.

No later outcome rewrites an earlier claim.

This ADR does not establish the new conflict adjudicator's credential validity, revocation status, checkpoint history, legal identity, independence, competence, honesty, or correctness. Those are separate possible successor layers.

It also does not add signatures, keys, trusted external time, public transparency infrastructure, majority logic, quorum, confidence, reputation, consensus, real witnesses, models, datasets, APIs, frontend, deployment, or an aggregate CTRT score.
