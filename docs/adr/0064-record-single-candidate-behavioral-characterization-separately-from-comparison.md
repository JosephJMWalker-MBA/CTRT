# ADR-0064: Record single-candidate behavioral characterization separately from comparison

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B research execution

## Context

ADR-0063 admitted `vaderSentiment==3.3.2` at `eligible_for_evaluation`. Admission authorized evaluation and nothing else. The candidate has never been executed inside CTRT.

The next bounded question is deliberately narrow:

> Can CTRT execute the exact admitted VADER candidate over a frozen, provenance-preserving behavioral probe corpus and preserve what it does, without converting the outputs into a verdict or claiming correctness?

That is a question about the *implementation*, not about sentiment. Answering it requires running a real analyzer over real inputs and writing down what happened — which is precisely the moment when a research run is most likely to be mistaken for a validation result.

## The single-analyzer problem

Before writing anything, we checked whether the inherited experiment contracts could truthfully carry one analyzer. They cannot. The requirement is independently hard-coded at five levels:

| Contract | Requirement |
| --- | --- |
| `ContentAnalysisWorkbench.run_content_item` | at least two analyzers |
| `WorkbenchComparison` | at least two result IDs and analyzer IDs |
| `WorkbenchRun` | at least two analyzer IDs |
| `VerifiedExecutionReceipt` | at least two analyzers |
| `SessionCompletion` | at least two result statuses |

`ExperimentPlan` reinforces it: a frozen plan requires at least two instrument revisions, which means even the candidate-eligibility and method-eligibility gates cannot be driven by a single-instrument plan.

These invariants are correct. They exist because the comparison chain's entire purpose is preserving disagreement between independent instruments, and disagreement is undefined with one instrument.

The available responses were:

1. register a fake comparator — rejected: it fabricates evidence;
2. compare VADER against the synthetic fixtures and call it validation — rejected: the fixtures recognize only `good` and `bad`, so agreement or disagreement with them establishes nothing about sentiment, and presenting it as validation would be a false claim;
3. duplicate VADER under two identities — rejected: it manufactures agreement with itself;
4. weaken the multi-result invariant — rejected: it damages the comparison chain to serve an unrelated question;
5. build a separate single-candidate record — **chosen**.

## Decision

Add a research-only single-candidate **behavioral characterization** record, built from the existing canonical serialization, artifact-storage, provenance, result, and verification primitives, and kept entirely separate from the comparison chain.

### Why characterization and comparison are different experiment types

They answer different questions and therefore carry different invariants:

| | Inter-instrument comparison | Behavioral characterization |
| --- | --- | --- |
| Question | Do independent instruments agree about this content? | What does this one admitted implementation do on these frozen inputs? |
| Minimum instruments | Two — one is meaningless | Exactly one — a second would be fabricated |
| Primary evidence | Agreement, disagreement, abstention across instruments | Preserved outputs per probe |
| Subject | The content | The implementation |
| Produces | A comparison artifact | Per-probe observations and narrow expectation outcomes |

`CharacterizationPlan` therefore carries the **inverse** invariant of `ExperimentPlan`: exactly one instrument. That is not a relaxation of the comparison rule; it is a different rule for a different record type. The comparison chain is untouched, and a test asserts it still refuses a single analyzer.

### Shared gates, not duplicated rules

The characterization path must not become a second, weaker gate. Two small behavior-preserving extractions give both paths one source of truth:

- `candidate_eligibility.candidate_authorization_reasons(...)` — the per-candidate registry rules. `_instrument_reasons` now delegates to it; reason strings and their order are unchanged.
- `extraction_method_eligibility.authorize_extraction_methods(...)` — the method rules minus the three plan-shaped checks. `validate_extraction_method_eligibility` now delegates to it.

Neither touches the workbench, execution session, or experiment runners. The 741 inherited tests passing unchanged is the empirical evidence that behavior is preserved.

## Frozen probe corpus

`docs/corpora/vader-behavioral-probes.v0.1.0.json` holds 24 probes authored specifically for CTRT. No text is copied from social media, published posts, or any external dataset, and nothing is retrieved at runtime. The parser refuses to load a corpus that declares `external_dataset`, `scraped_content`, `network_retrieval`, or `human_labels_present`.

Thirteen categories are exercised: plainly positive, plainly negative, neutral, mixed polarity, contrastive conjunction, negation, degree modifier, capitalization emphasis, punctuation emphasis, emoticon or emoji, informal short-form, context-dependent risk, and unsupported language.

