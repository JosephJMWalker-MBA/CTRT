# Phase 1A: Checkpoint-conflict adjudicator revocation checkpoint witnesses

## Purpose

This layer adds immutable named-witness observations to the exact checkpoint protecting the frozen revocation ledger for the credential used by a checkpoint-conflict adjudicator.

It answers one bounded question:

> Did every policy-required named witness report the exact independently verified `1.7.0` checkpoint head?

It does not decide whether a witness is truthful, independent, competent, or legally identifiable. It does not determine which conflicting observation is correct. It does not convert witness reports into votes, confidence, reputation, or consensus.

## Fixed synthetic graph

### Witness registry

```text
registry.synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-witnesses@0.1.0
sha256:b1913fc0755e92d266f22683f4cfb4e804be7f79eb2af291232eea06169b38b7
```

The frozen registry contains three required pseudonymous observers in exact order:

```text
witness.synthetic.checkpoint-conflict-alpha
witness.synthetic.checkpoint-conflict-beta
witness.synthetic.checkpoint-conflict-gamma
```

Each is bound to:

```text
identity_revision = synthetic-checkpoint-conflict-revocation-checkpoint-witness@0.1.0
role = checkpoint_observer
```

### Witness policy

```text
policy.synthetic-checkpoint-conflict-adjudicator-revocation-checkpoint-witnesses@0.1.0
sha256:05d42931c5a1df1d6390c331e199b76b6d303f77f771950ed913c6a13ebeb5a2
```

The accepted policy requires the exact registry and witness order, abstains on any conflicting head, and explicitly forbids vote aggregation.

### Exact checkpoint under observation

The attestations bind the exact checkpoint corpus:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-bound@1.7.0
sha256:26311c6a5da00c7e6ea3986406be48ca8d3087ccf3f41f07c783cd8db88635fb
```

They also bind the exact frozen checkpoint log:

```text
log.synthetic-adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:575a42f1c90435ab30e6c56c0b80aefc111ac44d89b1b9c7a401d6301aa4b2f2
```

And the exact checkpoint head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.adjudicator-checkpoint-conflict-adjudicator-credential-revocations.0000
sha256:ccf31947e678160514a5ac6f59eec7f3718c56e7800c973f23c0770895629422
```

### Immutable attestations

Canonical matching attestation hashes:

```text
alpha: sha256:f512252b9652407c2bc4b6c79f8eddec78568ee7c3119009832596a3d40e05ed
beta:  sha256:6c87ac3d32acb4dcdbb76552e92eaa7a1df1daf39a9197509db734893d0e9997
gamma: sha256:b5191d780400b6cf2c6ff6bacaf14775156d21e671be71966d57e0042ed4928c
```

Every attestation preserves:

- witness ID;
- immutable identity revision;
- exact checkpoint corpus reference;
- exact checkpoint log reference;
- expected checkpoint head;
- observed checkpoint head;
- observation kind;
- observation time;
- receipt time;
- witness-authored note.

The canonical fixed graph contains three matching observations. Tests introduce a conflicting observation without changing the published fixtures.

## Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-bound@1.7.0
sha256:26311c6a5da00c7e6ea3986406be48ca8d3087ccf3f41f07c783cd8db88635fb
```

Successor:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.8.0
sha256:3d48f367ce1b1101dd7044bb846da42786e3eb9af55c6de7d9bc9e5545f2479a
```

The `1.8.0` artifact is a compact successor manifest. It binds the exact immutable `1.7.0` predecessor, witness registry, witness policy, ordered attestation population, and unchanged content order.

Publication is manifest-last:

1. witness registry;
2. witness policy;
3. immutable attestations;
4. `1.8.0` manifest.

No predecessor artifact is edited.

## Witness evaluation

The validator independently preserves one observation summary per required witness.

### All required witnesses match

```text
alpha = matches_head
beta  = matches_head
gamma = matches_head
outcome = execute
```

The layer may delegate to the unchanged `1.7.0` checkpoint runner.

### Any required witness conflicts

```text
alpha = matches_head
beta  = matches_head
gamma = conflicting_head
outcome = abstain
```

Two matching observations do not outvote one conflict. The current witness decision is terminal and no `1.7.0` checkpoint-runner final artifact may be created.

The underlying checkpoint remains preserved and independently verifiable. The abstention means only that the exact required observation population did not uniformly report that head.

## Execution lifecycle

