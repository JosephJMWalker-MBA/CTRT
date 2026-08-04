# ADR-0036: Checkpoint-conflict witness adjudicator credentials require append-only revocation history

- Status: Accepted
- Date: 2026-08-03
- Phase: 1A

## Context

ADR-0035 bound the exact pseudonymous identity revision acting as the checkpoint-conflict witness adjudicator to an immutable issuer-authored credential before the adjudication it authorized.

That layer established a third separately inspectable outcome:

```text
witness outcome       -> what the required named witnesses reported
adjudication outcome  -> what accepted adjudication authority selected
credential outcome    -> whether that authority was issuer-authorized then
```

The credential attestation contains a declared base status and validity interval. Those fields are immutable evidence of what the issuer declared when the credential was published. They cannot safely serve as a mutable current-status record.

Editing the credential to represent a later suspension, revocation, or reinstatement would erase history and make earlier decisions impossible to reconstruct. Treating the original `active` field as permanently authoritative would ignore later issuer action.

The next bounded question is therefore:

> What was the exact effective status of the exact credential at the declared time, according to the exact immutable issuer-authored event history?

This question must remain separate from:

- whether the credential was originally valid;
- whether the adjudicator was competent, independent, honest, or correct;
- whether the adjudication selected the correct checkpoint head;
- what each witness reported;
- whether the credential status event was legally sufficient outside CTRT;
- whether an external trust, identity, signature, or timestamp service exists.

## Decision

CTRT will add a distinct append-only, time-relative credential-revocation layer over the exact immutable `1.10.0` credential-bound corpus.

The layer will:

1. use an accepted immutable revocation policy declaring permitted status effects, issuer requirements, event ordering, supersession, and abstention statuses;
2. represent each status change as a separate immutable issuer-authored event;
3. bind every event to the exact credential attestation, adjudicator ID, issuer ID, and immutable issuer revision;
4. distinguish the time an event was recorded from the time its status effect becomes effective;
5. preserve events in an exact ordered population within a frozen ledger;
6. require linear supersession when more than one event exists;
7. require nondecreasing effective times;
8. evaluate effective status at an explicit declared time;
9. apply only events whose `effective_at` is not later than the declared evaluation time;
10. prohibit any event from belonging to a historical decision before it was recorded and frozen into the ledger;
11. require the policy, recorded event population, frozen ledger, successor publication, and evaluation to form a valid chronology;
12. produce governed abstention when the effective status is `suspended` or `revoked`;
13. persist the run-specific revocation decision before invoking the credential lifecycle;
14. invoke the exact unchanged ADR-0035 credential runner only after revocation authorization;
15. preserve the credential, issuer record, adjudication, witness outcome, fork evidence, dissent, rationale, and selected checkpoint head without modification;
16. keep revocation, credential, adjudication, witness, checkpoint, reviewer, and analyzer outcomes separately inspectable.

An `execute` revocation decision adds only the narrower operational claim:

> According to the exact frozen issuer-authored event history available for this decision, the credential's effective status permitted credential evaluation at the declared time.

It does not establish that the credential or adjudication was correct.

## Recorded time and effective time

Every status event carries two distinct timestamps:

```text
recorded_at  -> when the event entered the issuer-authored history
effective_at -> when the event changes effective credential status
```

A future-effective event is permitted. It may be recorded, frozen, and published before its effect begins.

A future-recorded event is not permitted to influence or appear inside an earlier historical decision. CTRT therefore requires:

```text
policy.created_at <= event.recorded_at <= ledger.created_at
ledger.created_at <= successor.created_at <= evaluated_at
```

The event's `effective_at` may be later than `evaluated_at`. In that case the event remains preserved in the exact ledger but is not yet applied to effective status.

This distinction prevents two opposite errors:

- retroactively importing a newly recorded event into a historical decision;
- discarding a legitimately recorded future-effective event merely because its effect has not begun.

## Fixed canonical history

The fixed revocation policy is:

```text
policy_id = policy.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation
policy_version = 0.1.0
status = accepted
permitted_effects = active, suspended, revoked
abstain_on_statuses = suspended, revoked
created_at = 2026-08-03T19:54:32Z
```

The fixed immutable event is:

```text
event_id = event.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator.suspension.v0.1.0
effect = suspended
recorded_at = 2026-08-03T19:54:36Z
effective_at = 2027-01-01T00:00:00Z
```

The event is authored by the exact issuer revision from ADR-0035 and binds the exact credential attestation hash.

