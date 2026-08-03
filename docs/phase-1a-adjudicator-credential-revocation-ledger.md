# Phase 1A: Adjudicator credential revocation ledger

## Purpose

This phase adds an append-only status-history gate above adjudicator credential attestation.

It answers one bounded question:

> At the declared experiment timestamp, what status follows from the exact frozen event history for the exact adjudicator credential?

It does not determine whether the adjudicator, adjudication, witness, checkpoint, or analyzer result is correct.

## Artifact graph

```text
1.0.0 adjudicator-credential-bound corpus
  ├── immutable witness-conflict adjudication
  ├── preserved fork evidence and dissent
  ├── adjudicator registry
  ├── credential issuer registry
  ├── credential policy
  └── immutable adjudicator credential

adjudicator revocation policy
future-effective suspension event
frozen ordered revocation ledger
  ↓
1.1.0 adjudicator-revocation-bound corpus
```

The new policy, event, and ledger are stored before the `1.1.0` manifest is appended last.

## Fixed synthetic artifacts

### Policy

```text
docs/candidates/
  synthetic-witness-conflict-adjudicator-credential-revocation-policy.v0.1.0.json
```

Identity:

```text
policy.synthetic-witness-conflict-adjudicator-credential-revocation@0.1.0
```

The accepted policy requires:

- exact credential issuer authority;
- active, suspended, and revoked effects only;
- linear immediate supersession;
- nondecreasing effective timestamps;
- abstention on suspended or revoked status.

### Suspension event

```text
docs/corpora/extraction/revocations/witnesses/
  adjudicator-fork-suspension-event.json
```

Identity:

```text
adjudicator-credential-revocation-event:
  event.synthetic.fork.suspension.v0.1.0
```

The event binds:

```text
credential: adjudicator-credential:credential.synthetic.fork.v0.1.0
adjudicator: adjudicator.synthetic.fork
issuer: issuer.synthetic.witness-conflict-governance
issuer revision: synthetic-witness-conflict-governance@0.1.0
effect: suspended
recorded_at: 2026-08-03T13:47:30Z
effective_at: 2027-01-01T00:00:00Z
```

Because recording and effective times differ, the event is visible before it changes operational permission.

### Ledger

```text
docs/corpora/extraction/revocations/witnesses/
  adjudicator-credential-revocation-ledger.v0.1.0.json
```

Identity:

```text
ledger.synthetic-witness-conflict-adjudicator-credential-revocations@0.1.0
```

The frozen ledger binds the exact:

- `1.0.0` credential corpus;
- adjudicator credential issuer registry;
- revocation policy;
- ordered event population.

### Successor corpus

```text
docs/corpora/extraction/synthetic-corpus.v1.1.0.json
```

Identity:

```text
corpus.synthetic-three-items.adjudicator-credential-revocation-bound@1.1.0
```

The successor preserves every inherited governance field and adds:

```text
adjudicator_credential_revocation_predecessor_corpus_ref
adjudicator_credential_revocation_policy_ref
adjudicator_credential_revocation_ledger_ref
```

The exact predecessor is:

```text
corpus.synthetic-three-items.adjudicator-credential-bound@1.0.0
sha256:66d51cea8628df405ceb94e15a39effc55d3fa08b21adcaaae5ef5c539eb0dca
```

## Contract module

```text
src/ctrt/adjudicator_credential_revocation_ledger.py
```

### Policy snapshot

`AdjudicatorCredentialRevocationPolicySnapshot` binds the accepted effects, issuer rule, temporal rule, supersession rule, abstention states, lifecycle, timestamp, canonical bytes, and hash.

### Event snapshot

`AdjudicatorCredentialRevocationEventSnapshot` is immutable. Its parser rejects unsupported fields, including personal identity attributes and score fields.

### Ledger snapshot

`AdjudicatorCredentialRevocationLedgerSnapshot` preserves an ordered tuple of exact event references. Event order is evidence and cannot be reconstructed from timestamps or sorted automatically.

### Corpus wrapper

`RevocationBoundAdjudicatorCredentialCorpusSnapshot` wraps the complete credential-bound adjudication graph and adds exact revocation references without mutating inherited artifacts.

### Decision report

`AdjudicatorCredentialRevocationDecisionReport` records:

- experiment identity;
- revocation corpus, policy, and ledger references;
- immutable adjudication reference;
- per-adjudicator base and effective status;
- all applied event IDs;
- the final effective event ID;
- structured abstention reasons;
- evaluation timestamp;
- execute or abstain outcome.

It contains no scalar trust score, vote count, consensus percentage, or aggregate confidence.

## Structural validation

The validator requires:

