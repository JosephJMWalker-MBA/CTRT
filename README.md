# Content Tone & Revenue Transparency (CTRT)

CTRT is an open, explainable framework for measuring characteristics of digital content through modular analysis models, preserved evidence, explicit uncertainty, and reproducible evaluation.

## Current phase

**Phase 0: Constitutional and Research Foundations** has closed its schema-impacting contract gaps. CTRT has begun **Phase 1A: the Content Analysis Workbench** with dependency-free synthetic execution, versioned experiment records, exact candidate eligibility, canonical artifact hashing, append-only local persistence, and fail-closed governed execution sessions.

CTRT is not a censorship system and does not determine whether content should exist. It measures content items and reports the instruments, evidence, disagreement, confidence, and limitations behind each result.

## Initial research question

> Can interchangeable analysis models be orchestrated and evaluated in a way that produces useful, explainable, repeatable, and evidence-grounded measurements of real-world content?

## Foundation documents

- [CTRT Constitution](CONSTITUTION.md)
- [Phase 0 scope and exit criteria](docs/scope.md)
- [Provisional measurement ontology](docs/ontology.md)
- [Dimension eligibility registry](docs/dimensions/)
- [Structured confidence vector](docs/confidence.md)
- [Model evaluation research protocol](docs/research-protocol.md)
- [Open questions and resolution register](docs/open-questions.md)
- [Architecture Decision Records](docs/adr/)

## Accepted Phase 1A direction: Content Analysis Workbench

The first executable deliverable is not a fixed CTRT scoring product. It is a research workbench that can:

- register candidate models and libraries without preselecting them;
- run multiple eligible instruments on the same canonical content target;
- compare raw outputs, normalized outputs, taxonomies, evidence, confidence vectors, latency, resource observations, warnings, failures, and abstentions;
- compare extraction methods separately from downstream semantic analyzers;
- preserve repeatable experiment and selection records;
- justify later instrument selection with evidence.

See:

- [Phase 1 Content Analysis Workbench specification](docs/phase-1-content-analysis-workbench.md)
- [ADR-0007: Workbench first](docs/adr/0007-content-analysis-workbench-first.md)
- [Candidate technology registry](docs/candidates/)

No candidate is installed or selected merely because it appears in the registry. The initial workbench will not output an overall CTRT score.

## Executable synthetic workbench

The first Phase 1A implementation uses two deterministic fixture analyzers with no machine-learning dependency:

- `synthetic.sentiment.first-signal` selects the first exact `good` or `bad` token;
- `synthetic.sentiment.last-signal` selects the last exact `good` or `bad` token.

The workbench registers both analyzers, runs them on the same canonical content target, preserves each complete `ModelResult`, records taxonomy identity, and assembles a separate side-by-side comparison.

When the fixtures emit opposite valence signs, their original successful results remain unchanged while the comparison records strong disagreement and abstains. Missing fixture signals and out-of-domain language also produce preserved abstention records rather than invented scores.

See [Phase 1A Synthetic Workbench Slice](docs/phase-1a-synthetic-workbench.md).

This slice validates architecture only. It does not establish accuracy, calibration, model selection, or production readiness.

## Versioned experiments

Workbench execution is governed by immutable experiment records rather than mutable runtime settings.

A frozen experiment plan identifies:

- the research question;
- exact protocol, candidate-registry, and corpus artifact versions and hashes;
- authorized content and dimensions;
- ordered candidate, analyzer, dimension, implementation, adapter, and configuration revisions;
- declared metrics, exclusion rules, and stopping rules.

Every recorded run preserves its execution environment and references independently serialized result and comparison artifacts by SHA-256 hash. Successful reruns cannot replace prior failures or abstentions. A small append-only ledger rejects replacement of an existing plan version or run record.

See:

- [ADR-0009: Versioned experiment plans and run records](docs/adr/0009-versioned-experiment-plans-and-run-records.md)
- [Phase 1A Versioned Experiments](docs/phase-1a-versioned-experiments.md)

## Candidate eligibility and canonical artifacts

A frozen plan may execute only after every instrument passes the exact candidate-registry gate.

CTRT verifies:

- exact registry ID, version, and canonical hash;
- accepted registry lifecycle;
- analyzer capability and executable candidate disposition;
- at least provisional license verification;
- explicit analyzer-ID authorization;
- declared dimension compatibility;
- mandatory revision pinning and exact revision agreement.

Eligibility becomes its own immutable artifact and is referenced by the run record. The canonical artifact pipeline then deterministically serializes and hashes the plan, eligibility report, environment, analyzer results, comparison, and final run record using `ctrt-canonical-json@0.1.0`.

The accepted synthetic registry authorizes only the two first-party fixture analyzers. The initial real-candidate registry remains non-executable until candidates have accepted, pinned, license-reviewed, analyzer-specific records.

See:

- [ADR-0010: Candidate eligibility and canonical artifacts](docs/adr/0010-candidate-eligibility-and-canonical-artifacts.md)
- [Phase 1A Candidate Eligibility and Canonical Artifacts](docs/phase-1a-candidate-eligibility-and-canonical-artifacts.md)
- [Accepted synthetic candidate registry](docs/candidates/synthetic-registry.v0.1.0.json)

## Append-only artifact storage

Canonical experiment artifacts can now be persisted in a dependency-free local filesystem store.

The store separates:

- content-addressed blobs keyed by canonical SHA-256 hash;
- immutable artifact-ID indexes that permit exactly one hash per ID.

Identical repeat writes are idempotent. Reusing an existing ID for different bytes is rejected. Every retrieval recomputes the payload hash before returning a `CanonicalArtifact`.

Complete experiment bundles are represented by a canonical manifest written only after the plan, eligibility report, environment, ordered analyzer results, comparison, and run record have been stored. The manifest is a completion marker, not a claim of database transactionality. Bundle verification rereads and re-hashes every referenced member.

See:

- [ADR-0011: Append-only canonical artifact store](docs/adr/0011-append-only-canonical-artifact-store.md)
- [Phase 1A Append-only Artifact Store](docs/phase-1a-append-only-artifact-store.md)

This local store does not yet provide remote durability, signatures, access control, deletion, backup policy, or distributed consistency.

## Governed execution sessions

The first complete synthetic lifecycle is now enforced by `GovernedExecutionSession`.

Before execution, the session verifies:

- frozen-plan and exact candidate-registry eligibility;
- authorized content identity;
- one shared comparison dimension;
- loaded analyzer ID and dimension;
- loaded adapter and implementation revisions;
- canonical execution-configuration hash.

The provider-neutral analyzer contract exposes immutable `implementation_revision` and `execution_configuration` values. Every returned result must preserve the same execution configuration.

The session then executes, serializes, persists, and explicitly re-verifies the complete stored bundle. It returns a `VerifiedExecutionReceipt` only after the manifest and every referenced artifact pass read-time hash verification. Failures are identified as `preflight`, `execution`, `serialization`, `persistence`, or `verification` failures and do not produce partial success receipts.

A verified session is not necessarily a successful measurement. Analyzer abstentions, disagreement, and comparison-level abstention remain visible in the receipt and stored artifacts. `verified` means the governed lifecycle and stored evidence completed successfully.

See:

- [ADR-0012: Governed execution sessions](docs/adr/0012-governed-execution-session.md)
- [Phase 1A Governed Execution Session](docs/phase-1a-governed-execution-session.md)
- [Verified receipt schema](schemas/governed-execution-receipt.schema.json)

The initial session is intentionally limited to one content item, one shared dimension, the synthetic analyzers, and the local append-only store.

## Measurement contract decisions

Every analyzer result must preserve:

- the exact whole-item or segment target in canonical content coordinates;
- the upstream extraction or canonical-input reference;
- the full structured confidence vector;
- whether local evidence is native, post-hoc, deterministic, or unavailable;
- evidence spans only when their origin is declared and their coordinates fall inside the target;
- analyzer and taxonomy identity without implying taxonomy equivalence.

Taxonomies may be displayed side by side even when they are incompatible or unassessed. Any mapping must be versioned and record information loss. Phase 0 taxonomy comparison never permits score combination.

See [ADR-0008](docs/adr/0008-analysis-targets-evidence-and-taxonomy-comparability.md).

## Current experimental profile decision

The first experimental profile may evaluate:

- sentiment valence;
- an emotion profile under a declared taxonomy;
- category-level toxicity indicators under a declared taxonomy.

“Tone” is presently a transparent presentation profile, not a scalar measurement. Emotional intensity remains ineligible until its independent-versus-derived definition is resolved. No overall CTRT rating exists in Phase 0 or the initial workbench.

## Confidence decision

CTRT does not define an overall confidence percentage during Phase 0. Every analyzer result and assembled report carries a structured vector containing:

- instrument probability;
- calibration state;
- applicability;
- extraction quality;
- inter-instrument agreement;
- system abstention;
- a descriptive ambiguity budget.

Out-of-domain analysis, failed extraction, strong disagreement, or agreement-level abstention independently force abstention regardless of instrument probability. Aggregation policies must declare which confidence signals they read and must explicitly forbid `scalar-confidence`.

## Repository map

```text
src/ctrt/          Constitutional contracts, Workbench, eligibility, artifacts, storage, sessions
schemas/           Canonical JSON Schemas
tests/             Contract, schema, registry, Workbench, experiment, artifact, storage, session tests
docs/dimensions/   Versioned dimension eligibility records
docs/candidates/   Versioned candidate technology registries
docs/adr/          Architecture and governance decisions
```

## Scope boundary

The present logic and repository work may define:

- the CTRT Constitution;
- a provisional measurement ontology;
- versioned schemas and provider-neutral contracts;
- architecture decision records;
- candidate and dimension registries;
- model-evaluation and benchmarking protocols;
- dependency-free synthetic analyzers and workbench tests;
- frozen experiment plans and append-only run records;
- exact candidate eligibility gates;
- deterministic canonical serialization and artifact hashing;
- dependency-free append-only local artifact persistence;
- fail-closed governed synthetic execution sessions;
- the Phase 1 workbench specification.

This stage will not download or run transformer models, tune aggregate scores, deploy infrastructure, or begin large-scale corpus evaluation.

## Development

The package has no production runtime dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m mypy
python -m pytest -q
```

## Guiding principle

**CTRT publishes inspectable measurements—not verdicts about content, creators, or audiences.**

## Status

Phase 1A now has a complete governed synthetic path from frozen plan through exact runtime authorization, execution, canonical serialization, append-only persistence, and stored-bundle re-verification. No real candidate is executable, and no CTRT score is validated or suitable for consequential decision-making.
