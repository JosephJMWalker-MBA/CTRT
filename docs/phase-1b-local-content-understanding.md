# Phase 1B local content understanding

## Purpose

`ctrt.content_understanding_local` is the first executable local intake for the second original CTRT product door:

> **Understand this content**

It accepts one explicitly submitted UTF-8 text item plus reader-provided purpose, known context, and questions. It executes the accepted synthetic demonstration path, reverifies the resulting evidence graph, and renders the merged content-understanding reflection.

This is a local synthetic demonstration. It is not a production moderation, child-safety, surveillance, or real-candidate system.

## Command

```bash
python -m ctrt.content_understanding_local \
  --content-file content.txt \
  --purpose "Understand the wording before discussing it" \
  --known-context "It was shared during a project discussion" \
  --question "What source context should be checked?"
```

Repeat `--question` for additional questions. Every question must end with `?`.

Read from standard input with:

```bash
cat content.txt | python -m ctrt.content_understanding_local \
  --content-file - \
  --purpose "Inspect the content without presuming its meaning"
```

Write Markdown to a file with:

```bash
python -m ctrt.content_understanding_local \
  --content-file content.txt \
  --purpose "Understand the content" \
  --output understanding.md
```

Each run writes an append-only artifact store below:

```text
.ctrt/content-understanding-runs/<run-token>/artifacts
```

The command prints that exact path to standard error.

## Exact execution path

The submitted content is persisted through:

```text
raw-text source artifact
    ↓
identity-extraction manifest
    ↓
extracted-content artifact
```

The extraction manifest binds:

- exact submitted bytes;
- source and content SHA-256 identities;
- accepted method `synthetic.identity-text`;
- pinned revision `ctrt-synthetic-identity-text@0.1.0`;
- accepted configuration hash;
- exact content artifact identity; and
- one complete exact source-to-canonical coordinate span.

Before analyzer execution, CTRT verifies the accepted candidate and extraction-method registries and exact method configuration.

The run then uses:

- `EligibleExtractionExperimentRunner`;
- the two accepted synthetic fixtures;
- append-only canonical storage;
- full completion verification; and
- `build_eligible_extraction_evidence_view`.

The reader-facing view is derived only after those boundaries succeed.

## Why the experiment contains three items

The inherited synthetic experiment substrate requires multiple content items and comparison evidence. The local run therefore contains:

1. the submitted content;
2. a fixed material-disagreement control; and
3. a fixed no-signal abstention control.

The controls demonstrate that disagreement and abstention remain observable outcomes. They are not evidence about the submitted content and never appear in the rendered Markdown.

## Reader context boundary

The command accepts:

- required purpose;
- optional known context; and
- optional questions.

This information is visibly labeled as reader-provided context, not verified evidence. It is not stored as part of the canonical analysis graph and cannot amend source, extraction, analyzer, comparison, or completion artifacts.

The interface does not request or infer:

- viewer identity;
- age;
- parent, child, household, or relationship status;
- demographic information;
- emotional state;
- intent;
- risk level; or
- recommended restriction.

## Output

The Markdown contains:

1. exact submitted content;
2. reader purpose, context, and questions, visibly separated from evidence;
3. each instrument record independently;
4. exact evidence excerpts and coordinates when available;
5. comparison agreement, disagreement, or abstention;
6. calibration, applicability, extraction quality, ambiguity, and limitations separately;
7. deterministic questions for closer inspection;
8. neutral source-review and discussion paths;
9. interpretation notices; and
10. immutable evidence references.

Agreement is not approval. Disagreement is not a warning label. Abstention is not proof that no meaningful signal exists.

## Failure behavior

The command fails closed when:

- submitted content is empty;
- a question is malformed;
- a run token is unsafe;
- a registry cannot be read;
- an extraction configuration is unauthorized;
- an artifact cannot be persisted append-only;
- completion evidence is incomplete;
- stored bytes fail read-time SHA-256 verification; or
- exact content, extraction, analyzer, result, or comparison identity drifts.

## Explicit non-claims

This capability does not establish:

- complete meaning;
- sentiment correctness;
- model accuracy or calibration;
- content safety;
- a viewer or audience profile;
- a reason to block, restrict, punish, report, or monitor;
- suitability for children or another population;
- creator-facing real-candidate use;
- remote deployment; or
- production readiness.

The candidate lifecycle and provisional VADER license review are untouched.

## Next bounded step

After this local command is accepted, the next product slice may wrap `run_local_content_understanding` in a loopback-only browser form. That browser must remain an interface over this exact run function and may not reproduce extraction, analysis, or verification independently.
