# Phase 0 Scope — Constitutional and Research Foundations

## Purpose

Phase 0 creates the governed foundation required to investigate CTRT without competing with the active completion of Label Lens or prematurely committing compute to model execution.

The output of this phase is a research-ready repository, not a working content classifier.

## Primary question

> What must be defined, preserved, and tested before CTRT can responsibly claim to measure characteristics of real-world content?

## In scope

### Constitutional logic

- define the authority and limits of CTRT;
- separate measurement from judgment;
- establish provenance, uncertainty, disagreement, abstention, and versioning requirements;
- define rules for generative explanation layers;
- establish change-control and non-consequential-use defaults.

### Measurement design

- draft a provisional content-measurement ontology;
- distinguish constructs that are often improperly collapsed, including tone, sentiment, emotion, toxicity, and intensity;
- define dimension metadata and eligibility requirements;
- record unresolved constructs rather than forcing premature scores.

### Technical contracts

- define provider-neutral analyzer interfaces;
- define canonical content, evidence, model-result, and report records;
- preserve raw and normalized outputs;
- represent model identity, versions, configuration, warnings, errors, applicability, and timing;
- create synthetic fixtures and contract tests.

### Evaluation design

- define benchmark corpus requirements;
- define annotation and adjudication principles;
- define repeatability, agreement, calibration, robustness, bias, and explanation-fidelity tests;
- define evidence required to select or replace a model.

## Explicitly out of scope

Phase 0 will not:

- download or execute transformer models;
- select a production sentiment, emotion, or toxicity model;
- collect a large real-world corpus;
- tune weights or publish an overall CTRT score;
- build a production web interface;
- deploy infrastructure;
- implement producer profiles, audience profiles, parent controls, platform filters, or browser extensions;
- infer revenue flows or economic relationships;
- use CTRT outputs for moderation or other consequential decisions.

## Relationship to future phases

### Phase 1A — Instrument evaluation

Run candidate analyzers against a governed benchmark corpus and compare validity, reliability, calibration, stability, bias, cost, latency, and domain limitations.

### Phase 1B — Provisional measurement engine

Orchestrate selected analyzers through the provider-neutral contracts and produce dimension-level reports with evidence and explicit uncertainty.

### Phase 1C — Aggregate experiments

Test whether any aggregate CTRT representation adds information without concealing dimensions, disagreement, or uncertainty.

### Later phases

Producer-level longitudinal analysis, revenue transparency, audience tools, platform integration, and an open public specification remain separate future concerns.

## Phase 0 exit criteria

Phase 0 is complete when:

1. the Constitution has been reviewed and accepted as the controlling project document;
2. each proposed Phase 1 dimension has an operational definition or is explicitly deferred;
3. canonical schemas preserve raw output, normalized output, provenance, model identity, evidence spans, warnings, and uncertainty;
4. provider-neutral contracts can represent at least two hypothetical analyzers for the same dimension;
5. disagreement and abstention are first-class states;
6. the benchmark protocol defines measurable acceptance criteria without presupposing a winning model;
7. synthetic contract tests pass without any machine-learning dependency;
8. unresolved questions are recorded openly;
9. no document claims that an overall CTRT score is validated.

## Work-allocation boundary

Until Label Lens reaches its defined completion state, CTRT work remains limited to repository structure, written logic, schemas, contracts, synthetic fixtures, and lightweight tests. Any task requiring model downloads, corpus-scale processing, tuning, deployment, or prolonged experimentation is deferred.
