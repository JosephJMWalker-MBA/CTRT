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
- [Model evaluation research protocol](docs/research-protocol.md)
- [Open questions](docs/open-questions.md)
- [Architecture Decision Records](docs/adr/)

## Repository map

```text
src/ctrt/          Dependency-free provider-neutral contracts
schemas/           Canonical JSON Schemas
tests/             Contract and domain-invariant tests
docs/              Scope, ontology, protocol, questions, and ADRs
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
