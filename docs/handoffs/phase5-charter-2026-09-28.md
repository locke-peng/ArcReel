# ArcReel × MiniMax H3 — Phase 5 Charter — 2026-09-28

## 0. Formal declaration

Phase 5 is formally defined as:

**Phase 5 — Production Orchestration & Controlled Provider Repair**

Status at creation:

`DEFINED / NOT STARTED`

Phase 1–4 remain CLOSED.

Phase 5 starts from the Phase 4 final documentation HEAD, while the authoritative
Phase 4 tested code remains:

`48a6db8ff3f796535daff7acb29cdd54c62cd6ec`

Phase 4 final acceptance run:

`36370583579`

Phase 5 must reuse the accepted Phase 4 repair architecture. It must not create a second
failure taxonomy, repair planner, or implicit provider-recall path.

---

## 1. Mission

Turn the Phase 4 repair-ticket primitive into a production-grade orchestration loop.

Phase 4 already answers:

```text
What failed?
What H3FailureClass applies?
What action does plan_h3_media_repair() choose?
Can ArcReel repair deterministically?
If not, what exact shot requires provider repair?
```

Phase 5 must answer:

```text
Where is the Repair Ticket stored?
Who/what approved it?
Is the approval still valid for the exact bytes and shot?
Can a paid provider call run exactly once?
Can an interrupted repair resume without duplicate spend?
How is the repaired shot reassembled?
Did Re-QA pass?
What becomes current?
What evidence proves the entire lifecycle?
```

The Phase 5 production loop is:

```text
Phase 4 Media QA
→ Repair Ticket
→ persistent ticket state
→ explicit approval
→ budget / concurrency / idempotency gate
→ shot-scoped provider repair job
→ deterministic unit reassembly
→ Re-QA
→ PASS: formal selection
   OR
→ FAIL: history-only + bounded next escalation
→ immutable lifecycle evidence
```

---

## 2. Scope

### 2.1 Persistent Repair Ticket lifecycle

Productize the Phase 4 immutable Repair Ticket into a persisted production object.

Required lifecycle states:

```text
awaiting_approval
approved
queued
running
provider_completed
reassembling
reqa_running
accepted
rejected
cancelled
expired
human_review_required
```

The persisted record must preserve, at minimum:

- ticket ID;
- ticket SHA256;
- unit ID;
- shot ID;
- time range;
- failure class;
- planner repair action;
- source media SHA256;
- Provider Prompt SHA256;
- reference SHA256 values;
- evidence frame references;
- provider provenance when available;
- current lifecycle state;
- approval identity and timestamp;
- execution task identity;
- attempt count;
- repair output SHA256;
- Re-QA outcome;
- final selected artifact/version identity.

Lifecycle transitions must be explicit and validated. Invalid backwards or skip transitions
must fail closed.

### 2.2 Explicit approval contract

Phase 5 must expose a production approval boundary around
`H3ProviderRepairApproval`.

Approval must bind exactly to:

- Repair Ticket ID;
- Repair Ticket SHA256;
- source media SHA256;
- shot ID;
- approved repair action;
- approval actor;
- approval timestamp;
- maximum provider call count.

A stale approval must not survive any change to:

- source media;
- ticket;
- shot scope;
- Prompt SHA;
- reference identities;
- planner action.

Mismatched or stale approvals must block before any provider submission.

### 2.3 Controlled Provider Repair job

Integrate the Phase 4 shot-scoped executor into ArcReel's normal generation queue.

The repair job must:

1. load the persisted ticket;
2. revalidate ticket and approval;
3. rehash source media;
4. revalidate Prompt/Reference identity;
5. verify budget and call-count allowance;
6. create a unique execution identity;
7. submit only the approved shot repair;
8. persist provider task/checkpoint facts;
9. resume safely if the worker is interrupted;
10. never silently expand shot scope.

The provider runner must remain injected through ArcReel's existing provider/backend
architecture. Phase 5 must not add an H3-only shadow networking stack.

