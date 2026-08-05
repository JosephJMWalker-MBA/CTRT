# ADR-0053: Current revocation-conflict adjudicator checkpoints require named witness observations

- Status: Accepted
- Date: 2026-08-04
- Phase: 1A

## Context

ADR-0052 added an immutable `1.27.0` checkpoint over the exact `1.26.0` revocation ledger for the current revocation-checkpoint witness-conflict adjudicator credential.

That checkpoint establishes a deterministic local claim: one accepted checkpoint graph covers the exact ordered event prefix and exact ledger head used by `1.26.0`.

It does not establish what any independently named observer reported seeing. Treating checkpoint publication as self-authenticating would collapse two separable claims:

1. the checkpoint artifact exists and is internally valid;
2. named observers reported the same exact checkpoint head.

Witness observations must remain immutable evidence. A conflicting required observation must not be converted into a majority vote, confidence score, or silent rewrite of the checkpoint.

## Decision

CTRT will publish a bounded `1.28.0` named-witness layer over the exact immutable `1.27.0` checkpoint graph.

The layer will:

1. preserve `1.27.0` unchanged as the witness predecessor;
2. bind one accepted witness registry;
3. bind one accepted fail-closed witness policy;
4. require the exact named alpha, beta, and gamma witnesses;
5. bind every witness to an exact identity revision and `checkpoint_observer` role;
6. preserve each observation as a separate immutable attestation;
7. bind every attestation to the exact `1.27.0` corpus, checkpoint log, expected head, and observed head;
8. require observation and receipt chronology after checkpoint publication;
9. execute only when every required observation matches the exact checkpoint head;
10. abstain when any required observation reports a conflicting head;
11. forbid vote, majority, quorum, confidence, reputation, and trust aggregation;
12. treat missing witnesses, identity drift, reference substitution, chronology drift, storage drift, and serialization drift as structural failure;
13. persist checkpoint reverification and the witness decision before any `1.27.0` execution;
14. narrow the plan from exact `1.28.0` to exact `1.27.0` only after witness execution;
15. preserve the new witness result and every PR #49 and inherited result separately.

## Exact predecessor

```text
corpus.synthetic-three-items.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.27.0
sha256:e3e288981f17b308bf5f844cd84633b2e79c67103f6c31b6f13dc89fca672e21
```

The predecessor preserves the complete `1.27.0` checkpoint graph, `1.26.0` revocation graph, `1.25.0` credential graph, `1.24.0` conflict adjudication, exact selected checkpoint heads, dissent, fork evidence, and every inherited artifact. None is modified.

## Fixed witness graph

```text
witness registry = sha256:4ed633c94ad1329890b76a7511333f64d6637fe950993d1c7d1bbd0cc0d05c3b
witness policy   = sha256:0f03b5ac7191ded32e6d945b99bacf4d108efda37390a67bc0d226ea71b95c4f
alpha attestation = sha256:1c17fdd7b97e84f8be173eef4cdb3f640bfbbaaf10a8a0a4393240f125fa24e5
beta attestation  = sha256:8a7a408c9a035f31e0adb2219d4f44e0b83d5b491ca78128f90bfb64603a86ed
gamma attestation = sha256:0f33a9982f9d403627b779f4db0ecf4669ea648fc9b29cbdf0c338d66b19b850
successor 1.28.0  = sha256:4dce56cbccb761b273f65b5a2538b65ea3b9d62d804151644ddedf0294193b2f
```

## Exact observed head

```text
checkpoint:
  adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocations.0000

checkpoint hash:
  sha256:4e8e7c6366d806ff51c7acad75050e3245e02067c1106d867cd2d8dc981c6e12

checkpoint log:
  log.synthetic-current-revocation-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
```

Each canonical attestation reports `matches_head` for that exact head.

## Outcome semantics

### Every required witness matches

```text
new witness outcome = execute
PR #49              = eligible to run unchanged
```

### Any required witness conflicts

```text
new witness outcome = abstain
all PR #49 outcomes = null
terminal outcome    = abstain
```

Two matching witnesses do not outvote one conflicting witness. The conflict remains visible and the policy abstains.

### Structural failure

Missing required witnesses, unknown witnesses, identity-revision drift, duplicate observations, corpus or log substitution, expected-head substitution, invalid observation kinds, invalid chronology, storage drift, and noncanonical serialization fail structurally. Structural failure does not create a governed abstention artifact.

## Publication and execution order

Publication is manifest-last:

1. accepted witness registry;
2. accepted witness policy;
3. immutable alpha, beta, and gamma attestations;
4. compact `1.28.0` successor;
5. exact-hash reconstruction.

Execution is:

```text
load exact 1.28.0 witness graph
  -> load and reverify exact 1.27.0 checkpoint graph
  -> persist checkpoint verification report
  -> validate every named witness observation
  -> persist witness decision
  -> witness abstention or exact 1.27.0 plan derivation
  -> unchanged PR #49 under the same experiment run ID
  -> outer finalization
  -> complete storage reread
```

## Trust boundary

This layer does not establish:

- real-world or legal identity;
- cryptographic authorship or private-key possession;
- witness independence, competence, honesty, or correctness;
- checkpoint truth;
- ledger completeness or absence of alternate histories;
- trusted external time;
- majority support, quorum, consensus, confidence, reputation, or aggregate trust;
- analytical accuracy;
- deployment;
- an aggregate CTRT score.

It establishes only what the exact named witness records reported about the exact accepted `1.27.0` checkpoint head under the exact accepted policy.

## Consequences

### Positive

- checkpoint validity and external observation remain separate claims;
- each observer remains individually inspectable;
- conflicts are preserved rather than averaged away;
- execution remains fail-closed and reconstructable;
- all downstream outcomes remain independently visible.

### Costs

- three additional immutable attestations are required;
- witness identity revisions and chronology require explicit validation;
- named records do not prove genuine independence;
- the governance chain gains another bounded layer.

## Intentionally deferred

A later bounded layer may adjudicate a genuine conflict among this exact required witness population. Such a layer must preserve the canonical `1.28.0` witness graph, every original observation, the complete `1.27.0` checkpoint graph, and every inherited artifact unchanged.
