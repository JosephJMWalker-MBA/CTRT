# ADR-0012: Governed execution sessions return only after stored verification

- **Status:** Accepted
- **Date:** 2026-08-02
- **Decision owners:** CTRT stewardship
- **Supersedes:** none
- **Related:** ADR-0007, ADR-0009, ADR-0010, ADR-0011

## Context

CTRT already had separate contracts for:

- frozen experiment plans;
- exact candidate-registry eligibility;
- provider-neutral analyzer execution;
- canonical serialization and hashing;
- append-only artifact persistence;
- complete bundle manifests and re-verification.

Those capabilities could still be called independently and in the wrong order. A caller could execute before validating the loaded runtime, persist only part of a run, or report success before rereading the stored completion manifest.

A second gap remained between the frozen plan and the executable analyzer instance. The plan pinned an implementation revision and a configuration hash, but the provider-neutral `Analyzer` contract did not expose either value. Registry eligibility therefore proved what was authorized, not that the loaded implementation matched the authorization.

## Decision

CTRT will provide a fail-closed governed execution session for the first Phase 1A executable path.

### Runtime analyzer identity

Every executable analyzer must expose:

- `implementation_revision` — the immutable implementation revision loaded for execution;
- `execution_configuration` — the complete provider-neutral configuration used for the run.

The execution configuration is serialized through `ctrt-canonical-json@0.1.0` and compared with the `configuration_hash` frozen in the experiment plan.

The Workbench also requires every returned `ModelResult.configuration` to equal the loaded analyzer configuration. A result cannot silently report a different configuration from the runtime that produced it.

### Preflight

Before analysis begins, the session must verify:

1. the content item is authorized by the frozen plan;
2. the content hash uses the CTRT SHA-256 identity convention;
3. the exact candidate registry passes the eligibility gate;
4. eligibility preserves the frozen analyzer order;
5. the current session contains exactly one comparison dimension;
6. each loaded analyzer matches the plan's analyzer ID;
7. each loaded analyzer matches the planned dimension;
8. implementation revision matches exactly;
9. adapter version matches exactly;
10. canonical execution-configuration hash matches exactly.

Any preflight failure prevents analyzer execution and artifact persistence.

### Ordered lifecycle

A governed session performs these stages in order:

1. `preflight`
2. `execution`
3. `serialization`
4. `persistence`
5. `verification`

Failures are wrapped in `GovernedExecutionError` with the stage that did not complete. The original exception remains chained for diagnosis.

### Completion rule

The session returns a `VerifiedExecutionReceipt` only after:

- the Workbench run completes;
- the complete experiment artifact bundle is canonically serialized;
- every artifact and the bundle manifest are appended to the store;
- the stored manifest is reread;
- every manifest member is retrieved and re-hashed successfully.

There is no successful but unverified receipt state.

### Meaning of `verified`

`verified` describes the execution lifecycle and stored artifact integrity. It does **not** mean:

- every analyzer returned a successful measurement;
- the instruments agreed;
- the comparison avoided abstention;
- the measurement is accurate, calibrated, or production-ready;
- the content is good, bad, permissible, or impermissible.

A session may therefore return a verified receipt while preserving analyzer abstentions or a comparison-level abstention.

### Initial scope

The first governed session executes:

- one canonical content item;
- all analyzer revisions listed by the frozen plan;
- exactly one shared comparison dimension;
- the dependency-free synthetic analyzers;
- one local append-only artifact store.

## Consequences

### Positive

- Execution order is enforced rather than left to caller convention.
- The loaded runtime is cryptographically connected to the frozen configuration.
- A caller cannot receive success before storage re-verification.
- Measurement outcomes remain separate from infrastructure-integrity outcomes.
- Failure stages are explicit without rewriting partial artifacts.
- The full synthetic lifecycle can be tested without models or external services.

### Costs

- Analyzer adapters must expose additional immutable runtime metadata.
- Configuration objects must remain canonically serializable.
- The first session supports only one content item and one comparison dimension.
- The receipt is an execution proof, not a distributed attestation or signature.

## Rejected alternatives

### Let callers compose the lifecycle manually

Rejected because ordering and completion guarantees would remain aspirational.

### Treat persistence as completion without rereading

Rejected because successful writes do not prove that the stored manifest and referenced blobs can be retrieved and verified.

### Return partial success receipts

Rejected because they would blur the distinction between attempted execution and fully verified completion. Stage-specific exceptions already preserve failure location.

### Use analyzer model version as implementation revision

Rejected because a provider model version, adapter version, and implementation revision are distinct reproducibility obligations.

### Treat comparison abstention as session failure

Rejected because abstention is a valid preserved measurement outcome, not an infrastructure failure.

## Deferred

- multi-content experiment sessions;
- multi-dimension session scheduling;
- retries and resumable execution;
- process isolation and resource limits;
- signatures, attestations, and worker identity;
- remote or transactional storage;
- persistent session receipts;
- real candidate adapters and benchmark execution;
- APIs, frontend workflows, and deployment.
