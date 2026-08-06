# Phase 1B local browser launcher

## Purpose

The launcher starts CTRT's two local synthetic browser product doors with one command while keeping them operationally and evidentially separate.

It does not merge the creator-preflight and content-understanding workflows.

## Start all three servers

From the repository root:

```bash
python -m ctrt.local_browser_launcher
```

The command prints three loopback URLs:

```text
CTRT local workspace: http://127.0.0.1:8764/
Creator preflight: http://127.0.0.1:8765/
Content understanding: http://127.0.0.1:8766/
```

Open the workspace URL to choose a product door.

The command does not open a browser automatically.

## Product doors

### Check before I publish

Use this door when the submitted text is your own draft and you want reflection before deciding whether to publish.

The form asks for creator-provided intent, optional audience, and optional concerns. Those values remain outside canonical evidence.

### Understand this content

Use this door when you are explicitly inspecting one submitted content item.

The form asks for your purpose, optional known context, and optional questions. Those values remain outside canonical evidence.

The launcher does not choose between the doors and does not transfer values from one form to the other.

## Optional configuration

```bash
python -m ctrt.local_browser_launcher \
  --host 127.0.0.1 \
  --port 8764 \
  --creator-port 8765 \
  --understanding-port 8766 \
  --workspace .ctrt/local-browser-workspace
```

Each port may be set to `0` to request an operating-system-selected port.

Only a literal loopback IP address is accepted. Hostnames, `0.0.0.0`, LAN addresses, and public addresses are rejected before binding.

## Separate workspaces

Successful submissions are persisted under sibling roots:

```text
.ctrt/local-browser-workspace/creator-preflight
.ctrt/local-browser-workspace/content-understanding
```

The launcher landing page does not write content or artifacts.

The creator-preflight server cannot write into the content-understanding root through the launcher, and the content-understanding server cannot write into the creator-preflight root through the launcher.

## What the launcher does

The launcher:

1. validates the loopback host and all ports;
2. builds the unchanged creator-preflight server;
3. builds the unchanged content-understanding server;
4. derives their exact bound URLs;
5. builds a neutral GET-only landing page containing those links;
6. runs the two child servers in background threads;
7. runs the landing server in the foreground; and
8. stops and closes all three servers on exit.

## What the launcher does not do

It does not:

- accept submitted content itself;
- proxy a child request;
- forward form values;
- inspect or modify an artifact store;
- execute an analyzer;
- construct evidence;
- combine contexts or results;
- rank the product doors;
- infer which door a person should use;
- open a browser automatically;
- provide authentication;
- encrypt stored content;
- expose a remote service; or
- claim production readiness.

## Landing-page protections

The landing page:

- serves one path;
- accepts GET only;
- contains no form;
- uses no JavaScript;
- loads no external images, fonts, scripts, analytics, or other resources;
- sends `Cache-Control: no-store`;
- sends a restrictive Content Security Policy;
- sends MIME-sniffing, referrer, and frame protections; and
- escapes both child URLs before inserting them into HTML.

## Synthetic limitation

Both product doors still use the fixed synthetic identity extractor and synthetic analyzers. Their outputs exercise CTRT's governance, provenance, disagreement, abstention, and presentation contracts. They do not establish real-world meaning, safety, tone, quality, or fitness for publication.

## Local privacy limitation

Loopback is not authentication. Another process or user on the same machine may be able to reach the servers.

Submitted text and canonical artifacts are written unencrypted to the configured local workspace and are not removed automatically.

## Stop the launcher

Use `Ctrl+C` in the terminal where the launcher is running.

The launcher then stops both child server loops, joins their threads, and closes all three sockets.
