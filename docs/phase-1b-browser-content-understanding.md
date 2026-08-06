# Phase 1B browser content understanding

## Purpose

This is a local, synthetic-only browser demonstration for CTRT's **Understand this content** product door.

It lets a person explicitly submit one raw-text item and receive a content-directed reflection derived from the same verified extraction-backed evidence used by the merged command-line path.

It is not a moderation product, parental-control system, surveillance tool, safety classifier, or production service.

## Start the server

From the repository root:

```bash
python -m ctrt.content_understanding_web
```

The command prints a URL similar to:

```text
Local content understanding: http://127.0.0.1:8766/
```

Open that URL in a browser on the same machine.

The browser is not opened automatically.

## Optional command arguments

```bash
python -m ctrt.content_understanding_web \
  --host 127.0.0.1 \
  --port 8766 \
  --workspace .ctrt/content-understanding-web-runs
```

Only a literal loopback address is accepted. `0.0.0.0`, LAN addresses, hostnames, and public addresses are refused before binding.

Port `0` may be used to request an operating-system-selected local port.

## Form fields

The page accepts:

1. **Content to inspect** — exact submitted text.
2. **What are you trying to understand?** — required reader purpose.
3. **Known context** — optional reader-supplied context.
4. **Questions** — optional, one distinct question ending in `?` per line.

Purpose, known context, and questions are not verified evidence. They are not written into the canonical artifact graph.

The page does not request or infer a viewer, child, parent, household, audience profile, risk state, intent, emotional state, or enforcement preference.

## Execution path

A successful POST calls:

```text
run_local_content_understanding
```

That path performs:

1. raw-text source artifact creation;
2. authorized identity extraction;
3. extraction-manifest and extracted-content persistence;
4. synthetic candidate and extraction-method eligibility checks;
5. execution of the two accepted synthetic analyzers;
6. required disagreement and abstention controls;
7. append-only canonical persistence;
8. completion verification;
9. extraction-backed evidence reconstruction; and
10. derivation of `ContentUnderstandingView`.

The web module does not implement a parallel analysis or evidence path.

## Synthetic boundary

The two analyzers recognize only the words `good` and `bad` at fixed positions. Their output is useful for exercising CTRT's contracts and lifecycle. It is not evidence of real-world meaning, safety, tone, quality, or impact.

The two control texts are stored as part of the experiment and are never rendered on the reader-facing result page.

## Result page

The browser preserves:

- submitted content;
- reader context, visibly labeled non-evidentiary;
- each instrument result separately;
- normalized measurements and bounds;
- exact evidence excerpts when available;
- analyzer status and abstention;
- comparison agreement and disagreement;
- comparison abstention;
- calibration;
- applicability;
- extraction quality;
- ambiguity and uncertainty;
- reflection questions;
- neutral inspection paths;
- interpretation notices; and
- immutable evidence references.

Agreement does not appear as approval. Disagreement does not appear as a warning. Abstention does not appear as proof that nothing meaningful exists. All outcomes use the same neutral layout.

## Storage

Each successful submission creates a separate append-only workspace:

```text
.ctrt/content-understanding-web-runs/<run-token>/artifacts
```

The submitted content is stored unencrypted on the local filesystem. The web layer does not delete it automatically.

The result page is derived presentation. Canonical artifacts remain controlling.

## HTTP and browser protections

The surface:

- binds to loopback only;
- serves one path;
- accepts GET and POST only;
- requires URL-encoded form submissions;
- limits request bytes, field lengths, field count, and question count;
- escapes submitted and evidence-derived text;
- sends `Cache-Control: no-store`;
- sends a restrictive Content Security Policy;
- sends frame, referrer, and MIME-sniffing protections;
- uses no JavaScript;
- requests no external image, font, script, analytics, or network resource; and
- retains no analytical state between requests.

These controls do not constitute authentication. Other processes or users on the same machine may be able to reach the server or read the workspace.

## Explicit non-claims

This interface does not provide:

- a correct interpretation;
- an overall CTRT score;
- a safety or risk label;
- a content restriction recommendation;
- a person profile;
- monitoring or enforcement;
- a real analyzer;
- encrypted storage;
- multi-user isolation;
- remote deployment; or
- production readiness.

## Stop the server

Use `Ctrl+C` in the terminal where the command is running.

## Relationship to the creator-preflight browser

The two local browser surfaces reuse the same constitutional substrate but remain separate product doors:

- `ctrt.creator_preflight_web` asks a creator to reflect before publishing.
- `ctrt.content_understanding_web` asks a reader to inspect explicitly submitted content.

Their context models, run identities, wording, and decision boundaries are intentionally not merged.
