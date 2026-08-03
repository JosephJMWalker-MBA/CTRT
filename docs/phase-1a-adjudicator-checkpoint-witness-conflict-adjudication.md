# Phase 1A: Adjudicator checkpoint witness conflict adjudication

This layer governs what happens after the named witnesses to an adjudicator credential revocation checkpoint disagree.

It preserves three questions as separate claims:

```text
Checkpoint verification:
Is this exact ordered ledger state the valid head of this exact checkpoint chain?

Witness evaluation:
Did every policy-required named witness report that exact verified head?

Conflict adjudication:
Has an authorized adjudicator explicitly permitted the independently verified head to proceed despite preserved conflicting evidence?
```

A later revocation layer still independently answers what credential status follows from the event history at the declared evaluation time.

## Fixed synthetic graph

The fixed graph adds:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound@1.3.0
    ↓
checkpoint-witness-attestation:
attestation.synthetic.adjudicator-gamma.conflict.v0.1.0
    ↓
registry.synthetic-adjudicator-checkpoint-witness-conflict-adjudicators@0.1.0
    ↓
policy.synthetic-adjudicator-checkpoint-witness-conflict-adjudication@0.1.0
    ↓
witness-conflict-adjudication:
adjudication.synthetic.adjudicator-checkpoint-gamma-conflict.v0.1.0
    ↓
