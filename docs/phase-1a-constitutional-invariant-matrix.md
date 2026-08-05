# Phase 1A constitutional invariant matrix

This matrix compresses the Constitution and the completed Phase 1A machinery into a reviewable proof boundary. The Constitution remains controlling. The twelve headings organize the proof; they do not replace constitutional language or create new authority.

Primary executable gate:

```text
tests/test_constitutional_invariants.py
```

Detailed mechanism-specific tests remain authoritative diagnostic evidence beneath this gate.

## 1. Measurement ≠ Judgment

**Constitutional requirement**

CTRT measures declared dimensions and preserves instrument outputs. It does not issue an overall CTRT score, scalar tone judgment, consequential label, or production-readiness determination in Phase 1A.

**Enforcement boundary**

- provider-neutral result and comparison contracts;
- closed receipt and completion schemas;
- no score-combination permission during disagreement;
- recursive inspection of real returned and persisted constitutional artifacts.

**Primary proof**

- mixed fixture measurements remain separate and opposite;
- comparison abstains without changing either result;
- governed receipts, bundle members, extraction completion, and closure final contain no forbidden aggregate or consequential field.

**Detailed substrate**

- `tests/test_synthetic_workbench.py`
- `tests/test_execution_session.py`
- `tests/test_extraction_manifest_binding.py`
- closed final schemas through `1.32.0`

## 2. Verified ≠ Analytically Successful

**Constitutional requirement**

Verification states that the declared lifecycle and evidence graph completed and re-verified. It does not state that analyzers agreed, returned measurements, or produced a successful analytical conclusion.

**Enforcement boundary**

- `ExecutionSessionStatus.VERIFIED` remains separate from workbench and result status;
- closure verification remains separate from the delegated terminal outcome;
- receipt fields preserve each governed outcome independently.

**Primary proof**

- a governed execution receipt is verified while its comparison is abstained for strong disagreement;
- the exact closed governance chain is verified while a delegated later lifecycle outcome remains abstained.

**Detailed substrate**

- `tests/test_execution_session.py`
- `tests/test_closure_checkpoint_gated_current_revocation_conflict_adjudicator_checkpoint_witness_conflict_adjudicator_credential_revocation_runner.py`

## 3. Append-only & Non-replacement

**Constitutional requirement**

Prior plans, runs, failures, abstentions, receipts, and evidence are historical records. A later attempt may append a new record; it may not replace an existing artifact identity with different bytes.

**Enforcement boundary**

- one artifact ID maps to one canonical hash;
- exact duplicate append is idempotent;
- changed bytes under an existing ID fail;
- experiment plan and run ledgers are append-only;
- new specifications use new versioned records.

**Primary proof**

- exact duplicate canonical artifacts remain idempotent;
- changed bytes under the same ID fail;
- a second plan version coexists with the first;
- duplicate plan or run records fail without changing history.

**Detailed substrate**

- `tests/test_artifact_store.py`
- `tests/test_experiments.py`

## 4. Exact-match Gates Only

**Constitutional requirement**

Eligibility and authorization depend on exact identity, version, order, metadata, and canonical hash. Drift fails closed before execution or completion.

**Enforcement boundary**

- exact candidate registry reference;
- pinned candidate, analyzer, dimension, implementation revision, adapter version, and configuration;
- exact corpus and ordered content population;
- exact extraction, credential, revocation, checkpoint, witness, and adjudication references.

**Primary proof**

- exact accepted synthetic registry authorizes only its pinned analyzers;
- registry hash or implementation revision drift fails;
- the non-executable real-candidate registry cannot authorize execution;
- unresolved authority conflict stops before the delegated predecessor.

**Detailed substrate**

- `tests/test_candidate_eligibility.py`
- `tests/test_execution_session.py`
- `tests/test_adjudicated_current_revocation_conflict_adjudicator_checkpoint_witness_runner.py`

## 5. Content & Extraction Provenance Integrity

**Constitutional requirement**

Every execution input is reconstructible from exact frozen source, extraction, and content evidence. Exact UTF-8 content bytes and the canonical artifact containing text plus metadata remain distinct identities.

**Enforcement boundary**

- extraction corpus manifest binds source, extraction, and content artifacts;
- runtime loads and verifies the complete graph before analysis;
- canonical extraction references use the `extraction:` identity;
- legacy `content-item:` identities are not accepted as new extraction artifacts;
- missing source evidence prevents experiment completion.

**Primary proof**

- persisted extraction evidence reconstructs all content in declared order;
- extracted content and canonical extraction references are distinct and exact;
- legacy identity is rejected;
- simulated source-read failure creates no completion marker.

**Detailed substrate**

- `tests/test_corpus_manifest_binding.py`
- `tests/test_extraction_manifest_binding.py`

## 6. Canonical Serialization & Read-time Rehashing

**Constitutional requirement**

Persisted artifacts use the locked canonical JSON profile. Every retrieval and bundle verification re-hashes exact payload bytes before trusting an artifact.

**Enforcement boundary**

- `ctrt-canonical-json@0.1.0`;
- SHA-256 payload identity;
- read-time blob verification;
- manifest-last bundle persistence and member verification.

**Primary proof**

- stored references declare the locked canonicalization profile;
- direct blob tampering fails retrieval;
- tampered bundle membership fails full verification.

**Detailed substrate**

- `tests/test_serialization.py`
- `tests/test_artifact_store.py`
- every later manifest-last evidence graph test

## 7. Evidence Graph Completeness

**Constitutional requirement**

