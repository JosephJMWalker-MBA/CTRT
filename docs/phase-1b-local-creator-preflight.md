# Phase 1B local creator preflight

This guide describes the first executable local interaction surface for CTRT.

It accepts one raw-text draft and creator context, runs the authorized synthetic demonstration path, and renders the merged **Check before I publish** reflection contract.

It is not a real content-analysis product and does not decide whether anything should be published.

## Run it

From the repository root:

```bash
python -m ctrt.creator_preflight_local \
  --draft-file draft.txt \
  --intent "Explain the change without overstating certainty" \
  --audience "Project collaborators" \
  --concern "The contrast may sound harsher than intended"
```

By default:

- the Markdown preflight is printed to standard output;
- artifacts are stored below `.ctrt/creator-preflight-runs/<run-token>/artifacts`;
- a unique run token is generated; and
- the accepted repository fixture and extraction-method registries are used.

Write the presentation to a file with:

```bash
python -m ctrt.creator_preflight_local \
  --draft-file draft.txt \
  --intent "Share a balanced update" \
  --output preflight.md
```

Read the draft from standard input with:

```bash
cat draft.txt | python -m ctrt.creator_preflight_local \
  --draft-file - \
  --intent "Share a balanced update"
```

For a reproducible test run, provide a lowercase token:

```bash
python -m ctrt.creator_preflight_local \
  --draft-file draft.txt \
  --intent "Share a balanced update" \
  --run-token demo-run-0001
```

A reused token is safe only when every generated artifact is byte-identical. The append-only store rejects assigning changed bytes to an existing artifact ID.

## What is executed

The local interface constructs three content graphs.

### 1. Submitted draft

The exact UTF-8 draft becomes:

```text
raw-text source artifact
    ↓
identity-extraction manifest
    ↓
extracted-content artifact
```

The extraction manifest binds:

- the exact source artifact;
- `synthetic.identity-text`;
- `ctrt-synthetic-identity-text@0.1.0`;
- the accepted configuration hash;
- the exact extracted text hash; and
- one complete exact source-to-canonical coordinate span.

The analyzer input therefore comes from reverified extracted-content storage, not a caller-resupplied string and not the legacy `content-item:` identity.

### 2. Disagreement control

```text
The launch was good, but the support was bad.
```

The first-signal and last-signal fixtures emit opposite valence measurements. The comparison preserves both results and abstains on material disagreement.

### 3. No-signal control

```text
The report contains no fixture vocabulary.
```

Both fixtures abstain without inventing a measurement.

The controls satisfy the inherited multi-content experiment contract and verify that the two synthetic behaviors remain available. They do not appear in the submitted draft’s creator-facing preflight.

## Authorization sequence

Before analyzer execution, the interface checks:

1. the exact frozen candidate registry;
2. the two exact candidate, analyzer, adapter, configuration, and implementation revisions;
3. the exact frozen extraction-method registry;
4. accepted method-registry lifecycle;
5. provisionally verified method license state;
6. exact method revision pin;
7. raw-text source-type authorization;
8. exact coordinate-mapping authorization; and
9. exact extraction configuration-hash authorization.

An unauthorized method, configuration, source type, mapping kind, candidate, or revision stops execution.

## Persistence order

For each content item, the interface appends:

```text
source artifact
extracted-content artifact
extraction manifest
```

It then appends the method-bound extraction corpus last.

The eligible extraction runner subsequently persists and reverifies:

```text
method registry
method eligibility report
experiment artifacts and bundle manifests
experiment completion
extraction-bound completion
eligible-extraction completion
```

Partial artifacts may remain after failure. No later completion marker is written unless its required predecessor evidence exists and re-verifies.

## Creator-facing presentation

Only the submitted draft is selected from the verified three-item experiment.

The Markdown contains:

1. **Your draft** — exact stored extracted content;
2. **Your context** — creator-provided intent, audience, and concerns;
3. **What the evidence records** — lifecycle, instruments, comparison, uncertainty, and limitations;
4. **Questions for you** — deterministic condition-triggered reflection prompts;
5. **Your decision remains yours** — neutral unranked actions;
6. **Interpretation boundary** — fixed constitutional notices; and
7. **Immutable evidence references** — source through final completion.

Creator context is not persisted in the canonical artifact store by this layer. When the user chooses `--output`, it appears in the user-requested Markdown file.

## What the fixture vocabulary means

The synthetic analyzers recognize only exact `good` and `bad` fixture tokens.

Their output demonstrates orchestration and evidence preservation. It does not establish real sentiment validity.

Examples:

```text
This is good.                         → both fixtures find +1
This is good, but that is bad.        → fixtures disagree
This contains no recognized token.    → both fixtures abstain
```

Agreement is not approval. Disagreement is not a warning label. Abstention is not evidence that the draft lacks meaningful tone.

## Failure examples

The command fails before presentation when:

- the draft is empty;
- the run token permits unsafe path syntax;
- a registry cannot be read;
- the method configuration is not authorized;
- a source, extraction, or content artifact is changed;
- exact coordinate coverage fails;
- candidate identity drifts;
- content order changes;
- a session receipt differs from its stored bytes;
- an experiment bundle member is missing; or
- a completion artifact fails read-time hashing.

## Deliberate non-features

This local interface does not provide:

- a web page or desktop GUI;
- a real model;
- OCR, HTML parsing, transcription, or normalization;
- empirical calibration or accuracy evaluation;
- independent human extraction review;
- a safety, morality, quality, or publishability label;
- automatic revision suggestions;
- account or access controls;
- remote storage or durability;
- hidden monitoring; or
- production deployment.

## Next bounded step

After this interface is accepted, the next useful work is not another synthetic wrapper. It is to use the local shell to evaluate the human presentation:

- Which details help a creator reflect?
- Which details belong behind disclosure controls?
- Are disagreement and abstention understandable without technical vocabulary?
- Can provenance remain accessible without overwhelming the primary reading path?

Those findings should shape a minimal browser surface before any real analyzer is admitted.

That surface now exists as a thin wrapper around this same execution path. See [ADR-0062](adr/0062-wrap-creator-preflight-in-a-loopback-only-browser-surface.md) and [the browser preflight guide](phase-1b-browser-creator-preflight.md). It adds no second analysis path; this module remains the only way a draft reaches an analyzer.
