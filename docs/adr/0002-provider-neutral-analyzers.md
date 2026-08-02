# ADR-0002: Use Provider-Neutral Analyzer Contracts

- **Status:** Accepted for Phase 0
- **Date:** 2026-08-02

## Context

Phase 1 must compare existing open-source models rather than bind CTRT to one provider or model family. Model APIs, label taxonomies, confidence semantics, preprocessing, and output formats differ.

## Decision

Every analysis instrument will be accessed through a provider-neutral `Analyzer` contract.

The contract will require:

- declared dimension and taxonomy;
- analyzer, provider, model, and version identity;
- configuration identity;
- raw output preservation;
- normalized output as a separate field;
- evidence spans when supported;
- processing metadata;
- warnings, errors, and applicability statements;
- explicit success, partial, abstained, or failed status.

Provider adapters may translate outputs but may not discard source information required to audit the translation.

## Consequences

- Multiple instruments can run against the same content item.
- Instrument replacement does not redefine the domain model.
- Normalization errors remain inspectable.
- Adapters require more metadata than a minimal classifier wrapper.
- Candidate instruments that cannot satisfy provenance requirements may be excluded even when their headline accuracy is strong.