A verified receipt or completion marker exists only after the full required ordered evidence population is stored and re-verified. Partial progress remains inspectable but is not completion.

**Enforcement boundary**

- manifest-last persistence;
- exact ordered role/member population;
- post-persistence re-read;
- completion append only after all required content receipts exist;
- structural failure creates no governed completion marker.

**Primary proof**

- governed bundle verification covers plan, eligibility, environment, results, comparison, and run record;
- missing extraction source stops before completion;
- invalid closure chronology stops before PR #53 and creates no closure final.

**Detailed substrate**

- `tests/test_artifact_store.py`
- `tests/test_execution_session.py`
- `tests/test_extraction_manifest_binding.py`
- closure runner tests

## 8. Disagreement & Abstention Are First-class

**Constitutional requirement**

Disagreement, insufficient evidence, out-of-domain input, and governed abstention are preserved outcomes. They are not converted into invented measurements, votes, or scalar confidence.

**Enforcement boundary**

- analyzer result status independent of comparison status;
- strong disagreement records material disagreement and report abstention;
- missing signal and out-of-domain inputs return analyzer abstentions with empty measurements;
- confidence dimensions remain separate;
- authorized adjudication preserves the original conflicting observation and dissent.

**Primary proof**

- opposite fixture measurements remain successful original results while the comparison abstains;
- no-signal execution remains verified with analyzer abstentions and no normalized scores;
- unresolved conflict abstains before delegation;
- verified closure preserves a later delegated abstention.

**Detailed substrate**

- `tests/test_synthetic_workbench.py`
- `tests/test_execution_session.py`
- review, witness, and conflict-adjudication lifecycle tests

## 9. Credential / Revocation / Witness Invariants

**Constitutional requirement**

Authority evidence is itself exact, append-only, time-bounded, revocable, witnessed, and fail-closed. An inactive credential or unresolved conflict cannot authorize downstream execution. A resolved authorized adjudication preserves the original conflict and dissent.

**Enforcement boundary**

- exact issuer, subject identity revision, role, validity interval, and attestation;
- ordered append-only revocation events and deterministic as-of evaluation;
- immutable checkpoint head and named witness population;
- explicit conflict state and authorized adjudication;
- `1.32.0` closure checkpoint over the exact `1.31.0` head.

**Primary proof**

- pending and unresolved conflict states stop before PR #50;
- all delegated outcome fields remain null on that abstention;
- closed-chain verification preserves all 29 inherited outcomes;
- delegated abstention does not reopen or rewrite the closure graph.

**Detailed substrate**

- credential, revocation, checkpoint, witness, adjudication, and closure lifecycle tests from PRs #17–#54

## 10. Separation of Responsibilities

**Constitutional requirement**

Extraction establishes input provenance and quality. Analyzers measure declared dimensions. Comparison records agreement and disagreement. Governance authorizes or abstains. Explanation may describe evidence but may not silently assume another component's authority.

**Enforcement boundary**

- independent source/extraction/content graph;
- immutable analyzer identity and configuration;
- separate result and comparison artifacts;
- separate eligibility, quality, review, credential, revocation, witness, adjudication, and closure outcomes;
- no analytical aggregate in governance receipts.

**Primary proof**

- exact extraction evidence reconstructs content before semantic execution;
- runtime analyzer revision/configuration drift fails before analysis;
- opposite results remain unchanged when comparison abstains;
- closure verification and delegated terminal outcome remain separate fields.

**Detailed substrate**

- extraction, execution-session, workbench, and closure tests

## 11. Historical Interpretability

**Constitutional requirement**

Every stored result remains interpretable under the exact plan, registry, corpus, extraction, environment, analyzer configuration, and authority state that produced it. Reprocessing creates a new record.

**Enforcement boundary**

- versioned frozen plans;
- immutable plan references in run records;
- exact candidate, corpus, extraction, environment, and authority references;
- append-only artifact and experiment ledgers;
- preserved conflicts, dissent, failures, and abstentions.

**Primary proof**

- a new plan version appends beside the original;
- duplicate historical plan/run records cannot replace prior entries;
- real-chain final artifacts retain separate references and all inherited outcomes.

**Detailed substrate**

- `tests/test_experiments.py`
- every manifest and final-record schema

## 12. Scope Discipline (Phase 1A)

**Constitutional requirement**

Phase 1A proves the measurement and governance harness using synthetic fixtures. It does not claim validated production readiness, consequential decision support, or executable real-candidate integrations.

**Enforcement boundary**

- accepted synthetic candidate registry;
- exact pinned fixture implementations;
- initial real-candidate registry remains non-executable;
- forbidden production-readiness and consequential fields are absent from returned/persisted outputs;
- closure policy prohibits automatic governance successors.

**Primary proof**

- exact eligibility report authorizes only:
  - `synthetic.sentiment.first-signal`
  - `synthetic.sentiment.last-signal`
- initial real-candidate registry fails authorization;
- constitutional artifact inspection rejects production-readiness, consequential-decision, and overall-score fields;
- closure receipt states the branch is closed and automatic successors are forbidden.

**Detailed substrate**

- candidate registry and eligibility tests
- constitutional artifact-surface test
- `1.32.0` closure tests

## CI interpretation

A failure in `tests/test_constitutional_invariants.py` is a constitutional regression until shown otherwise. The preferred response is to identify which invariant was weakened and repair the enforcing boundary. Disabling, narrowing, or exempting the test requires an explicit constitutional rationale.

The detailed suite remains necessary for diagnosis. The constitutional gate remains intentionally small and must not grow merely to mirror every unit test.