# ArcReel × MiniMax H3 — Phase 5 Slice 3 Repair Queue / Execution Claim Acceptance — 2026-09-28

## Verdict

**PHASE 5 SLICE 3 — REPAIR QUEUE / EXECUTION CLAIM = PASS / CLOSED**

This acceptance closes Slice 3 only. It does not close Phase 5.

Formal stage state after this acceptance:

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  CLOSED
Phase 5  IN PROGRESS
  Slice 1  CLOSED
  Slice 2  CLOSED
  Slice 3  CLOSED
  Slice 4  NOT STARTED
```

No paid MiniMax provider generation was performed for this acceptance.

---

## 1. Repository / branch / tested code

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 2 accepted base:

`cee71cc41415aef622816212495ae8663940c682`

Slice 3 implementation commit:

`3e5e81888b5c` — `feat(h3): add Phase 5 repair queue execution claim`

Final tested Slice 3 code SHA:

`dabbf7f6b1cd0d919d22856a3e1105b8e7455453`

Concurrency fix:

`dabbf7f6b1cd0d919d22856a3e1105b8e7455453` — `fix(h3): refresh allowance after concurrent reservation`

Temporary validation PR:

`#10 ci: validate Phase 5 Slice 3 repair queue`

PR base is pinned to the Slice 2 commit above. The PR exists only to run the repository
pull_request test workflow for the Slice 3 delta and is not intended to trigger live MiniMax
generation.

Primary GitHub Actions run:

`36398887966`

---

## 2. Accepted architecture

Slice 3 does not create a second generic queue. It reuses ArcReel's existing `tasks` table,
task lifecycle semantics, execution checkpoint column, and provider job identity while keeping
H3 repair work on a dedicated dormant lane until Slice 4 wires the provider runtime.

Primary implementation:

- `lib/reference_video/h3_repair_queue.py`
- `lib/db/models/h3_repair_ticket.py`
- `alembic/versions/9b31d4f7c2aa_add_h3_repair_execution_claim.py`
- `lib/generation_worker.py`
- `tests/integration/lib/reference_video/test_h3_repair_queue.py`

Accepted chain:

```text
persisted immutable Repair Ticket
→ explicit APPROVED state
→ idempotent repair enqueue
→ deterministic execution identity
→ atomic ticket + task claim
→ RUNNING
→ approval revalidation
→ provider-call allowance reservation
→ immutable pre-submit checkpoint
→ provider job identity persistence
→ resume-only after persisted provider identity
```

The provider runtime itself is deliberately not wired in Slice 3.

---

## 3. Queue and execution identity

Only an explicitly approved Repair Ticket is queueable.

The execution identity is deterministic over the immutable ticket plus approval binding and is
persisted both on the Repair Ticket lifecycle row and the shared task row.

Duplicate enqueue requests resolve to the same task and execution identity.

The database additionally enforces uniqueness for project/execution identity.

---

## 4. Atomic claim

`H3RepairQueueService.claim_next()` atomically moves one eligible repair execution from:

```text
Repair Ticket: QUEUED → RUNNING
Task:          queued → running
```

The ticket claim uses a guarded SQL UPDATE based on one queued candidate and increments the
attempt count in the same transaction. The task transition is committed only when the matching
task row can also move from queued to running.

Concurrent claim coverage proves exactly one worker receives the execution.

---

## 5. Paid-call allowance and project ceiling

Claim ownership does not authorize supplier spend.

`reserve_provider_submission()` is the paid-call boundary. It:

1. revalidates the approval against current execution facts;
2. checks per-approval `max_provider_calls`;
3. checks the optional project-wide call ceiling;
4. atomically consumes the allowance;
5. persists the immutable pre-submit checkpoint before provider submission is allowed.

Phase 5 approval permits exactly one provider-call ordinal for this execution.

Concurrent reservation coverage proves one ticket allowance is consumed once and a project-wide
ceiling cannot be overspent by two concurrent tickets.

---

## 6. Crash-window safety

The accepted fail-closed semantics are:

```text
no checkpoint
  → eligible to reserve once

checkpoint + no provider_job_id
  → RESERVED_WITHOUT_PROVIDER_ID
  → automatic resubmit forbidden

checkpoint + provider_job_id
  → RESUME_ONLY
  → resume the existing supplier job
```

A different provider identity cannot replace the immutable checkpoint.

A different provider job ID cannot replace an already persisted provider job identity.

The generic generation worker explicitly leaves orphaned H3 repair tasks to the Phase 5 repair
runtime rather than requeueing/resubmitting them.

---

## 7. PostgreSQL concurrency defect found and fixed

The first concurrent PostgreSQL run exposed a real stale-read race:

```text
worker B reads provider_call_count = 0
worker A commits allowance + checkpoint
worker B later observes the committed checkpoint
worker B incorrectly treats its earlier count snapshot as current
```

Observed failure:

`H3RepairExecutionConflict: checkpoint exists without consumed provider-call allowance`

Fix:

When a persisted checkpoint is observed, the service re-reads the mutable
`provider_call_count` directly from the database before deciding whether the state is
inconsistent.

Fix commit:

`dabbf7f6b1cd0d919d22856a3e1105b8e7455453`

---

## 8. Acceptance evidence

Run `36398887966` at tested SHA `dabbf7f6b1cd0d919d22856a3e1105b8e7455453`:

```text
postgres-compat               SUCCESS
Backend tests (integration)   SUCCESS
```

The PostgreSQL job includes the Slice 3 concurrent enqueue, atomic claim, concurrent provider
submission reservation, and concurrent project ceiling scenarios.

The full backend unit job completed:

```text
9261 passed
19 skipped
2 failed
```

The two failures are pre-existing Phase 4 ffmpeg-dependent runtime tests:

- `test_h3_audio_runtime.py::test_audio_runtime_remuxes_only_audio_and_preserves_video`
- `test_h3_exact_text_runtime.py::test_exact_text_runtime_repairs_only_video_window_and_preserves_audio`

Both fail because the unit-test runner does not provide the `ffmpeg` executable. They are not
Slice 3 queue/claim failures and no Slice 3 file is named in either failure.

The repository-wide static/lint jobs also remain red because of previously existing Phase 1–4
violations outside the Slice 3 delta. Slice 3 production files introduced no new static error in
the scoped inspection. These historical gates are intentionally not modified by this acceptance.

---

## 9. Slice 3 acceptance checklist

- queue task type: PASS
- APPROVED-only enqueue: PASS
- duplicate enqueue idempotency: PASS
- deterministic execution identity: PASS
- atomic single-winner claim: PASS
- attempt count persistence: PASS
- per-approval paid-call allowance: PASS
- project-wide call ceiling: PASS
- immutable pre-submit checkpoint: PASS
- stale approval blocks before spend: PASS
- checkpoint crash window fails closed: PASS
- provider job identity is write-once/idempotent: PASS
- resume-only after persisted provider job: PASS
- PostgreSQL concurrency: PASS
- no paid MiniMax call during acceptance: PASS

---

## 10. Next slice

The next permitted work is:

**Phase 5 Slice 4 — Provider Repair Runtime**

Slice 4 must adapt the persisted/claimed Repair Ticket into the existing
`execute_h3_shot_scoped_provider_repair()` path, use the existing provider backend, persist the
real provider task identity, resume rather than resubmit, and deterministically reassemble the
repaired shot.

Slice 4 must not weaken any Slice 3 claim, allowance, checkpoint, or crash-window guarantee.
