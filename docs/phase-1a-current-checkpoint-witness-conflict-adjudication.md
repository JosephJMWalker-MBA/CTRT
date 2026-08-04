# Phase 1A: Current checkpoint witness conflict adjudication

## Purpose

This layer adds authorized conflict adjudication over the exact named-witness population introduced by `1.18.0`.

It answers one bounded question:

> When the exact required `1.18.0` witness population conflicts, what did the accepted adjudication authority select from the preserved observations?

It does not revise the witness record. It adds a separate authority claim over immutable disagreement evidence.

## Preserved predecessor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound-witness-bound@1.18.0
sha256:772d4989ccb1670676f17784a372028949ecc5d0d080261b412fa7c25733f3f2
```

The predecessor binds the exact `1.17.0` checkpoint corpus, witness registry, witness policy, and canonical alpha, beta, and gamma observations.

Nothing in `1.18.0` is edited.

## Exact checkpoint head

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:245efb3279bc1b10c5ffafa337665a947a8dd86e9693590cccf09a6021d829a2
```

A resolved adjudication may select only this head.

## Fixed adjudication graph

### Adjudicator registry

```text
registry.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicators@0.1.0
sha256:e2acef5f118157df9f77419a939b1920bfa83ea7a34d508d921fe41927909ead
```

Registered authority:

```text
adjudicator.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-fork
```

Identity revision:

```text
synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator@0.1.0
```

Role:

```text
witness_conflict_adjudicator
```

### Adjudication policy

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication@0.1.0
sha256:fb1adf97e37340fac363dfac3f5598d9810a5ff991050b5b3580bbb0bc3cf05e
```

The policy requires:

```text
abstain_on_pending = true
abstain_on_unresolved = true
resolution_must_select_declared_head = true
forbid_vote_aggregation = true
```

### Conflicting gamma observation

```text
checkpoint-witness-attestation:attestation.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma.conflict.v0.1.0
sha256:067f8962419550f6df976c14f96e1d084bcddae5ec521b77bebfc75a37e2cece
```

The current conflicting population is:

```text
alpha -> matches exact head
beta  -> matches exact head
gamma -> reports alternate head
```

The resulting witness outcome remains:

```text
abstain
```

Two matches do not outvote the required conflict.

### Adjudication record

```text
witness-conflict-adjudication:adjudication.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma-conflict.v0.1.0
sha256:75993645d1489767bf26f0828e42148b9b631f0747bfce5d3f4be35841b5d68f
```

The record preserves:

- the exact `1.18.0` predecessor;
- the exact witness registry and policy;
- the accepted adjudicator registry and policy;
- the exact checkpoint head;
- gamma's exact conflicting attestation;
- gamma's alternate observed head;
- fork evidence;
- preserved dissent;
- the selected exact checkpoint head;
- the rationale and decision timestamp.

### Successor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound-witness-conflict-adjudication-bound@1.19.0
sha256:ec430190b7e75d0f0e5e7a207a9a786edf24c090046098d2e7699b294876e784
```

The compact successor contains only exact references, unchanged content order, frozen status, and its publication timestamp.

It does not duplicate inherited evidence or add confidence, vote counts, reputation, or trust fields.

## Canonical chronology

```text
2026-08-03T19:57:52Z  1.18.0 witness successor published
2026-08-03T19:57:56Z  adjudicator registry created
2026-08-03T19:57:57Z  adjudication policy created
2026-08-03T19:57:59Z  adjudication record decided
2026-08-03T19:58:00Z  1.19.0 adjudication successor published
2026-08-03T19:58:01Z  conflicting witness population evaluated
2026-08-03T19:58:02Z  adjudication evaluated
2026-08-03T19:58:03Z  exact 1.17.0 checkpoint reverified after resolution
2026-08-03T19:58:04Z  canonical 1.18.0 witness population evaluated
2026-08-03T19:58:05Z  current revocation evaluated
```

The outer runner requires:

```text
1.19.0.created_at
  <= conflicting_witness_evaluated_at
  <= conflict_adjudication_evaluated_at
  <= current_checkpoint_verified_at
  <= canonical_current_witness_evaluated_at
  <= current_revocation_evaluated_at
  <= PR #40 completion
  <= outer completion
```

## Publication order

Manifest-last publication is:

1. accepted adjudicator registry;
2. accepted adjudication policy;
3. immutable conflicting gamma attestation;
4. immutable adjudication record;
5. compact `1.19.0` successor;
6. exact-hash reread of the complete graph and exact `1.18.0` predecessor.

## Contract adapter

```text
src/ctrt/current_checkpoint_witness_conflict_adjudication.py
```

Primary types:

```text
ConflictingCurrentCheckpointWitnessCorpusSnapshot
AdjudicationBoundCurrentCheckpointWitnessCorpusSnapshot
```

Public operations:

```text
load_current_checkpoint_conflict_adjudication_evidence
validate_current_checkpoint_conflict_adjudication
persist_current_checkpoint_adjudication_bound_corpus
```

The adapter reuses the provider-neutral adjudicator checkpoint-witness conflict grammar. It adds only:

- exact `1.17.0` checkpoint-predecessor binding;
- exact `1.18.0` witness-predecessor binding;
- the context-specific manifest prefix;
- compact successor parsing;
- chronology and manifest-last storage.

## Adjudication-gated runner

```text
src/ctrt/adjudicated_current_checkpoint_witness_runner.py
```