### 2.4 Exactly-once paid-call protection

Phase 5 must prevent duplicate supplier spend caused by:

- retrying an HTTP request after a persisted provider task already exists;
- worker restart;
- process crash;
- queue redelivery;
- duplicate approval clicks;
- duplicate API requests;
- concurrent workers claiming the same ticket.

Required mechanism:

```text
ticket + approval + execution identity
→ atomic claim
→ checkpoint before/at provider submission
→ provider task identity persisted
→ resume by task identity
→ no second paid submission unless a new explicit approval exists
```

A retry may resume polling/download/reassembly/Re-QA. It may not automatically resubmit a
paid generation.

### 2.5 Provider budget and attempt policy

Add a production budget/call-count guard.

Minimum required controls:

- maximum provider calls per approval: default and Phase 4 contract = 1;
- ticket-level attempt count;
- project-level optional repair-call ceiling;
- fail-closed behavior when the allowance is exhausted;
- no infinite retry loop;
- no automatic approval renewal.

The budget guard is an execution constraint only. It must not alter
`plan_h3_media_repair()`.

### 2.6 Shot-scoped deterministic reassembly

A successful provider shot must be reassembled into the source Unit at the ticket's
Canonical time range.

Required invariants:

- only the approved shot window may be replaced;
- surrounding accepted picture must remain unchanged;
- accepted audio must be preserved unless the existing planner explicitly owns an audio
  repair action;
- Canonical Unit duration must remain authoritative;
- no timing debt may leak into later shots;
- output media must receive a new immutable SHA identity.

Multi-shot failures remain separate repair jobs/tickets. ArcReel may orchestrate them
sequentially, but it must never silently collapse them into one whole-Unit regeneration.

### 2.7 Mandatory Re-QA before formal selection

Provider completion is not acceptance.

Every repaired Unit must run through the same trusted Phase 4 runtime gate again.

```text
provider repair
→ reassembly
→ Media QA
→ existing H3FailureClass
→ existing planner
```

If Re-QA passes:

- the repaired version may become current/formal;
- complete evidence is attached to the selected artifact.

If Re-QA fails:

- repaired media remains history-only;
- deterministic Phase 4 repair may run if applicable;
- a new provider-required failure may create a new ticket, but not silently reuse the old
  approval;
- UNKNOWN remains human-review-only.

### 2.8 Repair lineage and evidence

Every accepted/rejected repair execution must be reconstructable.

Minimum lineage:

```text
source formal artifact/version
→ QA finding
→ Repair Ticket
→ approval
→ queue job
→ provider submission/checkpoint/task
→ provider result
→ reassembled media
→ Re-QA findings/plans
→ selected/rejected final artifact
```

Each material artifact and contract must retain immutable SHA256 identities.

Phase 5 must extend the existing evidence mechanism rather than creating an unrelated
audit format.

### 2.9 Minimal operator/API surface

Phase 5 must expose enough product surface to operate the lifecycle safely.

Required operations:

- list/view pending repair tickets;
- inspect ticket evidence and scope;
- approve one ticket;
- reject/cancel one ticket;
- inspect execution state;
- inspect provider-call allowance;
- inspect final Re-QA result;
- retry/resume only where the persisted state makes that safe.

A minimal API/service surface is sufficient for Phase 5 closure.

A polished redesign of the entire ArcReel UI is not required.

### 2.10 Project-scale orchestration boundary

Phase 5 must support multiple independent Repair Tickets across a project without losing
isolation.

Required:

- tickets can coexist for multiple Units;
- work can be queued independently;
- one failed ticket does not corrupt another Unit;
- per-ticket state is queryable;
- concurrency cannot duplicate execution of the same ticket.

Phase 5 does **not** require autonomous regeneration of all 240 shots in one button press.

---

## 3. Non-goals

The following are explicitly outside Phase 5.

### 3.1 No second Repair Policy

Do not create:

