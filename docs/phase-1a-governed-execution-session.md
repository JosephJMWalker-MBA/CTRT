# Phase 1A Governed Execution Session

## Purpose

This slice connects the previously independent Phase 1A contracts into one fail-closed executable lifecycle.

A governed session accepts:

- one frozen `ExperimentPlan`;
- the exact `CandidateRegistrySnapshot` referenced by the plan;
- one `ExecutionEnvironment`;
- one canonical `ContentItem`;
- an `AnalyzerRegistry` containing the planned runtime analyzers;
- one append-only `FileSystemArtifactStore`;
- explicit run and timestamp identities.

It returns a `VerifiedExecutionReceipt` only after the persisted bundle has been reread and fully verified.

## Lifecycle

### 1. Preflight

The session first verifies candidate eligibility and runtime identity.

For every planned analyzer, the loaded runtime must match:

- analyzer ID;
- dimension ID;
- adapter version;
- immutable implementation revision;
- canonical execution-configuration hash.

The content ID must be authorized by the frozen plan, and the content hash must use a lowercase `sha256:` identity.

The initial session requires all planned instruments to share one dimension because the current Workbench comparison contract is dimension-specific.

No analyzer runs and no artifact is written when preflight fails.

### 2. Execution

The session executes every analyzer in frozen plan order through `ContentAnalysisWorkbench`.

The Workbench preserves:

- one immutable `ModelResult` per analyzer;
- the exact canonical target;
- raw and normalized outputs;
- evidence provenance;
- the full structured confidence vector;
- warnings, failures, and abstentions;
- a separate comparison and disagreement record.

Each result configuration must exactly equal the runtime analyzer's declared `execution_configuration`.

### 3. Canonical serialization

The plan, eligibility report, environment, results, comparison, and run record are serialized using `ctrt-canonical-json@0.1.0`.

All hashes are derived from canonical bytes. The session does not accept caller-supplied placeholder hashes.

### 4. Append-only persistence

The complete artifact bundle is written to the local append-only store.

The store persists:

- the plan;
- candidate-eligibility evidence;
- execution environment;
- ordered analyzer results;
- comparison;
- run record;
- the bundle completion manifest.

The manifest is written last.

### 5. Re-verification

After persistence returns, the session explicitly verifies the bundle again.

The store must successfully:

- retrieve the manifest by ID and expected hash;
- reproduce the canonical manifest bytes;
- retrieve every referenced member;
- recompute every member SHA-256 hash.

Only then is a receipt created.

## Verified receipt

The receipt contains:

- session, experiment, run, record, content, and bundle identities;
- ordered analyzer IDs;
- preserved analyzer result statuses;
- preserved Workbench comparison status;
- the immutable manifest reference;
- the exact completed verification checks;
- execution timestamps.

Its status is always `verified` because unsuccessful sessions do not return receipts.

The receipt schema is:

- [`schemas/governed-execution-receipt.schema.json`](../schemas/governed-execution-receipt.schema.json)

## Orthogonal status domains

A verified session is not necessarily a successful measurement.

Examples:

- Both analyzers may succeed while disagreeing strongly. The comparison abstains, but the session is verified.
- Both analyzers may abstain because no fixture signal exists. The comparison abstains, but the session is verified.
- A storage or verification failure prevents a verified receipt even when analyzer measurements were successful.

This separation prevents infrastructure health from being mistaken for epistemic certainty.

## Failure stages

`GovernedExecutionError.stage` identifies the first incomplete boundary:

- `preflight`
- `execution`
- `serialization`
- `persistence`
- `verification`

The original exception is chained. The session does not translate a failed stage into a partial success receipt.

## Synthetic proof cases

The tests establish that:

- successful but contradictory analyzer results produce a verified receipt with an abstained comparison;
- analyzer abstentions remain preserved in a verified receipt;
- unauthorized content fails before execution;
- implementation-revision drift fails before execution;
- execution-configuration drift fails before execution;
- analyzer exceptions fail at the execution stage;
- append failures fail at the persistence stage;
- a manifest failure introduced only after persistence prevents receipt creation at the verification stage.

## Runtime adapter obligations

The provider-neutral `Analyzer` protocol now requires:

```python
class Analyzer(Protocol):
    @property
    def dimension_id(self) -> str: ...

    @property
    def implementation_revision(self) -> str: ...

    @property
    def execution_configuration(self) -> Mapping[str, object]: ...

    @property
    def identity(self) -> AnalyzerIdentity: ...

    def analyze(self, content: ContentItem) -> ModelResult: ...
```

Future real adapters must expose these values before they can enter a governed session.

## Current limits

The session does not yet provide:

- multiple content items in one invocation;
- multiple comparison dimensions;
- retries or resumable execution;
- resource quotas or process isolation;
- signatures or worker attestations;
- remote or transactional storage;
- persistent receipt indexing;
- real candidate execution;
- APIs or a user interface.

These limits preserve the current low-compute research boundary.
