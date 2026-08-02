# ADR-0013: Multi-content experiment completion preserves receipts without aggregation

- Status: Accepted
- Date: 2026-08-02
- Decision owners: CTRT maintainers
- Scope: Phase 1A Content Analysis Workbench

## Context

ADR-0012 established a fail-closed governed execution session for one content item. A session returns a verified receipt only after its canonical artifact bundle has been stored and re-verified.

A frozen experiment plan may authorize more than one content item. CTRT therefore needs an experiment-level execution boundary that can:

- prove that the exact declared content set was attempted;
- preserve each completed session independently;
- stop without claiming experiment completion if any later session fails;
- verify every stored session and bundle before declaring completion;
- avoid converting multiple session outcomes into an undeclared aggregate score or verdict.

The artifact store is append-only and intentionally non-transactional. A multi-content runner must therefore distinguish valid partial progress from complete experiment execution.

## Decision

CTRT will use a dependency-free `MultiContentExperimentRunner` for the first experiment-level execution slice.

### 1. Exact ordered content scope

Before any session begins, the runner requires execution requests to match `ExperimentPlan.content_ids` exactly and in the frozen order.

Missing, additional, duplicated, or reordered content items fail preflight. This prevents runtime input selection from silently changing the experiment population.

### 2. Stable experiment-run identity

Each experiment attempt receives an explicit `experiment_run_id`.

Per-content run IDs are derived deterministically from:

- the experiment-run ID;
- the zero-based frozen content position;
- the content ID.

A later rerun uses a new experiment-run ID rather than replacing prior artifacts.

### 3. One governed session per content item

Every content item is executed through the existing `GovernedExecutionSession`.

The multi-content runner does not bypass or weaken session preflight, runtime revision checks, canonical serialization, persistence, or bundle re-verification.

### 4. Independent receipt persistence

After each governed session returns, its `VerifiedExecutionReceipt` is canonically serialized and stored as an independent append-only artifact.

If a later content session fails, earlier verified session receipts remain valid and inspectable. They do not, by themselves, establish experiment completion.

### 5. Complete bundle re-verification

Before writing an experiment completion manifest, the runner:

- re-reads every stored session receipt by ID and hash;
- reconstructs every stored session bundle manifest;
- re-verifies every artifact referenced by every bundle;
- verifies the stored frozen plan hash.

A missing, changed, unreadable, or corrupt artifact prevents experiment completion.

### 6. Completion manifest written last

Only after every declared session and receipt has verified does the runner append an `ExperimentCompletionManifest`.

The completion manifest records:

- experiment and experiment-run identity;
- exact frozen plan reference;
- ordered content IDs;
- one ordered session completion record per content item;
- receipt and bundle-manifest references;
- preserved analyzer-result and Workbench comparison statuses;
- the required experiment verification checks.

The runner then re-reads and verifies the completion manifest and all referenced session evidence before returning a `VerifiedExperimentReceipt`.

### 7. No aggregate analytical outcome

The experiment completion manifest does not contain:

- an overall CTRT score;
- an experiment-wide confidence percentage;
- a synthesized success or failure judgment about content;
- an average of analyzer outputs;
- an aggregate Workbench status.

Session analyzer and comparison outcomes remain separate and ordered. `verified` describes execution completeness and artifact integrity only.

### 8. Partial progress is not completion

A failure after one or more sessions may leave valid append-only session bundles and receipt artifacts.

This is intentional. No rollback or deletion occurs. Without a successfully re-verified experiment completion manifest, the experiment run is incomplete.

## Consequences

### Positive

- The frozen experiment population is enforced before execution.
- Every completed content session remains independently auditable.
- Later failure does not erase valid prior evidence.
- Experiment completion has a precise, machine-readable boundary.
- The system remains compatible with the append-only filesystem store.
- Measurement outcomes are not collapsed into an undeclared aggregate.

### Costs

- The first runner is sequential.
- Every session bundle is re-read more than once.
- Partial failed runs may leave unreferenced or incomplete artifact groups.
- Callers must supply recorded execution windows for every content request.
- A separate experiment-run identity is required for each rerun.

## Intentionally deferred

This decision does not add:

- parallel or distributed execution;
- retries or resume scheduling;
- multiple dimensions in one experiment run;
- corpus membership proofs beyond the frozen content IDs;
- signatures or external attestations;
- database transactions, rollback, or garbage collection;
- real model or dataset execution;
- aggregate scoring or model selection.

## Rejected alternatives

### Treat any set of session receipts as experiment completion

Rejected because missing or reordered content could be mistaken for a completed experiment.

### Write the completion manifest before bundle re-verification

Rejected because completion would then depend on artifacts that had not passed the final integrity boundary.

### Delete partial receipts after a later failure

Rejected because deletion conflicts with append-only provenance and destroys valid evidence about what completed.

### Derive an overall experiment status from session outcomes

Rejected because execution completion and measurement interpretation are separate responsibilities.

## Verification

The implementation must prove:

- exact ordered content-scope rejection before writes;
- deterministic per-content run IDs;
- independent canonical receipt persistence;
- preservation of earlier receipts after a later session failure;
- no completion manifest after session, receipt, or bundle-verification failure;
- completion-manifest persistence only after every declared session verifies;
- final completion re-verification before a receipt is returned;
- absence of aggregate score and overall analytical status fields.
