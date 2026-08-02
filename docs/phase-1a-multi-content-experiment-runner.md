# Phase 1A Multi-content Experiment Runner

## Purpose

The multi-content runner is the first experiment-level execution boundary in CTRT.

It executes one existing governed session for every content item declared by a frozen experiment plan, stores each verified session receipt independently, and creates an experiment completion manifest only after the complete declared set re-verifies.

This implementation validates orchestration and provenance. It does not evaluate real models or produce an overall CTRT score.

## Inputs

`MultiContentExperimentRunner.run` receives:

- one frozen `ExperimentPlan`;
- the exact accepted `CandidateRegistrySnapshot` referenced by the plan;
- one `ExecutionEnvironment`;
- an ordered tuple of `ContentExecutionRequest` values;
- one explicit `experiment_run_id`.

Each content request contains:

- one canonical `ContentItem`;
- an externally recorded start timestamp;
- an externally recorded completion timestamp.

The request content IDs must equal `ExperimentPlan.content_ids` exactly and in order.

## Stable run identity

For content position `N`, the runner derives:

```text
<experiment-run-id>:<zero-padded-position>:<content-id>
```

Example:

```text
experiment-run-001:0001:content-002
```

The governed session then derives its session, run-record, bundle, and receipt IDs from that stable run ID.

A rerun should use a new experiment-run ID. Existing artifacts are never replaced.

## Lifecycle

### 1. Experiment preflight

Before any content session executes, the runner verifies:

- the experiment-run ID is nonempty;
- the plan is frozen;
- at least two content requests are present;
- request content IDs match the frozen content IDs exactly and in order;
- request content hashes are valid SHA-256 identities;
- the current runner slice has exactly one declared dimension;
- the supplied candidate registry authorizes the frozen instrument revisions.

A preflight failure produces no session artifacts.

### 2. Governed content sessions

For each request, in frozen order, the runner invokes `GovernedExecutionSession`.

Every session independently performs:

- candidate eligibility;
- runtime revision and configuration matching;
- analyzer execution;
- canonical artifact serialization;
- append-only bundle persistence;
- stored bundle re-verification.

The multi-content runner does not reproduce or bypass those checks.

### 3. Independent receipt persistence

After a session returns a `VerifiedExecutionReceipt`, the runner serializes it as:

```text
<session-id>:receipt
```

The receipt is stored and immediately re-read by ID and hash.

If a later content item fails, earlier receipt artifacts remain preserved. They represent verified partial progress, not a completed experiment.

### 4. Pre-completion re-verification

After all sessions return, the runner re-verifies:

- the frozen plan artifact stored by the session bundles;
- every session receipt artifact;
- every session bundle manifest;
- every artifact referenced by every session bundle.

The artifact store reconstructs canonical bundle-manifest contracts from stored JSON before checking every member.

### 5. Completion manifest

The runner then creates an `ExperimentCompletionManifest` containing:

- completion and experiment-run identity;
- experiment and plan identity;
- exact ordered content IDs;
- one `ExperimentSessionCompletion` per content item;
- each stored receipt reference;
- each stored bundle-manifest reference;
- each session's original result statuses;
- each session's original Workbench comparison status;
- the experiment-level integrity checks.

The manifest is appended only after all preceding checks pass.

### 6. Final verification

Before returning, the runner:

- re-reads the completion manifest by ID and hash;
- compares it with the expected canonical bytes;
- re-reads the stored plan;
- re-reads every session receipt;
- reloads and fully re-verifies every session bundle.

Only then does it return `VerifiedExperimentReceipt`.

## Completion semantics

`ExperimentRunnerStatus.VERIFIED` means:

- the exact declared content scope executed;
- every governed session returned a verified receipt;
- every receipt was stored independently;
- every session bundle passed full re-verification;
- the completion manifest was stored and re-verified.

It does not mean:

- every analyzer succeeded;
- every analyzer agreed;
- no session abstained;
- the experiment was accurate or calibrated;
- the content was good, bad, safe, unsafe, or valuable;
- an overall CTRT score exists.

## Failure stages

`MultiContentExperimentError` records one of five stages:

- `preflight`;
- `session-execution`;
- `receipt-persistence`;
- `completion-persistence`;
- `verification`.

For failures after execution begins, the error also preserves:

- the current content ID when applicable;
- the ordered content IDs whose receipts had already been persisted.

No failure returns a partial success receipt.

## Partial progress

The filesystem store is append-only and does not roll back.

A failure on content 2 may therefore leave a fully verified bundle and receipt for content 1. Those artifacts remain inspectable and hash-verifiable.

The absence of a valid experiment completion manifest is the machine-readable fact that the experiment run did not complete.

## Idempotence

Repeating the same experiment run with identical:

- experiment-run ID;
- frozen plan;
- content bytes;
- timestamps;
- runtime revisions;
- configuration;
- environment;

produces the same canonical artifact hashes. Exact repeated writes are idempotent.

Changing any canonical input while reusing an existing artifact ID produces an append-only conflict rather than silent replacement.

## Non-aggregation boundary

The completion manifest carries each session's result and comparison statuses only to preserve provenance.

It does not calculate:

- a majority result;
- an average score;
- a scalar confidence;
- an overall success status;
- a cross-content content judgment.

Later research may define experiment summaries, but those must remain separate versioned artifacts with explicit methods and information-loss disclosures.

## Current limitations

The Phase 1A runner is intentionally limited to:

- synthetic analyzers;
- one shared dimension per experiment run;
- sequential execution;
- caller-provided timestamps;
- the local append-only filesystem store;
- exact content-ID scope rather than a cryptographic corpus-membership proof.

It does not provide:

- real model downloads or execution;
- parallel workers;
- retries or resume scheduling;
- cancellation;
- signatures or attestations;
- remote durability;
- authentication or authorization;
- deletion or garbage collection;
- aggregate CTRT scoring.

## Related records

- [ADR-0012: Governed execution sessions](adr/0012-governed-execution-session.md)
- [ADR-0013: Multi-content experiment completion](adr/0013-multi-content-experiment-completion.md)
- [Governed execution session](phase-1a-governed-execution-session.md)
- [Append-only artifact store](phase-1a-append-only-artifact-store.md)
- [Experiment completion manifest schema](../schemas/experiment-completion-manifest.schema.json)
