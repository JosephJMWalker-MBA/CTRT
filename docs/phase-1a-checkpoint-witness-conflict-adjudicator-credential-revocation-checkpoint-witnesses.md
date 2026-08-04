# Phase 1A: Named witnesses for the checkpoint-fork adjudicator revocation checkpoint

## Bounded question

> What did each required named witness report about the exact immutable `1.17.0` checkpoint head?

This layer records observations. It does not rate witnesses, aggregate votes,
resolve disagreement, or strengthen the checkpoint's external truth claim.

## Corpus evolution

```text
1.18.0 plan -> current witness decision and outer finalization
1.17.0 plan -> unchanged PR #39 checkpoint lifecycle after witness execution
1.16.0 plan -> unchanged current revocation lifecycle
1.15.0 plan -> unchanged current credential lifecycle
1.14.0 plan -> unchanged current disagreement/adjudication lifecycle
1.13.0 plan -> unchanged predecessor named-witness lifecycle
1.12.0 plan -> unchanged inherited checkpoint lifecycle
```

Only the corpus reference and identical ordered content IDs narrow. Experiment
identity, version, parameters, run ID, and all inherited evidence remain
unchanged.

## Exact predecessor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.17.0
sha256:e801447e9d897baa442effd11f2a1d059624e05d7286ad7ec2bc3761e328849d
```

The predecessor binds the exact checkpoint head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:245efb3279bc1b10c5ffafa337665a947a8dd86e9693590cccf09a6021d829a2
```

and checkpoint log:

```text
log.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:45e9330da82ddf1295a07cd0f763c1447a9cbfccc716b20f590d94113409aa24
```

## Fixed witness graph

### Registry

```text
registry.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:53be7d043a958e6d7c5ae281524ddc2e88700535bc9487863fdc192556f79526
```

Required pseudonymous witnesses:

```text
witness.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-alpha
witness.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-beta
witness.synthetic.witness-conflict-adjudicator-checkpoint-witness-conflict-gamma
```

Each is bound to the same exact identity revision and the
`checkpoint_observer` role.

### Policy

```text
policy.synthetic-witness-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:f9d0e889087b08e7e6e8c70e57b56dac3ea1993b7bdc82d254257f34f8c156ac
```

```text
all three witness IDs required
abstain_on_conflicting_head = true
forbid_vote_aggregation = true
```

### Canonical attestations

```text
alpha = sha256:c02cdb6188eef0a1368c7ff8cbe7e7547b1c221bd83ab79a221d828cfcfde247
beta  = sha256:c324552540e83cea3d3b37ed51e06bf698ab02c79e1c5f0aa940b42a923ff603
gamma = sha256:b842850d96f1155c417bb857fa65ffbeb4b7287313eef4a15d15aec4bc3bebec
```

Every canonical attestation reports `matches_head` for the exact `1.17.0`
checkpoint head. Each attestation remains a separate immutable artifact.

### Successor

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound-witness-bound@1.18.0
sha256:772d4989ccb1670676f17784a372028949ecc5d0d080261b412fa7c25733f3f2
```

The successor contains only exact predecessor, registry, policy, attestation,
content-order, status, and publication references. It does not duplicate
checkpoint, ledger, credential, disagreement, or adjudication evidence.

## Canonical chronology

```text
2026-08-03T19:57:44Z  1.17.0 checkpoint successor published
2026-08-03T19:57:45Z  current witness registry created
2026-08-03T19:57:46Z  current witness policy created
2026-08-03T19:57:47Z  alpha observed
2026-08-03T19:57:48Z  alpha received; beta observed
2026-08-03T19:57:49Z  beta received; gamma observed
2026-08-03T19:57:50Z  gamma received
2026-08-03T19:57:52Z  1.18.0 witness successor published
2026-08-03T19:57:53Z  current checkpoint reverified
2026-08-03T19:57:54Z  current witness population evaluated
2026-08-03T19:57:55Z  current revocation evaluated after witness execution
```

The outer lifecycle requires:

```text
1.18.0.created_at
  <= current_checkpoint_verified_at
  <= current_witness_evaluated_at
  <= current_revocation_evaluated_at
  <= outer completion
