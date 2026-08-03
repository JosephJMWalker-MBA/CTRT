# Phase 1A — Checkpoint Witness Attestation

## Purpose

This slice adds immutable named-witness observations to the credential-revocation checkpoint chain.

It answers one bounded question:

> Which exact checkpoint head does each required witness claim to have observed?

It does not answer whether the witnesses are trustworthy, independent, correctly identified, or globally representative.

## Constitutional boundary

CTRT does not infer truth from witness count.

The implementation preserves every required witness observation separately. A single structurally valid conflicting-head observation triggers a governed abstention even when multiple other witnesses match the declared head.

No majority vote, quorum score, consensus percentage, or aggregate witness confidence is produced.

## Artifact progression

The append-only synthetic corpus progression is now:

```text
0.4.0  review-bound extraction corpus
0.5.0  reviewer-credential-bound corpus
0.6.0  credential-revocation-bound corpus
0.7.0  revocation-checkpoint-bound corpus
0.8.0  checkpoint-witness-bound corpus
```

Each layer has a distinct artifact identity and retains an exact predecessor reference.

The `0.8.0` corpus adds:

- `witness_predecessor_corpus_ref`;
- `checkpoint_witness_registry_ref`;
- `checkpoint_witness_policy_ref`;
- ordered `checkpoint_witness_attestation_refs`.

The registry, policy, and witness attestations are persisted first. The witness-bound corpus is published last.

## Synthetic witness registry

The accepted fixture registry contains three synthetic identities:

```text
witness.synthetic.alpha
witness.synthetic.beta
witness.synthetic.gamma
```

Each identity binds:

- `identity_revision: synthetic-checkpoint-witness@0.1.0`;
- `role: checkpoint_observer`.

These are governance identities, not verified real-world identities.

The registry contains no name, address, government identifier, biometric, network location, or private credential payload.

## Witness policy

The accepted synthetic policy requires the exact registry population in exact order.

It fixes two rules:

```json
{
  "abstain_on_conflicting_head": true,
  "forbid_vote_aggregation": true
}
```

Every required witness must have one immutable attestation. Missing, duplicated, reordered, unknown, or revision-drifted witnesses fail structurally.

## Witness attestation

Each attestation contains:

- deterministic artifact and attestation IDs;
- witness ID and identity revision;
- exact `0.7.0` checkpoint-corpus reference;
- exact checkpoint-log reference;
- declared expected-head reference;
- witness-observed-head reference;
- derived observation kind;
- observation timestamp;
- receipt timestamp;
- explanatory note.

### Derived observation kind

The observation kind is not accepted as an independent assertion.

```text
observed_head_ref == expected_head_ref  -> matches_head
observed_head_ref != expected_head_ref  -> conflicting_head
```

A payload that labels equal references as conflicting, or unequal references as matching, is rejected.

### Time rules

The observation may not predate checkpoint publication.

The attestation receipt may not predate observation.

The attestation receipt must be no later than the witness evaluation timestamp used for the experiment run.

These checks establish internal chronology only. They do not establish trusted external time.

## Validation sequence

`validate_checkpoint_witness_attestations` performs these checks:

1. experiment plan is frozen;
2. plan matches the witness-bound corpus exactly;
3. corpus binds the exact witness registry and policy;
4. registry and policy are accepted;
5. policy binds the exact registry;
6. policy requires the complete registry population in exact order;
7. attestation references equal the corpus population exactly;
8. one attestation exists per required witness;
9. supplied head checkpoint equals the checkpoint-bound corpus head;
10. witness IDs are unique and ordered;
11. identity revisions and roles match the registry;
12. checkpoint corpus, log, and expected-head references match exactly;
13. observation and receipt chronology is valid;
14. conflicting-head abstention is derived per witness;
15. the final execute-or-abstain outcome is derived from individual observations.

Structural validation failures do not produce a verified witness decision.

## Decision report

The run-specific decision preserves one summary per named witness:

- witness ID;
- exact attestation reference;
- observation kind;
- expected head;
- observed head;
- structured abstention reasons.

The report does not contain:

- vote count;
- matching-witness count;
- majority flag;
- quorum threshold;
- consensus percentage;
- scalar trust score;
- aggregate CTRT score.

The detailed report is stored at:

```text
<experiment-run-id>:checkpoint-witness-decision
```

A deterministic plan-level index is also written for discovery.

## Witness-gated execution

`WitnessGatedCheckpointExperimentRunner` wraps the existing checkpoint-gated runner rather than rewriting it.

### Stages

```text
preflight
  -> evidence-loading
  -> checkpoint-validation
  -> checkpoint-report-persistence
  -> witness-validation
  -> witness-decision-persistence
  -> checkpoint-execution or witness abstention
  -> final-persistence
  -> verification
```

