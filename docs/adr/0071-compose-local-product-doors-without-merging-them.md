# ADR-0071: Compose local product doors without merging them

- Status: Accepted
- Date: 2026-08-06
- Decision owners: CTRT maintainers
- Scope: Phase 1B local synthetic demonstrations

## Context

CTRT now has two complete local browser product doors:

1. **Check before I publish** for creator-directed reflection.
2. **Understand this content** for reader-directed inspection.

Both doors use the same constitutional evidence substrate, but they have intentionally different context models, experiment identities, workspace roots, language, and decisions. Requiring two separate terminal commands is an unnecessary usability burden. Combining the two request handlers or forms, however, would weaken the boundary that keeps each workflow truthful.

## Decision

Add `ctrt.local_browser_launcher`.

The launcher binds three loopback servers:

1. a neutral GET-only landing page;
2. the existing creator-preflight browser server; and
3. the existing content-understanding browser server.

The landing page links to the two exact child URLs. It does not proxy requests, forward form values, read artifacts, execute analyzers, or persist content.

The two existing applications are instantiated unchanged and receive separate workspace roots:

```text
<workspace>/creator-preflight
<workspace>/content-understanding
```

## Separation boundary

The launcher does not combine:

- form fields;
- creator and reader context;
- product wording;
- run tokens;
- experiment, corpus, source, or environment identities;
- artifact stores;
- evidence views;
- decision or inspection paths; or
- result pages.

Choosing a link is a user navigation action, not a CTRT analytical decision.

## Network boundary

All three servers bind to the same literal loopback IP address. Hostnames and non-loopback addresses are rejected before any server is built.

Default ports are:

```text
8764  launcher landing page
8765  creator preflight
8766  content understanding
```

Any port may be set to `0` to request an operating-system-selected local port.

Loopback is not authentication. Another user or process on the same machine may be able to access a server or read the unencrypted workspaces.

## Landing-page boundary

The landing page:

- accepts GET only;
- serves one path;
- contains no form;
- loads no external resource;
- uses no JavaScript;
- sends `Cache-Control: no-store`;
- sends restrictive content, framing, referrer, and MIME-sniffing headers;
- displays the synthetic and local-storage limitations; and
- does not rank or recommend either product door.

## Server lifecycle

The creator-preflight and content-understanding servers run in separate daemon threads. The landing server runs in the foreground. On shutdown, both child servers are explicitly stopped, their threads are joined, and all three sockets are closed.

If binding a later server fails, every server already built during that attempt is closed before the error is returned.

## Alternatives rejected

### Merge both forms into one application

Rejected because the product doors request different context and support different human decisions.

### Route both apps under path prefixes in one server

Rejected for this slice because the existing forms use root-relative actions and links. Rewriting their HTML would couple the launcher to presentation details and create a new routing layer with no governance benefit.

### Proxy child requests through the landing page

Rejected because the launcher would become an intermediary for submitted content and potentially blur artifact and security boundaries.

### Open three browser tabs automatically

Rejected because launching applications is an unnecessary action. The command prints the landing and child URLs and leaves navigation with the user.

## Consequences

A person can start both product doors with one command while each continues to execute through its own merged local and browser contracts.

The launcher is a local convenience layer. It adds no real analyzer, moderation function, user account, authentication, remote deployment, or production-readiness claim.
