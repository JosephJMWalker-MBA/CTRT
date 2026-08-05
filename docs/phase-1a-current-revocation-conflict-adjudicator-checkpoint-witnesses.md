# Phase 1A: Current revocation-conflict adjudicator checkpoint witnesses

## Bounded question

> What did the exact required named witness population report about the exact immutable `1.27.0` checkpoint head?

This layer does not decide whether the checkpoint is true, globally complete, or independently trustworthy. It preserves exact named observations and applies one accepted fail-closed policy.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.27.0
sha256:e3e288981f17b308bf5f844cd84633b2e79c67103f6c31b6f13dc89fca672e21
```

The predecessor remains immutable and carries the exact `1.26.0` revocation graph, the exact `1.25.0` credential graph, the complete `1.24.0` adjudication graph, all earlier checkpoint and witness evidence, and every inherited artifact.

## Fixed graph

| Artifact | Exact hash |
| --- | --- |
| Witness registry | `sha256:4ed633c94ad1329890b76a7511333f64d6637fe950993d1c7d1bbd0cc0d05c3b` |
| Witness policy | `sha256:0f03b5ac7191ded32e6d945b99bacf4d108efda37390a67bc0d226ea71b95c4f` |
| Alpha attestation | `sha256:1c17fdd7b97e84f8be173eef4cdb3f640bfbbaaf10a8a0a4393240f125fa24e5` |
| Beta attestation | `sha256:8a7a408c9a035f31e0adb2219d4f44e0b83d5b491ca78128f90bfb64603a86ed` |
| Gamma attestation | `sha256:0f33a9982f9d403627b779f4db0ecf4669ea648fc9b29cbdf0c338d66b19b850` |
| Successor `1.28.0` | `sha256:4dce56cbccb761b273f65b5a2538b65ea3b9d62d804151644ddedf0294193b2f` |

## Required named witnesses

The accepted registry requires exactly:

```text
witness.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-alpha
witness.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-beta
witness.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-gamma
```

Each registry member binds:

```text
identity revision:
  synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness@0.1.0

role:
  checkpoint_observer
```

The registry names records. It does not prove real-world identity, independence, competence, honesty, or private-key possession.

## Exact observed head

Every canonical attestation binds the exact same checkpoint graph:

```text
checkpoint corpus:
  corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.27.0

checkpoint log:
  log.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0

checkpoint head:
  adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocations.0000

checkpoint head hash:
  sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12
```

Alpha, beta, and gamma each report `matches_head` in the canonical graph.

## Publication order

Publication is manifest-last:

1. accepted witness registry;
2. accepted witness policy;
3. alpha attestation;
4. beta attestation;
5. gamma attestation;
6. compact frozen `1.28.0` successor;
7. exact-hash reread and deterministic reconstruction.

The successor contains references only. It does not inline, summarize, or rewrite an observation.

## Evaluation rules

### All required observations match

```text
new witness outcome = execute
exact 1.27.0 plan    = eligible for delegation
```

### One or more required observations conflict

```text
new witness outcome = abstain
all PR #49 outcomes = null
terminal outcome    = abstain
```

A matching majority does not override a conflict. The policy explicitly forbids vote aggregation.

### Structural failure

The boundary fails structurally for:

- missing or extra required witnesses;
- duplicate attestations;
- unknown witness IDs;
- witness identity-revision drift;
- registry, policy, corpus, log, or head substitution;
- expected-head or observed-head reference drift;
- invalid observation kind;
- observation before checkpoint publication;
- receipt before observation;
- evaluation before required evidence exists;
- run-identity mismatch;
- storage or serialization drift.

Structural failure creates no governed abstention artifact.

## Execution sequence

```text
load exact 1.28.0 witness graph
  -> load exact 1.27.0 checkpoint graph
  -> reverify exact checkpoint head and event prefix
  -> persist checkpoint verification report
  -> validate each required named observation
  -> persist witness decision
  -> witness abstention or exact 1.27.0 plan derivation
  -> execute unchanged PR #49 under the same run ID
  -> preserve the new witness result and all 23 delegated outcomes separately
  -> outer finalization
  -> complete storage reread
```

## Plan scopes

```text
1.28.0 plan -> witness evidence, checkpoint reverification, decision, finalization
1.27.0 plan -> unchanged PR #49 checkpoint lifecycle
1.26.0 plan -> unchanged PR #48 revocation lifecycle
1.25.0 plan -> unchanged PR #47 credential lifecycle
1.24.0 plan -> unchanged PR #46 conflict-adjudication lifecycle
```

Only the corpus reference narrows. The experiment run ID and ordered content IDs remain unchanged.

## Final-record preservation

The final record stores one new field:

```text
current_revocation_conflict_adjudicator_checkpoint_witness_outcome
```

It also preserves all 23 PR #49 and inherited outcomes individually. No scalar confidence, overall governance score, vote total, or compressed success value is introduced.

## Reconstruction

A verifier reconstructs the layer by:

1. reading the exact `1.28.0` manifest;
2. loading the exact registry and policy by hash;
3. loading all attestation references in declared order;
4. rereading the exact `1.27.0` predecessor;
5. checking each witness identity revision and head reference;
6. recomputing the witness decision;
7. verifying stored checkpoint and witness reports;
8. verifying the optional exact PR #49 final when delegation occurred;
9. verifying the outer final manifest last.

## Explicit exclusions

This layer does not establish:

- checkpoint truth;
- global ledger completeness;
- absence of alternate histories;
- trusted external time;
- legal identity or cryptographic authorship;
- witness independence, competence, honesty, or correctness;
- majority support, quorum, consensus, confidence, reputation, or aggregate trust;
- analytical accuracy;
- deployment;
- an aggregate CTRT score.

## Test coverage

The bounded test suite locks:

- exact immutable hashes and closed schemas;
- exact `1.28.0 -> 1.27.0` predecessor binding;
- all three canonical matching observations;
- one required conflict producing abstention without majority voting;
- identity-revision drift as structural failure;
- invalid observation chronology as structural failure;
- deterministic manifest-last reconstruction;
- exact PR #49 delegation under the same run ID;
- no PR #49 final after witness abstention;
- preservation of a later delegated abstention;
- public API exactness;
- rejection of unsupported confidence fields.