```

## No-majority decision

```text
match + match + match    -> execute
match + match + conflict -> abstain
```

A required conflict remains visible as its own observation and stops before PR
#39. Two matching witnesses cannot outvote it.

The canonical corpus is all matching. The conflict test substitutes one exact
gamma attestation and updates the successor's exact reference, proving the
abstention path without rewriting canonical evidence.

## Manifest-last publication

Publication order is:

1. accepted witness registry;
2. accepted witness policy;
3. immutable attestations in exact required order;
4. compact `1.18.0` successor;
5. exact-hash reread of registry, policy, attestations, successor, predecessor,
   checkpoint log, and checkpoint head.

## Contract adapter

```text
src/ctrt/checkpoint_witness_conflict_adjudicator_credential_revocation_checkpoint_witness.py
```

Primary type:

```text
WitnessBoundCheckpointWitnessConflictAdjudicatorCredentialRevocationCorpusSnapshot
```

Public operations:

```text
load_current_checkpoint_witness_evidence
validate_current_checkpoint_witness_attestations
persist_current_checkpoint_witness_corpus
```

The adapter reuses the provider-neutral adjudicator checkpoint-witness grammar.
It adds only exact `1.17.0` binding, context-specific names, chronology, and
manifest-last publication.

## Witness-gated runner

```text
src/ctrt/witness_gated_current_checkpoint_runner.py
```

`WitnessGatedCurrentCheckpointExperimentRunner` performs:

1. exact frozen-plan, predecessor, registry, policy, attestation order, checkpoint
   graph, run identity, and chronology preflight;
2. storage-backed loading of current witness and checkpoint evidence;
3. exact `1.17.0` checkpoint reverification;
4. independent checkpoint-report persistence;
5. current named-witness validation;
6. independent witness-decision persistence;
7. terminal abstention for any required conflicting head;
8. exact `1.18.0 -> 1.17.0` plan narrowing only after witness execution;
9. unchanged PR #39 invocation under the same experiment run ID;
10. outer final persistence and complete storage-backed reread.

## Run-specific artifacts

Checkpoint reverification:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-checkpoint-verification
```

Witness decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-decision
```

Current witness abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-abstention
```

Successful or downstream-abstaining finals end in `completion` or
`terminal-abstention` respectively.

## Independent outcomes

```text
current checkpoint witness outcome
current checkpoint verification
current revocation outcome
current credential outcome
current conflict-witness outcome
current conflict-adjudication outcome
predecessor witness outcome
all inherited outcomes
terminal outcome
```

The current witness outcome remains `execute` when a later revocation boundary
causes downstream abstention.

## Outcome matrix

### All required current witnesses match

```text
current checkpoint witnesses = execute
PR #39                      = invoked
terminal outcome            = exact delegated result
```

### One required current witness conflicts

```text
current checkpoint witnesses = abstain
checkpoint report            = persisted
witness decision             = persisted
PR #39                       = not invoked
all downstream outcomes      = null
terminal outcome             = abstain
```

### All current witnesses match; current suspension later becomes effective

```text
current checkpoint witnesses = execute
current revocation           = abstain
current credential and later = null
terminal outcome             = abstain
```

The witness decision is not rewritten by the later revocation result.

## Structural failure boundaries

The layer fails closed for:

- `1.17.0` predecessor identity or hash drift;
- content-order drift;
- registry, policy, or attestation-reference substitution;
- missing or duplicate required witnesses;
- witness identity-revision drift;
- checkpoint corpus, log, or head substitution;
- observation before checkpoint publication;
- receipt before observation;
- witness evaluation before checkpoint reverification;
- delegated receipt run-identity mismatch;
- stored artifact or canonical serialization drift.

A valid conflicting observation is governed abstention rather than structural
failure.

## Test map

Contract tests prove:

- all fixed hashes and closed schemas;
- exact `1.17.0` predecessor binding;
- canonical unanimous execution;
- one required conflict abstains without vote aggregation;
- identity-revision substitution fails structurally;
- observation chronology is enforced;
- manifest-last reconstruction is deterministic;
- unsupported confidence fields are rejected.

Stored lifecycle tests use the real PR #30 through PR #39 evidence chain and
prove:

- unanimous current witnesses delegate exact PR #39;
- one required conflict persists both reports and creates no PR #39 final;
- unanimous current witnesses remain `execute` when current revocation later
  abstains;
- invalid outer chronology fails before delegation;
- execution and abstention satisfy one closed final schema;
- the same experiment run ID crosses every delegated boundary.

## Trust boundary

This layer does not establish:

- legal or real-world witness identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- witness independence, competence, honesty, or correctness;
- checkpoint or ledger completeness;
- absence of undisclosed events, ledgers, or checkpoint chains;
- global uniqueness or public availability of the observed head;
- majority support, quorum, consensus, confidence, reputation, or trust;
- correctness of inherited adjudications or selected heads;
- extraction, analyzer, model, dataset, or content accuracy;
- a frontend, deployment, or aggregate CTRT score.

## Bounded successor

The next layer may add authorized adjudication for a conflict among the exact
`1.18.0` observations. It must preserve every original observation, the original
abstention, the exact `1.17.0` checkpoint report and head, every current and
inherited decision, fork evidence, dissent, rationale, and selected head.
