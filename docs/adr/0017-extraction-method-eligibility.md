# ADR-0017: Extraction methods require frozen registry eligibility

- **Status:** Accepted
- **Date:** 2026-08-03
- **Phase:** 1A — Content Analysis Workbench

## Context

ADR-0016 replaced the temporary `content-item:<content-id>` convention with immutable source, extraction, coordinate-map, and extracted-content artifacts. That work made extraction provenance inspectable and reproducible.

The extraction manifest still described whatever method identity the artifact declared. Nothing independently established whether that method, revision, source type, coordinate mapping, license state, or configuration was authorized for an executable experiment.

Analyzer candidates already pass a separate frozen candidate-registry gate. Extraction methods require an equivalent governance boundary without pretending the two instrument families are interchangeable.

## Decision

CTRT will authorize extraction methods through a separate immutable extraction-method registry.

Each executable method record declares:

- stable method ID;
- lifecycle disposition;
- license-review status;
- whether immutable revision pinning is mandatory;
- the exact pinned method revision;
- supported source types;
- permitted coordinate-mapping kinds;
- explicitly authorized canonical configuration hashes.

The initial accepted registry authorizes only the first-party synthetic identity-text fixture:

- method ID `synthetic.identity-text`;
- revision `ctrt-synthetic-identity-text@0.1.0`;
- raw-text input;
- exact coordinate mapping;
- configuration hash `sha256:bc8e485583a873ac9269382749b2ff803b649939b3ec829ec8bf140db6e350c8`.

No external extractor is installed, selected, or made executable by this decision.

### Registry binding is append-only

The existing extraction corpus `0.1.0` remains unchanged.

A new extraction corpus version `0.2.0` carries an exact method-registry reference containing registry ID, version, and canonical SHA-256 hash. The stricter eligibility runner accepts only this method-bound corpus form.

### Eligibility checks

Before execution, CTRT verifies:

1. the experiment plan is frozen;
2. the plan references the exact method-bound extraction corpus;
3. the corpus references the exact supplied method registry;
4. the registry lifecycle is accepted;
5. every extraction method exists in the registry;
6. method disposition is executable;
7. license review is provisionally verified or verified;
8. immutable revision pinning is required and the extraction revision matches;
9. the source type is explicitly supported;
10. every coordinate-mapping kind is explicitly permitted;
11. the extraction configuration hash is explicitly authorized.

Any failure prevents experiment execution.

### Eligibility is a separate artifact

A successful gate produces an immutable `ExtractionMethodEligibilityReport` containing:

- experiment identity and version;
- exact corpus reference;
- exact method-registry reference;
- one ordered authorization record per extraction artifact;
- method ID and revision;
- configuration hash;
- source type;
- observed mapping kinds.

The report is distinct from:

- the extraction manifest, which records what happened;
- the registry, which records what is permitted;
- the experiment results, which record analyzer measurements.

### Execution and completion

`EligibleExtractionExperimentRunner` performs these stages:

1. validate frozen plan, corpus, ordered content IDs, and timing windows;
2. load and hash-verify the extraction manifests;
3. evaluate method eligibility;
4. persist and reread the exact registry and eligibility report;
5. delegate the existing extraction-bound experiment runner;
6. write a final eligible-extraction completion marker;
7. reread and reverify the registry, eligibility report, extraction-bound completion, and final completion.

If later execution fails, the registry and eligibility report may remain as valid append-only evidence that the method gate passed. Earlier verified session receipts may also remain. No final eligible-extraction completion is written.

### Configuration constraints are exact hashes initially

The first constraint language is intentionally narrow: a method record lists complete canonical configuration hashes that are authorized.

Range rules, optional keys, environment expressions, or partial configuration schemas are deferred. Exact hashes are less expressive but unambiguous and auditable.

### Verification is not endorsement

A verified eligible-extraction completion proves:

- the exact accepted registry was used;
- every method revision and configuration passed the frozen policy;
- extraction provenance and coordinate maps reverified;
- governed experiment execution completed;
- final linked artifacts reverified.

It does not prove:

- real-world extraction accuracy;
- OCR quality;
- semantic fidelity under normalization or omission;
- analyzer success or agreement;
- calibration;
- content quality;
- an aggregate CTRT score.

## Consequences

### Positive

- Extraction methods can no longer self-authorize through their own manifests.
- License state remains explicit and separately inspectable.
- Revision, source-type, mapping, and configuration drift fail closed.
- Authorization decisions become reproducible research artifacts.
- Existing extraction and experiment runners remain unchanged and composable.
- Legacy frozen corpus artifacts remain preserved.

### Costs and limits

- The registry must be maintained as extraction methods evolve.
- Exact configuration hashes require a new authorized value for every meaningful configuration change.
- The current mapping vocabulary contains only `exact`.
- License review is recorded, not automated.
- The local artifact store still lacks remote durability, access control, signatures, retention policy, and transactional rollback.

## Rejected alternatives

### Trust method identity declared by the extraction manifest

Rejected because provenance describes what was claimed to run; it does not independently authorize that instrument.

### Reuse the analyzer candidate registry unchanged

Rejected because extractors have different eligibility dimensions: source types, coordinate mappings, and extraction configurations.

### Add the registry reference to the old corpus artifact

Rejected because frozen research artifacts are append-only. The method-bound corpus is a new version.

### Allow arbitrary configurations by default

Rejected because unbounded configuration changes would defeat exact reproducibility and policy inspection.

### Treat eligibility as proof of extraction accuracy

Rejected because governance authorization and empirical instrument validity are separate questions.
