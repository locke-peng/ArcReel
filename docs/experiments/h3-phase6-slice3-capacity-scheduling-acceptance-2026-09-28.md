# ArcReel × MiniMax H3 — Phase 6 Slice 3 Capacity / Scheduling Acceptance — 2026-09-28

## Verdict

**PHASE 6 SLICE 3 — CAPACITY / SCHEDULING CONTROL = PASS / CLOSED**

Phase 6 remains IN PROGRESS.

---

## 1. Tested state

Repository:

`locke-peng/ArcReel`

Branch:

`phase6/h3-production-control-plane`

Tested SHA:

`6636886f2b9490502049430b585bbc9a5e7fd28c`

Draft PR:

`#15 feat: begin Phase 6 production control plane`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 6 Slice 3 Capacity Control`

Run:

`36447626951`

Job:

`109013916682 capacity-control`

Result:

`SUCCESS`

Test result:

```text
16 passed, 1 warning in 7.51s
```

Alembic result:

```text
c6e2a91f4b70 (head)
```

No live or paid MiniMax call was used.

---

## 3. Accepted architecture

Slice 3 does not create a second scheduler or repair queue.

The accepted path remains:

```text
Phase 5 H3 Repair Queue
→ H3RepairQueueService.claim_next()
→ GenerationWorker._claim_h3_repair_task()
→ existing worker lease
→ existing SlotTable
→ existing task execution / provider runtime
```

Phase 6 adds only project-level **admission controls** before the existing atomic claim.

---

## 4. Persisted project control

New table:

`h3_repair_project_control`

Fields:

- `project_name`
- `paused`
- `max_running_tasks`
- timestamps

Semantics:

- no row = admission enabled + no project-specific cap;
- `paused=true` = queued H3 repair work remains queued and cannot be freshly claimed;
- `max_running_tasks=N` = no more than N H3 repair tasks from that project may be running simultaneously.

The control record is not an execution state machine and does not replace Repair Ticket lifecycle state.

---

## 5. Alembic

Migration:

`alembic/versions/c6e2a91f4b70_add_h3_repair_project_control.py`

Down revision:

`9b31d4f7c2aa`

The final acceptance gate proves exactly one Alembic head:

`c6e2a91f4b70`

---

## 6. Atomic admission

Pause and project capacity are enforced inside the candidate query of the existing:

`H3RepairQueueService.claim_next()`

This is important because admission is evaluated **before** the ticket/task atomically transition to RUNNING.

The implementation does not:

- claim then requeue due to project cap;
- create a shadow scheduling queue;
- create a second execution identity;
- weaken the Phase 5 atomic claim.

---

## 7. Pause / resume behavior

Acceptance proves:

```text
project A paused
project B enabled

claim_next()
→ project B may be claimed
→ project A remains QUEUED
→ project A task remains queued
```

After a later persisted `paused=false` update, a new session can claim project A.

Running work is not retroactively corrupted by pause.

Pause controls fresh admission only.

---

## 8. Project running-task cap

Acceptance proves:

```text
project cap = 1

ticket A → claimed / RUNNING
ticket B → remains QUEUED
second claim → None

ticket A releases running capacity

next claim
→ ticket B can be claimed
```

The cap is derived against the existing shared `tasks` table and H3 task type.

No provider-call allowance semantics are changed.

---

## 9. Fair scheduling

Eligible H3 repair candidates are ordered by:

1. project current running H3 repair count;
2. task queued time;
3. task ID.

Therefore a project with fewer currently running repairs is preferred over a project already occupying more repair capacity.

Acceptance proves:

```text
project A: one running + another queued
project B: zero running + one queued

next claim
→ project B
```

This provides project-level fairness without a new scheduler.

---

## 10. Restart safety

Project controls are persisted in the database.

Acceptance proves that after closing the original session and creating a new one:

- pause remains active;
- running cap remains configured;
- admission still honors both values;
- resume persists and is honored by a later session.

There is no in-memory-only scheduling truth required for project controls.

---

## 11. Existing worker architecture preserved

H3 repairs still run through:

- the existing GenerationWorker lease;
- the existing SlotTable;
- the existing task table;
- the existing H3 Repair Queue atomic claim;
- the existing provider execution path;
- the existing interruption/resume logic.

No second worker or H3 scheduler was introduced.

---

## 12. Phase invariants preserved

Slice 3 does not modify:

- `H3FailureClass`;
- `plan_h3_media_repair()`;
- Repair Ticket immutable scope;
- approval binding;
- provider-call allowance reservation;
- provider checkpoint/resume identity;
- Re-QA;
- formal selection.

Paused/capped tasks do not consume provider budget merely by waiting.

---

## 13. Slice status

```text
Phase 6                 IN PROGRESS
Slice 1 Projection      CLOSED
Slice 2 Batch Contract  CLOSED
Slice 3 Capacity        CLOSED
Slice 4 Budget Ledger   NOT STARTED
Slice 5 Operator API    NOT STARTED
Slice 6 Dashboard       NOT STARTED
Slice 7 Acceptance      NOT STARTED
```

Next implementation slice:

**Slice 4 — Budget / Cost Ledger**
