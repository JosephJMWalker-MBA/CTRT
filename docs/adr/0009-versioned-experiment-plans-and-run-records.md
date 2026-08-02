# ADR-0009: Freeze Experiment Plans and Preserve Append-Only Run Records

- **Status:** Accepted for Phase 1A
- **Date:** 2026-08-02
- **Decision scope:** Workbench experiment authorization, reproducibility, and record lifecycle

## Context

The synthetic Workbench proves that interchangeable analyzers can run against the same canonical target while preserving disagreement and abstention. That proof is not yet a reproducible experiment system.

Without a frozen experiment record, a researcher could change the protocol, candidate set, corpus, metric, stopping rule, configuration, or execution environment after seeing results. A run could then appear to have been produced under conditions that did not actually govern it.

Likewise, storing only mutable result rows would make it possible to replace failed or abstained outputs with later successful outputs and erase the development history that CTRT is intended to expose.

## Decision

### Frozen authorization

Every governed Workbench execution must be authorized by an immutable, versioned experiment plan.

Before execution, the plan must identify:

- the research question;
- protocol artifact and version;
- candidate-registry artifact and version;
- corpus or fixture-set artifact and version;
- exact content identifiers;
- dimensions under evaluation;
- exact candidate, analyzer, implementation, adapter, and configuration revisions;
- declared metrics;
- exclusion rules;
- stopping rules;
- creation timestamp.

Only a plan whose status is `frozen` may authorize execution. A draft plan may be edited before freezing, but it is not an execution authority.

### Revision pinning

An executable instrument entry must name a concrete implementation revision, adapter version, and configuration hash. A floating model name, package channel, branch name, or `latest` alias is insufficient.

Candidate eligibility remains governed by the referenced candidate-registry version. A later execution gate must verify that every candidate is eligible in that exact registry artifact before real candidate execution begins.

### Execution environment

Every run record must preserve a versioned environment identity including:

- Python version;
- operating system;
- architecture;
- dependency-lock hash;
- runtime-configuration hash;
- hardware profile.

Environment identity is descriptive evidence, not a performance claim.

### Artifact references

Analyzer results and comparisons remain their own immutable canonical artifacts. An experiment run record references their identifiers, statuses, and SHA-256 hashes rather than embedding a mutable copy that can silently diverge.

A run record must preserve:

- the exact frozen plan artifact reference;
- Workbench run identity;
- execution environment;
- content identity;
- instrument revision order;
- every result artifact, including failed and abstained results;
- the comparison artifact and all result identifiers it includes;
- start and completion timestamps;
- the comparison-derived run status.

### Append-only lifecycle

Experiment plan versions and run records are append-only.

Corrections or methodological changes create:

- a new experiment-plan version;
- an explicit amendment or supersession relationship in a later phase;
- new run records.

They do not replace prior plans, results, comparisons, or run records.

### No retrospective protocol reassignment

A run produced under one plan, registry, corpus, or environment may not be reassigned to a later artifact version. Later analysis may reference the old run, but must preserve the original governing references.

## Consequences

### Positive

- Results can be interpreted against the conditions that actually produced them.
- Failed and abstained runs remain research evidence.
- Candidate, protocol, corpus, and environment drift becomes visible.
- Reproduction attempts can distinguish instrument behavior from configuration or environment changes.
- The Workbench can later add persistent storage without changing the canonical lifecycle.

### Costs

- Artifacts must be serialized and hashed before a complete run record is appended.
- Amendments create more records rather than editing one convenient object.
- Registry and protocol version management become part of experiment operations.

## Rejected alternatives

### Mutable experiment configuration

Rejected because results could no longer be tied reliably to the conditions that produced them.

### Embed results directly in one mutable experiment document

Rejected because replacement or normalization could erase original failures, abstentions, and raw outputs.

### Record only package versions

Rejected because adapter configuration, runtime configuration, hardware, and source revision can materially change behavior.

### Permit execution from draft plans

Rejected because protocol changes after partial observation would be difficult to distinguish from preregistered decisions.

## Deferred

- persistent database implementation;
- signed manifests or content-addressed object storage;
- formal amendment and supersession schemas;
- candidate-registry eligibility resolution at runtime;
- distributed execution and worker attestation;
- benchmark scheduling;
- real model execution.
