# ADR-0058: Make constitutional invariants the primary Phase 1A proof gate

- Status: Accepted
- Date: 2026-08-05
- Decision owners: CTRT maintainers
- Supersedes: none
- Related: Constitution Articles I–XII; ADR-0057

## Context

Phase 1A now contains a complete governed lifecycle from frozen plans and exact candidate eligibility through canonical persistence, extraction provenance, review, credential, revocation, checkpoint, witness, conflict adjudication, and the immutable `1.32.0` closure checkpoint.

The detailed suite proves each mechanism locally. That breadth is necessary, but it makes the constitutional boundary difficult to see in one place. The next risk is not the absence of another governance wrapper. It is semantic regression across already-complete mechanisms: a future change could preserve local type and schema validity while collapsing measurement into judgment, treating verification as analytical success, weakening append-only identity, bypassing exact-match authorization, or claiming readiness beyond Phase 1A's scope.

ADR-0057 closes automatic governance recursion. Therefore this decision adds no new authority, corpus version, credential, revocation event, witness, or checkpoint. It establishes a proof surface over the completed system.

## Decision

Phase 1A SHALL have one high-signal constitutional invariant module:

```text
tests/test_constitutional_invariants.py
```

That module is a primary CI gate alongside, not instead of, the detailed suite.

The module SHALL:

1. exercise real implementation boundaries and existing real-chain fixtures;
2. inspect canonical returned and persisted artifacts rather than only helper booleans;
3. prove both successful execution and governed abstention paths;
4. prove structural failures stop before unauthorized downstream execution;
5. reject semantic aggregate fields that would turn measurements into judgments;
6. preserve the distinction between canonical artifact identity and exact content bytes;
7. verify that only the accepted, pinned synthetic analyzer records are executable;
8. verify that historical plans, runs, failures, dissent, and abstentions remain non-replaceable; and
9. include the exact closed `1.32.0` governance chain without creating a successor governance layer.

The constitutional module SHALL remain small. Detailed edge cases continue to belong in the mechanism-specific tests. A constitutional test is added only when it proves a cross-cutting non-negotiable property or when a concrete regression demonstrates that the current proof surface is incomplete.

## Constitutional interpretation

### Measurement is not judgment

Per-analyzer normalized measurements are allowed. Overall CTRT scores, scalar tone ratings, aggregate confidence, consequential labels, and production-readiness fields are not allowed in Phase 1A returned or persisted outputs.

### Verified is not analytically successful

`verified` means the declared governed lifecycle and evidence graph completed and were re-read successfully. A verified receipt may preserve analyzer abstentions, strong disagreement, review abstention, credential abstention, revocation abstention, or another governed downstream abstention.

### Conflict is preserved, not outvoted

An unresolved or unauthorized required conflict must abstain. An exact authorized adjudication may restore operational execution only while preserving the original conflict, fork evidence, and dissent. This is not consensus and does not rewrite the conflicting observation.

### Confidence remains dimensional

Confidence evidence is optional. When present, instrument confidence, inter-instrument agreement, calibration, domain applicability, extraction quality, and abstention remain separate. A scalar `confidence`, `confidence_score`, or aggregate confidence field may not substitute for those dimensions.

### Executability remains exact

The durable scope rule is not merely a count of fixtures. Only candidates with an accepted exact registry record, pinned analyzer identity and implementation revision, compatible configuration, and permitted license disposition may execute. At the accepted Phase 1A head, that rule authorizes exactly the two synthetic fixture analyzers and no real candidate.

## Proof organization

The constitutional matrix uses twelve review headings as an organizational aid:

1. Measurement ≠ Judgment
2. Verified ≠ Analytically Successful
3. Append-only & Non-replacement
4. Exact-match Gates Only
5. Content & Extraction Provenance Integrity
6. Canonical Serialization & Read-time Rehashing
7. Evidence Graph Completeness
8. Disagreement & Abstention Are First-class
9. Credential / Revocation / Witness Invariants
10. Separation of Responsibilities
11. Historical Interpretability
12. Scope Discipline

The Constitution remains controlling when a heading is ambiguous or incomplete.

## Consequences

### Positive

- Reviewers gain one concentrated proof surface for the system's non-negotiable meaning.
- CI failures identify constitutional regressions rather than only local implementation defects.
- The proof layer creates a defensible stopping point for Phase 1A governance construction.
- The paper can cite an explicit invariant matrix and executable proof module.
- Future content-evaluation work can proceed without reopening recursive governance by default.

### Costs

- The real-chain constitutional test is intentionally slower than a unit test.
- Some detailed mechanisms are exercised both locally and through the constitutional gate.
- Maintainers must resist turning the constitutional module into another exhaustive test suite.

## Rejected alternatives

### Add another governance wrapper

Rejected by ADR-0057. No concrete unrepresented failure requires one.

### Replace detailed tests with the constitutional module

Rejected. The constitutional module composes selected proofs; it does not replace mechanism-level diagnosis.

### Test only schemas or field names

Rejected. Schema closure is necessary but cannot prove execution order, append-only behavior, evidence completeness, or downstream abstention preservation.

### Encode every constitutional sentence as a separate test

Rejected. That would produce a large, repetitive suite with weak signal. Cross-cutting lifecycle proofs are preferred.

## Reopening criterion

This ADR may be revised when either:

- a concrete constitutional regression passes the current primary gate; or
- a new, explicitly authorized phase changes the Constitution or Phase 1A scope.

A desire for symmetry, more wrappers, or a larger test count is not sufficient.