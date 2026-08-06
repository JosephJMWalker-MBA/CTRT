# Phase 1B content understanding

## Purpose

`ctrt.content_understanding` provides the second plain-language Phase 1B workflow:

> **Understand this content**

It helps a person inspect one explicitly submitted content item without deciding what the
content means, profiling the person who encountered it, or recommending restriction.

This is a derived application-shell view over the verified stored-content evidence graph.
It is not a new analyzer, score, moderation system, or canonical artifact.

## Input boundary

The builder accepts:

```python
ContentUnderstandingRequest
VerifiedStoredContentExperimentReceipt
FileSystemArtifactStore
```

A request selects one exact `content_id` and supplies `ReaderProvidedContext`:

- `purpose` — required;
- `known_context` — optional; and
- `questions` — optional explicit questions.

Reader-provided values are context, not verified evidence. They do not amend canonical
artifacts and are not used to infer a viewer profile.

## Verification boundary

`build_content_understanding` first calls
`build_stored_content_evidence_view`.

Therefore it inherits the merged evidence reader's complete verification sequence:

1. require a verified stored-content receipt;
2. verify exact ordered content identity;
3. reread stored-content, corpus-bound, and experiment completion markers;
4. reconstruct canonical content by exact ID and hash;
5. compare supplied session receipts with persisted canonical receipt bytes;
6. rebuild and verify every experiment bundle and member;
7. verify analyzer order, result status, target, and extraction identity;
8. verify comparison identity and result order; and
9. quote evidence only from reverified canonical text.

Unknown content IDs, caller-modified receipts, reordered identities, or changed stored
bytes fail before any reflection is derived.

## Structured view

`ContentUnderstandingView` preserves:

- exact submitted content;
- reader purpose, context, and questions in a visibly non-evidentiary field;
- lifecycle status;
- every instrument observation separately;
- agreement, disagreement, and comparison abstention;
- uncertainty dimensions and limitations;
- deterministic reflection prompts;
- neutral inspection paths; and
- immutable evidence references.

The view is not persisted as canonical evidence.

## Markdown structure

`render_content_understanding_markdown` produces:

1. **Submitted content** — exact stored text;
2. **Your questions and context** — explicitly not verified evidence;
3. **What the verified evidence records** — lifecycle, instruments, comparison,
   uncertainty, and limitations;
4. **Questions for closer inspection** — deterministic evidence-triggered questions;
5. **Ways to continue understanding** — neutral, unranked source-review and discussion
   paths;
6. **Interpretation boundary** — fixed notices; and
7. **Immutable evidence references** — exact artifact IDs and hashes.

## Inspection paths

The fixed paths are:

- read the content in its original surrounding context;
- check source, date, authorship, and omitted material;
- discuss the content with the person who encountered or shared it; and
- pause judgment and seek knowledgeable context when evidence is incomplete.

CTRT does not rank or choose among them.

## Evidence-triggered questions

Every view asks about the reader's purpose, source context, and open-ended discussion.
Additional prompts appear only when supported by explicit conditions:

- reader-supplied known context or questions;
- exact evidence spans;
- material disagreement;
- instrument agreement;
- analyzer or comparison abstention;
- calibration not validated;
- applicability short of `in-domain`;
- extraction quality short of `clean`;
- preserved uncertainty; or
- comparison limitations.

Agreement does not establish approval, truth, or impact. Abstention does not establish
absence of a meaningful signal.

## Non-claims

This capability does not produce:

- an overall score or verdict;
- a complete interpretation of meaning;
- a safe/unsafe label;
- a restriction, blocking, punishment, or reporting recommendation;
- inferred viewer intent or emotional state;
- a child, parent, household, or audience profile;
- ambient monitoring;
- automatic enforcement;
- empirical analyzer validity;
- creator-facing real-candidate execution; or
- production readiness.

## Current phase boundary

This first slice uses already verified synthetic evidence. It establishes the interaction
contract before any local **Understand this content** intake surface is added.

A future local surface must:

- accept only explicitly submitted content;
- use the accepted raw-text extraction path;
- reuse this builder and renderer rather than duplicate analysis;
- remain local and non-surveillant; and
- preserve the same prohibition on scores, profiles, and restriction decisions.

## Example

```python
view = build_content_understanding(
    request=ContentUnderstandingRequest(
        content_id="content-001",
        context=ReaderProvidedContext(
            purpose="Understand the contrast and what context should be checked.",
            known_context="The sentence was submitted directly for inspection.",
            questions=("What does the contrast emphasize?",),
        ),
    ),
    receipt=verified_receipt,
    artifact_store=store,
)

print(render_content_understanding_markdown(view))
```

The controlling output remains the verified artifact graph, not the rendered Markdown.
