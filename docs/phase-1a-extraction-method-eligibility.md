# Phase 1A Extraction Method Eligibility

This slice authorizes immutable extraction artifacts through an exact frozen method registry before governed experiment execution.

## Boundary

The layer does not run an extractor. It evaluates already stored extraction manifests against a versioned policy artifact.

The method registry records:

- method identity and lifecycle disposition;
- license-review status;
- mandatory immutable revision pinning;
- supported source types;
- permitted coordinate-mapping kinds;
- authorized canonical configuration hashes.

The accepted synthetic registry contains one first-party identity fixture and no external dependency.

## Append-only corpus evolution

The prior extraction corpus `0.1.0` remains unchanged.

The new `0.2.0` corpus includes `method_registry_ref`, binding the corpus to one exact registry ID, version, and SHA-256 hash. `MethodBoundExtractionCorpusSnapshot` parses the complete document while reusing the existing extraction-corpus contracts.

## Eligibility report

`validate_extraction_method_eligibility` compares each ordered extraction manifest with the corresponding corpus entry and registry method record.

A successful decision produces `ExtractionMethodEligibilityReport`, a canonical artifact preserving:

- experiment and corpus identity;
- exact registry identity;
- extraction artifact identity;
- method ID and pinned revision;
- configuration hash;
- source type;
- observed mapping kinds.

The report does not contain analyzer scores or an extraction-quality judgment.

## Governed execution

`EligibleExtractionExperimentRunner`:

1. validates the frozen plan and ordered execution windows;
2. loads every extraction manifest by exact stored ID and hash;
3. evaluates method eligibility;
4. persists and rereads the registry and eligibility report;
5. delegates `ExtractionBoundExperimentRunner`;
6. writes `EligibleExtractionExperimentCompletion`;
7. rereads and verifies every final governance link.

The caller supplies no content text or extraction configuration. The configuration identity comes from the stored extraction manifests.

## Failure semantics

Failures are classified as:

- `preflight`;
- `extraction-loading`;
- `eligibility`;
- `eligibility-persistence`;
- `experiment-execution`;
- `completion-persistence`;
- `verification`.

Eligibility failures happen before analyzers execute and before an eligibility report is written.

If experiment execution later fails, the verified registry and eligibility report remain preserved. Earlier content-session receipts remain preserved according to the multi-content runner contract. No final eligible-extraction completion is produced.

## Synthetic policy

The accepted synthetic registry authorizes:

```text
method ID:          synthetic.identity-text
revision:           ctrt-synthetic-identity-text@0.1.0
source type:        raw_text
mapping kind:       exact
configuration hash: sha256:bc8e485583a873ac9269382749b2ff803b649939b3ec829ec8bf140db6e350c8
license status:     provisionally_verified
```

## Validation coverage

Tests cover:

- registry, method-bound corpus, eligibility-report, and completion schemas;
- exact successful authorization and execution;
- idempotent repeated execution;
- rejection of legacy corpora without registry binding;
- registry hash mismatch;
- draft registry lifecycle;
- blocked license review;
- pinned-revision mismatch;
- unsupported source type;
- unauthorized configuration hash;
- missing method record;
- prevention of analyzer execution on eligibility failure;
- preservation of authorization evidence and earlier receipts after later failure;
- absence of final completion after completion-persistence failure.

## Meaning of verified

`verified` means the declared method policy, stored extraction provenance, governed execution lifecycle, and append-only completion links all passed integrity checks.

It does not mean the extractor is accurate, the analyzers agree, the content is acceptable, or an aggregate CTRT score exists.
