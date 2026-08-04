# Phase 1A: Witness-conflict adjudicator checkpoint witness conflict adjudication

## Purpose

This layer adds an append-only operational decision over a preserved conflict in the named observations governing the exact `1.12.0` checkpoint.

It asks only:

> Did an accepted adjudicator, under an accepted fail-closed policy, issue a structurally valid resolution for the exact preserved conflicting witness population?

It does not ask whether the witnesses agree, whether the checkpoint is true in the external world, or whether the newly named adjudicator is credential-valid.

## Inherited evidence

The layer preserves the exact PR #35 predecessor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.13.0
sha256:e03f982b4d1ee04299f165b1a699b9b643ae0aff4650f800f29d97e64557c4f3
```

That predecessor binds the exact immutable `1.12.0` checkpoint:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.12.0
sha256:3fdaa55c2fb1ab14aaca5482093ff6415f6835483f0c2b2e3bd6a758af40a096
```

The declared checkpoint head is:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.0000
sha256:350d6550bbe969457fde6f556505e2b6ef270f4d1cedd296c6a835505ed37359
```

No inherited artifact is edited or republished under a new hash.

## New conflicting observation

The `1.14.0` population retains the original alpha and beta observations and substitutes one new immutable gamma observation:

```text
checkpoint-witness-attestation:attestation.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma.conflict.v0.1.0
sha256:85217c3ac90b75125f063a574c6456d6eaae28d60b50798a9fad01874c615ca2
```

Gamma reports this alternate head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.conflict
sha256:9999999999999999999999999999999999999999999999999999999999999999
```

The original matching gamma observation remains in `1.13.0`. The conflict is a new artifact, not an edit.

## Witness decision

The existing accepted witness policy still governs the population:

```text
alpha match + beta match + gamma conflict → abstain
```

Two matches do not outvote one required conflict. No count, majority, quorum, confidence, consensus, reputation, or trust score is derived.

The witness decision remains:

```text
checkpoint_witness_outcome = abstain
```

## Conflict adjudicator registry

```text
registry.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicators@0.1.0
sha256:86a2e4f938e88201a37615069d91403d398d5b3726abf7b182a27286ed418965
```

Registered authority:

```text
adjudicator.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Role:

```text
witness_conflict_adjudicator
```

The registry is pseudonymous and structural. It does not establish real-world identity or competence.

## Adjudication policy

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication@0.1.0
sha256:7d5e8d24f293d0d64cbb2c6278e1bbebd6d6f55cb712893fbbceb317d5e820d7
```

The policy requires:

```text
abstain_on_pending = true
abstain_on_unresolved = true
resolution_must_select_declared_head = true
forbid_vote_aggregation = true
```

## Canonical adjudication

```text
witness-conflict-adjudication:adjudication.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma-conflict.v0.1.0
sha256:7a3033a23631219f4ad9644bbfc9ec5c049223445106a8f41dfdf062f99fb958
```

Canonical state:

```text
resolution_status          = resolved
selected_head              = exact independently verified checkpoint head
conflict_adjudication      = execute
checkpoint_witness_outcome = abstain
```

The record preserves:

- the exact `1.13.0` predecessor;
- exact witness registry and policy references;
- exact conflict-adjudicator registry and policy references;
- the declared checkpoint head;
- the selected head;
- exact fork evidence reconstructed from gamma's conflicting observation;
- gamma's dissent after resolution;
- rationale and decision time.

## Shared `1.14.0` payload

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-adjudication-bound@1.14.0
sha256:a2b4ff05a5e23bcdf0d54b721b4e3cd376788a65f7464b26dc543207d9cfb74e
```

One canonical payload serves two compatible views:

1. a witness-bound corpus over the exact `1.12.0` checkpoint with alpha, beta, and conflicting gamma observations;
2. an adjudication-bound successor over the exact all-matching `1.13.0` predecessor.

This avoids a hidden intermediate corpus and ensures the witness decision and adjudication decision refer to the same immutable artifact hash.

## Manifest-last publication

Publication order is:

1. conflicting gamma observation;
2. accepted conflict-adjudicator registry;
3. accepted conflict-adjudication policy;
4. adjudication record;
5. `1.14.0` successor manifest;
6. exact-hash reread of the complete graph.

The original alpha and beta observations, witness registry, witness policy, `1.13.0`, `1.12.0`, and all lower evidence are reused by exact reference.

## Contract adapter

```text
src/ctrt/witness_conflict_adjudicator_checkpoint_witness_conflict_adjudication.py
```

Primary types:

```text
ConflictingCheckpointWitnessCorpusSnapshot
AdjudicationBoundCheckpointWitnessCorpusSnapshot
```

Operations:

```text
load_conflict_adjudication_evidence
validate_conflict_adjudication
persist_adjudication_bound_corpus
```

The adapter reuses the established adjudicator-checkpoint witness-conflict validator. The reused validator enforces:

- exact corpus and content population;
- exact witness registry, policy, and observation population;
- accepted adjudicator registry and policy;
- exact required adjudicator order;
- exact predecessor and checkpoint head;
- witness abstention whenever conflict evidence exists;
- exact fork-evidence reconstruction;
- preserved dissent;
- registered adjudicator identity revision and role;
- selected-head restriction;
- pending and unresolved abstention;
- prohibition on vote aggregation.

## Outer runner

```text
src/ctrt/adjudicated_witness_conflict_adjudicator_checkpoint_runner.py
```

`AdjudicatedWitnessConflictAdjudicatorCheckpointExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, registry, policy, observation population, adjudicator, adjudication, run, and chronology preflight;
2. storage-backed loading of the complete `1.14.0` graph;
3. independent evaluation of the conflicting witness population;
4. persistence and reread verification of the witness decision;
5. independent validation of the conflict adjudication;
6. persistence and reread verification of the adjudication decision;
7. terminal abstention for pending or unresolved adjudication;
8. exact plan narrowing from `1.14.0` to `1.13.0` only after adjudication execution;
9. invocation of the unchanged PR #35 runner with the original all-matching `1.13.0` observation population;
10. outer final-manifest persistence;
11. storage-backed reread of the final, complete conflict graph, both current decisions, and optional PR #35 final.

