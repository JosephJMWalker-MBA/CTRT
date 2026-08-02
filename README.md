# Content Tone & Revenue Transparency (CTRT)

CTRT is an open, explainable framework for measuring characteristics of digital content through modular analysis models, preserved evidence, explicit uncertainty, and reproducible evaluation.

## Current phase

The merged repository contains **Phase 0: Constitutional and Research Foundations**. The next proposed executable step is **Phase 1A: the Content Analysis Workbench**.

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

## Phase 1A proposal: Content Analysis Workbench

The first executable deliverable is not a fixed CTRT scoring product. It is a research workbench that can:

- register candidate models and libraries without preselecting them;
- run multiple eligible instruments on the same canonical content;
- compare raw outputs, normalized outputs, taxonomies, evidence, confidence vectors, latency, resource observations, warnings, failures, and abstentions;
- compare extraction methods separately from downstream semantic analyzers;
- preserve repeatable experiment and selection records;
- justify later instrument selection with evidence.

See:

- [Phase 1 Content Analysis Workbench specification](docs/phase-1-content-analysis-workbench.md)
- [ADR-0007: Workbench first](docs/adr/0007-content-analysis-workbench-first.md)
- [Candidate technology registry](docs/candidates/)

No candidate is installed or selected merely because it appears in the registry. The initial workbench will not output an overall CTRT score.

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
src/ctrt/          Dependency-free contracts and constitutional gates
schemas/           Canonical JSON Schemas
tests/             Contract, schema, registry, and domain-invariant tests
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
- synthetic fixtures and contract tests;
- the Phase 1 workbench specification.

This stage will not download or run transformer models, tune aggregate scores, deploy infrastructure, or begin large-scale corpus evaluation.

## Development

The constitutional package has no production runtime dependencies.

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

Early constitutional and workbench design. No CTRT score is currently validated or suitable for consequential decision-making.
