# Phase 1A: Current conflict-adjudicator revocation checkpoint witnesses

## Purpose

This bounded layer adds immutable named-witness observations above the exact `1.22.0` checkpoint introduced by PR #44.

It asks only:

> What did each policy-required named witness report about the exact immutable `1.22.0` checkpoint head?

It does not change the checkpoint, revocation ledger, credential, preserved witness disagreement, prior abstention, adjudication, fork evidence, dissent, selected head, rationale, or any inherited outcome.

## Exact predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.22.0
sha256:3ef12c528781ddec9976323b8a23670f3592839ce2145afed60cda39170c0304
```

The predecessor binds the exact frozen checkpoint log:

```text
log.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:5f9dde79fcffcafd0372229262b5e6cd9fdc148ff63750134f6467d77497b48b
```

and exact head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
```

## Fixed witness graph

### Registry

```text
registry.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:2d0fe7764d111f480fd556b62357725d0ba5997e7abcce5dfa7057b398f18eb9
```

Required order:

```text
witness.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-alpha
witness.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-beta
witness.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma
```

Each witness binds the exact identity revision:

```text
synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness@0.1.0
```

and role `checkpoint_observer`.

### Policy

```text
policy.synthetic-current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:b9f2a86df193ba17900b1c682b5526002ab775a810bbbf704a2c382c3f36fdab
```

The accepted policy binds the exact registry and required order and requires:

```text
abstain_on_conflicting_head = true
forbid_vote_aggregation = true
```

### Canonical observations

```text
alpha = sha256:5971087e0b9cc985b7349f486780c7fbaf1420c2469fa20f0fa8a4d1c19751fc
beta  = sha256:f655cfbeff98550eb8fdbb7516fc5e89246e3547a0ae2c8d2cca95a6b6c15945
gamma = sha256:1d0d661270308e4d7b13e2e42ecaf0bec9124aff309bc35aa36caab1a597ae36
```

Each observation binds:

- exact witness ID and identity revision;
- exact `1.22.0` checkpoint corpus;
- exact checkpoint log;
- exact expected head;
- separately recorded observed head;
- observation kind;
- observation timestamp;
- receipt timestamp;
- non-authoritative note.

The canonical population contains three `matches_head` observations. Conflict paths introduce a new immutable conflicting observation and a successor reference to it; canonical artifacts are not edited.

### Successor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.23.0
sha256:73cc89c16ebb72c07ec7731ae1b25c3981681eb590005c8fe66c953facca4666
```

The successor is compact. It contains only exact predecessor, registry, policy, ordered attestation references, unchanged content IDs, frozen status, and publication time.

## No-majority semantics

```text
alpha match + beta match + gamma match    -> execute
alpha match + beta match + gamma conflict -> abstain
```

Two matches cannot outvote a required conflict. No count, majority, quorum, consensus, confidence, reputation, or trust score is derived.

A conflict means only that the exact required population did not uniformly report the declared checkpoint head. It does not invalidate the checkpoint, determine which witness was correct, or erase matching observations.

## Canonical chronology

```text
2026-08-03T19:58:21Z  1.22.0 checkpoint successor published
2026-08-03T19:58:22Z  witness registry created
2026-08-03T19:58:23Z  witness policy created
2026-08-03T19:58:24Z  alpha observed
2026-08-03T19:58:25Z  alpha received; beta observed
2026-08-03T19:58:26Z  beta received; gamma observed
2026-08-03T19:58:27Z  gamma received
2026-08-03T19:58:29Z  1.23.0 successor published
2026-08-03T19:58:30Z  exact 1.22.0 checkpoint reverified
2026-08-03T19:58:31Z  current witness population evaluated
```

The outer boundary additionally requires delegated `1.22.0` checkpoint verification, revocation evaluation, delegated completion, and outer completion to occur in nondecreasing order after witness evaluation.

## Manifest-last publication

Publication order is:

1. accepted witness registry;
2. accepted witness policy;
3. immutable observations in exact required order;
4. compact `1.23.0` successor manifest;
5. exact-hash reread of registry, policy, observations, successor, predecessor, checkpoint log, and checkpoint head.

The exact `1.22.0` predecessor is verified but never rewritten.

## Contract adapter

```text
src/ctrt/current_checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_witness.py
```

Primary type:

```text
WitnessBoundCurrentConflictAdjudicatorRevocationCheckpointCorpusSnapshot
```

Public operations:

```text
load_current_conflict_adjudicator_revocation_checkpoint_witness_evidence
validate_current_conflict_adjudicator_revocation_checkpoint_witnesses
persist_current_conflict_adjudicator_revocation_checkpoint_witness_corpus
```

The adapter reuses the provider-neutral adjudicator checkpoint-witness grammar and adds only exact `1.22.0` binding, context chronology, compact successor parsing, and manifest-last persistence.

## Witness-gated runner

```text
src/ctrt/witness_gated_current_revocation_checkpoint_runner.py
```

`WitnessGatedCurrentRevocationCheckpointExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, registry, policy, attestation order, checkpoint graph, run identity, and chronology preflight;
2. storage-backed loading of witness and checkpoint evidence;
3. exact `1.22.0` checkpoint reverification;
4. independent checkpoint-report persistence;
5. current named-witness validation;
6. independent witness-decision persistence;
7. terminal abstention for any required conflict;
8. exact plan narrowing from `1.23.0` to `1.22.0` only after witness execution;
9. unchanged PR #44 invocation under the same experiment run ID;
10. outer final persistence and complete storage reread.

