# ADR-0061: Run local creator preflight through authorized raw-text provenance

- **Status:** Accepted
- **Date:** 2026-08-05
- **Phase:** 1B application shell

## Context

ADR-0060 established a creator-controlled reflection contract over an already verified evidence view. The next bounded capability is a local interaction surface that accepts one draft and creator context, executes the authorized synthetic analyzers, and renders that reflection.

A direct shortcut through the legacy canonical-content runner would assign the temporary identity:

```text
content-item:<content-id>
```

That convention was superseded by ADR-0016 and is not acceptable for new execution. A local creator draft must therefore enter through the existing source, extraction, and extracted-content artifact graph.

The inherited multi-content harness also requires at least two content items. A one-draft interface cannot silently weaken that invariant.

## Decision

The local creator-preflight interface will:

1. accept one UTF-8 raw-text draft;
2. preserve creator intent, audience, and concerns as non-evidentiary context;
3. create an immutable raw-text source artifact;
4. create an exact identity-extraction manifest using:
   - `synthetic.identity-text`;
   - `ctrt-synthetic-identity-text@0.1.0`;
   - the exact authorized configuration hash;
   - one complete exact coordinate span;
5. create an extracted-content artifact that references that extraction manifest;
6. pair the draft with two fixed synthetic controls:
   - one material-disagreement control;
   - one no-signal abstention control;
7. publish the three-item method-bound extraction corpus last;
8. authorize every extraction against the accepted synthetic method registry;
9. execute only the two accepted synthetic analyzers;
10. reverify source, extraction, content, registry, eligibility, experiment, and completion evidence;
11. derive the merged creator-preflight reflection for the submitted draft only; and
12. print or write deterministic Markdown while retaining the append-only artifact store locally.

The interface is invoked without an added runtime dependency:

```bash
python -m ctrt.creator_preflight_local \
  --draft-file draft.txt \
  --intent "Explain the update clearly" \
  --audience "Project collaborators"
```

## Why two controls are present

The experiment substrate requires multiple content items. The controls preserve that invariant and demonstrate two distinct fixture behaviors in every local run:

```text
material disagreement
no-signal abstention
```

They are part of the stored experiment graph, not evidence about the creator. The creator-facing Markdown selects only the submitted draft and does not display either control text.

## Evidence boundary

The local interface does not trust the draft after initial ingestion. Presentation begins only after the system has:

- rehashed the exact source bytes;
- reverified the extraction identity and complete exact coordinate map;
- rehashed the extracted-content artifact;
- verified the accepted extraction-method registry;
- verified the method revision and configuration hash;
- verified candidate eligibility;
- persisted and reread every analyzer bundle member;
- persisted and reread experiment completion;
- persisted and reread extraction-bound completion;
- persisted and reread method-eligible completion; and
- reconstructed evidence excerpts from stored extracted content.

Creator context remains outside that evidence graph.

## Presentation boundary

The local interface may display:

- the exact submitted draft;
- creator-provided context, clearly labeled as such;
- each synthetic analyzer result separately;
- exact supporting excerpts and coordinates;
- disagreement or agreement;
- analyzer and comparison abstention;
- dimensional uncertainty and limitations;
- deterministic reflection questions;
- neutral creator-controlled actions; and
- immutable artifact references.

It may not display or infer:

- an overall CTRT score;
- overall sentiment or tone;
- scalar confidence;
- safe/unsafe, good/bad, approved/prohibited, or publish-ready status;
- a recommendation to publish, revise, block, restrict, or suppress;
- an automatic rewrite;
- creator character, intent, or audience profiles; or
- production-readiness claims.

## Failure semantics

The interface fails closed before presentation when any required relationship is absent or changed, including:

- empty draft text;
- unsafe run identity;
- unreadable registry documents;
- source, extraction, content, corpus, registry, or eligibility drift;
- unauthorized extraction configuration;
- analyzer or candidate revision drift;
- missing or tampered stored artifacts;
- changed session receipts;
- incomplete completion evidence; or
- failure to reconstruct exactly one submitted draft.

A synthetic analyzer abstention remains a valid analytical outcome. It is not converted into a structural failure or an invented score.

## Scope and non-claims

This ADR does not introduce:

- a real extractor;
- a real semantic analyzer;
- independent empirical extraction-quality validation;
- a browser or hosted application;
- ambient monitoring;
- authentication, authorization, remote persistence, or multi-user isolation;
- production packaging or deployment;
- a new canonical creator-context or preflight artifact;
- a scoring or recommendation policy; or
- a reopening of the completed Phase 1A governance recursion.

The exact identity map proves that the stored raw text and analyzer input are byte-for-byte identical. It does not establish broader extraction accuracy for OCR, HTML, transcription, normalization, or lossy transforms.

## Consequences

### Positive

- The first usable creator workflow obeys the extraction-provenance boundary already established in Phase 1A.
- No new execution uses the legacy `content-item:` convention.
- The CLI remains standard-library-only.
- The creator sees one draft while the research harness retains multi-content integrity.
- Method authorization and evidence inspection remain separate from analytical success.
- The artifact store provides an inspectable local record for every run.

### Costs

- A single creator draft produces a three-item experiment.
- The local artifact graph is larger than the rendered interaction.
- The synthetic fixtures remain too narrow for real content interpretation.
- Full extraction-quality and later governance layers are not dynamically regenerated for arbitrary drafts.

## Reopening criterion

Revisit this decision only when one of the following becomes concrete:

- the multi-content substrate gains an authorized single-content experiment contract;
- a real raw-text or document extractor is admitted through pinned evaluation records;
- a user test shows that control-item execution creates unacceptable confusion or cost;
- the local shell requires a browser surface while preserving the same evidence boundary; or
- constitutional tests identify a semantic regression not represented here.
