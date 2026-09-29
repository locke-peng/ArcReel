# ArcReel × MiniMax H3 — Phase 6 Charter — 2026-09-28

## 0. Formal declaration

Phase 6 is formally defined as:

**Phase 6 — Production Control Plane & Studio Operations**

Status at creation:

`DEFINED / NOT STARTED`

Phase 1–5 remain CLOSED.

Phase 6 starts from the Phase 5 final documentation HEAD.

The authoritative Phase 5 tested code remains:

`615a54c1019f532642ede5b19d8d5da6ee7d8627`

Phase 5 master acceptance:

- workflow: `H3 Phase 5 Master Acceptance`
- run: `36442253421`
- job: `108995453521`
- result: `SUCCESS`
- master regression total: `136 passed`
- artifact: `10979242103`

Phase 6 must consume the Phase 5 production orchestration as an accepted subsystem. It must not replace or fork the repair policy, approval model, repair queue, provider runtime, Re-QA gate, or formal-selection contract.

---

## 1. Mission

Turn the Phase 5 per-ticket production lifecycle into a project-scale **production control plane** that lets an operator understand and safely coordinate an entire ArcReel production.

Phase 5 already answers:

```text
What Repair Ticket exists?
Is it approved?
Can this provider repair spend exactly once?
Can it resume safely?
Did the repaired shot pass Re-QA?
What artifact became current?
```

Phase 6 must answer:

```text
What is the state of the whole project / episode / Unit fleet?
Which work is blocked, ready, running, accepted, or requires human action?
How much approved provider budget has been reserved / spent / blocked?
Can operators safely coordinate many independent tickets without changing ticket semantics?
Can the studio inspect lineage and evidence across episodes and Units?
Can a batch action remain a collection of individually valid, immutable operations?
Can the production state be reconstructed after process restart?
```

The Phase 6 control-plane loop is:

```text
Canonical project / episode / Unit inventory
→ production-state projection
→ readiness / blocking view
→ operator batch selection
→ per-ticket validation / approval boundary
→ existing Phase 5 queue/runtime
→ cost + execution projection
→ accepted/rejected result projection
→ evidence / audit bundle
```

The control plane coordinates existing primitives. It does not become a second source of truth.

---

## 2. Scope

### 2.1 Project / episode / Unit production-state projection

Add a persisted or deterministically rebuildable projection that summarizes production state without mutating the underlying Phase 5 lifecycle semantics.

Minimum dimensions:

- project;
- episode;
- Unit;
- shot;
- Repair Ticket;
- execution task;
- provider-call allowance;
- Re-QA state;
- formal/current media state;
- human-review state.

Required aggregate states must be derived from authoritative underlying records rather than stored as an independent policy truth.

At minimum the projection must distinguish:

```text
not_started
ready
awaiting_approval
queued
running
blocked
human_review_required
accepted
failed_history_only
complete
```

### 2.2 Readiness and dependency model

Phase 6 must expose why work can or cannot proceed.

Examples:

- missing accepted source artifact;
- pending Repair Ticket approval;
- provider-call budget exhausted;
- active execution already owns the ticket;
- Re-QA still pending;
- human review required;
- upstream Unit/shot state not yet acceptable.

Readiness is descriptive. It may not invent a new repair decision.

### 2.3 Safe batch operations

Support operator-selected multi-ticket operations while preserving per-ticket invariants.

Required:

- select multiple existing tickets;
- preview the exact intended action set;
- validate every ticket against current facts;
- approve/reject/cancel as independent immutable ticket operations;
- enqueue eligible approved tickets;
- report partial success/failure per ticket;
- never collapse multiple tickets into one provider repair identity;
- never expand shot scope implicitly.

A batch is a coordination envelope, not a new approval primitive.

### 2.4 Capacity and concurrency control

Add project-level operational controls over the existing queue.

Required controls may include:

- maximum concurrently running repair tasks;
- per-project queue pause/resume;
- provider-specific concurrency caps when the existing backend exposes provider identity;
- fair scheduling across Units/projects;
- visibility into queued/running capacity.

This layer must reuse the accepted Phase 5 queue/execution claim. It must not introduce a second competing repair queue.

### 2.5 Budget and cost ledger

Expose a production-facing ledger around the accepted provider-call allowance boundary.

Minimum records:

- project;
- ticket;
- execution identity;
- provider/model;
- allowed call count;
- reserved call count;
- completed call count;
- blocked/exhausted state;
- known provider cost when ArcReel has authoritative cost data;
- unknown/unpriced state when authoritative cost data is unavailable.

Rules:

