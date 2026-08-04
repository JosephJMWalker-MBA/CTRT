# Phase 1A — Named witnesses for the witness-conflict adjudicator revocation checkpoint

This bounded layer records what the exact policy-required witness population reported about the immutable `1.12.0` checkpoint head before that checkpoint may authorize the inherited lifecycle.

It asks only:

> Did every policy-required named witness report the exact independently verifiable `1.12.0` checkpoint head?

The layer does not establish that the witnesses are legally identified, independent, truthful, competent, cryptographically authenticated, or correct. It does not turn agreement into checkpoint truth.

## Fixed graph

```text
1.12.0 checkpoint-bound corpus
  → accepted ordered witness registry
  → accepted no-majority witness policy
  → three immutable named observations
  → manifest-last 1.13.0 witness-bound corpus
```

### Witness registry

```text
registry.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:58d9cbadba843fc15ef6a92b2a0b27d1e1ff69ec1fb533b59eceb3de58fcbe60
```

Required order:

1. `witness.synthetic.checkpoint-conflict-revocation-witness-conflict-alpha`
2. `witness.synthetic.checkpoint-conflict-revocation-witness-conflict-beta`
3. `witness.synthetic.checkpoint-conflict-revocation-witness-conflict-gamma`

All use identity revision:

```text
synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness@0.1.0
```

All have role `checkpoint_observer`.

### Witness policy

```text
policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witnesses@0.1.0
sha256:a3aef0506da906c030d9b2dce3cc84524ad11e62f7e3852e4640bfeae1e2f66e
```

The policy binds the exact registry and exact witness order and requires:

```text
abstain_on_conflicting_head = true
forbid_vote_aggregation = true
```

### Exact checkpoint under observation

Corpus:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.12.0
sha256:3fdaa55c2fb1ab14aaca5482093ff6415f6835483f0c2b2e3bd6a758af40a096
```

Checkpoint log:

```text
log.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoints@0.1.0
sha256:829e5900a8977de21d9d2a939fe48d2efc504541592fcfefe93f9c60c2759e47
```

Checkpoint head:

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations.0000
sha256:350d6550bbe969457fde6f556505e2b6ef270f4d1cedd296c6a835505ed37359
```

## Immutable observations

```text
alpha = sha256:af96324d4961dc44d39005765009aae841c199acec7ed37cf9e1e4124614d62f
beta  = sha256:3193313a44be680b27309a3fc81868f28db34c6dbfe34dceaa16d997c96d6245
gamma = sha256:9f49b590140340b6750d4b9ad6daa5705fb7571c7fec4bedbf9c65f949fad84f
```

Each observation binds:

- exact witness ID and identity revision;
- exact `1.12.0` checkpoint corpus;
- exact checkpoint log;
- exact expected checkpoint head;
- separately recorded observed checkpoint head;
- observation kind;
- observation time and receipt time;
- a non-authoritative note.

The canonical fixed population reports `matches_head` three times. Conflict is introduced only in tests by publishing a changed immutable observation and a changed compact manifest; the original matching observation is not edited.

## No-majority rule

```text
alpha match + beta match + gamma match    → execute
alpha match + beta match + gamma conflict → abstain
```

Two matching witnesses do not outvote one required conflict. CTRT does not derive vote count, majority, quorum, consensus, confidence, reputation, or trust score.

A conflict means only that the exact required population did not uniformly report the declared head. It does not invalidate the checkpoint and does not decide which witness is correct.

## Corpus evolution

Predecessor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.12.0
sha256:3fdaa55c2fb1ab14aaca5482093ff6415f6835483f0c2b2e3bd6a758af40a096
```

Successor:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.13.0
sha256:e03f982b4d1ee04299f165b1a699b9b643ae0aff4650f800f29d97e64557c4f3
```

The compact `1.13.0` manifest binds:

- exact immutable `1.12.0` predecessor;
- exact witness registry;
- exact witness policy;
- exact ordered observation population;
- unchanged ordered content IDs.

No predecessor artifact is modified or duplicated.

## Manifest-last publication

Publication order is:

1. accepted witness registry;
2. accepted witness policy;
3. immutable observations in exact required order;
4. compact `1.13.0` successor manifest;
5. exact-hash reread of the complete graph.

## Chronology

```text
2026-08-03T19:54:54Z  1.12.0 checkpoint corpus published
2026-08-03T19:54:55Z  witness registry created
2026-08-03T19:54:56Z  witness policy created
2026-08-03T19:54:57Z  alpha observed exact head
2026-08-03T19:54:58Z  alpha observation received
2026-08-03T19:54:59Z  beta observed exact head
2026-08-03T19:55:00Z  beta observation received
2026-08-03T19:55:01Z  gamma observed exact head
2026-08-03T19:55:02Z  gamma observation received
2026-08-03T19:55:03Z  1.13.0 successor published
2026-08-03T19:55:04Z  1.12.0 checkpoint independently reverified
2026-08-03T19:55:05Z  current witness population evaluated
2026-08-03T19:55:06Z  delegated revocation evaluated
2026-08-03T19:55:10Z  credential evaluated
2026-08-03T19:55:30Z  adjudication evaluated
2026-08-03T19:56:00Z  adjudication lifecycle completed
2026-08-03T19:56:30Z  credential lifecycle completed
2026-08-03T19:56:45Z  revocation lifecycle completed
2026-08-03T19:57:00Z  checkpoint lifecycle completed
2026-08-03T19:57:15Z  current witness lifecycle completed
```

## Contract adapter

The public contract module is:

```text
src/ctrt/witness_conflict_adjudicator_checkpoint_witness.py
```

Primary successor type:

```text
WitnessBoundCheckpointCorpusSnapshot
```

Public operations:

```text
load_witness_evidence
validate_witness_attestations
persist_witness_corpus
```

The adapter reuses the established generic checkpoint-witness registry, policy, attestation, decision-report, stored-evidence, validation, and persistence contracts. It adds only the exact `1.12.0` predecessor and `1.13.0` manifest binding.

## Witness-gated runner

The outer runner is:

```text
src/ctrt/witness_gated_witness_conflict_adjudicator_checkpoint_runner.py
```

`WitnessGatedWitnessConflictAdjudicatorCheckpointExperimentRunner` performs:

1. exact frozen-plan, successor, predecessor, content-order, registry, policy, observation population, checkpoint policy, log, head, run, and chronology preflight;
2. storage-backed loading of the complete `1.13.0` witness graph and exact `1.12.0` checkpoint graph;
3. independent sequence, ancestry, prefix, chronology, ledger-head, and event-population checkpoint verification;
4. run-specific checkpoint-verification persistence and reread verification;
5. exact current witness validation without vote aggregation;
6. run-specific witness-decision persistence and reread verification;
7. current-witness abstention or exact plan narrowing from `1.13.0` to `1.12.0`;
8. invocation of the unchanged PR #34 runner only after current witness execution;
9. outer final-manifest persistence;
10. storage-backed reread of the final, witness graph, checkpoint population, both decisions, and optional delegated PR #34 final.

## Explicit scope transition

```text
1.13.0 plan   → checkpoint reverification, current witness decision, outer finalization
1.12.0 plan   → unchanged PR #34 checkpoint lifecycle
1.11.0 plan   → unchanged PR #33 revocation lifecycle
1.10.0 plan   → unchanged credential lifecycle
1.9.0 plan    → unchanged adjudication lifecycle
1.8.0 receipt → immutable inherited witness evidence
1.7.0 scope   → lower checkpoint and downstream lifecycle
```

Only the corpus reference and matching content order are narrowed. Experiment identity, version, candidates, analyzers, execution parameters, and all inherited evidence remain unchanged.

## Run-specific artifacts

Independent checkpoint verification:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-checkpoint-verification
```

Current witness decision:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-decision
```

Current witness conflict:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-abstention
```

Successful complete lifecycle:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-completion
```

Current witness execution followed by a downstream abstention:

```text
<run>:checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-terminal-abstention
```

## Independent outcomes

```text
checkpoint reverification       → whether the exact 1.12.0 head remains structurally valid
current checkpoint witness      → what the exact 1.13.0 witness population reported
revocation outcome              → whether the event history permits credential evaluation then
credential outcome              → whether the adjudicator is issuer-authorized then
inherited checkpoint witness    → what the earlier required witness population reported
resolution status               → whether inherited witness conflict required resolution
adjudication outcome            → what the accepted inherited authority selected
terminal outcome                → whether the complete governed lifecycle executed
```

No later outcome rewrites an earlier one.

### Canonical execution

```text
current checkpoint witness   = execute
revocation outcome           = execute
credential outcome           = execute
inherited checkpoint witness = execute
resolution status            = not_required
adjudication outcome         = execute
terminal outcome             = execute
```

### Current witness conflict

```text
current checkpoint witness   = abstain
revocation outcome           = null
credential outcome           = null
inherited checkpoint witness = null
resolution status            = null
adjudication outcome         = null
terminal outcome             = abstain
```

The independent checkpoint report and current witness decision remain stored. PR #34 is not invoked.

### Later effective suspension

```text
current checkpoint witness   = execute
revocation outcome           = abstain
credential outcome           = null
inherited checkpoint witness = null
resolution status            = null
adjudication outcome         = null
terminal outcome             = abstain
```

The current witness execution remains independently visible when the later revocation layer correctly abstains.

## Test coverage

Contract and storage tests prove:

- canonical registry, policy, observation, and successor hashes;
- closed registry, policy, attestation, successor, and final schemas;
- exact `1.12.0` predecessor and content-order binding;
- exact required witness population and order;
- all-matching execution;
- one-conflict abstention despite two matches;
- identity-revision drift rejection;
- observation-before-checkpoint rejection;
- manifest-last persistence and deterministic reconstruction;
- content-order drift rejection;
- unsupported-confidence rejection.

Stored lifecycle tests use real lower PR #30–#34 evidence to prove:

1. all current witnesses matching delegates the exact PR #34 lifecycle;
2. one current conflict preserves both matching observations, persists checkpoint and witness decisions, and abstains before PR #34;
3. current witness execution remains separate when the future suspension becomes effective and PR #34 abstains;
4. current witness evaluation before checkpoint reverification fails at outer preflight;
5. execution, witness-abstention, and downstream-terminal-abstention finals satisfy the same closed schema.

## Privacy and trust boundary

Artifacts contain stable pseudonymous IDs, immutable identity revisions, exact artifact references, expected and observed heads, deterministic hashes, timestamps, observation kinds, abstention metadata, and separate outcomes.

Verification does not establish:

- legal or real-world witness, adjudicator, or issuer identity;
- cryptographic authorship, signatures, or private-key possession;
- trusted external time;
- witness independence, truthfulness, competence, or correctness;
- checkpoint truth beyond structural verification of the frozen graph;
- event completeness beyond the exact frozen ledger;
- absence of undisclosed events or alternate checkpoint chains;
- global checkpoint uniqueness or public availability;
- adjudicator competence, independence, honesty, or correctness;
- adjudication correctness;
- majority support, quorum, consensus, confidence, reputation, or trust score;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred layers

Conflict adjudication for the exact current `1.13.0` observations, credentials and revocation history for that future authority, signatures, keys, trusted timestamp authorities, public transparency services, real witnesses, APIs, frontend, and deployment remain separate future layers.
