# Phase 1B candidate-reference evaluation protocol

## Purpose

This slice preregisters how CTRT may place the admitted VADER candidate beside
the verified human-reference synthesis.

It answers one bounded question:

> Can the comparison rules be frozen before candidate outputs are paired with
> human judgments, while preserving disagreement and refusing to call
> correspondence accuracy?

The answer implemented here is a protocol contract only. No evaluation results
exist in this slice.

## Files

```text
docs/protocols/vader-human-reference-evaluation.v0.1.0.json
src/ctrt/candidate_reference_evaluation_protocol.py
tests/test_candidate_reference_evaluation_protocol.py
docs/adr/0072-preregister-candidate-reference-evaluation-before-pairing-results.md
```

## Exact bindings

The protocol binds the current accepted repository identities:

### Candidate

```text
registry:            registry.real-candidates@0.1.0
candidate:           vader.sentiment
candidate status:    eligible_for_evaluation
analyzer:            vader.sentiment.polarity
package:             vaderSentiment==3.3.2
adapter revision:    ctrt-vader-adapter@0.1.0
configuration hash:  sha256:5340cf6874a87273383109a1c591c7f4f32b450c99ae71454927aad480b52e15
dimension:           sentiment_valence@0.1.0
```

All four outputs remain required and ordered:

```text
neg
neu
pos
compound
```

### Human reference

```text
annotation protocol: protocol.human-reference-sentiment-valence@0.1.0
synthesis protocol:  protocol.human-reference-synthesis@0.1.0
corpus:              corpus.human-reference-sentiment@0.1.0
dimension:           sentiment_valence@0.1.0
required coverage:   meets_declared_minimum_coverage
```

`validate_repository_bindings` reads and validates these repository documents.
It computes the registry hash and verifies package, adapter, configuration,
protocol, corpus, dimension, lifecycle, and execution-boundary facts.

It does not call `installed_vader_version`, import the VADER package, instantiate
the scorer, or analyze text. The default dependency-free installation can parse
and verify this protocol.

## Frozen candidate direction

The upstream VADER conventions are recorded without tuning:

```text
[-1.00, -0.05]  unfavorable
(-0.05, 0.05)   neutral
[0.05, 1.00]    favorable
```

`CandidateReferenceEvaluationProtocol.classify_compound` requires:

- a numeric value;
- a finite value;
- a value inside the admitted `[-1, 1]` bounds; and
- exactly one matching frozen interval.

Boolean values, NaN, infinity, and out-of-bounds values fail closed.

The result is a directional bucket only. The original `compound`, `neg`, `neu`,
and `pos` values must remain present in any later evaluation record.

## Frozen human direction

The original human response distribution has six exact categories:

```text
strongly_unfavorable
somewhat_unfavorable
neither_clearly_favorable_nor_unfavorable
somewhat_favorable
strongly_favorable
cannot_determine_responsibly
```

The protocol derives a second four-count description:

```text
unfavorable = strongly_unfavorable + somewhat_unfavorable
neutral     = neither_clearly_favorable_nor_unfavorable
favorable   = somewhat_favorable + strongly_favorable
abstention  = cannot_determine_responsibly
```

`collapse_human_distribution` refuses partial distributions, unexpected keys,
negative counts, booleans, and non-integer counts. It does not mutate the input.

The original six-option distribution is not replaced. A later item record must
carry both the original and derived descriptions.

## Denominator-preserving correspondence

`describe_correspondence` accepts one measured candidate direction and one human
directional distribution. It returns:

- candidate direction;
- same-direction human count;
- unfavorable human count;
- neutral human count;
- favorable human count;
- the complete non-abstaining denominator; and
- human abstention count.

It exposes no `accuracy`, `rate`, `score`, or correctness field.

Candidate abstention or failure cannot be forced into a directional bucket.
Those outcomes require their own explicit later records.

## Why not a five-way candidate label?

VADER does not emit the human protocol's five ordered categories. Creating
`strongly` and `somewhat` thresholds would require new, corpus-specific cutoffs.
Those cutoffs do not exist in the admitted adapter or upstream convention and
would be especially vulnerable to post-result tuning.

The protocol therefore permits only the upstream three-way direction while
retaining the human intensity categories in the original distribution.

## Why not accuracy?

The human protocol has no answer key. The synthesis has no majority, consensus,
adjudicated, gold, or correct label. Each response is an independent judgment
under written instructions.

A count of human judgments in the same directional bucket as VADER describes
correspondence with those exact judgments. It does not establish that VADER is
correct, that another judgment is wrong, or that the candidate will generalize.

## Blinding boundary

The protocol freezes:

- thresholds;
- permitted measures;
- prohibited measures;
- item inclusion rules;
- candidate and human identities; and
- lifecycle non-claims.

It requires that:

- the protocol exist before results are paired;
- candidate execution remain independent of human responses;
- human collection artifacts remain candidate-blind;
- items pair only by exact identity and content hash;
- no frozen corpus item disappear silently; and
- insufficient coverage, candidate abstention, and candidate failure remain
  separate explicit states.

## What this slice does not do

This slice does not:

- execute VADER;
- read an annotation collection;
- read a synthesis completion;
- pair any candidate result with any human judgment;
- create an evaluation plan, item record, completion, or report;
- compute an empirical metric;
- choose or rank a candidate;
- change the candidate registry;
- resolve licensing questions;
- authorize either browser product door to use VADER; or
- claim production readiness.

## Test coverage

The bounded test suite verifies:

- exact default protocol identity and hash;
- exact candidate and human repository bindings;
- validation without loading the optional VADER distribution;
- every threshold boundary and invalid numeric state;
- complete human-distribution preservation;
- denominator-preserving correspondence;
- candidate abstention refusal at the directional boundary;
- rejection of partial, unexpected, negative, and boolean human counts;
- rejection of protocol status, confidence, tuning, lifecycle, mapping, and
  threshold drift;
- rejection of candidate registry status and configuration drift;
- rejection of annotation, synthesis, and corpus identity drift; and
- a bounded public module surface.

## Next bounded implementation

After this protocol is accepted, the next PR may implement an append-only
research runner that:

1. loads this protocol and revalidates repository bindings;
2. consumes one verified human-reference synthesis receipt;
3. independently executes the admitted candidate on the exact same frozen
   corpus items;
4. stores exact per-item candidate results;
5. pairs only exact item IDs and content hashes;
6. emits original human distributions plus derived directional counts;
7. preserves candidate abstention, failure, and insufficient coverage;
8. stores a three-by-three count contingency without an accuracy label;
9. verifies every stored artifact on read; and
10. leaves `vader.sentiment` at `eligible_for_evaluation`.

That later runner remains research-only and cannot be imported by creator
preflight, content understanding, either browser surface, or the local launcher.