## Plan scopes

```text
1.14.0 plan → conflicting witness decision, current conflict adjudication, outer finalization
1.13.0 plan → unchanged PR #35 named-witness lifecycle
1.12.0 plan → unchanged PR #34 checkpoint lifecycle
1.11.0 plan → unchanged PR #33 revocation lifecycle
1.10.0 plan → unchanged credential lifecycle
1.9.0 plan  → unchanged inherited adjudication lifecycle
```

Only the corpus reference and matching ordered content population are narrowed. Experiment identity, version, execution parameters, and inherited evidence remain unchanged.

## Run-specific artifacts

Conflicting witness decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-witness-decision
```

Conflict adjudication decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-decision
```

Pending or unresolved adjudication:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-abstention
```

Resolved full execution:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-completion
```

Resolved adjudication followed by downstream abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-terminal-abstention
```

## Outcome matrix

### Canonical resolved execution

```text
current checkpoint witness      = abstain
current resolution status       = resolved
current adjudication outcome    = execute
1.13.0 predecessor witness      = execute
revocation outcome              = execute
credential outcome              = execute
inherited checkpoint witness    = execute
inherited resolution status     = not_required
inherited adjudication outcome  = execute
terminal outcome                = execute
```

### Pending current adjudication

```text
current checkpoint witness      = abstain
current resolution status       = pending
current adjudication outcome    = abstain
all predecessor/downstream      = null
terminal outcome                = abstain
```

Both current decisions remain stored. PR #35 is not invoked.

### Resolved conflict with later effective suspension

```text
current checkpoint witness      = abstain
current resolution status       = resolved
current adjudication outcome    = execute
1.13.0 predecessor witness      = execute
revocation outcome              = abstain
remaining inherited outcomes    = null
terminal outcome                = abstain
```

The witness disagreement and its resolution remain visible when a later governance layer independently stops execution.

## Chronology

Canonical outer chronology:

```text
2026-08-03T19:57:21Z  1.14.0 successor published
2026-08-03T19:57:22Z  conflicting witness population evaluated
2026-08-03T19:57:23Z  conflict adjudication evaluated
2026-08-03T19:57:24Z  delegated 1.12.0 checkpoint reverified
2026-08-03T19:57:25Z  delegated 1.13.0 predecessor witnesses evaluated
2026-08-03T19:57:26Z  delegated revocation evaluated
2026-08-03T19:57:30Z  delegated credential evaluated
2026-08-03T19:57:40Z  inherited adjudication evaluated
2026-08-03T19:58:00Z  inherited adjudication completed
2026-08-03T19:58:15Z  credential lifecycle completed
2026-08-03T19:58:30Z  revocation lifecycle completed
2026-08-03T19:58:45Z  checkpoint lifecycle completed
2026-08-03T19:59:00Z  PR #35 predecessor witness lifecycle completed
2026-08-03T19:59:15Z  current conflict-adjudication lifecycle completed
```

## Failure boundaries

The runner preserves the exact stage at which execution failed:

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

A structural failure raises an experiment error. A governed pending or unresolved adjudication creates a verified terminal abstention receipt.

## Test coverage

Contract tests prove:

- exact conflict observation, registry, policy, adjudication, and successor hashes;
- closed schemas;
- exact `1.13.0` predecessor;
- exact unchanged `1.12.0` checkpoint predecessor;
- witness abstention despite two matching observations;
- resolved adjudication execution;
- exact fork evidence and preserved dissent;
- pending and unresolved fail-closed outcomes;
- alternate-head selection rejection;
- decision chronology rejection;
- manifest-last persistence and deterministic reconstruction;
- unsupported confidence rejection.

Lifecycle tests use real PR #30–#35 evidence to prove:

1. resolved conflict delegates the exact PR #35 lifecycle;
2. pending adjudication abstains before PR #35;
3. resolved adjudication remains distinct from a later revocation abstention;
4. adjudication before witness evaluation fails at preflight;
5. all final variants satisfy one closed schema.

## Privacy and trust boundary

Artifacts contain pseudonymous identifiers, immutable identity revisions, exact artifact references, deterministic hashes, timestamps, observation kinds, fork evidence, dissent, rationale, resolution status, and separately preserved outcomes.

This layer does not establish:

- legal or real-world witness or adjudicator identity;
- cryptographic authorship or private-key possession;
- trusted external time;
- witness independence, competence, honesty, or correctness;
- conflict-adjudicator credential validity or revocation status;
- conflict-adjudicator independence, competence, honesty, or correctness;
- correctness of the selected operational response;
- checkpoint truth beyond structural verification of the frozen graph;
- global checkpoint uniqueness or public availability;
- absence of undisclosed events or alternate chains;
- majority support, quorum, consensus, confidence, reputation, or trust;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Intentionally deferred

A later bounded layer may attest the exact credential authorizing this new conflict adjudicator. Any such layer must preserve the `1.14.0` witness abstention, adjudication decision, fork evidence, dissent, and every inherited artifact unchanged.