**No human ground-truth labels exist.** Each probe carries a `probes` description stating what the item is designed to exercise, plus `not_a_ground_truth_label: true`. A description is a research-design statement about the item; it is never a claim about what the item's sentiment truly is.

## Narrow behavioral expectations

Eight expectations are encoded. Six are metamorphic pairs and two are implementation facts. Each declares a `basis` and a `basis_detail`, and each carries `not_a_correctness_claim: true`.

They are deliberately relational — they compare the implementation's own outputs on two probes that differ by one documented feature:

```text
adding "but" before the negative clause    does not increase compound
inserting "not"                            decreases compound
adding "extremely"                         does not decrease compound
adding "marginally"                        does not increase compound
capitalizing the lexicon token             does not decrease compound
adding exclamation points                  does not decrease compound
```

This construction is what keeps them honest. A relation between two of the implementation's own outputs needs no ground truth to evaluate. None of them says a text is "truly positive", that VADER should match human judgment, that an output is accurate, or that any item proves sentiment understanding.

An unsatisfied expectation means only that the observed implementation did not satisfy that exact probe. It is never a content verdict and never a candidate score. **No overall expectation rate is computed**, because a "6 of 8 passed" figure would immediately be read as a quality score.

## Persisted evidence

Every probe preserves exact content and extraction identity, the full candidate/package/adapter/taxonomy/configuration identity, raw `neg`/`neu`/`pos`/`compound`, each normalized measurement with its own bounds, evidence-support unavailability, zero evidence spans, calibration and applicability status, the extraction-quality evidence reference, ambiguity and limitations, abstention when triggered, and immutable artifact references. Expectation outcomes are stored as separate artifacts beside the results, never merged into them.

Lifecycle counts — completed, abstained, structurally failed — are preserved as **lifecycle information only**, carrying an inline note that they are not a pass rate, an accuracy measure, or any statement of analytical quality.

## Candidate lifecycle is unchanged

The candidate remains `eligible_for_evaluation`. The registry record was not edited, and it records nothing about this run. `CharacterizationCompletion` refuses to serialize any other lifecycle status, and a test asserts the registry document contains no reference to a characterization run.

A technical characterization run is not an evaluation under a declared protocol against human-referenced data. Advancing the lifecycle on the strength of "we executed it and wrote down the numbers" would be exactly the kind of quiet promotion the registry exists to prevent.

## Non-claims

This run does not produce an overall CTRT score, a mean sentiment value, an overall positive/negative/neutral classification, a pass percentage presented as quality, scalar confidence, a candidate ranking, a selection recommendation, or any creator-facing output. Licensing remains `provisionally_verified`. Nothing here is imported by creator preflight, the browser surface, or the creator-facing local CLI.

**Behavioral characterization records what the admitted implementation does on frozen probes. It does not establish that the outputs are correct, calibrated, fair, or suitable for creator-facing use.**

## Required later work

Before human-referenced empirical evaluation or selection:

1. a preregistered evaluation protocol and a declared corpus;
2. human annotation under written instructions, with inter-annotator agreement;
3. calibration analysis, or an explicit statement that calibration remains unknown;
4. quoted-speech, negation, irony, dialect, and reclaimed-language tests at scale;
5. subgroup and identity-term bias analysis;
6. domain-shift evaluation before any domain-valid claim;
7. resolution of both open licensing questions; and
8. a separate accepted, domain-bounded selection record.

## Consequences

### Positive

- CTRT has executed a real analyzer end to end through authorized extraction, canonical storage, read-time rehashing, and completion verification.
- The single-analyzer problem was resolved by adding a record type rather than by weakening an invariant.
- Both eligibility gates now have one source of truth shared by both experiment types.
- The probe corpus is a reusable, frozen, license-clean research asset.

### Costs

- CTRT now has two experiment types, and the difference must be explained wherever either appears.
- A report full of real numbers invites exactly the misreading the non-claims forbid; the interpretation boundary is load-bearing.
- The probe corpus is small and repository-authored, so it exercises documented behavior rather than sampling real usage.

## Reopening criterion

Revisit when a preregistered evaluation protocol with human-referenced data exists, when a second real candidate makes comparison meaningful, when upstream publishes a version beyond `3.3.2`, or when a documented expectation stops holding and the cause is not understood.