- a second `H3FailureClass`;
- a second routing matrix;
- a second repair planner;
- UI-side repair decisions;
- provider-specific shadow policy.

The only repair decision authority remains:

`plan_h3_media_repair()`

### 3.2 No new speculative Media QA

Phase 5 does not introduce generic:

- OCR;
- ASR;
- face recognition;
- identity embeddings;
- semantic scene classifiers;
- hallucination detectors;
- "AI judge" scoring.

Trusted new QA contracts belong in a separately defined future phase or separately
accepted scope.

### 3.3 No implicit paid provider calls

Forbidden:

- automatic repair call immediately after Media QA;
- automatic resubmission after timeout;
- automatic second attempt after a provider-quality failure;
- using CI artifact expiry as justification for a fresh supplier call;
- background paid calls without an explicit approval contract.

### 3.4 No whole-Unit regeneration for shot-scoped failures

A shot-scoped Repair Ticket may not silently become a whole-Unit regeneration request.

Any scope expansion requires a new finding/ticket/approval.

### 3.5 No re-opening Phase 1–4

The six representative Units remain closed regression baselines:

```text
E12U06
E4U02
E13U01
E13U03
E11U02
E15U03
```

Use retained evidence for regression. Do not repeat their paid supplier validation simply
to prove old phases again.

### 3.6 No new provider transport stack

Phase 5 must reuse ArcReel's existing generation backend, queue, checkpoint, artifact, and
version-management infrastructure.

### 3.7 No autonomous publishing/release pipeline

Phase 5 ends at a safely accepted formal repaired media artifact.

Automatic episode packaging, release scheduling, publishing, distribution, and analytics
are not Phase 5 goals.

### 3.8 No full production dashboard requirement

A minimal inspect/approve/status surface is required.

A comprehensive studio dashboard, cost analytics suite, or season-wide planning UI is a
future product phase unless independently approved.

---

## 4. Architecture invariants

Phase 5 must preserve these invariants from earlier phases.

1. Canonical Shot IR remains the factual authority.
2. Prompt is a compiled execution artifact, not the source of truth.
3. Preview/Runtime Provider Prompt SHA lock remains mandatory.
4. Phase 4 Media QA schema remains the structured finding boundary.
5. `H3FailureClass` remains the failure taxonomy.
6. `plan_h3_media_repair()` remains the only repair policy.
7. Deterministic Phase 4 repair paths remain unchanged unless a demonstrated regression
   requires a separately accepted fix.
8. Provider-required failures remain history-only until a newly repaired candidate passes
   Re-QA.
9. Approval cannot bypass Media QA.
10. Provider completion cannot directly select current media.
11. A stale source SHA invalidates approval before provider execution.
12. A duplicate execution identity cannot spend twice.
13. UNKNOWN never receives automatic provider repair.
14. Evidence must distinguish tested code SHA from later docs-only commits.

---

## 5. Required implementation slices

Phase 5 implementation should proceed in this order.

### Slice 1 — Persistent Repair Ticket Store

Deliver:

- persistence schema/model;
- repository/service methods;
- lifecycle transition validator;
- immutable ticket identity preservation;
- migration;
- unit tests.

### Slice 2 — Approval Service

Deliver:

- approve/reject/cancel operations;
- approval binding validation;
- stale-ticket invalidation;
- idempotent duplicate approval handling;
- audit fields;
- tests.

### Slice 3 — Repair Queue / Execution Claim

Deliver:

- queue task type;
- atomic ticket claim;
- execution identity;
- call allowance guard;
- checkpoint before paid submission;
- concurrency/idempotency tests.

### Slice 4 — Provider Repair Runtime

Deliver:

- adapter from persisted ticket to the existing
  `execute_h3_shot_scoped_provider_repair()`;
- existing provider backend integration;
- resume from stored provider task identity;
- no automatic resubmit;
- deterministic shot reassembly.

### Slice 5 — Re-QA / Formal Selection

Deliver:

- invoke trusted Phase 4 runtime gate on repaired media;
- accept only PASS;
- history-only archive on failure;
- bounded creation of a new ticket when the existing planner requires provider repair;
- no approval inheritance.

### Slice 6 — Operator/API Surface

Deliver minimal:

- pending ticket query;
- ticket detail;
- approve;
- reject/cancel;
- execution status;
- repair result / Re-QA result.

UI may be minimal but must show:

- Unit;
- Shot;
- failure class;
- repair action;
- time range;
- Prompt/Reference provenance;
- provider-call allowance;
- current lifecycle state.

### Slice 7 — Phase 5 Evidence / Acceptance

Deliver:

- production lifecycle E2E;
- interruption/resume E2E;
- stale approval negative test;
- duplicate execution negative test;
- multi-ticket project isolation test;
- full subsystem regression;
- formal master acceptance;
- Phase 5 final handoff.

---

## 6. Required acceptance scenarios

Phase 5 cannot close until all scenarios below pass.

### AC-01 — Ticket persistence round trip

Create a real Phase 4 Repair Ticket, persist it, reload it, and prove immutable identity
fields are byte-for-byte/field-for-field preserved.

PASS requires:

- ticket ID unchanged;
- ticket SHA unchanged;
- source SHA unchanged;
- shot/time scope unchanged;
- Prompt/Reference SHA unchanged;
- failure/action unchanged.

### AC-02 — Explicit approval binding

Approve one shot ticket.

PASS requires the approval to be accepted only when:

- ticket ID matches;
- ticket SHA matches;
- source SHA matches;
- shot ID matches;
- approved action matches;
- allowance is positive and within policy.

Every mutated binding must fail before provider submission.

### AC-03 — Stale source rejection

Create approval, then change source media/version.

PASS requires:

```text
provider submissions = 0
ticket state = blocked/expired/review-required
```

### AC-04 — Exactly-once execution

Deliver the same approved queue task twice or execute concurrently.

PASS requires:

```text
paid provider submissions = 1
provider task identity = 1 persisted identity
formal repair execution = single logical attempt
```

### AC-05 — Interrupted provider resume

Simulate interruption after the supplier task identity is persisted but before download or
formal completion.

PASS requires the resumed worker to continue from persisted provider state and **not**
submit a second provider generation.

### AC-06 — Shot-scope enforcement

Use an approved shot-scoped ticket.

PASS requires:

- provider request represents only the approved shot;
- deterministic assembly only replaces the authorized Unit window;
- surrounding accepted picture remains unchanged;
- source/current artifact lineage is preserved.

### AC-07 — Re-QA success path

Use an existing accepted provider shot/result as a replay fixture.

PASS requires:

```text
approved ticket
→ one controlled repair execution
→ reassembly
→ Re-QA PASS
→ formal selection
```

No fresh paid provider call is required for this acceptance; a SHA-pinned historical
provider result may drive the injected provider runner.

### AC-08 — Re-QA failure path

Feed a provider repair result that still violates Canonical.

PASS requires:

- repaired candidate remains history-only;
- it is not selected current;
- deterministic repair may run only if the existing planner chooses it;
- provider-required recurrence creates a new ticket;
- the previous approval is not reused;
- no infinite retry.

### AC-09 — Multi-shot independence

Use E13U03-style two-shot failure.

PASS requires:

- two tickets;
- two lifecycle states;
- independent approvals;
- independent execution identities;
- one ticket may pass while the other remains pending/failed;
- no whole-Unit blind regeneration.

### AC-10 — Dialogue / identity controlled repair routing

Use Phase 4 closed routing fixtures.

Required routes:

```text
DIALOGUE_VISUALIZATION
→ RECOMPILE_DIALOGUE_DETACHED

IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
```

PASS requires these routes to enter approval-bound execution without changing the planner.

No paid provider call is required if historical provider evidence is available.

### AC-11 — UNKNOWN remains fail-closed