- cost must never be fabricated from assumptions;
- allowance reservation remains the pre-spend safety boundary;
- dashboard projections cannot bypass provider-call ceilings;
- project/episode budget policy must fail closed before spend where configured.

### 2.6 Studio operator API

Expose project-scale read and coordination operations.

At minimum:

- project production summary;
- episode summary;
- Unit summary;
- blockers;
- pending approvals;
- active executions;
- human-review queue;
- budget/call ledger;
- batch preview;
- batch approve/reject/cancel;
- batch enqueue for already approved tickets;
- evidence lookup.

All write endpoints must call existing domain services. Router/UI code may not implement repair policy.

### 2.7 Studio dashboard

Provide a focused production dashboard sufficient to operate the control plane.

Required views:

- project overview;
- episode/Unit progress;
- pending approvals;
- active/running repairs;
- human-review-required items;
- budget/call usage;
- accepted vs history-only outputs;
- ticket/execution evidence drill-down.

The dashboard is an operator surface over server-side authoritative facts.

### 2.8 Evidence and audit export

A project-scale acceptance/audit bundle must reconstruct:

```text
project
→ episode / Unit / shot
→ source artifact
→ QA finding
→ Repair Ticket
→ approval
→ queue/execution identity
→ provider checkpoint/result when applicable
→ repaired/reassembled candidate
→ Re-QA
→ formal selection or history-only rejection
→ cost/call ledger facts
```

Evidence must retain immutable hashes and the final tested code SHA.

### 2.9 Restart / rebuild behavior

Project production state must survive service restart.

If an aggregate projection is materialized, it must be rebuildable from authoritative persisted records or protected by consistency checks.

A restart must not:

- duplicate provider spend;
- convert history-only artifacts to formal;
- lose human-review-required state;
- lose budget reservations;
- turn stale approvals valid again.

### 2.10 Project-scale representative acceptance

Acceptance must exercise multiple episodes/Units and simultaneous states.

Use the existing closed H3 representative Units as regression fixtures where useful:

```text
E12U06
E4U02
E13U01
E13U03
E11U02
E15U03
```

Do not reopen their paid provider validation.

---

## 3. Non-goals

### 3.1 No second Repair Policy

Forbidden:

- second `H3FailureClass`;
- second repair routing table;
- second repair planner;
- dashboard-side repair classification;
- batch-specific shadow repair policy.

The only repair decision authority remains:

`plan_h3_media_repair()`

### 3.2 No speculative new Media QA

Phase 6 does not add generic OCR, ASR, face recognition, embeddings, semantic judges, or hallucination scoring unless separately chartered and accepted.

### 3.3 No automatic paid repair

A dashboard, batch operation, scheduler, or background process may not implicitly create a paid provider submission.

Existing explicit approval and allowance rules remain mandatory.

### 3.4 No second queue / provider transport stack

Phase 6 must coordinate the existing Phase 5 queue and ArcReel generation backend.

It may add scheduling policy around admission/capacity, but it may not create an unrelated execution queue or MiniMax client.

### 3.5 No approval weakening

Batch operations cannot weaken approval binding.

Each provider-required Repair Ticket remains individually bound to its immutable approval facts.

### 3.6 No autonomous whole-season regeneration

Phase 6 is not permission to regenerate all 240 shots automatically.

The control plane may coordinate explicitly selected eligible work, but it must preserve shot/ticket scope and spend boundaries.

### 3.7 No publishing / distribution

Out of scope:

- release scheduling;
- social-platform publishing;
- CDN distribution;
- audience analytics;
- marketing automation;
- monetization reporting.

These require a separately defined future phase.

### 3.8 No canonical rewrite from operational state

Control-plane state cannot rewrite Canonical Shot IR.

Canonical Shot IR remains the factual authority.

---

## 4. Architecture invariants

Phase 6 must preserve all accepted Phase 1–5 invariants, including:

1. Canonical Shot IR is the factual authority.
2. Provider Prompt is a compiled execution artifact.
3. Preview/runtime Prompt SHA lock remains mandatory.
4. Phase 4 Media QA remains the structured QA boundary.
5. `H3FailureClass` remains the failure taxonomy.
6. `plan_h3_media_repair()` remains the only repair policy.
7. Phase 5 Repair Ticket is the provider-repair scope primitive.
8. Approval remains immutable and scope-bound.
9. Stale approval blocks before spend.
10. Provider-call allowance is reserved before submission.
11. Duplicate execution cannot duplicate spend.
12. Resume uses persisted provider identity/checkpoint.
13. Re-QA is mandatory before formal selection.
14. Failed candidates remain history-only.
15. UNKNOWN remains human-review-only.
16. Project isolation remains mandatory.
17. Batch operations decompose into valid per-ticket domain operations.
18. UI/API projections are not sources of repair truth.
19. Tested code SHA must be recorded separately from later documentation-only commits.

