# Phase 1A: Current revocation-checkpoint witness conflict adjudication

## Purpose

This bounded layer adds authorized adjudication over an exact conflicting witness population derived from PR #45's immutable `1.23.0` named-witness graph.

It asks only:

> When the exact required current revocation-checkpoint witness population conflicts, what did the accepted adjudication authority select from the preserved observations?

It does not alter the canonical `1.23.0` witness graph, the `1.22.0` checkpoint, the `1.21.0` revocation ledger, credential issuance, earlier disagreement or adjudication evidence, or any inherited outcome.

## Exact predecessors

### Canonical witness predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-bound@1.23.0
sha256:73cc89c16ebb72c07ec7731ae1b25c3981681eb590005c8fe66c953facca4666
```

### Checkpoint predecessor

```text
corpus.synthetic-three-items.current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-bound@1.22.0
sha256:3ef12c528781ddec9976323b8a23670f3592839ce2145afed60cda39170c0304
```

### Independently verified head

```text
adjudicator-credential-revocation-checkpoint:checkpoint.synthetic.current-checkpoint-witness-conflict-adjudicator-credential-revocations.0000
sha256:546847de7b5557ae3a12c9e7b7d222b5bca0212168e793c09ce68363b0029d6b
```

## Preserved and new evidence

The canonical `1.23.0` population remains:

```text
alpha -> matches head
beta  -> matches head
gamma -> matches head
```

The new `1.24.0` conflicting view is:

```text
alpha -> unchanged canonical match
beta  -> unchanged canonical match
gamma -> new immutable alternate-head observation
```

The new gamma observation does not replace the canonical gamma observation. Both remain immutable artifacts with different identities and hashes.

## Fixed graph

```text
gamma conflict       = sha256:914deff79eae3b553c1ff068ac72840e19dd9bd1ebbb38b8c3f664afb666cce9
adjudicator registry = sha256:aa657368aa10e3b24c45f550ecb7a897bca900ce34fda72038076370aa196f54
adjudication policy  = sha256:1df94869e96a2ea024bb50b571a0579637d9e300a91bb20c091c5c0326dc6a6f
adjudication record  = sha256:0dd962ff196b63672cf595a8c0d160683f45518962848494490f80a3e1fc62ee
successor 1.24.0     = sha256:a98bcdc6c6c146de7d688ea708285f8d4b82bd93a8486ac5e37e76bf3acaa5fb
```

## Conflict rule

The accepted witness policy remains unchanged:

```text
match + match + conflict -> abstain
```

Two matching required witnesses do not outvote one required conflict. The conflicting witness decision is persisted independently before adjudication.

## Adjudication rule

```text
witness abstain + resolved authorized adjudication   -> adjudication execute
witness abstain + pending authorized adjudication    -> adjudication abstain
witness abstain + unresolved authorized adjudication -> adjudication abstain
```

A resolved adjudication may select only the exact checkpoint head independently verified by `1.22.0`.

Fork evidence must reconstruct the exact conflicting witness observation. Preserved dissent must continue to identify gamma's alternate head and immutable attestation reference.

## Canonical chronology

```text
2026-08-03T19:58:29Z  canonical 1.23.0 witness successor published
2026-08-03T19:58:30Z  gamma observes alternate head
2026-08-03T19:58:31Z  gamma conflict received
2026-08-03T19:58:32Z  conflict-adjudicator registry created
2026-08-03T19:58:33Z  adjudication policy created
2026-08-03T19:58:35Z  adjudication decided
2026-08-03T19:58:36Z  1.24.0 successor published
2026-08-03T19:58:37Z  conflicting population evaluated
2026-08-03T19:58:38Z  adjudication evaluated
2026-08-03T19:58:39Z  exact 1.22.0 checkpoint reverified
2026-08-03T19:58:40Z  canonical 1.23.0 population reevaluated
```

The outer lifecycle requires:

```text
1.24.0.created_at
  <= conflicting_witness_evaluated_at
  <= conflict_adjudication_evaluated_at
  <= canonical_checkpoint_verified_at
  <= canonical_witness_evaluated_at
  <= delegated_checkpoint_verified_at
  <= current_conflict_adjudicator_revocation_evaluated_at
  <= delegated revocation completion
  <= delegated checkpoint completion
  <= PR #45 completion
  <= outer completion
