# ADR-0057: Close the current governance branch with one immutable checkpoint

- **Status:** Accepted
- **Date:** 2026-08-03
- **Decision scope:** Exact `1.31.0` current conflict-adjudicator credential-revocation head

## Context

The Phase 1A governance harness has demonstrated immutable predecessors,
manifest-last publication, named witness observations, conflict adjudication,
issuer-bound credentials, append-only revocation history, and immutable
checkpoint verification across a complete real-chain lifecycle.

Those mechanisms can be recursively wrapped forever. Additional wrappers are
not evidence of additional safety unless they represent a concrete failure mode
that the existing graph cannot express. Continuing merely because another
wrapper is possible would convert governance into unbounded recursion and delay
the research paper and the return to CTRT's content-evaluation mission.

The exact predecessor closed by this decision is:

```text
corpus.synthetic-three-items.current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocation-bound@1.31.0
sha256:74b4ffaa1b3d4be26331f1543928526633c3adc3f820c47eed09a7bb9af7c0c1
```

Its exact frozen revocation-ledger head is:

```text
ledger.synthetic-current-revocation-conflict-adjudicator-checkpoint-witness-conflict-adjudicator-credential-revocations@0.1.0
sha256:c5b57e6345dd16f4b37d98ab858a114dca0d43ee405843db84580a35b3396665
```

## Decision

Publish one immutable genesis checkpoint over the complete ordered event
population already frozen into `1.31.0`, freeze a one-checkpoint log, and publish
the compact `1.32.0` successor manifest last.

The accepted closure policy additionally declares:

```text
branch_state = closed
automatic_successor_layers_allowed = false
reopen_requires_documented_failure = true
permitted_reopen_trigger = concrete-unrepresented-failure
```

The closure policy protects the exact `1.31.0` predecessor by ID, version, and
canonical hash. It cannot be reused to close a substituted corpus.

The closure checkpoint does not modify the event, ledger, credential,
adjudication, witness observations, selected heads, fork evidence, dissent, or
any inherited result.

## Fixed graph

```text
closure policy        = sha256:9fe6e27c52e86225f99403eb455cd3dbe631974cf0e0aecd402a21125889274c
event population      = sha256:72fe6000b56ef23f788f84745b8a873da0a85be038e0baf3cd35e683f8533391
genesis checkpoint    = sha256:0af1e06a2171d441783c1f34fdbaad43ca294276a80b4851792bc21a5d4c0443
frozen checkpoint log = sha256:0ba849b730ae32155d7c726ea5999af1208587fe16d336b769c6eeba7ac8b784
successor 1.32.0      = sha256:5a33f77334c305a2dfa2dc43711decf08afd68cdb87504d29e897c25f9c512d0
```

## Publication order

1. exact immutable `1.31.0` predecessor;
2. accepted closure checkpoint policy;
3. immutable checkpoint population in exact sequence order;
4. frozen checkpoint log;
5. compact `1.32.0` successor manifest last;
6. exact-hash reread of every stored artifact.

## Execution order

1. load the exact `1.32.0` closure graph;
2. verify the closure policy protects the exact `1.31.0` predecessor;
3. verify the exact ledger and complete ordered event prefix;
4. persist the run-specific checkpoint verification report;
5. derive the exact `1.31.0` plan under the same experiment run ID;
6. execute PR #53 unchanged;
7. preserve all 29 PR #53 and inherited outcome fields separately;
8. persist the closure final;
9. reread the complete stored graph.

## Structural failure

The boundary fails closed for predecessor, policy, log, checkpoint, ledger,
event population, event order, sequence, ancestry, chronology, storage, hash,
serialization, run identity, or closed-schema drift.

Structural checkpoint failure creates no governed abstention artifact because
the system cannot establish which evidence head it evaluated.

A structurally verified closure checkpoint remains verified when PR #53 later
produces a governed abstention.

## Trust boundary

The closure checkpoint does not establish real-world identity, cryptographic
authorship, trusted external time, ledger completeness beyond the exact stored
population, absence of alternate histories, witness or adjudicator
independence, correctness, consensus, confidence, reputation, aggregate trust,
analytical accuracy, deployment readiness, or a CTRT score.

It establishes only that the exact accepted closure graph covers the exact
ordered `1.31.0` event population and ledger head used by governed execution.

## Reopening rule

This governance branch is closed after `1.32.0`.

A later governance layer requires all of the following:

1. a concrete observed or reproducible failure;
2. evidence that the failure cannot be represented by the current graph;
3. a bounded claim describing the missing invariant;
4. preservation of the complete `1.32.0` closure graph; and
5. explicit human authorization to reopen the branch.

Novelty, symmetry, hypothetical completeness, or the mere possibility of
another wrapper are not valid reopening triggers.

## Consequences

After this checkpoint is merged and its invariants are proven, work proceeds to
the governance proof and paper. CTRT then returns toward recognizable
content-evaluation logic. Further recursive governance is not automatic.