The frozen ledger is:

```text
ledger_id = ledger.synthetic-checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocations
ledger_version = 0.1.0
status = frozen
created_at = 2026-08-03T19:54:42Z
```

The canonical successor is published at:

```text
2026-08-03T19:54:48Z
```

The canonical revocation evaluation occurs at:

```text
2026-08-03T19:54:50Z
```

The ADR-0035 credential evaluation follows at:

```text
2026-08-03T19:55:00Z
```

At canonical evaluation time, the future suspension has been recorded but is not yet effective:

```text
base_status = active
effective_status = active
applied_event_ids = []
revocation_outcome = execute
```

At the suspension boundary:

```text
evaluated_at = 2027-01-01T00:00:00Z
base_status = active
effective_status = suspended
applied_event_ids = [event.synthetic.checkpoint-conflict-revocation-witness-conflict-adjudicator.suspension.v0.1.0]
revocation_outcome = abstain
```

The credential artifact remains byte-for-byte unchanged in both evaluations.

## Canonical hashes

```text
revocation policy = sha256:c2c986f5f75c0e1bcb288283e634e60cfd99bf1f5289cc2381b8ea2e90ca030f
suspension event  = sha256:2ebecda7a78b91ffde208dc7f200feb2b79bcb6aefdbcf5d806526ce6791be1a
revocation ledger = sha256:697066b82e49ceb53b3b9c3c1539dbb9801f981eb94e89dbd3275c14f9e4bda6
predecessor 1.10.0 = sha256:1ef073d0b8af20d4ea511f7828a0f90d753d532a1c46b3d6bd36e8a90df21b0f
successor 1.11.0 = sha256:33b05c3429a0d8f58bb12a4ad497c1c885a4e23386fc80fa017f8cbe9ccaf280
```

## Successor-manifest boundary

The revocation-bound corpus is a compact successor manifest:

```text
corpus.synthetic-three-items.checkpoint-conflict-revocation-witness-conflict-adjudicator-credential-revocation-bound@1.11.0
```

It binds:

- the exact immutable `1.10.0` credential-bound predecessor;
- the exact accepted revocation policy;
- the exact frozen revocation ledger;
- the unchanged ordered content population.

The ledger independently binds:

- the exact `1.10.0` credential corpus;
- the exact ADR-0035 issuer registry;
- the exact revocation policy;
- the exact ordered immutable event population.

Publication remains manifest-last:

1. revocation policy;
2. immutable event population in exact order;
3. frozen revocation ledger;
4. compact `1.11.0` successor manifest;
5. exact-hash reread of the complete graph.

No `1.10.0`, `1.9.0`, `1.8.0`, `1.7.0`, credential, issuer, adjudication, witness, checkpoint, reviewer, analyzer, or content artifact is edited.

## Status derivation

The immutable credential's declared status is the base status.

Applicable ledger events are selected in exact ledger order where:

```text
event.effective_at <= evaluated_at
```

Each applicable event replaces only the effective status used by the current decision. It does not alter the credential or earlier events.

For a linear history:

```text
active -> suspended -> active -> revoked
```

an evaluation before the first event remains `active`; an evaluation between events uses the latest applicable event; an evaluation after revocation remains `revoked` unless a later policy-permitted event explicitly supersedes it.

Every applied event ID remains in the decision report.

## Four-outcome separation

This layer preserves four independent facts:

```text
witness outcome       -> what the required named witnesses reported
adjudication outcome  -> what accepted adjudication authority selected
credential outcome    -> whether that authority was issuer-authorized then
revocation outcome    -> whether append-only status history permitted that credential evaluation
```

No later result rewrites an earlier one.

A fully authorized canonical execution may contain:

```text
revocation_outcome    = execute
credential_outcome    = execute
witness_outcome       = execute
adjudication_outcome  = execute
terminal_outcome      = execute
```

An effective suspension contains:

```text
revocation_outcome    = abstain
credential_outcome    = null
witness_outcome       = null
adjudication_outcome  = null
terminal_outcome      = abstain
```

A revocation decision may execute while the credential independently abstains later, for example at the credential validity boundary:

```text
revocation_outcome    = execute
credential_outcome    = abstain
witness_outcome       = null
adjudication_outcome  = null
terminal_outcome      = abstain
```

The outer final must preserve that distinction.

## Explicit scope transition

The complete scope transition is:

```text
1.11.0 plan -> revocation validation, decision persistence, outer finalization
1.10.0 plan -> unchanged ADR-0035 credential lifecycle
1.9.0 plan  -> unchanged ADR-0034 adjudication lifecycle
1.8.0 receipt -> immutable original witness outcome and attestations
1.7.0 plan or receipt -> lower checkpoint, revocation, and downstream lifecycle
```

Experiment identity, version, content IDs, content order, candidate population, analyzer population, execution windows, and every prior governance artifact remain unchanged.

Only the corpus reference is explicitly narrowed after each layer authorizes the next immutable layer.

## Runner ordering

The revocation-gated runner performs:

1. exact frozen-plan, predecessor, policy, ledger, content-order, run, and chronology preflight;
2. storage-backed loading and hash verification of the complete `1.11.0` revocation graph;
3. storage-backed loading and hash verification of the exact `1.10.0` credential graph;
4. exact as-of revocation evaluation;
5. run-specific revocation-decision persistence and reread verification;
6. terminal revocation abstention or delegation to the unchanged ADR-0035 credential runner;
7. outer final-manifest persistence;
8. storage-backed reread of the final, successor, predecessor, policy, ledger, events, credential authority, adjudication record, revocation decision, and optional credential final.

A revocation abstention terminates before the ADR-0035 credential decision, ADR-0034 adjudication decision, lower checkpoint execution, reviewer governance, or analyzers.

## Failure and abstention boundaries

Structural failure includes:

- a non-frozen or mismatched experiment plan;
- a substituted `1.10.0` predecessor;
- a substituted revocation policy or ledger;
- a ledger bound to a different credential corpus, issuer registry, or policy;
- an event population or event order differing from the ledger;
- duplicate event IDs or references;
- unknown credential, adjudicator, or issuer IDs;
- issuer-revision drift;
- event credential-reference drift;
- an effect not permitted by policy;
- non-linear supersession;
- decreasing effective time;
- an event recorded before policy creation;
- an event recorded after ledger freeze;
- a ledger created after successor publication;
- evaluation before successor publication;
- revocation evaluation after credential evaluation;
- impossible witness, revocation, credential, adjudication, or completion chronology;
- append, reread, serialization, or storage-integrity failure;
- delegated ADR-0035 receipt drift.

Structural failure produces no governed revocation decision.

Governed abstention includes:

- effective credential status `suspended`;
- effective credential status `revoked`;
- any later credential, adjudication, checkpoint, reviewer, or analyzer abstention after revocation authorization.

A later credential abstention remains separate from revocation `execute`.

## Consequences

### Positive

- credential history is append-only rather than overwritten;
- historical effective status can be reproduced at an explicit time;
- future-effective events can be published without taking effect early;
- future-recorded events cannot be imported retroactively into earlier decisions;
- issuer, credential, policy, event, ledger, and successor references remain exact and inspectable;
- suspension and revocation prevent credential execution without rewriting preserved evidence;
- the existing generic adjudicator revocation grammar is reused rather than forked;
- `1.11.0` through `1.7.0` scopes remain explicit and testable;
- revocation, credential, adjudication, and witness outcomes remain distinct.

### Costs

- callers must carry another policy, ordered event population, frozen ledger, evaluation time, decision artifact, and successor manifest;
- status history is only as complete as the exact ledger supplied to the decision;
- the ledger is not yet independently checkpointed or witnessed;
- stable pseudonymous issuer records and JSON events do not prove legal identity or cryptographic authorship;
- chronology becomes another fail-closed integration boundary.

## Non-claims

Verification does not establish:

- legal or real-world adjudicator identity;
- legal or real-world issuer identity;
- cryptographic authorship or possession of a private key;
- trusted external time;
- issuer trustworthiness, authority, independence, or competence;
- event completeness outside the exact frozen ledger;
- that no undisclosed event exists;
- global ledger uniqueness or public availability;
- adjudicator independence, competence, honesty, or correctness;
- adjudication correctness;
- witness correctness, independence, competence, or truthfulness;
- majority support, quorum, consensus, confidence, or reputation;
- complete real-world event disclosure;
- extraction, model, analyzer, or content accuracy;
- an aggregate CTRT score.

## Deferred work

The next bounded layer may checkpoint the exact frozen `1.11.0` revocation ledger so later execution can prove which ledger head it relied upon without changing the credential, event history, adjudication, witness abstention, fork evidence, dissent, rationale, or selected checkpoint head.

Named witnesses over that checkpoint, checkpoint-conflict adjudication, signatures, keys, identity providers, external timestamp authorities, and live transparency services remain separate future decisions.