An UNKNOWN / unresolved finding must never be approval-eligible for automatic provider
repair.

PASS requires:

```text
provider submissions = 0
state = human_review_required
```

### AC-12 — Budget / allowance exhaustion

After the allowed provider call is consumed, replay/retry/duplicate API requests must not
submit another paid generation.

PASS requires:

```text
second automatic provider submission = impossible
```

### AC-13 — Project isolation

Run multiple tickets across at least two Units.

PASS requires:

- state isolation;
- execution isolation;
- artifact isolation;
- no cross-Unit Prompt/Reference/source SHA leakage.

### AC-14 — Existing Phase 4 regressions remain green

At minimum retain:

- Phase 3 repair planner regression;
- six representative Unit regression;
- Phase 4 runtime/ticket regression;
- H3 Compiler / Preview Runtime Lock;
- Reference Video / H3 subsystem;
- compile;
- Ruff.

### AC-15 — Phase 5 Master Gate

Phase 5 closes only when one master workflow depends on all required software/E2E gates and
produces a master acceptance artifact containing:

- tested code SHA;
- final status;
- provider submissions performed during acceptance;
- explicitly approved live calls, if any;
- ticket lifecycle evidence artifact IDs/digests;
- interruption/resume evidence;
- stale-approval negative evidence;
- multi-ticket isolation evidence.

The master gate must not label Phase 5 CLOSED before every required dependency succeeds.

---

## 7. Provider-spend policy for Phase 5 acceptance

Default acceptance strategy:

```text
historical SHA-pinned provider evidence
+ injected/replay provider runner
+ real queue/persistence/assembly/Re-QA code
```

This is sufficient to validate orchestration semantics because live MiniMax generation was
already validated in earlier phases.

A fresh paid MiniMax call is **not** an automatic Phase 5 requirement.

If a live repair call is later desired, it must be separately and explicitly authorized,
and its approval must itself pass the Phase 5 lifecycle.

CI must never receive provider credentials merely to make the normal Phase 5 test suite
green.

---

## 8. Suggested representative acceptance set

Use existing closed evidence wherever possible.

Primary:

- **E12U06** — large semantic failure → approved shot regeneration lifecycle.
- **E13U03** — two independent tickets; identity bridge + semantic shot repair.
- **E4U02** — dialogue-detached and identity-controlled routing.
- **E13U01** — prove deterministic repairs bypass provider orchestration and still use the
  Phase 4 path.
- **E11U02 / E15U03** — regression-only; must not be reopened for paid tests.

This set exercises both sides of the system:

```text
deterministic repair
vs.
approval-bound provider repair
```

---

## 9. Closure definition

Phase 5 is CLOSED only when all of the following are true:

1. Repair Tickets are persisted with explicit lifecycle states.
2. Approval is immutable and scope-bound.
3. Stale approvals fail before supplier spend.
4. Duplicate execution cannot cause duplicate supplier spend.
5. Interrupted supplier execution resumes without blind resubmit.
6. Provider repair remains shot-scoped.
7. Reassembly is deterministic and scope-safe.
8. Re-QA is mandatory before formal selection.
9. Failed repaired media remains history-only.
10. New provider-required failures require new tickets/approvals.
11. UNKNOWN remains human-review-only.
12. Budget/call allowance is enforceable.
13. Multi-ticket project execution is isolated.
14. Phase 1–4 regression gates remain green.
15. Phase 5 master gate and acceptance artifacts are successful.
16. Tested code SHA is recorded separately from later documentation-only commits.

Until all sixteen conditions are proven:

**Phase 5 remains IN PROGRESS.**

---

## 10. Initial branch / working-name convention

The implementation branch should be:

`phase5/h3-production-orchestration`

Initial status immediately after branch creation:

`Phase 5 = DEFINED / READY TO START`

The first implementation slice on that branch is:

**Persistent Repair Ticket Store**

Do not begin by modifying the planner or by adding new Media QA.
