# Laya System-One Decision Model — Exploratory Candidate Note

**Status:** proposed research candidate only; not executable, selected, or authorized for any product door  
**Reviewed:** 2026-09-21

## Why this belongs in CTRT's research surface

Laya is an open-weight, non-autoregressive decision-model family that accepts unstructured state plus typed questions and returns bounded outputs rather than generated prose. Public implementations expose three useful primitives:

- `choice` — categorical selection with a probability distribution over declared options;
- `score` — an expected position over an ordered rubric with its distribution;
- `noul` — a probability for a bounded yes/no proposition.

The public Python implementation is maintained at `NandhaKishorM/laya`. A separate Node.js / TypeScript package at `receptron/laya` runs Laya through ONNX Runtime and describes its request/response shape as compatible with TypeSafe Jev's `system_one` API.

These properties make Laya relevant to CTRT because it may eventually serve as a candidate analyzer for dimensions whose ontology can be expressed as bounded categorical, ordinal, or binary questions. It is especially interesting for comparing:

- decision-native probability outputs with CTRT's structured confidence evidence;
- one-pass multi-question inference with conventional analyzer pipelines;
- local execution and reproducibility against remote-service candidates;
- domain adaptation versus zero-shot behavior;
- explicit typed outputs versus post-hoc parsing from generative models.

## Current evidence posture

This note records an external candidate; it does **not** establish accuracy, calibration, suitability, or CTRT eligibility.

Important constraints visible in the public material include:

- capability varies substantially by checkpoint and task;
- public project reports indicate that domain fine-tuning accounts for a large share of performance on its typed-decision workflow benchmark;
- shipped probabilities should not be treated as calibrated for a CTRT domain merely because the model emits probabilities;
- public benchmark material reports confident failures under distribution/language shift, so confidence gating alone is not a sufficient safety or quality mechanism;
- high-cardinality `choice` tasks are constrained by option/token budgets at default settings;
- held-out content-moderation results reported by the project are weak enough that CTRT should not infer moderation suitability from hand-picked examples or the existence of a moderation preset;
- published Laya-versus-Jev comparisons are not a controlled CTRT head-to-head and should be treated as external claims until independently reproduced under one frozen protocol.

## CTRT governance interpretation

Laya's own confidence value is **not** a substitute for CTRT's structured confidence contract. If evaluated, CTRT should preserve at least:

```text
raw model probabilities
+ exact question schema
+ exact checkpoint/runtime revision
+ calibration procedure and evidence
+ extraction/input provenance
+ dimension/taxonomy identity
+ disagreement across candidates
+ abstention/escalation state
+ limitations and distribution bounds
```

A candidate should not be allowed to turn a high probability into authority by itself.

Before any executable CTRT admission, a future candidate record would need to pin and review, at minimum:

- exact Laya checkpoint and immutable revision;
- Python or ONNX runtime implementation and exact version/revision;
- tokenizer and decision-head configuration;
- context and option-budget settings;
- any temperature or calibration parameters;
- license status for code, weights, and transitive dependencies;
- candidate-to-CTRT taxonomy mapping;
- evidence-localization behavior, if any;
- abstention semantics;
- local resource/latency observations on the declared host;
- the exact CTRT dimension(s) authorized for evaluation.

## Proposed experimental posture

If Laya is evaluated later, the first question should be narrow:

> Does a pinned local decision-native model provide useful, reproducible measurement evidence for one CTRT-eligible dimension under the same preregistered, candidate-to-reference lifecycle used for other real candidates?

A first experiment should prefer a low-cardinality dimension with independently collected human-reference evidence and should measure calibration explicitly. It should not begin with moderation, enforcement, creator restriction, or another consequential use.

The current candidate disposition remains:

```text
proposed
not eligible_for_evaluation
not selected_for_domain
not authorized for creator-facing output
not authorized for reader-facing output
not authorized for moderation/restriction/enforcement
```

This candidate note does not modify the accepted VADER lifecycle or current Phase 1B priorities.

## Sources reviewed

- `https://github.com/NandhaKishorM/laya`
- `https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md`
- `https://github.com/receptron/laya`
- `https://typesafe.ai/blog/introducing-system-one-models-and-jev`

Licenses and terms must be re-verified at the exact revision used by any future experiment.
