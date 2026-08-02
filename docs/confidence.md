# Phase 0 Confidence Vector

**Status:** Canonical design specification  
**Authority:** [ADR-0006](adr/0006-structured-confidence-and-abstention.md)

## Purpose

CTRT confidence is a set of inspectable signals, not a claim that one number captures system reliability.

```json
{
  "instrument_probability": {
    "value": null,
    "source": null,
    "notes": "No report-level probability was derived."
  },
  "calibration": {
    "status": "unknown",
    "method": null,
    "domain": null,
    "evidence_ref": null
  },
  "applicability": {
    "status": "unknown",
    "reasons": ["Domain applicability has not been evaluated."],
    "evidence_ref": null
  },
  "extraction_quality": {
    "status": "clean",
    "issues": [],
    "evidence_ref": "content-item:content-001"
  },
  "inter_instrument_agreement": {
    "status": "single-instrument",
    "participants": ["synthetic.sentiment.a"],
    "metric": null,
    "value": null,
    "notes": "Agreement cannot be inferred from one analyzer."
  },
  "system_abstention": {
    "triggered": false,
    "reasons": []
  },
  "ambiguity_budget": {
    "status": "preserved",
    "preserved_uncertainties": ["Calibration is unknown."],
    "forced_resolutions": [],
    "notes": "Uncertainty remains explicit rather than converted into a score."
  }
}
```

## Signal semantics

### Instrument probability

The probability or confidence-like value emitted by an instrument, or produced by an explicitly declared derivation. A null value means no such value is represented at this level. It does not imply zero probability.

### Calibration

Whether instrument probability has demonstrated correspondence with observed reliability for a declared domain.

- `unknown`: no accepted calibration evidence;
- `estimated`: preliminary method and evidence exist but have not met validation criteria;
- `validated`: accepted under the research protocol for the named domain.

Phase 0 defaults to `unknown`.

### Applicability

Whether the analyzed content fits the declared language, domain, genre, length, and other boundaries under which the instrument has been evaluated.

- `in-domain`;
- `borderline`;
- `out-of-domain`;
- `unknown`.

Out-of-domain use forces abstention.

### Extraction quality

Whether the canonical text and evidence coordinate system were preserved upstream.

- `clean`;
- `partial`;
- `degraded`;
- `failed`.

Failed extraction forces abstention. Partial and degraded extraction must remain visible in limitations.

### Inter-instrument agreement

Agreement is only meaningful among compatible instruments measuring the same versioned construct and compatible taxonomy.

- `single-instrument`;
- `agreement`;
- `partial-disagreement`;
- `strong-disagreement`;
- `abstain`.

Strong disagreement and agreement-level abstention force system abstention.

### System abstention

A separate decision signal. It may be triggered by one critical condition even when instrument probability is high. Reasons use stable machine-readable codes supplemented by report explanations.

Phase 0 mandatory reason codes include:

- `out-of-domain`;
- `extraction-failure`;
- `strong-disagreement`;
- `agreement-abstain`.

### Ambiguity budget

A descriptive account of uncertainty that remains unresolved.

- `unassessed`: no ambiguity accounting has occurred;
- `preserved`: unresolved uncertainty is carried forward without forced resolution;
- `constrained`: a declared method resolved some ambiguity and records what it forced;
- `exceeded`: unresolved ambiguity is too material for the method to summarize faithfully.

The ambiguity budget is never a percentage in Phase 0.

## Result-level and report-level vectors

An analyzer result records the vector known when that analyzer runs. It normally uses `single-instrument` agreement.

A report creates a new vector after comparing analyzer results. It does not rewrite the original result vectors. Report-level instrument probability may remain null because combining instrument probabilities is itself an aggregation claim.

## Aggregation boundary

Any component that reads confidence signals must use a versioned aggregation policy. The policy identifies permitted inputs, signals allowed to trigger abstention, and forbidden outputs. Phase 0 requires `scalar-confidence` to remain forbidden.

## Explanation boundary

Natural-language summaries must cite the confidence signals used. They may say, for example:

> The model reported a high class probability, but calibration is unknown and the content is borderline for the evaluated domain.

They may not say:

> Overall confidence is 82%.

unless a future accepted specification explicitly defines and validates that construct.