1. a frozen experiment plan matching the exact `1.1.0` corpus and content order;
2. exact corpus, policy, ledger, issuer-registry, and credential-policy references;
3. accepted adjudicator, issuer, credential-policy, and revocation-policy lifecycle states;
4. a frozen ledger;
5. an event tuple exactly matching ledger order and hashes;
6. known credential references;
7. exact adjudicator IDs;
8. exact issuer IDs and immutable revisions;
9. event issuer equality with the original credential issuer;
10. policy-permitted effects;
11. unique event IDs;
12. a first event with no predecessor;
13. every later event naming the immediately prior event;
14. nondecreasing effective timestamps;
15. status coverage for the adjudicator named by the immutable adjudication.

A structural failure produces no verified final receipt.

## As-of evaluation

The evaluator begins with the original credential status, then applies events in ledger order when:

```text
event.effective_at <= evaluated_at
```

For the fixed ledger:

```text
2026-08-03T14:00:00Z → active → execute
2027-01-01T00:00:00Z → suspended → abstain
```

A later synthetic `active` event may reinstate permission only when it directly supersedes the suspension. The decision then lists both events in `applied_event_ids`; history is not erased.

## Runner

```text
src/ctrt/revocation_gated_adjudicated_witness_runner.py
```

`RevocationGatedAdjudicatedWitnessExperimentRunner` performs:

1. exact preflight binding;
2. storage-backed revocation and credential evidence loading;
3. as-of ledger validation;
4. run-specific revocation-decision persistence;
5. terminal revocation abstention or delegation to the unchanged adjudicator-credential runner;
6. final persistence;
7. complete storage-backed reverification.

Run-specific decision:

```text
<run>:adjudicator-credential-revocation-decision
```

Terminal artifacts:

```text
<run>:adjudicator-credential-revocation-abstention
<run>:adjudicator-credential-revocation-completion
<run>:adjudicator-credential-revocation-terminal-abstention
```

## No-downstream abstention

When the effective status is suspended or revoked, the runner does not invoke adjudicator credential evaluation or any lower governance or analyzer layer.

No new run-specific artifacts are created for:

```text
adjudicator-credential-decision
credential-revocation-checkpoint-verification
checkpoint-witness-decision
witness-conflict-adjudication-decision
reviewer-credential-revocation-decision
governed execution session
analyzer result
```

The revocation decision and final abstention marker remain stored and verified. The original credential and adjudication remain available because they predate the run.

## Separate outcomes

The final receipt preserves:

```text
adjudicator_revocation_outcome
adjudicator_credential_outcome
witness_outcome
adjudication_outcome
reviewer_revocation_outcome
terminal_outcome
```

One layer cannot overwrite another layer's evidence.

## Failure preservation

If downstream execution fails after revocation authorization:

- the revocation policy, event, ledger, and corpus remain stored;
- the run-specific revocation decision remains stored;
- completed downstream evidence remains stored;
- no revocation completion artifact is claimed.

If final persistence fails, prior evidence remains inspectable but no verified final receipt is returned.

## Schemas

```text
schemas/adjudicator-credential-revocation-policy.schema.json
schemas/adjudicator-credential-revocation-event.schema.json
schemas/adjudicator-credential-revocation-ledger.schema.json
schemas/adjudicator-credential-revocation-bound-corpus.schema.json
schemas/adjudicator-credential-revocation-decision.schema.json
schemas/adjudicator-revocation-gated-final.schema.json
```

Policy, event, and ledger documents are closed. Decision and final documents contain no trust, vote, consensus, or aggregate-score field.

## Test matrix

`tests/test_adjudicator_credential_revocation_ledger.py` covers:

- fixed fixture and schema validation;
- pre-effective execution;
- post-effective suspension abstention;
- no downstream artifacts after abstention;
- superseding reinstatement with preserved suspension history;
- broken immediate-predecessor chains;
- decreasing effective times;
- adjudicator and issuer drift;
- unknown credential references;
- ledger/event population order mismatch;
- unsupported private or score fields;
- exact storage reconstruction and idempotence;
- missing stored events;
- downstream failure preservation;
- final persistence failure.

The complete repository suite contains 288 passing tests before final public-export validation.

## Verification statement

A verified result establishes that CTRT reverified the exact supplied event graph and evaluated it at the declared time.

It does not establish legal identity, issuer trustworthiness, cryptographic authorship, trusted time, global event completeness, adjudicator correctness, checkpoint uniqueness, content quality, analyzer accuracy, consensus, or an aggregate CTRT score.

## Deferred work

The next bounded layer is immutable checkpoints over this adjudicator revocation ledger. It may detect omission, reordering, stale heads, and rollback between published ledger views without introducing signatures or a live transparency service.
