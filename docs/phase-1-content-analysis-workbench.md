# Phase 1 Technical Specification: Content Analysis Workbench

**Status:** Draft  
**Predecessors:** CTRT Constitution, measurement ontology, eligibility records, research protocol, structured confidence specification  
**Primary deliverable:** A research workbench that discovers and documents defensible analyzer combinations

## 1. Purpose

Phase 1 will not begin by building a single CTRT scoring application.

It will build a **Content Analysis Workbench** that can orchestrate, compare, and evaluate interchangeable open-source technologies for:

- content extraction;
- sentiment valence;
- emotion profiles;
- toxicity indicators;
- optional transcript acquisition.

The workbench exists to determine which instruments are suitable for which CTRT dimensions and domains. A later CTRT product may use selected instruments, but selection must follow recorded evidence.

## 2. Primary research question

> Which combinations of existing open-source instruments produce the most useful, explainable, repeatable, and appropriately bounded measurements of real-world content under declared domains?

Supporting questions include:

1. Which instruments comply with CTRT’s canonical output contracts?
2. Where do instruments disagree on the same content?
3. Which disagreements are caused by taxonomy, domain, preprocessing, or model behavior?
4. Which extraction method best preserves the primary content for a given webpage class?
5. How stable are outputs under repeated runs and meaning-preserving perturbations?
6. What resource and deployment costs accompany each instrument?
7. Does any combined presentation add value beyond transparent side-by-side measurements?

## 3. Non-goals

The initial workbench will not:

- create or train a new foundation model;
- select a production model without benchmark evidence;
- output an overall CTRT rating;
- collapse confidence into a percentage;
- infer creator intent, moral worth, truthfulness, or audience impact;
- implement producer profiles, revenue attribution, filtering, parent controls, browser extensions, or platform integrations;
- perform speech recognition;
- imply multilingual validity beyond evaluated languages.

## 4. Architecture

```text
Submitted source
      |
      v
Acquisition / Extraction Workbench
      |
      v
Canonical ContentItem + extraction provenance
      |
      v
Versioned segmentation manifest
      |
      +--------------------+--------------------+
      |                    |                    |
      v                    v                    v
Analyzer A             Analyzer B             Analyzer C
      |                    |                    |
      +--------------------+--------------------+
                           |
                           v
Canonical ModelResult records
                           |
                           v
Comparison and Evaluation Layer
                           |
                           v
Workbench report + benchmark records
```

The workbench must preserve a distinction between:

- **acquisition:** obtaining source material or transcripts;
- **extraction:** converting a source into canonical analyzable text;
- **segmentation:** creating versioned derivative spans;
- **measurement:** running a declared analyzer for a declared CTRT dimension;
- **comparison:** describing agreement, disagreement, latency, resource use, and contract compliance;
- **selection:** a later governance decision supported by benchmark evidence.

## 5. Provider neutrality

Semantic instruments implement the existing generic `Analyzer` protocol.

Each analyzer declares:

- stable analyzer identity;
- provider and model identity;
- exact model and adapter versions;
- dimension identifier and version;
- taxonomy identifier and version;
- execution configuration;
- domain and language claims;
- raw and normalized outputs;
- confidence vector;
- evidence spans where supported;
- warnings, errors, and timing.

The workbench may group analyzers by dimension in the user interface, but category-specific interfaces must not replace the generic contract merely for convenience.

Extraction and transcript acquisition use separate capability contracts because they produce content and provenance rather than semantic measurements.

## 6. Candidate registry

Candidate technologies are stored in a versioned, machine-readable registry.

Each record includes:

- candidate identifier;
- capability type;
- implementation reference;
- candidate status;
- intended dimension or extraction task;
- expected output taxonomy;
- declared training or operating domain when known;
- source location;
- license-review status;
- revision-pinning requirement;
- known risks and open verification questions;
- reason for inclusion.

A candidate registry is not a dependency file. No candidate is installed merely because it is listed.

## 7. Core workbench workflows

### 7.1 Register candidate

A researcher records a candidate technology, source, intended capability, and verification status.

### 7.2 Define experiment

A researcher selects:

- research question;
- corpus and content items;
- eligible dimensions;
- extraction method or canonical text;
- segmentation method;
- candidate instruments;
- execution environment;
- metrics;
- stopping and exclusion rules.

The experiment definition is frozen before execution. Amendments are append-only.

### 7.3 Execute comparable runs

Every instrument in a comparison receives the same canonical content representation unless preprocessing is itself the experimental variable.

### 7.4 Inspect side by side

The workbench displays:

- raw outputs;
- normalized outputs;
- taxonomies;
- evidence spans;
- structured confidence vectors;
- abstentions and failures;
- timing and resource observations;
- warnings and limitations.

### 7.5 Compare

The comparison layer calculates only declared, versioned metrics appropriate to the output type. It must not compare incompatible taxonomies as though label names or ranges were interchangeable.

### 7.6 Preserve disposition

The workbench records whether a candidate remains proposed, is deferred, rejected, evaluated, selected for a domain, or not selected.

## 8. Evaluation dimensions

Every candidate evaluation should address, where applicable:

- contract compliance;
- repeatability;
- agreement with independent human annotation;
- inter-instrument agreement;
- calibration status;
- perturbation stability;
- domain robustness;
- bias and confounding;
- evidence-span fidelity;
- explanation fidelity;
- processing time;
- peak memory or resource observations;
- installation and deployment complexity;
- deterministic operation or run-to-run variance;
- licensing and redistribution constraints;
- maintenance and version-pinning risk.

“Output quality” must be decomposed into declared measures rather than recorded as an unexplained subjective score.

## 9. Extraction evaluation

Extraction candidates are evaluated separately from semantic analyzers.

The workbench must preserve:

- original source URI;
- retrieval timestamp and status;
- retrieval configuration;
- original response hash where lawful and practical;
- extractor identity and version;
- extracted title and text;
- excluded or unresolved regions;
- text hash;
- truncation or encoding warnings;
- extraction-quality status;
- comparison against human-reviewed reference text where available.

Extraction evaluation should include diverse page structures, not only conventional news articles.

## 10. Transcript acquisition

Transcript acquisition is optional and subordinate to the initial text and webpage workbench.

Speech recognition remains outside scope. Transcript tools may retrieve existing human-authored or automatically generated captions, but the result must identify:

- source video identifier;
- language;
- transcript type when known;
- retrieval method and version;
- timing metadata;
- translation status;
- missing or unavailable transcript state;
- upstream service or undocumented-interface risk.

## 11. Storage

The workbench stores append-only records for:

- candidate registry versions;
- experiment definitions and amendments;
- canonical content items;
- extraction results;
- segmentation manifests;
- model results;
- comparison reports;
- benchmark summaries;
- model-selection records;
- rejected and negative results.

SQLite is sufficient for an initial local workbench, provided canonical records remain exportable as versioned JSON.

## 12. User interface

The first interface should optimize research inspection rather than consumer scoring.

Required views:

1. **Candidate Registry** — proposed technologies and verification state.
2. **Experiment Builder** — corpus, dimensions, instruments, metrics, and frozen protocol.
3. **Run Matrix** — content items by instruments with completion, failure, and abstention states.
4. **Side-by-Side Results** — raw output, normalized output, confidence vectors, evidence, and warnings.
5. **Comparison View** — declared metrics, disagreement, latency, and resource observations.
6. **Selection Record** — rationale for selecting or rejecting an instrument for a domain.

The interface must not visually privilege an instrument merely because it reports a higher probability.

## 13. API boundary

Initial API concepts:

- `POST /candidates`
- `GET /candidates`
- `POST /experiments`
- `POST /experiments/{id}/runs`
- `GET /experiments/{id}`
- `GET /runs/{id}`
- `GET /comparisons/{id}`
- `POST /selection-records`

These routes are provisional. Canonical domain records and invariants take precedence over route naming.

## 14. Success criteria

Phase 1A succeeds when the workbench can:

- register multiple interchangeable candidates for an eligible dimension;
- analyze the same canonical text with multiple instruments;
- compare raw and normalized results without hiding taxonomy differences;
- preserve structured confidence, abstention, provenance, timing, and errors;
- compare at least two extraction methods on the same webpages;
- save and reproduce an experiment definition;
- display side-by-side disagreement;
- generate a complete domain-bounded selection record or a justified decision that no candidate should yet be selected;
- export canonical records without requiring the web interface.

A decision not to select any candidate is a valid Phase 1 result.

## 15. Exit boundary before CTRT scoring

The project may begin a user-facing CTRT scoring product only after:

1. at least one instrument has an accepted selection record for each included dimension;
2. extraction quality requirements are defined and tested;
3. incompatible taxonomy handling is explicit;
4. confidence and abstention policies are validated in workbench reports;
5. explanations remain faithful to canonical measurements;
6. a proposed aggregate demonstrates value beyond the transparent profile;
7. the aggregate receives its own versioned ADR and research protocol.

Until then, the workbench discovers and evaluates measurement instruments. It does not claim to be the final CTRT analyzer.