The checkpoint chain is reverified before witness observations are evaluated. This means a witness decision is never used to excuse a malformed checkpoint chain.

### All witnesses match

When every required witness reports the declared checkpoint head:

1. the checkpoint verification report is persisted;
2. the witness decision is persisted with `outcome: execute`;
3. the existing checkpoint-gated runner executes unchanged;
4. revocation, credential, review, quality, and analyzer outcomes remain independent;
5. the final witness artifact links the downstream checkpoint result.

Successful downstream execution produces:

```text
<experiment-run-id>:checkpoint-witness-completion
```

### Conflicting witness

When any required witness reports another head:

1. the checkpoint verification report remains persisted;
2. every witness observation remains persisted;
3. the witness decision records `outcome: abstain`;
4. no checkpoint-gated execution is invoked;
5. no revocation decision is created;
6. no reviewer-credential decision is created;
7. no review-adjudication decision is created;
8. no extraction-quality decision is created;
9. no analyzer session or experiment completion is created;
10. the final witness abstention artifact is persisted and reverified.

The final artifact is:

```text
<experiment-run-id>:checkpoint-witness-abstention
```

Two matching witnesses do not outvote one conflict.

### Downstream abstention

All witnesses may match while a later boundary abstains, such as an effective credential suspension.

That produces:

```text
<experiment-run-id>:checkpoint-witness-terminal-abstention
```

The final artifact preserves separately:

- `witness_outcome`;
- `revocation_outcome`;
- `terminal_outcome`.

## Failure preservation

The store remains append-only across failure boundaries.

### Witness provenance failure

Malformed or missing witness evidence prevents a witness decision. Earlier checkpoint and corpus artifacts remain, but no run-specific witness decision or final witness artifact is created.

### Downstream analyzer failure

When witnesses authorize execution but a later analyzer fails:

- the run-specific checkpoint report remains;
- the witness decision remains;
- any earlier verified content receipts remain;
- no witness-gated final completion is created.

### Final persistence failure

If the final witness artifact cannot be appended:

- checkpoint report remains;
- witness decision remains;
- completed downstream artifacts remain;
- no verified witness receipt is returned;
- no claim of witness-layer completion is made.

## Storage reconstruction

`load_checkpoint_witness_evidence` rereads and verifies:

- the witness-bound corpus;
- witness registry;
- witness policy;
- every ordered witness attestation.

It checks exact IDs, hashes, canonical payloads, order, and population size.

A valid reference alone is insufficient if the stored payload differs from the expected canonical document.

## Schemas

This slice adds six JSON Schemas:

```text
checkpoint-witness-registry.schema.json
checkpoint-witness-policy.schema.json
checkpoint-witness-attestation.schema.json
witness-bound-checkpoint-corpus.schema.json
checkpoint-witness-decision.schema.json
witness-gated-checkpoint-final.schema.json
```

The schemas close the new registry, policy, attestation, decision, and final-artifact surfaces. The corpus schema governs the new witness bindings while inherited corpus structure continues to be validated by existing parsers and schemas.

## Test coverage

The executable suite covers:

- three matching witnesses and downstream execution;
- one conflict among two matching witnesses;
- proof that conflict cannot be outvoted;
- schema validation;
- absence of vote and aggregate fields;
- idempotent ingestion and execution;
- exact storage reconstruction;
- identity-revision drift;
- checkpoint-log substitution;
- expected-head substitution;
- observation before checkpoint publication;
- receipt after evaluation;
- duplicate witness identity;
- observation-kind inconsistency;
- forbidden vote fields;
- missing stored attestation;
- missing stored checkpoint;
- downstream partial failure;
- final persistence failure;
- full regression coverage for every previous CTRT layer.

## Trust and non-claims

A verified witness artifact means the supplied named observations and their exact relationships were checked and rechecked from append-only storage.

It does not establish:

- real-world witness identity;
- witness independence;
- witness honesty;
- cryptographic authorship;
- that a witness observed the checkpoint over a trustworthy channel;
- that every witness or checkpoint is represented;
- that no unreported fork exists;
- global checkpoint consistency;
- transparency-log inclusion;
- trusted timestamp authority;
- extraction or analyzer accuracy;
- content quality;
- a scalar confidence or aggregate CTRT verdict.

## Deferred work

This slice intentionally does not implement:

- conflicting-witness adjudication;
- witness credentials or revocation;
- digital signatures;
- key management;
- live witness gossip;
- transparency-log inclusion and consistency proofs;
- fork reconciliation;
- network publication or monitoring;
- external identity providers;
- private identity data;
- real witnesses, models, extractors, or datasets;
- frontend, API, deployment, retries, parallelism, or distributed workers.
