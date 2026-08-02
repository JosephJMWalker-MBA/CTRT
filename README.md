# Content Tone & Revenue Transparency (CTRT)

CTRT is an open, explainable framework for measuring characteristics of digital content through modular analysis models, preserved evidence, explicit uncertainty, and reproducible evaluation.

## Current phase

This repository is beginning with **Phase 0: Constitutional and Research Foundations**. The immediate purpose is to define what CTRT measures, how measurements are represented, and what evidence is required before implementing a production scoring engine.

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

## Current experimental profile decision

The first experimental profile may evaluate:

- sentiment valence;
- an emotion profile under a declared taxonomy;
- category-level toxicity indicators under a declared taxonomy.

“Tone” is presently a transparent presentation profile, not a scalar measurement. Emotional intensity remains ineligible until its independent-versus-derived definition is resolved. No overall CTRT rating exists in Phase 0.

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
tests/             Contract, schema, and domain-invariant tests
docs/dimensions/   Versioned dimension eligibility records
docs/adr/          Architecture and governance decisions
```

## Scope boundary

During Phase 0, this repository will contain:

- the CTRT Constitution;
- a provisional measurement ontology;
- versioned schemas and provider-neutral contracts;
- architecture decision records;
- a model-evaluation and benchmarking protocol;
- synthetic fixtures and contract tests.

Phase 0 will not download or run transformer models, tune aggregate scores, deploy infrastructure, or begin large-scale corpus evaluation.

## Development

The Phase 0 package has no runtime dependencies.

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

Early constitutional design. No CTRT score is currently validated or suitable for consequential decision-making.