`WitnessGatedAdjudicatorCheckpointConflictExperimentRunner` performs:

1. exact `1.8.0` plan, manifest, registry, policy, attestation population, content order, run ID, and timestamp preflight;
2. storage-backed loading of the witness graph and the complete `1.7.0` checkpoint graph;
3. independent structural revalidation of the exact checkpoint chain and ledger-head coverage;
4. run-specific checkpoint-verification persistence and reread verification;
5. structural validation of every named witness attestation;
6. run-specific witness-decision persistence and reread verification;
7. terminal witness abstention or explicit scoped delegation;
8. final-manifest persistence;
9. complete storage-backed reread verification.

Run-specific artifacts:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-verification
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-decision
```

Terminal artifacts:

```text
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-abstention
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-completion
<run>:adjudicator-checkpoint-conflict-adjudicator-credential-revocation-checkpoint-witness-terminal-abstention
```

## Explicit nested-plan delegation

The outer witness runner receives a frozen plan bound to `1.8.0`.

When every current witness matches, it derives a nested plan bound to the exact immutable `1.7.0` predecessor and invokes the unchanged ADR-0032 runner:

```text
outer plan:
  corpus = 1.8.0
  purpose = checkpoint reverification, witness evaluation, outer finalization

nested plan:
  corpus = 1.7.0
  purpose = unchanged checkpoint, revocation, and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidates, analyzers, execution windows, and all prior governance evidence remain identical. Only the corpus reference is explicitly narrowed to the predecessor required by the delegated runner.

## Terminal behavior

### Current witness outcome: `execute`; delegated terminal outcome: `execute`

The outer runner preserves:

- current checkpoint-verification report;
- current witness decision and all named observation summaries;
- delegated checkpoint receipt;
- revocation and credential outcomes;
- prior checkpoint-witness and conflict-adjudication outcomes;
- reviewer governance outcomes;
- final analysis outcome.

### Current witness outcome: `abstain`

The outer runner persists the checkpoint report, witness decision, and witness-abstention final.

It must not create or report:

- the delegated `1.7.0` checkpoint final;
- the revocation decision;
- checkpoint-conflict adjudicator credential evaluation;
- earlier witness or conflict-adjudication stages;
- reviewer governance;
- analyzer execution.

Every downstream outcome remains null.

### Current witness outcome: `execute`; delegated revocation outcome: `abstain`

The current witness decision remains independently `execute` because every named witness matched the checkpoint head.

The delegated revocation decision remains independently `abstain` because the credential suspension became effective at the later evaluation boundary.

The final outcome is terminal abstention without rewriting either decision.

## Structural failure versus governed abstention

Structural failure includes:

- exact-reference drift;
- registry, policy, witness-population, or order drift;
- missing, duplicate, or unknown witnesses;
- identity-revision drift;
- observed-head and observation-kind inconsistency;
- observation before checkpoint publication;
- receipt before observation;
- evaluation before receipt;
- altered or missing stored evidence;
- persistence or reread defects.

Governed abstention is reserved for a structurally valid required witness reporting a conflicting checkpoint head.

This prevents malformed evidence from being represented as ordinary witness disagreement.

## Schemas

This slice reuses the established generic schemas for:

- adjudicator-checkpoint witness registry;
- adjudicator-checkpoint witness policy;
- adjudicator-checkpoint witness attestation;
- adjudicator-checkpoint witness decision.

It adds context-specific schemas for:

- the compact `1.8.0` witness-bound corpus;
- the witness-gated final manifest.

The final schema requires every downstream outcome and the delegated checkpoint-final reference to be null when the current witness decision abstains.

## Privacy boundary

Artifacts contain stable pseudonymous IDs, immutable revisions, roles, artifact references, observation kinds, timestamps, notes, statuses, and declared governance outcomes.

They contain no private identity data, signatures, keys, certificate chains, reputation scores, vote counts, quorum, consensus percentages, model outputs, datasets, or aggregate CTRT score.

## Trust boundary

`verified` means that the declared immutable checkpoint and witness graphs were reconstructed and validated under the accepted contracts.

It does not establish legal identity, witness independence, honesty, competence, cryptographic authorship, trusted external time, public availability, global checkpoint uniqueness, complete event disclosure, adjudicator correctness, witness truthfulness, or analytical accuracy.

See [ADR-0033](adr/0033-checkpoint-conflict-revocation-checkpoints-require-named-witness-observations.md).
