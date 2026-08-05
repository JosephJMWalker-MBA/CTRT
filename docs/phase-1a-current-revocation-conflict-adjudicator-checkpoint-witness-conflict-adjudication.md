# Phase 1A: Current revocation conflict-adjudicator checkpoint witness adjudication

## Purpose

This bounded layer adds authorized adjudication over a preserved conflict inside the exact `1.28.0` named-witness population.

It answers only:

> Did the exact authorized adjudicator resolve the exact preserved conflict over the exact `1.27.0` checkpoint head under the exact accepted policy?

It does not rewrite the canonical witnesses, infer consensus, or establish that the selected head is externally true.

## Exact ancestry

```text
1.29.0 adjudication corpus
  -> exact 1.28.0 named-witness corpus
  -> exact 1.27.0 checkpoint corpus
  -> exact 1.26.0 revocation corpus
  -> exact 1.25.0 credential corpus
  -> exact 1.24.0 conflict-adjudication corpus
```

Exact `1.28.0` predecessor:

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.28.0
sha256:4dce56cbccb761b273f65b5a2538b65ea3b9d62d804151644ddedf0294193b2f
```

## Immutable artifacts

### Preserved conflict

```text
checkpoint-witness-attestation:attestation.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma.conflict.v0.1.0
sha256:23b019395719301fc92bff835ffc19c13e263e67a38fe2e5d6bc8b6e87df27b3
```

This is a separate gamma attestation. It does not replace gamma's canonical matching observation in `1.28.0`.

### Adjudicator registry

```text
registry.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicators@0.1.0
sha256:b845c378233efcd660720b61c63af80e80f767ab089a56e97ed8ab1e74bcd8bc
```

### Adjudication policy

```text
policy.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication@0.1.0
sha256:72cdbde0ff3f21b3a73f28b7c1d781cda002b2ac37a593536535d7b0e524f4f8
```

### Adjudication record

```text
witness-conflict-adjudication:adjudication.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma-conflict.v0.1.0
sha256:ad432dab42a5425cf3ad2192b334b1a915ead108551f39963f9f48da638a6575
```

### Manifest-last successor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-bound@1.29.0
sha256:7f764303de2ed1d57856403bd900d0690ebf18c37b40a944e29e0e9b27a70cc4
```

## Conflict population

The evaluated conflicting population is:

```text
alpha: canonical matches_head observation
beta:  canonical matches_head observation
gamma: separately appended conflicting_head observation
```

The witness decision for this population is `abstain`. The two matching observations do not outvote gamma.

## Authorized resolution

The accepted adjudicator is:

```text
adjudicator.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Role:

```text
witness_conflict_adjudicator
```

The adjudication selects only the exact checkpoint head declared by `1.27.0`:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12
```

Gamma's alternate observation remains in both `fork_evidence` and `preserved_dissent`.

## Persistence order

```text
exact 1.28.0 predecessor already stored
  -> witness registry
  -> witness policy
  -> alpha matching attestation
  -> beta matching attestation
  -> gamma conflict attestation
  -> adjudicator registry
  -> adjudication policy
  -> adjudication record
  -> 1.29.0 corpus manifest last
```

During execution:

```text
load 1.29.0 graph
  -> validate conflicting witness population
  -> persist conflicting witness decision
  -> validate authorized adjudication
  -> persist adjudication decision
  -> abstain or derive exact 1.28.0 plan
  -> execute PR #50 unchanged under same run ID
  -> persist outer final
  -> reread every stored dependency
```

## Plan narrowing

The outer plan has the exact `1.29.0` corpus reference.

When adjudication executes, derive the delegated plan by changing only:

```text
corpus_ref  = exact 1.28.0 witness corpus
content_ids = exact unchanged ordered content population
```

Preserve:

```text
experiment_run_id
experiment_id
experiment_version
ordered content IDs
all inherited governance inputs
```

## Chronology

```text
1.28.0 published              2026-08-03T19:59:02Z
gamma conflict observed       2026-08-03T19:59:03Z
gamma conflict received       2026-08-03T19:59:04Z
adjudicator registry created  2026-08-03T19:59:05Z
adjudication policy created   2026-08-03T19:59:06Z
adjudication decided          2026-08-03T19:59:07Z
1.29.0 published              2026-08-03T19:59:08Z
conflict witness evaluated    2026-08-03T19:59:09Z or later
adjudication evaluated        after conflict evaluation
canonical witness lifecycle   after adjudication execution
```

Chronology drift is structural failure.

## Runtime stages

```text
preflight
evidence-loading
witness-validation
witness-decision-persistence
adjudication-validation
adjudication-decision-persistence
witness-execution
final-persistence
verification
```

A failure records the stage and any completed content IDs. It does not manufacture a governed abstention.

## Outcome fields

The final and verified receipt preserve:

1. conflicting current witness outcome;
2. current conflict resolution status;
3. current conflict-adjudication outcome;
4. resolved canonical `1.28.0` witness outcome;
5. every one of the 23 PR #50 and inherited outcomes;
6. terminal outcome.

The original conflict outcome remains `abstain` even when adjudication resolves it operationally.

## Governed outcomes

### Resolved adjudication

```text
conflicting witness = abstain
resolution          = resolved
adjudication        = execute
canonical witness   = execute
PR #50              = execute unchanged
```

### Pending adjudication

```text
conflicting witness = abstain
resolution          = pending
adjudication        = abstain
canonical witness   = null
PR #50 outcomes     = null
terminal            = abstain
```

### Unresolved adjudication

```text
conflicting witness = abstain
resolution          = unresolved
adjudication        = abstain
canonical witness   = null
PR #50 outcomes     = null
terminal            = abstain
```

### Later delegated abstention

```text
conflicting witness = abstain
resolution          = resolved
adjudication        = execute
canonical witness   = execute
later outcome       = abstain
terminal            = abstain
```

No earlier result is rewritten by a later abstention.

## Structural validation

Reject:

- wrong `1.28.0` or `1.27.0` reference;
- changed content ordering;
- witness registry or witness policy drift;
- missing, extra, duplicated, or substituted attestations;
- adjudicator registry, ID, identity revision, or role drift;
- adjudication policy drift;
- changed fork evidence or dissent;
- resolved selection of the alternate undeclared head;
- decision-time or evaluation-time inversion;
- run-ID mismatch;
- stored-byte or hash drift;
- noncanonical serialization;
- extra schema fields such as confidence or aggregate score.

## Closed schemas

The layer adds:

```text
schemas/current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudication-bound-corpus.schema.json
schemas/adjudicated-current-revocation-conflict-adjudicator-checkpoint-witness-final.schema.json
```

Both use `additionalProperties: false`.

## Public API

Contract module:

```text
ctrt.current_revocation_conflict_adjudicator_checkpoint_witness_conflict_adjudication
```

Runner module:

```text
ctrt.adjudicated_current_revocation_conflict_adjudicator_checkpoint_witness_runner
```

Public API regression tests lock the exported names.

## Trust boundary

This layer proves only that the accepted adjudication graph was evaluated and carried forward according to its declared policy.

It does not prove:

- real identity or cryptographic authorship;
- independence, competence, honesty, or correctness;
- checkpoint truth or ledger completeness;
- that no other history exists;
- trusted time;
- consensus, majority, quorum, confidence, reputation, or trust;
- analytical correctness or deployment readiness;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may attest the exact adjudicator identity and role with an accepted issuer-bound credential.

That layer must preserve the entire `1.29.0` conflict and adjudication graph, including gamma's dissent, unchanged.