corpus.synthetic-three-items.adjudicator-checkpoint-witness-adjudication-bound@1.4.0
```

The successor binds the parsed canonical predecessor document:

```text
corpus.synthetic-three-items.adjudicator-checkpoint-witness-bound@1.3.0
sha256:640fbcb6d5fac9fe5e686c5dcc625263beff1c5dd9a9ad585f6240b04f00e650
```

The conflict attestation reports an alternate synthetic head while preserving the independently verified expected head.

## Original witness outcome remains immutable

The three named observations are:

```text
alpha → matches_head
beta  → matches_head
gamma → conflicting_head
```

The witness layer therefore records:

```text
adjudicator_checkpoint_witness_outcome = abstain
```

That result does not change after adjudication. The outer receipt preserves the original witness final and decision exactly.

A separate adjudication outcome may be:

```text
conflict_adjudication_outcome = execute
```

This does not mean the witnesses later agreed. It means a separately authorized governance record permitted the independently checkpoint-verified head to proceed while preserving the conflict.

## Resolution states

### `not_required`

Every required witness matched. No conflict authority is needed.

### `pending`

Conflict evidence exists but no authorized decision has been made. The experiment abstains before downstream execution.

### `resolved`

An authorized adjudicator selects the checkpoint head already established by the checkpoint chain, gives a rationale, and preserves every conflicting observation as dissent. The unchanged checkpoint runner may then execute.

### `unresolved`

An authorized adjudicator concludes that the evidence does not support operational resolution. The experiment abstains before downstream execution, and dissent remains preserved.

## No-majority boundary

The adjudication does not count matching and conflicting witnesses. It does not compute a quorum, consensus percentage, confidence score, reputation score, or winning side.

The facts remain:

```text
2 matching observations
1 conflicting observation
original witness outcome = abstain
```

The resolved outcome comes from a distinct declared authority and rationale, not from the numerical relationship between those observations.

## Selected-head restriction

A resolved adjudication may select only:

```text
adjudicator-credential-revocation-checkpoint:
checkpoint.synthetic.witness-conflict-adjudicator-revocations.0000
sha256:4034f2202a16a95902b535e38330d71358e5485ded645c4c649cccb1967c5e45
```

That head was already established by the frozen checkpoint chain.

The adjudicator may not:

- select gamma's alternate head;
- invent a third head;
- merge incompatible heads;
- replace the checkpoint chain;
- erase the conflict;
- infer truth from witness count.

## Preserved fork and dissent

The immutable adjudication record contains both:

```text
fork_evidence
preserved_dissent
```

`fork_evidence` reproduces the exact witness, attestation reference, expected head, and observed head from the original witness decision.

`preserved_dissent` keeps gamma's observation and note visible after operational resolution. Resolution changes what may proceed; it does not rewrite what was observed.

## Publication lifecycle

`persist_adjudication_bound_adjudicator_checkpoint_witness_corpus`:

1. re-reads and verifies the exact `1.3.0` predecessor corpus;
2. validates the complete conflicting witness population;
3. validates the exact adjudicator registry and accepted policy;
4. verifies that the adjudication record reproduces the original fork;
5. verifies adjudicator identity revision and role when decided;
6. verifies selected-head restrictions and preserved dissent;
7. appends witness and adjudication dependencies in order;
8. appends the `1.4.0` successor corpus manifest last;
9. reloads the complete graph by hash.

The predecessor witness decision, checkpoint chain, revocation ledger, credential, prior adjudication, extraction evidence, and analyzer contracts are not modified.

## Execution lifecycle

`AdjudicatedAdjudicatorCheckpointWitnessExperimentRunner` performs:

1. exact plan, corpus, authority, content-order, and timestamp preflight;
2. storage-backed loading of witness, checkpoint, and adjudication evidence;
3. execution of the existing witness gate, preserving its original receipt;
4. independent adjudication validation;
5. run-specific adjudication decision persistence;
6. either terminal conflict-adjudication abstention or delegation to the unchanged checkpoint runner;
7. final outer manifest persistence;
8. complete storage-backed reread and verification.

Run-specific decision artifact:

```text
<run>:adjudicator-checkpoint-witness-conflict-adjudication-decision
```

Terminal artifacts:

```text
<run>:adjudicator-checkpoint-witness-conflict-adjudication-abstention
<run>:adjudicator-checkpoint-witness-conflict-adjudication-completion
<run>:adjudicator-checkpoint-witness-conflict-adjudication-terminal-abstention
```

## Outcome separation

The verified receipt preserves:

```text
adjudicator_checkpoint_witness_outcome
conflict_adjudication_outcome
adjudicator_revocation_outcome
adjudicator_credential_outcome
reviewer_checkpoint_witness_outcome
reviewer_witness_adjudication_outcome
reviewer_revocation_outcome
terminal_outcome
```

A resolved adjudication may later be followed by a revocation abstention. That does not undo the adjudication result. Likewise, adjudication cannot convert an independently inactive credential into execution.

## Structural failures

No verified terminal receipt is produced for:

- missing or tampered predecessor, registry, policy, attestation, adjudication, or corpus artifacts;
- stale canonical hashes;
- incorrect predecessor or successor references;
- an adjudication not exactly bound by the corpus manifest;
- missing, duplicate, reordered, or substituted conflict evidence;
- unknown adjudicators;
- identity-revision or role substitution;
- selected-head drift;
- missing preserved dissent;
- a decision after the declared evaluation time;
- final persistence or reread failure.

The fixed fixture development caught one such error: an early temporary probe hashed the JSON text as a string rather than hashing the parsed canonical document. The predecessor comparison rejected the stale reference before the graph could be accepted. The corrected fixture binds the parsed canonical document hash shown above.

## Privacy and constitutional boundary

The layer stores pseudonymous adjudicator and witness IDs, immutable revisions, roles, exact artifact references, resolution status, rationale, timestamps, fork evidence, and dissent.

It stores no real names, contact details, private identity attributes, vote counts, consensus percentages, confidence scores, reputation scores, rankings, or aggregate CTRT score.

`verified` means the supplied immutable graph satisfies its declared governance rules. It does not establish global checkpoint uniqueness, real identity, independence, honesty, competence, signature validity, trusted time, publication completeness, adjudication correctness, extraction accuracy, or content quality.

## Intentionally excluded

- adjudicator credential attestations for this new authority;
- adjudicator credential revocation and checkpoints;
- signatures, keys, and certificate chains;
- live fork-resolution or transparency services;
- real identity or independence verification;
- witness or adjudicator reputation scoring;
- quorum, majority voting, or consensus percentages;
- automatic determination of which witness was truthful;
- real witnesses, adjudicators, models, datasets, APIs, frontend, or deployment.

Credential attestation for the new conflict adjudicator is the next bounded governance layer, not part of this one.
