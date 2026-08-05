# ADR-0054: Current revocation conflict-adjudicator checkpoint witness conflicts require authorized adjudication

- **Status:** Accepted
- **Date:** 2026-08-03
- **Decision owners:** CTRT Phase 1A governance architecture
- **Supersedes:** None
- **Depends on:** ADR-0053 and the exact `1.28.0` named-witness graph

## Context

The accepted `1.28.0` corpus binds three named witness observations to the exact immutable `1.27.0` checkpoint head. Its canonical alpha, beta, and gamma records all report `matches_head`.

A later observation may conflict with that accepted head. Such an observation cannot be silently substituted for the canonical witness record, deleted because it is inconvenient, or outvoted by the other witnesses. It must be appended as a separate immutable artifact.

The witness policy correctly returns a governed abstention when any required witness reports a conflicting head. That abstention records the conflict but does not itself authorize an operational choice between heads.

The system therefore requires a separate authorized adjudication layer with a bounded claim:

> Did the exact accepted adjudicator resolve the exact preserved witness conflict under the exact accepted policy while retaining the original observation, fork evidence, and dissent?

## Decision

Introduce an additive `1.29.0` successor that binds:

1. the exact immutable `1.28.0` predecessor;
2. the exact accepted witness registry and witness policy;
3. alpha and beta's original matching observations;
4. a separately appended gamma conflicting observation;
5. an accepted conflict-adjudicator registry;
6. an accepted conflict-adjudication policy;
7. an immutable adjudication record;
8. a compact manifest-last successor.

The adjudication record may select only the exact checkpoint head already declared by the accepted `1.27.0` checkpoint graph. The conflicting alternate head remains preserved as fork evidence and dissent.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.28.0
sha256:4dce56cbccb761b273f65b5a2538b65ea3b9d62d804151644ddedf0294193b2f
```

No predecessor artifact is rewritten.

## Exact conflict graph

```text
gamma conflict      = sha256:23b019395719301fc92bff835ffc19c13e263e67a38fe2e5d6bc8b6e87df27b3
adjudicator registry = sha256:b845c378233efcd660720b61c63af80e80f767ab089a56e97ed8ab1e74bcd8bc
adjudication policy = sha256:72cdbde0ff3f21b3a73f28b7c1d781cda002b2ac37a593536535d7b0e524f4f8
adjudication        = sha256:ad432dab42a5425cf3ad2192b334b1a915ead108551f39963f9f48da638a6575
successor 1.29.0    = sha256:7f764303de2ed1d57856403bd900d0690ebf18c37b40a944e29e0e9b27a70cc4
```

## Exact authority

```text
adjudicator ID:
  adjudicator.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork

identity revision:
  synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0

role:
  witness_conflict_adjudicator
```

The registry and policy are immutable inputs. A different ID, identity revision, role, registry, or policy is structural drift.

## Exact conflict

Alpha and beta retain their canonical matching observations. Gamma's canonical `1.28.0` observation also remains unchanged. The new graph appends a separate gamma record:

```text
observation kind: conflicting_head
expected head:    exact accepted 1.27.0 checkpoint head
observed head:    separately identified alternate head
```

The conflicting population evaluated by this layer is alpha canonical, beta canonical, and gamma conflict. Its witness decision remains `abstain`.

## Exact resolution

The adjudication record:

- has status `resolved`;
- names the exact accepted adjudicator and identity revision;
- selects the exact declared checkpoint head;
- preserves the alternate observation as fork evidence;
- preserves gamma's dissent and note;
- supplies an explicit rationale;
- records its decision time.

A resolved adjudication that selects the alternate undeclared head is invalid under the accepted policy.

## Chronology

```text
1.28.0 successor published  2026-08-03T19:59:02Z
gamma conflict observed     2026-08-03T19:59:03Z
gamma conflict received     2026-08-03T19:59:04Z
adjudicator registry        2026-08-03T19:59:05Z
adjudication policy         2026-08-03T19:59:06Z
adjudication decided        2026-08-03T19:59:07Z
1.29.0 successor published  2026-08-03T19:59:08Z
conflict evaluated          2026-08-03T19:59:09Z or later
adjudication evaluated      after conflict evaluation
canonical PR #50 lifecycle  after adjudication execution
```

## Execution semantics

The outer runner must:

1. load the exact `1.29.0` graph;
2. validate and persist the conflicting witness decision;
3. validate and persist the adjudication decision separately;
4. stop with governed abstention when adjudication is pending or unresolved;
5. when adjudication executes, narrow only the corpus reference to exact `1.28.0` under the same run ID;
6. execute PR #50 unchanged with the original canonical witness population;
7. preserve the conflict, resolution, adjudication, resolved canonical witness result, and every delegated outcome separately;
8. publish the final record last and reread all stored evidence.

## Outcome preservation

The final record contains distinct fields for:

- the conflicting witness outcome;
- the conflict resolution status;
- the adjudication outcome;
- the resolved canonical witness outcome;
- all 23 PR #50 and inherited outcomes;
- the terminal outcome.

No field may substitute for another.

### Resolved

```text
conflicting witness outcome = abstain
resolution status           = resolved
adjudication outcome        = execute
resolved canonical witness  = execute
PR #50                      = executed unchanged
```

### Pending or unresolved

```text
conflicting witness outcome = abstain
adjudication outcome        = abstain
resolved canonical witness  = null
all PR #50 outcomes         = null
terminal outcome            = abstain
```

### Later delegated abstention

A successful adjudication remains `execute` even when a later inherited governance layer abstains. Both claims remain separately visible.

## Structural failures

The layer fails closed for:

- predecessor, content-order, registry, policy, attestation, checkpoint-head, or adjudication substitution;
- missing, duplicate, or unknown witness or adjudicator identities;
- identity-revision or role drift;
- fork-evidence or preserved-dissent drift;
- a resolved selection outside the declared checkpoint head;
- chronology inversion;
- run-identity mismatch;
- stored-artifact or serialization drift;
- closed-schema violations.

Structural failure creates no governed abstention artifact.

## Rejected alternatives

### Majority vote

Rejected. Two matching observations do not erase or outvote a conflicting required witness.

### Replace gamma's canonical observation

Rejected. The conflict is a new historical record and must not rewrite `1.28.0`.

### Treat adjudication as proof of truth

Rejected. Adjudication authorizes an operational selection under a policy; it does not establish metaphysical or external truth.

### Collapse conflict and adjudication into one outcome

Rejected. The original abstention, resolution status, adjudication result, and downstream results are distinct historical claims.

## Trust boundary

This layer does not establish:

- real-world or legal identity;
- cryptographic authorship;
- adjudicator independence, competence, honesty, or correctness;
- witness independence or correctness;
- checkpoint truth or ledger completeness;
- absence of alternate histories;
- trusted external time;
- majority support, quorum, consensus, confidence, reputation, or trust score;
- analytical accuracy, deployment readiness, or an aggregate CTRT score.

It establishes only that the exact accepted adjudicator record resolved the exact preserved conflict under the exact accepted policy and that the resulting operational selection was carried forward without erasing dissent.

## Consequences

- Conflicts remain inspectable after resolution.
- Operational continuation requires explicit authority rather than implicit preference.
- Pending and unresolved authority produce governed abstention.
- The canonical `1.28.0` witness graph remains immutable.
- Later layers may evaluate the adjudicator's credential or revocation status without reopening this decision.