## Explicit scopes

```text
1.23.0 plan -> current named-witness decision and outer finalization
1.22.0 plan -> unchanged PR #44 checkpoint lifecycle
1.21.0 plan -> unchanged conflict-adjudicator revocation lifecycle
1.20.0 plan -> unchanged conflict-adjudicator credential lifecycle
1.19.0 plan -> unchanged disagreement and adjudication lifecycle
1.18.0 plan -> unchanged canonical current named-witness lifecycle
1.17.0 plan -> unchanged lower checkpoint lifecycle
```

Only the corpus reference and identical ordered content IDs narrow between layers.

## Independent outcomes

The final record preserves separately:

```text
current_conflict_adjudicator_revocation_checkpoint_witness_outcome
current_conflict_adjudicator_revocation_outcome
current_conflict_adjudicator_credential_outcome
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

Checkpoint reverification remains independently visible through its stored report. No later result rewrites an earlier observation or governance claim.

## Outcome matrix

### All required witnesses match; complete execution

```text
current revocation-checkpoint witness = execute
PR #44                                = invoked
terminal outcome                      = exact delegated result
```

### One required witness conflicts

```text
current revocation-checkpoint witness = abstain
checkpoint report                     = persisted
witness decision                      = persisted
PR #44                                = not invoked
all PR #44 outcomes                   = null
terminal outcome                      = abstain
```

### All witnesses match; revocation later abstains

```text
current revocation-checkpoint witness = execute
current conflict-adjudicator revocation = abstain
later outcomes                          = null
terminal outcome                        = abstain
```

The witness execution remains visible and unchanged.

## Run-specific artifacts

Checkpoint reverification report:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-checkpoint-verification
```

Witness decision:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-decision
```

Witness conflict:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-abstention
```

Successful lifecycle:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-completion
```

Witness execution followed by downstream abstention:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-terminal-abstention
```

## Test coverage

Contract and storage tests prove:

- exact registry, policy, observation, predecessor, and successor hashes;
- closed registry, policy, attestation, successor, and final schemas;
- exact `1.22.0` predecessor, checkpoint log, and head binding;
- exact required witness population and order;
- unanimous execution;
- one-conflict abstention despite two matches;
- identity-revision substitution failure;
- observation-before-checkpoint failure;
- manifest-last reconstruction;
- unsupported-confidence rejection;
- public API stability.

Stored lifecycle tests use a real PR #44 receipt from the complete authority chain and prove:

1. unanimous witnesses delegate exact PR #44;
2. the same experiment run ID crosses the `1.23.0 -> 1.22.0` boundary;
3. one required conflict creates no PR #44 final;
4. witness execution remains separate from later revocation abstention;
5. invalid outer chronology fails before delegation;
6. execution, witness abstention, and downstream abstention satisfy one closed final schema.

## Structural failures

The boundary fails closed for predecessor, content order, registry, policy, attestation population, witness order, identity revision, checkpoint log, checkpoint head, observation chronology, receipt chronology, run identity, stored artifact, or canonical serialization drift.

A valid required conflicting observation is governed abstention rather than structural failure.

## Trust boundary

Artifacts preserve stable pseudonymous IDs, immutable identity revisions, exact artifact references, expected and observed heads, deterministic hashes, timestamps, observation kinds, abstention metadata, and separate outcomes.

Verification does not establish legal identity, cryptographic authorship, key possession, trusted external time, witness independence or correctness, checkpoint truth beyond structural verification, ledger completeness, absence of alternate histories, global uniqueness, public availability, majority support, quorum, consensus, confidence, reputation, adjudication correctness, analytical accuracy, deployment, or an aggregate CTRT score.

## Intentionally deferred

The next bounded layer may add authorized conflict adjudication over an exact conflicting `1.23.0` observation population.

It must preserve every original observation, the original witness abstention, the exact `1.22.0` checkpoint report and head, all revocation and credential evidence, fork evidence, dissent, rationale, selected heads, and every inherited artifact unchanged.
