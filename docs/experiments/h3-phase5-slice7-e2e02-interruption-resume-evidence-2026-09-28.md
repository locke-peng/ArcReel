# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-02 Interruption / Resume Evidence — 2026-09-28

## Verdict

**E2E-02 — INTERRUPTION / RESUME = PASS**

This evidence proves that a Phase 5 H3 provider-repair execution can survive an abrupt worker/process interruption after durable provider submission state exists, then resume the exact same provider job without a second provider submission, without consuming a second provider-call allowance, and without creating a new Repair Ticket, task, or execution identity.

This is Slice 7 evidence. It does not close Slice 7 or Phase 5 by itself.

No live or paid MiniMax request was performed.

---

## 1. Tested repository state

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 6 CLOSED base:

`d1ac863dcbd52b5c1fdf99ae773b9cafd94f6b16`

Final tested E2E-02 SHA:

`0134a6ecef6beb19aa1f109c74e55a70f8d5d5b0`

Dedicated Slice 7 PR:

`#14 ci: validate Phase 5 Slice 7 production lifecycle evidence`

Dedicated workflow:

`.github/workflows/h3-phase5-slice7-e2e02.yml`

E2E source:

`tests/e2e/reference_video/test_h3_phase5_interruption_resume_e2e.py`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 5 Slice 7 E2E-02`

Run:

`36436812060`

Job:

`108976752731 interruption-resume-e2e`

Result:

```text
SUCCESS
1 passed, 1 warning
```

The workflow separately validates the machine-readable evidence JSON after pytest passes.

---

## 3. Uploaded machine-readable artifact

Artifact ID:

`10975986687`

Artifact name:

`h3-phase5-slice7-e2e02-0134a6ecef6beb19aa1f109c74e55a70f8d5d5b0`

Artifact digest:

`sha256:426170185b7ddfeb4fdb0cdd5b9e4e5fc31c47e2818dd83881acf23e2178fa2c`

Artifact size:

`779 bytes`

Retention expiry:

`2026-10-28T14:34:04Z`

Contained evidence file:

`e2e02-interruption-resume.json`

---

## 4. Interruption model

E2E-02 uses the real fresh-submit and resume branches in
`server/services/h3_repair_tasks.py`.

The first execution enters the real fresh path:

```text
execute_h3_repair_task()
→ _provider_shot_from_fresh_submission()
→ before_submit()
→ H3RepairQueueService.reserve_provider_submission()
→ immutable execution checkpoint persisted
→ provider-call allowance consumed
→ on_provider_job_id()
→ provider job identity persisted
```

Immediately after the durable provider job identity is persisted, the deterministic provider double raises a test-only `BaseException` subclass to model abrupt process death.

The use of `BaseException` is intentional. The production runtime catches ordinary `Exception` and fails closed to human review; a real hard process termination does not run that application-level exception handler. The test therefore models the durable state left by process death without patching private production recovery functions.

The interrupted ticket remains:

`RUNNING`

with checkpoint, provider job identity, and consumed allowance already persisted.

---

## 5. Recovery path

The second execution calls the same public production entry point again:

`execute_h3_repair_task(existing_task)`

The runtime reloads the persisted task and detects:

- `execution_checkpoint_json != NULL`;
- `provider_job_id != NULL`.

It then enters the real resume branch:

```text
H3RepairSubmissionCheckpoint.from_json()
→ H3RepairQueueService.reserve_provider_submission()
→ RESUME_ONLY
→ _provider_shot_from_resume()
→ generator.resume_video_async(existing_job_id)
```

No second `generate_video_async()` call is allowed by the deterministic provider double.

---

## 6. Identity continuity evidence

Ticket ID before:

`h3rt_f2091f157e597ab9af15736b`

Ticket ID after:

`h3rt_f2091f157e597ab9af15736b`

New ticket created:

`false`

Task ID before:

`f1081737038a4386a596a0ef1cb06a0c`

Task ID after:

`f1081737038a4386a596a0ef1cb06a0c`

New task created:

`false`

Execution identity before:

`h3rx_566a916cb55819e10e060250`

Execution identity after:

`h3rx_566a916cb55819e10e060250`

New execution identity:

`false`

Provider job ID before:

`provider-job-e2e02`

Provider job ID after:

`provider-job-e2e02`

Checkpoint stable across recovery:

`true`

This proves restart recovery continues the same durable execution rather than creating a parallel execution.

---

## 7. Provider-call allowance evidence

Fresh provider submission calls:

`1`

Resume calls:

`1`

Persisted provider-call count after recovery:

`1`

Paid MiniMax calls:

`0`

The recovery path therefore does not consume a second provider-call allowance.

---

## 8. Lifecycle evidence

The machine-readable artifact records:

```text
awaiting_approval
→ approved
→ queued
→ running
→ [hard process interruption]
→ provider_completed
→ reassembling
→ reqa_running
→ accepted
```

The interruption itself is not persisted as a new lifecycle state; the durable ticket correctly remains `running` until the existing provider job is resumed.

Evidence field:

`interrupted_lifecycle_state = "running"`

Recovery field:

`resumed_existing_job = true`

---

## 9. Re-QA and selection evidence

After resume completes, the repaired provider shot flows through the same deterministic reassembly and mandatory Slice 5 Re-QA path used by E2E-01.

Re-QA outcome:

`PASS`

Selected current:

`true`

Selected artifact:

`reference_videos/E12U06.mp4`

Selected version:

`reference_videos:E12U06:v2`

Source version:

`v1`

Final selected version:

`v2`

This proves interruption/resume does not bypass mandatory Re-QA or formal selection.

---

## 10. Static / test-hygiene evidence

The final tested SHA was checked by the repository-wide gates.

### test-lint

Slice 7 adds no new test-lint violation.

The gate reports only the existing five historical violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

### workflow-static

Both Slice 7 workflows are audited without a Slice 7 finding:

- `.github/workflows/h3-phase5-slice7-e2e.yml`;
- `.github/workflows/h3-phase5-slice7-e2e02.yml`.

The remaining workflow-static failure is the historical unpinned action in:

`.github/workflows/h3-e4u02-v4-dialogue-detached-live.yml`

### backend-static

Both Slice 7 E2E files are collected by backend-static and no longer appear as Ruff error sources.

The earlier E2E import-order findings were fixed using the exact Ruff-generated normalization diff before this final acceptance run.

---

## 11. E2E-02 acceptance checklist

- persisted Repair Ticket reused: PASS
- same ticket ID after restart: PASS
- same shared task after restart: PASS
- same execution identity after restart: PASS
- same provider job identity after restart: PASS
- immutable checkpoint remains stable: PASS
- first provider submission count = 1: PASS
- resume count = 1: PASS
- no second fresh provider submit: PASS
- provider-call count remains 1: PASS
- no new Repair Ticket: PASS
- no new execution task: PASS
- no new execution identity: PASS
- interrupted lifecycle remains RUNNING: PASS
- existing provider job resumed: PASS
- deterministic reassembly completes: PASS
- mandatory Re-QA still runs: PASS
- Re-QA outcome = PASS: PASS
- repaired artifact selected current: PASS
- current version advances v1 → v2: PASS
- final ticket lifecycle = ACCEPTED: PASS
- paid MiniMax calls: 0

**E2E-02 = PASS**

---

## 12. Next Slice 7 evidence

With E2E-01 and E2E-02 locked, the next required negative evidence is:

**E2E-03 — Stale Approval Rejection**

It must prove that a Repair Ticket approved against one source/provenance snapshot cannot spend provider allowance or enter provider execution after the authoritative source facts change.
