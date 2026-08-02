# Phase 1A: Frozen Corpus Manifest Binding

## Purpose

This slice closes the gap between a frozen experiment's declared content IDs and the exact content bytes presented to analyzers.

A corpus-bound experiment must identify one canonical manifest by ID, version, and SHA-256 hash. The manifest freezes the ordered content population and the metadata required to interpret each item.

## Manifest contract

Each corpus entry records:

- `position` — contiguous zero-based order;
- `content_id` — stable content identity;
- `content_hash` — SHA-256 of exact UTF-8 text bytes;
- `language` — explicit language tag used for applicability checks;
- `source_type` — raw text, webpage, transcript, or other;
- `extraction_ref` — exact extraction identity used by downstream analysis targets.

The manifest itself records a stable corpus ID, corpus version, frozen lifecycle status, and timezone-aware creation timestamp. Its canonical JSON bytes produce the hash stored in `ExperimentPlan.corpus_ref`.

## Preflight sequence

`CorpusBoundExperimentRunner` performs the following work before any store write:

1. Require a frozen experiment plan and a non-empty experiment-run ID.
2. Require the current one-dimension synthetic execution profile.
3. Revalidate candidate eligibility.
4. Compare the plan's corpus reference with the canonical manifest reference.
5. Compare plan content IDs, manifest IDs, and runtime IDs exactly and in order.
6. Recompute SHA-256 from every runtime content item's actual UTF-8 text.
7. Compare the recomputed hash with both the content object and manifest.
8. Compare language, source type, and extraction identity.
9. Require the current `content-item:<content_id>` extraction convention.

Any mismatch produces a `preflight` failure and leaves the append-only store empty.

## Execution and completion

After preflight:

1. The canonical corpus manifest is persisted and reread.
2. The existing `MultiContentExperimentRunner` executes one governed session per content item.
3. The existing experiment completion manifest is produced only after all sessions verify.
4. A `CorpusBoundExperimentCompletion` artifact links the stored corpus manifest to that verified experiment completion.
5. The linked completion, corpus artifact, and experiment completion are reread by ID and hash.
6. Only then is a `VerifiedCorpusBoundExperimentReceipt` returned.

The wrapper preserves partial-progress semantics from the multi-content runner. If a later session fails, prior verified session receipts and the immutable corpus manifest may remain, but no corpus-bound completion exists.

## Completion semantics

`verified` means:

- the plan named the exact corpus manifest;
- runtime content matched the manifest byte-for-byte and metadata-for-metadata;
- the manifest was persisted without replacement;
- the underlying experiment completed and reverified;
- the linked corpus-bound completion reverified.

It does **not** mean:

- every analyzer returned success;
- instruments agreed;
- measurements were accurate or calibrated;
- the content was good, bad, safe, unsafe, valuable, or objectionable;
- an aggregate CTRT score exists.

## Synthetic fixture

`docs/corpora/synthetic-three-items.v0.1.0.json` freezes the three content items used by the dependency-free Workbench tests. It contains one disagreement example, one agreement example, and one no-signal abstention example.

The fixture is architectural evidence only. It is not a research dataset and makes no empirical claim about sentiment measurement.

## Deliberate exclusions

This slice does not add:

- arbitrary extraction methods;
- extraction manifests;
- embedded source text or source documents;
- licensing or acquisition evidence;
- Unicode normalization policy;
- real model or dataset execution;
- aggregate measurement or experiment-wide confidence;
- database, remote storage, signatures, API, frontend, or deployment.

## Relevant artifacts

- `src/ctrt/corpus_manifest.py`
- `src/ctrt/corpus_bound_runner.py`
- `schemas/corpus-manifest.schema.json`
- `schemas/corpus-bound-experiment-completion.schema.json`
- `docs/corpora/synthetic-three-items.v0.1.0.json`
- `docs/adr/0014-frozen-corpus-manifest-binding.md`
- `tests/test_corpus_manifest_binding.py`