`AdjudicatedCurrentCheckpointWitnessExperimentRunner` performs:

1. exact frozen-plan and graph preflight;
2. storage-backed loading of the complete conflict graph;
3. validation of the exact conflicting witness population;
4. persistence of the original witness decision;
5. validation of the accepted adjudication;
6. persistence of the adjudication decision;
7. terminal abstention for pending or unresolved status;
8. exact plan narrowing from `1.19.0` to `1.18.0` after resolved execution;
9. unchanged PR #40 invocation under the same experiment run ID;
10. outer final persistence;
11. complete storage-backed reread.

## Explicit scopes

```text
1.19.0 plan -> conflicting witness decision, adjudication, outer finalization
1.18.0 plan -> unchanged PR #40 named-witness lifecycle
1.17.0 plan -> unchanged checkpoint lifecycle
1.16.0 plan -> unchanged current revocation lifecycle
1.15.0 plan -> unchanged current credential lifecycle
1.14.0 plan -> unchanged lower disagreement/adjudication lifecycle
1.13.0 plan -> unchanged lower named-witness lifecycle
1.12.0 plan -> unchanged inherited checkpoint lifecycle
```

Only the corpus reference and identical ordered content IDs narrow between layers.

## Independent outcomes

The outer receipt preserves separately:

```text
conflicting_witness_outcome
current_resolution_status
current_conflict_adjudication_outcome
resolved_current_witness_outcome
current_revocation_outcome
current_credential_outcome
lower_checkpoint_witness_outcome
lower_resolution_status
lower_conflict_adjudication_outcome
lower_predecessor_witness_outcome
inherited_revocation_outcome
inherited_credential_outcome
inherited_checkpoint_witness_outcome
inherited_resolution_status
inherited_adjudication_outcome
terminal_outcome
```

No later result rewrites an earlier claim.

## Outcome matrix

### Resolved conflict; complete execution

```text
conflicting witness            = abstain
current resolution             = resolved
current conflict adjudication  = execute
canonical current witnesses    = execute
current revocation             = execute
current credential             = execute
lower checkpoint witness       = abstain
lower resolution               = resolved
lower conflict adjudication    = execute
lower predecessor witness      = execute
inherited revocation           = execute
inherited credential           = execute
inherited checkpoint witness   = execute
inherited resolution           = not_required
inherited adjudication         = execute
terminal outcome               = execute
```

### Pending or unresolved conflict

```text
conflicting witness            = abstain
current resolution             = pending | unresolved
current conflict adjudication  = abstain
all downstream outcomes        = null
terminal outcome               = abstain
PR #40                         = not invoked
```

### Resolved conflict; later current suspension

```text
conflicting witness            = abstain
current resolution             = resolved
current conflict adjudication  = execute
canonical current witnesses    = execute
current revocation             = abstain
current credential/later       = null
terminal outcome               = abstain
```

The resolution remains `execute`; the later revocation remains a separate `abstain`.

## Run-specific artifacts

Conflicting witness decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-witness-decision
```

Adjudication decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-decision
```

Successful completion:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-completion
```

Adjudication abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-abstention
```

Resolved adjudication followed by downstream abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-terminal-abstention
```

## Structural failures

The boundary fails closed for:

- predecessor identity or hash drift;
- content-order drift;
- witness registry or policy drift;
- attestation omission, substitution, reordering, or identity-revision drift;
- adjudicator registry or policy drift;
- adjudication-record reference drift;
- fork-evidence or preserved-dissent drift;
- selection of any head other than the exact declared checkpoint head;
- decision or lifecycle chronology drift;
- experiment run-identity mismatch;
- stored artifact or canonical serialization drift.

Pending and unresolved statuses are governed abstentions, not structural failures.

## Test coverage

Contract and storage tests prove:

- exact registry, policy, conflict, adjudication, predecessor, and successor hashes;
- closed schemas;
- original witness abstention remains unchanged;
- resolved adjudication executes;
- pending and unresolved adjudications abstain;
- alternate-head selection fails;
- decision chronology is enforced;
- manifest-last reconstruction is deterministic;
- unsupported confidence fields are rejected.

Stored lifecycle tests use the real PR #30 through PR #40 evidence chain and prove:

1. resolved adjudication delegates exact PR #40;
2. the same run ID crosses the `1.19.0 -> 1.18.0` boundary;
3. pending and unresolved statuses create no PR #40 final;
4. later current suspension preserves adjudication execution;
5. invalid outer chronology fails before delegation;
6. execution and abstention satisfy one closed final schema;
7. every public contract and runner symbol remains importable.

## Review checklist

1. Does `1.19.0` bind the exact immutable `1.18.0` predecessor?
2. Is the exact conflicting witness population preserved in required order?
3. Does the witness decision remain `abstain`?
4. Are fork evidence and gamma dissent preserved exactly?
5. Is the accepted authority bound by exact identity revision and role?
6. Can resolved adjudication select only the exact `1.17.0` checkpoint head?
7. Do pending and unresolved statuses stop before PR #40?
8. Are witness and adjudication decisions persisted before delegation?
9. Does resolved execution narrow only to exact `1.18.0` under the same run ID?
10. Are every current, lower, inherited, and terminal outcome kept independent?

## Next boundary

The next bounded layer may add credential attestation for the exact new adjudicator identity revision and `witness_conflict_adjudicator` role.

It must preserve the complete `1.19.0` disagreement and adjudication graph unchanged.
