# Candidate Technology Registry

The candidate registry records technologies that may be evaluated by the CTRT Content Analysis Workbench.

## Inclusion does not mean selection

A registry entry means only that a technology is relevant enough to investigate. It does not establish that the technology is:

- accurate;
- calibrated;
- suitable for a CTRT dimension;
- production ready;
- legally distributable;
- compatible with another candidate's taxonomy;
- selected for any domain.

## Status progression

- **proposed** — named but not yet cleared for execution;
- **eligible_for_evaluation** — sufficiently specified for a preregistered experiment;
- **deferred** — intentionally postponed;
- **rejected_before_execution** — excluded without running, with rationale;
- **evaluated** — executed under a versioned protocol;
- **selected_for_domain** — supported by an accepted, domain-bounded selection record;
- **not_selected** — evaluated but not selected under the declared criteria.

No status implies universal fitness.

## Version pinning

Model-hub names, package names, branches, and `latest` aliases are not reproducible identities. Before execution, every candidate must be pinned to an immutable model revision, package version, or commit and must record its tokenizer, adapter, configuration, and taxonomy where applicable.

## Licensing

A source page's license declaration is only the beginning of review. CTRT must distinguish:

- source-code license;
- model-weight license;
- dataset restrictions;
- lexicon or bundled-resource terms;
- transitive dependency obligations;
- rights to store and redistribute analyzed source content.

A candidate with pending license review cannot be selected for production distribution.

## Real candidate registry

[`real-registry.v0.1.0.json`](real-registry.v0.1.0.json) records candidates backed by an installable third-party distribution. It is separate from the frozen synthetic fixture registry.

It currently holds one candidate, `vader.sentiment` (`vaderSentiment==3.3.2`), at `eligible_for_evaluation`. See [ADR-0063](../adr/0063-admit-vader-as-the-first-real-analyzer-candidate.md) and the [admission guide](../phase-1b-vader-candidate-admission.md).

Real candidates additionally bind `package_binding`, `taxonomy`, `configuration_hash`, `evidence_localization`, and `execution_boundary`. Those fields are optional in the schema so fixture candidates remain valid unchanged.

## Initial registry

[`initial-registry.v0.1.0.json`](initial-registry.v0.1.0.json) records the first technologies proposed for sentiment, emotion, toxicity, extraction, and optional transcript acquisition.

The registry intentionally includes competing technologies and known complications. Its purpose is to make assumptions visible before installation or execution.