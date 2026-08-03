# Phase 1A: Witness Conflict Adjudication

This guide describes the dependency-free witness-conflict adjudication slice implemented by CTRT.

The layer begins after a checkpoint-witness decision has already been computed. It does not reinterpret witness observations or count witnesses. It preserves the original witness outcome, adds an independently authorized adjudication record, and either abstains or permits the existing checkpoint-gated lifecycle to proceed.

## Constitutional rule

> Witness observations are evidence. Adjudication is a governed decision about whether the independently verified declared checkpoint head may proceed. Neither witness count nor adjudicator authority becomes a truth score.

## Inputs

The adjudication layer binds the exact:

- frozen experiment plan;
- checkpoint-bound and witness-bound corpus lineage;
- checkpoint log and verified head;
- witness registry and policy;
- ordered witness-attestation population;
- original witness decision;
- adjudicator registry;
- adjudication policy;
- immutable adjudication record;
- evaluation timestamps.

No input is resolved by name alone. Every persistent relationship is bound by immutable ID, version where applicable, and canonical hash.

## Public contracts

### Adjudicator authority

`WitnessConflictAdjudicatorRecord` records:

- adjudicator ID;
- immutable identity revision;
- role.

The initial supported role is:

```text
witness_conflict_adjudicator
```

`WitnessConflictAdjudicatorRegistrySnapshot` is frozen, versioned, canonical, and append-only.

### Adjudication policy

`WitnessConflictAdjudicationPolicySnapshot` binds:

- exact adjudicator registry;
- exact required adjudicator population;
- fail-closed pending behavior;
- fail-closed unresolved behavior;
- requirement that resolution select the declared verified head;
- prohibition on vote aggregation.

The initial accepted policy requires all of these safeguards to be enabled.

### Fork evidence

`WitnessForkEvidence` preserves one conflicting witness claim:

- witness ID;
- exact witness-attestation reference;
- expected checkpoint head;
- observed conflicting checkpoint head.

The record is reconstructed from the existing witness decision. An adjudication payload cannot silently add, remove, or rewrite the witness conflict population.

### Preserved dissent

`PreservedWitnessDissent` binds:

- the same witness ID;
- the same attestation;
- the same observed head;
- a human-readable note.

Every decided conflict must preserve one dissent record for every fork-evidence record.

### Adjudication record

`WitnessConflictAdjudicationSnapshot` records:

- exact predecessor witness corpus;
- exact witness registry and policy;
- exact adjudicator registry and policy;
- exact declared checkpoint head;
- lifecycle status;
- adjudicator identity and revision when decided;
- selected head only when resolved;
- complete fork evidence;
- complete preserved dissent;
- rationale;
- decision timestamp.

The artifact ID derives deterministically from the adjudication ID.

### Adjudication-bound corpus

`AdjudicationBoundWitnessCorpusSnapshot` wraps the complete witness-bound corpus and adds exact references to:

- the immutable `0.8.0` predecessor;
- adjudicator registry;
- adjudication policy;
- adjudication record.

The synthetic successor is:

```text
corpus.synthetic-three-items.witness-adjudication-bound@0.9.0
```

The predecessor and successor use distinct artifact IDs and coexist in append-only storage.

## Lifecycle states

### `not_required`

Used only when no witness conflict exists.

It contains:

- no fork evidence;
- no adjudicator identity;
- no selected head;
- no preserved dissent.

The original witness outcome must be `execute`.

### `pending`

Used when a conflict exists but no adjudicator decision is claimed.

It contains:

- complete fork evidence;
- no adjudicator identity;
- no selected head;
- no preserved dissent claim.

The result is governed abstention.

### `resolved`

Used when an authorized adjudicator permits the independently verified declared checkpoint head to proceed.

It requires:

- complete fork evidence;
- authorized adjudicator ID, revision, and role;
- selected head equal to the declared checkpoint head;
- exact preserved dissent for every conflict;
- rationale and decision time.

The original witness outcome remains `abstain`. The adjudication outcome becomes `execute`.

### `unresolved`

Used when an authorized adjudicator considered the conflict but did not select a head.

It requires:

- complete fork evidence;
- authorized adjudicator identity and role;
- no selected head;
- exact preserved dissent for every conflict;
- rationale and decision time.

The result is governed abstention.

## Publication workflow

`persist_adjudication_bound_witness_corpus` performs manifest-last publication.

1. Reverify the stored `0.8.0` predecessor.
2. Recompute the witness decision from the supplied witness artifacts.
3. Validate adjudicator authority and the adjudication record.
4. Persist or idempotently reread witness registry and policy.
5. Persist or idempotently reread every witness attestation.
6. Persist or idempotently reread adjudicator registry and policy.
7. Persist or idempotently reread the adjudication record.
8. Write the `0.9.0` corpus manifest last.
9. Reload and reverify the complete stored graph.

An unauthorized adjudicator, substituted reference, or incomplete dissent record prevents publication of a complete adjudication-bound corpus.

Partial graph members may remain in append-only storage, but they do not constitute a published `0.9.0` corpus.

## Execution workflow

`AdjudicatedWitnessCheckpointExperimentRunner` uses these stages:

### 1. Preflight

Checks:

- frozen experiment plan;
- exact plan-to-corpus reference;
- exact ordered content population;
- exact witness registry and policy references;
- exact adjudicator registry, policy, and record references;
- exact execution-window order;
- timezone-aware timestamps.

### 2. Evidence loading

Reloads and rehashes:

- adjudication-bound corpus;
- adjudicator registry;
- adjudication policy;
- adjudication record;
- witness-bound evidence graph;
- checkpoint evidence graph.

### 3. Checkpoint verification

Revalidates the complete checkpoint chain and persists:

```text
<experiment-run-id>:credential-revocation-checkpoint-verification
```

### 4. Witness validation

Recomputes the witness decision and persists:

```text
<experiment-run-id>:checkpoint-witness-decision
```

The synthetic resolved fixture intentionally still produces:

```text
witness_outcome = abstain
```

because gamma reports a conflicting checkpoint head.

### 5. Adjudication validation

Validates the adjudicator, complete conflict population, selected head, dissent, rationale, and timestamps. It persists:

```text
<experiment-run-id>:witness-conflict-adjudication-decision
```

### 6. Execute or abstain

For `pending` or `unresolved`, the runner stores a verified adjudication-abstention artifact and creates no downstream governance or analyzer artifacts.

For `not_required` or `resolved`, it delegates the existing `CheckpointGatedRevocationExperimentRunner` unchanged.

### 7. Finalization

Possible final artifact IDs are:

```text
<experiment-run-id>:witness-conflict-adjudication-abstention
<experiment-run-id>:witness-conflict-adjudication-completion
<experiment-run-id>:witness-conflict-adjudication-terminal-abstention
```

The final artifact preserves separately:

- `witness_outcome`;
- `adjudication_outcome`;
- `revocation_outcome`, when downstream execution occurs;
- `terminal_outcome`.

### 8. Verification

The runner rereads and rehashes:

- final artifact;
- adjudication-bound corpus;
- witness attestations;
- adjudicator registry and policy;
- adjudication record;
- checkpoint report;
- witness decision;
- adjudication decision;
- downstream checkpoint final, when present.

Only then is a verified receipt returned.

## Synthetic resolved case

The fixed fixture contains:

- alpha: matching head;
- beta: matching head;
- gamma: conflicting head;
- one authorized synthetic adjudicator;
- one resolved adjudication selecting the independently verified declared head;
- gamma's exact conflicting observation preserved as fork evidence and dissent.

This is not a two-to-one result.

The observable sequence is:

```text
checkpoint continuity verified
witness decision abstains because one conflict exists
adjudication preserves the conflict and selects the verified declared head
adjudication authorizes execution
existing revocation, credential, review, quality, and analyzer lifecycle proceeds
```

## Fail-closed cases

Execution does not proceed when:

- adjudication is pending;
- adjudication is unresolved;
- adjudicator is absent when a decision is claimed;
- adjudicator is unknown;
- adjudicator identity revision drifts;
- adjudicator role is unauthorized;
- selected head differs from the declared verified checkpoint head;
- fork evidence differs from the witness decision;
- decided conflict omits dissent;
- dissent references a different attestation or head;
- policy, registry, corpus, or artifact hashes drift;
- decision time is after evaluation;
- stored evidence is missing or tampered;
- vote, majority, quorum, or consensus fields are inserted.

Structural failures do not create a verified adjudication decision. Pending and unresolved records produce verified abstention because the uncertainty itself is valid evidence.

## Failure preservation

If downstream analysis fails after adjudication authorized execution:

- checkpoint verification remains persisted;
- witness decision remains persisted;
- adjudication decision remains persisted;
- adjudication record and dissent remain persisted;
- any earlier verified content receipts remain persisted;
- no final adjudication-completion artifact is created.

If final persistence fails, all earlier verified artifacts remain available without a final receipt.

## JSON Schemas

This layer adds:

- `witness-conflict-adjudicator-registry.schema.json`;
- `witness-conflict-adjudication-policy.schema.json`;
- `witness-conflict-adjudication.schema.json`;
- `adjudication-bound-witness-corpus.schema.json`;
- `witness-conflict-adjudication-decision.schema.json`;
- `adjudicated-witness-final.schema.json`.

The new governance surfaces are closed documents. The corpus schema validates the newly added bindings while inherited corpus structure remains governed by the existing parsers and schemas.

## Validation coverage

The automated suite covers:

- resolved conflict with original witness abstention;
- downstream execution after authorized resolution;
- exact preserved dissent;
- pending abstention;
- unresolved abstention;
- prohibition on downstream artifacts after abstention;
- selected-head drift;
- unknown adjudicator rejection during publication;
- missing dissent;
- unsupported vote fields;
- schema validation;
- idempotent publication and execution;
- exact storage reconstruction;
- downstream partial failure preservation;
- final persistence failure preservation;
- complete regression coverage for all previous CTRT layers.

## Trust and privacy limits

The layer stores only synthetic stable IDs, revisions, roles, references, timestamps, rationale, and evidence. It introduces no names, addresses, government identifiers, biometrics, private credential payloads, or real identity provider.

A verified adjudication does not establish:

- real-world adjudicator identity;
- adjudicator independence, honesty, or competence;
- cryptographic authorship;
- global checkpoint uniqueness;
- complete fork disclosure;
- reliable observation channels;
- trusted external time;
- transparency-log consistency;
- correctness of the conflicting or selected head beyond the supplied checkpoint proof;
- extraction or analyzer accuracy;
- content quality;
- consensus;
- an aggregate CTRT score.

## Excluded from this slice

- adjudicator credential attestation and revocation;
- signatures and key management;
- Merkle inclusion or consistency proofs;
- witness gossip;
- live transparency networks;
- fork reconciliation;
- external identity services;
- private identity attributes;
- frontend, API, deployment, retries, parallelism, or distributed workers;
- real witnesses, adjudicators, models, extractors, or datasets.
