# ADR-0030: Adjudicator-checkpoint conflict resolution requires issuer-bound adjudicator credentials

- Status: Accepted
- Date: 2026-08-03
- Decision owners: CTRT maintainers
- Scope: Phase 1A adjudicator-checkpoint witness conflict governance

## Context

ADR-0029 permits a separately authorized adjudicator to allow the independently verified adjudicator-credential revocation checkpoint head to proceed when required checkpoint witnesses disagree. The original witness outcome remains `abstain`; fork evidence and dissent remain immutable; witness count never determines the result.

The adjudication registry binds a stable pseudonymous adjudicator ID, identity revision, and role. Registry membership alone does not establish that an issuer authorized that exact identity revision to exercise that role at the experiment time.

The missing question is:

> Was the exact pseudonymous adjudicator identity revision issuer-authorized for the exact conflict-adjudicator role at the declared evaluation time?

This authorization question is separate from whether the preserved conflict was resolved correctly.

## Decision

CTRT will place an issuer-bound credential gate above adjudicator-checkpoint witness conflict adjudication.

The gate will:

1. preserve a frozen credential-issuer registry;
2. preserve a frozen credential policy;
3. preserve an immutable credential attestation for each required conflict adjudicator;
4. bind the attestation to the exact adjudicator ID, identity revision, and registry role;
5. bind the exact issuer ID, immutable issuer revision, and credential type;
6. evaluate status and the half-open validity interval at an explicit experiment timestamp;
7. persist a run-specific credential decision before the ADR-0029 runner may execute;
8. produce governed abstention before witness, adjudication, checkpoint, revocation, reviewer, or analyzer work when the credential is inactive;
9. delegate the ADR-0029 runner unchanged when credentials authorize execution;
10. preserve the original witness conflict, adjudication record, rationale, selected head, fork evidence, and dissent without mutation.

The implementation reuses the existing generic adjudicator credential contracts. The governance subject differs, but credential status, issuer binding, identity-revision binding, exact-role matching, and temporal evaluation are the same class of claim.

## Exact subject binding

The synthetic attestation identifies:

```text
adjudicator.synthetic.adjudicator-checkpoint-fork
synthetic-adjudicator-checkpoint-conflict-adjudicator@0.1.0
witness_conflict_adjudicator
```

Its deterministic subject reference remains:

```text
witness-conflict-adjudicator:
<adjudicator-id>@<identity-revision>
```

The prefix describes the generic governance role family. The surrounding registry, policy, credential type, corpus predecessor, and preserved adjudication distinguish this specific checkpoint-conflict authority.

A substituted adjudicator ID, identity revision, role, subject reference, issuer revision, or credential type is structural failure rather than a weaker score.

## Credential state

The accepted credential statuses remain:

- `active`;
- `suspended`;
- `revoked`.

The credential is valid only when:

```text
valid_from <= evaluated_at < valid_until
```

An inactive issuer, not-yet-valid credential, expired credential, suspended credential, or revoked credential produces governed abstention.

Evaluation uses the declared experiment timestamp, not ambient wall-clock state.

## Separation of claims

The gate preserves separate claims:

- the checkpoint chain identifies one exact internally verified head;
- named witnesses preserve what each witness reported;
- the witness layer remains abstained when any required witness conflicts;
- ADR-0029 preserves an authorized operational resolution;
- this ADR establishes whether the resolving adjudicator was issuer-authorized for the role at the declared time;
- downstream revocation, credential, reviewer, extraction, and analyzer layers remain independent.

Credential authorization does not establish:

- real-world identity;
- issuer trustworthiness;
- cryptographic authorship;
- adjudicator honesty, independence, competence, or correctness;
- which witness was truthful;
- global checkpoint uniqueness;
- complete fork or witness disclosure;
- consensus;
- content quality;
- an aggregate CTRT score.

## Append-only corpus evolution

The immutable predecessor is:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-witness-adjudication-bound@1.4.0
```

The successor is:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-conflict-adjudicator-credential-bound@1.5.0
```

The successor preserves the complete inherited graph and adds exact references to:

- the parsed canonical `1.4.0` predecessor;
- the checkpoint-conflict adjudicator credential-issuer registry;
- the credential policy;
- the ordered credential population.

Issuer, policy, and credential artifacts are appended and reverified before the `1.5.0` manifest is written last. No predecessor artifact is modified.

## Execution ordering

`CredentialedAdjudicatorCheckpointConflictExperimentRunner` performs:

1. exact plan, corpus, content-order, registry, policy, adjudication, and timestamp preflight;
2. storage-backed loading of issuer, policy, credential, corpus, registry, and adjudication evidence;
3. credential validation at the declared time;
4. run-specific credential-decision persistence and reread verification;
5. either terminal credential abstention or delegation to the unchanged ADR-0029 runner;
6. final-manifest persistence;
7. complete storage-backed reread verification.

Credential abstention creates no new downstream witness, conflict-adjudication, checkpoint, revocation, reviewer, governed-session, or analyzer result.

## Structural failure versus governed abstention

Structural failure includes:

- plan or content-scope drift;
- predecessor-corpus drift;
- substituted registry, issuer registry, policy, adjudication, or credential references;
- identity-revision or role drift;
- unsupported credential type;
- unknown issuer or issuer-revision drift;
- malformed subject or timestamps;
- missing, altered, noncanonical, or hash-mismatched artifacts;
- extra, missing, duplicated, or reordered credential entries.

Governed abstention includes structurally valid evidence whose operational state is inactive at the declared time.

A verified abstention is a successful governance result. It preserves the evidence explaining why execution stopped; it does not delete or disprove the historical adjudication.

## Consequences

### Positive

- the authority used to resolve the second-order checkpoint fork becomes independently inspectable;
- credential permission is evaluated before adjudication can affect execution;
- inactive authority fails closed without rewriting history;
- one generic credential grammar serves multiple adjudicator contexts;
- earlier conflict, dissent, and witness abstention remain visible;
- no personal identity attributes or vote aggregation are introduced.

### Costs

- the synthetic artifact graph gains another issuer, policy, credential, corpus, decision, and final layer;
- callers provide another explicit evaluation timestamp;
- the outer runner has a wider but still mechanically delegated signature;
- synthetic issuer authority remains an internal declared assumption.

## Alternatives rejected

### Treat adjudicator-registry membership as sufficient

Rejected because registry membership and issuer-bound authorization are different claims.

### Modify the preserved adjudication artifact with credential status

Rejected because authorization changes over time while the historical adjudication must remain immutable.

### Infer authority from witness count or checkpoint agreement

Rejected because witness count is not credential evidence and cannot determine truth.

### Introduce a trust score

Rejected because identity, role, issuer, status, and time must remain separately inspectable.

### Integrate signatures or a live identity provider now

Rejected for this bounded slice. External identity, keys, network state, and live revocation require separate contracts.

## Intentionally deferred

- append-only revocation events for this new credential;
- revocation checkpoints and witnesses for the new authority;
- signatures, keys, certificate chains, and external timestamping;
- real identity proofing or issuer trust frameworks;
- adjudicator independence and conflict-of-interest evaluation;
- live transparency or fork-resolution networks;
- real adjudicators, models, datasets, APIs, frontend, or deployment.
