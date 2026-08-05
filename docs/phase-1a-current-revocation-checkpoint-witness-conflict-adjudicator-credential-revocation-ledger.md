# Phase 1A: Current revocation-checkpoint conflict-adjudicator credential revocation ledger

## Bounded question

> According to the exact accepted revocation policy and exact frozen issuer-authored event ledger, what was the effective status of the exact `1.25.0` credential at the declared evaluation time?

This layer does not reconsider the credential, the adjudication, the witness conflict, or the selected checkpoint head.

## Exact immutable predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-bound@1.25.0
sha256:b43a185d7b21879b3a234fe84233f324ae66a07a034b9ae3b7cd3577c226dca0
```

The predecessor remains the source of truth for:

- adjudicator ID and identity revision;
- issuer registry and issuer revision;
- credential type and exact role;
- credential validity interval;
- credential attestation reference;
- the complete `1.24.0` conflict adjudication;
- all witness, checkpoint, revocation, disagreement, and inherited evidence.

## New immutable artifacts

### Revocation policy

```text
policy.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation@0.1.0
sha256:e46213a13225814e673fdba2824a036dfb0030fd4f4bc11c91bfedbd52a00739
```

The accepted policy requires:

- issuer authority matching the credential attestation;
- permitted effects limited to `active`, `suspended`, and `revoked`;
- monotonic effective time;
- linear supersession;
- abstention on `suspended` and `revoked`.

### Future-effective suspension

```text
adjudicator-credential-revocation-event:event.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator.suspension.v0.1.0
sha256:0d634c690052226e9461268afedbc02d479465d9509246528e4d19b7ff780b63
```

```text
recorded_at  = 2026-08-03T19:58:43Z
effective_at = 2027-02-01T00:00:00Z
effect       = suspended
```

Recording and effectiveness are separate facts. The event is immutable and visible before it becomes effective.

### Frozen ledger

```text
ledger.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0
sha256:98a2bdddc91074042cd84b6ec79145eee4bf9da0f47119b0912f26edbb042919
```

The ledger binds:

- exact `1.25.0` credential corpus;
- exact issuer registry;
- exact revocation policy;
- exact ordered event references;
- frozen publication timestamp.

### Compact successor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.26.0
sha256:05c322ff072be8b63868d7b8aad77aa69752ce92eef5e66ab88d169156e515f8
```

The successor contains references only. It does not copy or rewrite predecessor evidence.

## Contract adapter

```text
src/ctrt/current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger.py
```

Primary type:

```text
RevocationBoundCurrentRevocationCheckpointWitnessConflictAdjudicatorCredentialCorpusSnapshot
```

Public operations:

```text
load_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_evidence
validate_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_ledger
persist_current_revocation_checkpoint_witness_conflict_adjudicator_credential_revocation_bound_corpus
```

The adapter reuses the provider-neutral adjudicator-credential revocation implementation. It adds only:

- exact `1.25.0` predecessor binding;
- compact context-specific parsing;
- publication and evaluation chronology;
- manifest-last persistence.

## Runner

```text
src/ctrt/revocation_gated_current_revocation_checkpoint_witness_conflict_runner.py
```

Primary runner:

```text
RevocationGatedCurrentRevocationCheckpointWitnessConflictExperimentRunner
```

Stages:

```text
preflight
evidence-loading
revocation-validation
decision-persistence
credential-execution
final-persistence
verification
```

The runner performs:

1. exact frozen-plan and successor preflight;
2. exact predecessor, policy, ledger, run identity, and chronology validation;
3. storage-backed loading of the complete `1.26.0` graph;
4. storage-backed loading of the preserved `1.25.0` credential graph;
5. deterministic as-of revocation evaluation;
6. revocation-decision persistence before predecessor execution;
7. terminal abstention for effective suspension or revocation;
8. exact plan narrowing from `1.26.0` to `1.25.0` only after execution authorization;
9. unchanged PR #47 invocation under the same experiment run ID;
10. outer final persistence and complete storage reread.

## Explicit plan scopes

```text
1.26.0 plan -> new revocation decision and outer finalization
1.25.0 plan -> unchanged PR #47 credential lifecycle
1.24.0 plan -> unchanged PR #46 conflict-adjudication lifecycle
1.23.0 plan -> unchanged named-witness lifecycle
1.22.0 plan -> unchanged checkpoint lifecycle
1.21.0 plan -> unchanged earlier revocation lifecycle
1.20.0 plan -> unchanged earlier credential lifecycle
1.19.0 plan -> unchanged earlier adjudication lifecycle
```

Only the corpus reference narrows. Ordered content IDs and experiment run ID remain identical.

## Outcome matrix

### Before suspension

```text
current_revocation_checkpoint_conflict_adjudicator_revocation_outcome = execute
current_revocation_checkpoint_conflict_adjudicator_credential_outcome = execute
terminal_outcome                                                     = execute
```

All PR #47 and inherited outcomes are preserved individually.

### At or after suspension

```text
current_revocation_checkpoint_conflict_adjudicator_revocation_outcome = abstain
all PR #47 outcomes                                                   = null
terminal_outcome                                                      = abstain
```

The revocation decision and immutable event history remain stored. PR #47 is not invoked.

### Revocation executes; a later delegated layer abstains

```text
new revocation outcome                        = execute
new credential outcome                        = execute
later delegated revocation outcome            = abstain
later outcomes                                = null
terminal outcome                              = abstain
```

No later abstention rewrites the new revocation decision or any earlier claim.

## Run-specific artifacts

```text
<run>:current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-decision
<run>:current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-abstention
<run>:current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-completion
<run>:current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-terminal-abstention
```

## Structural failure versus governed abstention

Structural failure means the evidence graph cannot support a valid decision. Examples:

- predecessor or content-order drift;
- credential, adjudicator, issuer, or issuer-revision substitution;
- policy, ledger, event-reference, or event-payload drift;
- broken event ordering or supersession;
- recording after ledger freeze;
- invalid publication or execution chronology;
- storage or serialization mismatch.

Governed abstention means the graph is valid but the effective status disallows execution:

- `suspended`;
- `revoked`.

## Test coverage

Contract tests prove:

- exact canonical hashes;
- closed schemas;
- exact `1.25.0` predecessor binding;
- active status before the event boundary;
- suspended abstention at the exact boundary;
- unchanged base credential state;
- content-order drift rejection;
- issuer drift rejection;
- event-recording chronology rejection;
- deterministic manifest-last reconstruction;
- unsupported-confidence rejection;
- stable public API.

Lifecycle tests prove:

1. active status delegates an exact PR #47 receipt;
2. the same run ID crosses `1.26.0 -> 1.25.0`;
3. effective suspension creates no PR #47 final;
4. this revocation decision remains independent from a later delegated abstention;
5. invalid outer chronology fails before delegation;
6. execution, revocation abstention, and delegated abstention satisfy one closed final schema.

## Trust boundary

The layer does not claim ledger completeness, external time trust, authorship, signatures, real-world identity, issuer independence, adjudicator competence, adjudication correctness, selected-head truth, consensus, confidence, reputation, deployment, analytical accuracy, or an aggregate score.

It claims only deterministic effective credential status under the exact accepted frozen evidence graph at the declared evaluation time.