---

## 5. Required implementation slices

### Slice 1 — Production State Projection

Deliver:

- project/episode/Unit aggregate schema;
- deterministic projection service;
- blocker/readiness derivation;
- rebuild/idempotency tests.

Acceptance focus:

- projection agrees with underlying Phase 5 ticket/execution/formal-media state;
- no new policy authority is introduced.

### Slice 2 — Batch Coordination Contract

Deliver:

- batch preview;
- per-ticket validation;
- batch approve/reject/cancel;
- batch enqueue;
- partial-result reporting.

Acceptance focus:

- individual ticket invariants survive batch operation;
- stale or ineligible items fail independently;
- no scope merge and no implicit provider call.

### Slice 3 — Capacity / Scheduling Control

Deliver:

- project concurrency cap;
- pause/resume admission;
- safe fair scheduling policy over existing queue;
- restart-safe scheduling state.

Acceptance focus:

- no duplicate claim;
- no provider replay;
- no second repair queue.

### Slice 4 — Budget / Cost Ledger

Deliver:

- project/episode/ticket call ledger;
- reservation/completion/blocking views;
- configured budget gate where authoritative cost/call data is available;
- unknown-cost explicit state.

Acceptance focus:

- budget exhaustion blocks before spend;
- ledger reconciles with Phase 5 provider-call records.

### Slice 5 — Studio Operator API

Deliver project-scale read/write endpoints backed by domain services.

Acceptance focus:

- authenticated actor propagation;
- no raw internal checkpoint leakage;
- server-side validation remains authoritative.

### Slice 6 — Studio Dashboard

Deliver the focused operational UI over the accepted API.

Acceptance focus:

- accurate project/episode/Unit states;
- explicit pending approval/human review/budget visibility;
- no client-side repair decisions.

### Slice 7 — Resilience / Evidence / Master Acceptance

Deliver:

- restart/rebuild test;
- concurrent multi-project/multi-Unit test;
- partial batch failure test;
- budget exhaustion test;
- stale approval inside batch test;
- evidence export test;
- Phase 1–5 regression gate;
- Phase 6 master acceptance artifact.

---

## 6. Acceptance criteria

Phase 6 is CLOSED only when all of the following are proven:

1. Project/episode/Unit production state is derivable from authoritative persisted records.
2. Projection rebuild is deterministic and restart-safe.
3. Readiness/blockers are descriptive and cannot bypass repair policy.
4. Batch preview reports exact per-ticket intended operations.
5. Batch approval preserves individual immutable approval bindings.
6. Partial batch failure does not corrupt successful independent tickets.
7. Batch enqueue cannot duplicate task/execution identities.
8. Project concurrency limits are enforceable.
9. Pause/resume affects admission without corrupting running work.
10. Scheduling uses the existing Phase 5 queue rather than a second queue.
11. Budget/call ledger reconciles with provider allowance records.
12. Configured budget exhaustion blocks before provider spend.
13. Studio API delegates writes to accepted domain services.
14. Dashboard renders authoritative server facts and contains no repair policy.
15. Human-review-required work is clearly isolated from automatic execution.
16. Evidence export reconstructs end-to-end lineage.
17. Multi-project isolation remains intact.
18. No live paid provider call is required for CI acceptance.
19. Phase 1–5 regression gates remain green.
20. Phase 6 master gate and artifacts pass.
21. Final tested code SHA is recorded separately from documentation-only closure commits.

Until all twenty-one conditions are proven:

**Phase 6 remains IN PROGRESS.**

---

## 7. Provider-call policy for Phase 6

Default Phase 6 development and CI:

`LIVE / PAID MINIMAX CALLS = FORBIDDEN`

Use:

- deterministic fakes;
- persisted historical provider evidence;
- existing closed Phase 3–5 acceptance evidence;
- contract/integration/E2E tests around the provider boundary.

Any new live supplier validation must be explicitly approved as a separate acceptance action and must never be triggered automatically by CI.

---

## 8. Branch convention

Implementation branch:

`phase6/h3-production-control-plane`

Initial Phase 6 status after branch creation:

`DEFINED / READY TO START`

The first implementation slice is:

**Slice 1 — Production State Projection**

Do not begin Phase 6 by changing the repair planner, failure taxonomy, Media QA classifier, MiniMax transport, or formal-selection rules.