```

## Manifest-last publication

Publication order is:

1. immutable gamma conflict observation;
2. accepted conflict-adjudicator registry;
3. accepted adjudication policy;
4. immutable adjudication record;
5. compact `1.24.0` successor manifest;
6. exact-hash reread of the successor, exact `1.23.0` witness predecessor, exact `1.22.0` checkpoint predecessor, authorities, record, and complete conflicting population.

## Contract adapter

```text
src/ctrt/current_revocation_checkpoint_witness_conflict_adjudication.py
```

Primary types:

```text
ConflictingCurrentRevocationCheckpointWitnessCorpusSnapshot
AdjudicationBoundCurrentRevocationCheckpointWitnessCorpusSnapshot
```

Public operations:

```text
load_current_revocation_checkpoint_conflict_adjudication_evidence
validate_current_revocation_checkpoint_conflict_adjudication
persist_current_revocation_checkpoint_adjudication_bound_corpus
```

The adapter delegates witness and adjudication semantics to the provider-neutral adjudicator-checkpoint witness-conflict grammar. It adds only exact predecessor binding, compact context parsing, chronology, and manifest-last persistence.

## Adjudication-gated runner

```text
src/ctrt/adjudicated_current_revocation_checkpoint_witness_runner.py
```

`AdjudicatedCurrentRevocationCheckpointWitnessExperimentRunner` performs:

1. exact frozen-plan, predecessor, witness population, authority, policy, adjudication record, run identity, and chronology preflight;
2. storage-backed loading of the complete `1.24.0` graph;
3. validation and independent persistence of the conflicting witness decision;
4. validation and independent persistence of the adjudication decision;
5. terminal abstention for pending or unresolved adjudication;
6. exact `1.24.0 -> 1.23.0` plan narrowing only after resolved execution;
7. invocation of the unchanged PR #45 lifecycle under the same experiment run ID;
8. outer final persistence;
9. storage-backed reread of the complete graph, both new decisions, exact predecessor, and optional PR #45 final.

## Explicit scopes

```text
1.24.0 plan -> conflicting witness decision, adjudication, outer finalization
1.23.0 plan -> unchanged PR #45 named-witness lifecycle
1.22.0 plan -> unchanged PR #44 checkpoint lifecycle
1.21.0 plan -> unchanged current conflict-adjudicator revocation lifecycle
1.20.0 plan -> unchanged current conflict-adjudicator credential lifecycle
1.19.0 plan -> unchanged earlier disagreement and adjudication lifecycle
```

Only the corpus reference and identical ordered content IDs narrow between layers.

## Independent outcomes

The final record preserves separately:

```text
conflicting_current_revocation_checkpoint_witness_outcome
current_revocation_checkpoint_resolution_status
current_revocation_checkpoint_conflict_adjudication_outcome
resolved_current_revocation_checkpoint_witness_outcome
current_conflict_adjudicator_revocation_outcome
current_conflict_adjudicator_credential_outcome
conflicting_witness_outcome
current_resolution_status
current_conflict_adjudication_outcome
resolved_current_witness_outcome
current_revocation_outcome
current_credential_outcome
lower_checkpoint_witness_outcome
lower_resolution_status
lower_conflict_adjudication_outcome
lower_predecessor_witness_outcome
inherited_revocation_outcome
inherited_credential_outcome
inherited_checkpoint_witness_outcome
inherited_resolution_status
inherited_adjudication_outcome
terminal_outcome
```

No later claim rewrites an earlier evidentiary or authority result.

## Outcome matrix

### Resolved; complete execution

```text
new conflicting witness             = abstain
new resolution status               = resolved
new adjudication                     = execute
canonical 1.23.0 witness             = execute
current conflict-adjudicator revocation = execute
terminal outcome                     = execute
```

### Pending or unresolved

```text
new conflicting witness = abstain
new resolution status   = pending | unresolved
new adjudication         = abstain
all PR #45 outcomes      = null
terminal outcome         = abstain
```

### Resolved; later suspension effective

```text
new adjudication                     = execute
canonical 1.23.0 witness             = execute
current conflict-adjudicator revocation = abstain
later outcomes                       = null
terminal outcome                     = abstain
```

## Run-specific artifacts

Conflicting witness decision:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-witness-decision
```

Adjudication decision:

```text
<run>:current-checkpoint-witness-conflict-adjudicator-credential-revocation-checkpoint-witness-conflict-adjudication-decision
```

Final markers use the same prefix with:

```text
-abstention
-completion
-terminal-abstention
```

## Test coverage

Contract tests prove:

- fixed canonical hashes and closed schemas;
- exact `1.22.0` and `1.23.0` binding;
- original witness abstention preservation;
- resolved execution;
- pending and unresolved abstention;
- exact fork reconstruction and dissent preservation;
- alternate-head selection rejection;
- decision chronology rejection;
- manifest-last reconstruction;
- unsupported-confidence rejection;
- explicit public API stability.

Lifecycle tests use a real PR #45 receipt and prove:

1. resolved adjudication delegates the exact canonical `1.23.0` plan;
2. the same experiment run ID crosses `1.24.0 -> 1.23.0`;
3. pending and unresolved states create no PR #45 final;
4. resolved adjudication remains independently visible when later revocation abstains;
5. invalid outer chronology fails before delegation;
6. execution, adjudication abstention, and downstream abstention satisfy one closed final schema.

## Structural failure versus abstention

Structural failure means the evidence graph cannot be trusted as the declared graph. Examples include substituted predecessors, altered content order, wrong authorities, malformed observations, mismatched fork evidence, alternate selected-head resolution, invalid chronology, or storage drift.

Governed abstention means the graph is structurally valid but policy does not authorize continuation. Pending and unresolved adjudication are governed abstentions.

## Privacy and trust boundary

Artifacts use stable pseudonymous IDs and immutable revisions. They do not establish real-world identity, legal authority, signatures, key possession, trusted time, witness or adjudicator independence, competence, honesty, or correctness, checkpoint or ledger completeness, absence of alternate histories, public availability, consensus, confidence, reputation, analytical accuracy, deployment, or an aggregate CTRT score.

## Next bounded layer

After merge, the next layer may attest an issuer-bound credential for the exact new conflict adjudicator. It must preserve the complete `1.24.0` conflict, witness abstention, fork evidence, dissent, selected head, rationale, adjudication record, and every predecessor and inherited artifact unchanged.
