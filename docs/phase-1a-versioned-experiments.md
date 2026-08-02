# Phase 1A Slice: Versioned Experiments

## Purpose

This slice turns the dependency-free synthetic Workbench into a reproducible experiment instrument without introducing real models, benchmark corpora, persistence infrastructure, or deployment.

The synthetic Workbench already proves that two analyzers can produce immutable results and that a comparison can abstain without rewriting them. The versioned-experiment layer answers the next question:

> Can CTRT preserve exactly which protocol, registry, corpus, instrument revisions, environment, results, and comparison governed one execution?

## Records

### Versioned artifact reference

A protocol, candidate registry, corpus, fixture set, or frozen plan is identified by:

- artifact identifier;
- artifact version;
- SHA-256 hash.

The identifier and version make the artifact understandable. The hash prevents a later file with the same name from silently replacing the artifact that governed a run.

### Instrument revision

Each planned instrument records:

- candidate identifier;
- executable analyzer identifier;
- exact implementation revision;
- adapter version;
- configuration hash.

The initial slice uses dependency-free fixture analyzers. Real candidate execution remains deferred.

### Frozen experiment plan

A frozen plan records:

- research question;
- protocol reference;
- candidate-registry reference;
- corpus or fixture-set reference;
- content identifiers;
- dimensions;
- ordered instrument revisions;
- versioned metrics;
- exclusion rules;
- stopping rules;
- creation time.

A draft plan cannot authorize a run. Methodological changes produce a new plan version rather than changing the plan associated with prior results.

### Execution environment

The environment record preserves:

- environment identity and version;
- Python version;
- operating system;
- architecture;
- dependency-lock hash;
- runtime-configuration hash;
- hardware description.

These fields support diagnosis and reproduction. They do not imply that two environments are equivalent merely because their labels are similar.

### Result and comparison artifact references

A completed Workbench run is serialized into independent immutable artifacts. The experiment record references:

- every result identifier;
- analyzer and content identity;
- original result status, including `failed` or `abstained`;
- result artifact hash;
- comparison identity and status;
- comparison artifact hash;
- the ordered result identifiers used by the comparison.

No successful rerun replaces an earlier failed or abstained artifact.

### Append-only ledger

The initial implementation includes a small in-memory ledger that rejects:

- replacement of an existing experiment-plan version;
- replacement of an existing run record;
- attaching a run to an unknown or hash-mismatched plan artifact;
- recording the same Workbench run twice.

The ledger is an executable lifecycle proof, not the persistence design. SQLite or content-addressed storage remains a later implementation decision.

## Execution sequence

1. Author a draft experiment plan.
2. Resolve all required artifact versions and instrument revisions.
3. Freeze the plan.
4. Execute the existing synthetic Workbench using the declared analyzer order and content.
5. Serialize each immutable `ModelResult` and the `WorkbenchComparison`.
6. calculate and preserve SHA-256 hashes for those serialized artifacts.
7. Create an `ExperimentRunRecord` tied to the frozen plan and execution environment.
8. Append the plan and run record to the experiment ledger.

## Enforced invariants

- only frozen plans authorize execution records;
- protocol, registry, and corpus references are mandatory;
- a frozen plan requires at least two pinned instrument revisions;
- scalar-confidence metrics are forbidden;
- Workbench analyzer order must match the frozen plan;
- content must be authorized by the plan;
- result hashes must cover exactly the preserved results;
- result statuses are copied without reinterpretation;
- the comparison references every result in order;
- run status preserves comparison status;
- timestamps include timezones and completion cannot precede start;
- plan versions and run records are append-only.

## Current boundary

This slice does not:

- resolve candidate eligibility from the registry at runtime;
- download or execute real analyzers;
- build a benchmark corpus;
- compute empirical accuracy, calibration, robustness, or bias metrics;
- persist artifacts to a database;
- schedule distributed runs;
- sign manifests;
- expose an API or user interface;
- produce a CTRT aggregate score.

The next implementation boundary is an explicit candidate-eligibility execution gate and canonical serialization for the synthetic artifacts. Only after those exist should the repository consider the first lightweight real candidate adapter.
