# ArcReel × MiniMax H3 — Phase 5 Slice 4 Provider Repair Runtime Acceptance — 2026-09-28

## Verdict

**PHASE 5 SLICE 4 — PROVIDER REPAIR RUNTIME = PASS / CLOSED**

This acceptance closes Slice 4 only. It does not close Phase 5.

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
  Slice 4  CLOSED
  Slice 5  NOT STARTED
```

No paid MiniMax provider generation was performed for this acceptance.

---

## 1. Repository / branch / tested code

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 3 CLOSED base:

`9aab8c36d11a08a0b5de521382d41635964978b5`

Final tested Slice 4 code SHA:

`5adc140dc4808209d468cf6e8d43a3721dc8ff95`

Dedicated Slice 4 validation PR:

`#11 ci: validate Phase 5 Slice 4 provider repair runtime`

PR base:

`ci/phase5-slice4-base` → `9aab8c36d11a08a0b5de521382d41635964978b5`

Primary GitHub Actions run:

`36411037931`

The validation PR exists only to run the repository pull-request workflow against the Slice 4
delta. It is a draft PR and is not intended to merge or trigger live MiniMax generation.

---

## 2. Slice 4 charter mapping

The Phase 5 charter requires Slice 4 to deliver:

1. an adapter from persisted Repair Ticket state into the existing
   `execute_h3_shot_scoped_provider_repair()` path;
2. integration with ArcReel's existing provider backend;
3. resume from persisted provider task identity;
4. no automatic resubmit;
5. deterministic shot reassembly.

All five requirements are present in the tested code.

Primary implementation:

- `lib/reference_video/h3_provider_repair_runtime.py`
- `server/services/h3_repair_tasks.py`
- `lib/reference_video/h3_repair_queue.py`
- `lib/generation_worker.py`
- `lib/media_generator.py`
- `lib/video_backends/base.py`
- `lib/resource_paths.py`

Primary acceptance tests:

- `tests/integration/server/services/test_h3_repair_tasks.py`
- `tests/integration/lib/reference_video/test_h3_repair_queue.py`
- `tests/unit/lib/reference_video/test_h3_provider_repair_runtime.py`
- `tests/unit/lib/test_resource_paths.py`

---

## 3. Accepted execution chain

The accepted Slice 4 execution chain is:

```text
persisted APPROVED Repair Ticket
→ Slice 3 queue + atomic claim
→ RUNNING
→ reload exact accepted source Unit/version
→ re-hash source media / prompt / references
→ build approved shot-scoped H3 repair request
→ freeze provider request into Slice 3 checkpoint
→ existing ArcReel provider backend
→ persist provider task identity
→ provider completion
→ execute_h3_shot_scoped_provider_repair()
→ deterministic shot-window reassembly
→ REQA_RUNNING
```

Slice 4 does not select a repair action. It consumes the existing Phase 4 repair plan and the
explicit Phase 5 approval binding.

---

## 4. Source and provider identity freeze

`resolve_h3_repair_source_version()` reloads the current accepted Unit/version and verifies:

- source media SHA;
- accepted provider prompt SHA;
- reference SHA set;
- provider ID;
- provider model;
- actual backend model;
- endpoint guard;
- execution capability;
- aspect ratio;
- resolution;
- generate-audio setting;
- service tier;
- seed.

A mismatch fails closed before a new provider submission.

Before paid submission, `H3RepairProviderRequestFacts` freezes the provider-facing execution
request into the existing H3 repair checkpoint, including:

- generation capability;
- backend model;
- endpoint guard;
- exact repair prompt and SHA;
- duration;
- aspect ratio;
- resolution;
- audio flag;
- service tier;
- seed.

Restart therefore does not reconstruct a potentially different provider request from mutable
project configuration.

---

## 5. Existing provider backend integration

Slice 4 does not introduce a new MiniMax client or provider transport.

Fresh execution uses the existing:

`resolve_generation_context() → MediaGenerator.generate_video_async()`

Resume uses the existing:

`MediaGenerator.resume_video_async()`

Provider job identity is persisted through the existing provider-job persistence seam and the
Slice 3 immutable execution record.

The provider/model/backend/endpoint identity resolved at runtime must equal the frozen checkpoint
identity or execution fails closed.

---

## 6. Exactly-once and restart semantics

Accepted fresh path:

```text
no checkpoint
→ reserve provider allowance
→ persist immutable checkpoint
→ submit once
→ persist provider_job_id
```

Accepted interruption path:

```text
checkpoint + provider_job_id
→ RESUME_ONLY
→ resume existing provider task
→ no new submit
```

Fail-closed crash window:

```text
checkpoint + no provider_job_id
→ automatic resubmit forbidden
```

This preserves Slice 3's paid-call and crash-window guarantees.

---

## 7. Shot-scope enforcement and deterministic reassembly

The provider repair prompt is projected from the previously accepted H3 provider prompt into only
the approved Canonical shot window.

The repair runtime:

- emits exactly one repair-shot request;
- preserves the approved repair action semantics;
- forbids preceding/following shot generation;
- constrains duration to the authorized shot window;
- keeps provider audio non-authoritative for shot repair;
- stores the provider repair shot in the intermediate
  `repairs/provider_shots` history bucket;
- deterministically replaces only the authorized Unit picture window;
- preserves the accepted source Unit audio;
- writes the reassembled Unit into `repairs/reassembled_units`;
- does not select the repaired artifact as formal current media.

Formal selection belongs to Slice 5 after mandatory Re-QA.

---

## 8. Cancellation behavior

A repair cancelled before provider submission:

- does not consume provider-call allowance;
- persists no checkpoint;
- persists no provider job identity;
- moves the Repair Ticket to CANCELLED.

Cancellation after provider completion is not silently discarded; the paid artifact remains
inspectable and the ticket is routed to a review-safe state.

---

## 9. Acceptance defects found and fixed

Strict acceptance found three Slice 4 defects and all were fixed before the final tested SHA.

### 9.1 Repair resource type contract drift

Adding `h3_repair_shots` to the central resource-path registry initially left the canonical
resource-path unit contract stale.

Fixed by updating the resource-path test contract to cover:

- `repairs/provider_shots/<execution_identity>.mp4`;
- `.mp4` extension;
- membership in `RESOURCE_TYPES`.

### 9.2 PostgreSQL event-loop/session-factory leak

Initial Slice 4 worker dispatch used global `safe_session_factory()` inside
`_claim_h3_repair_task()`.

In tests, GenerationWorker is wired to an injected per-test/per-event-loop queue session factory.
The global factory could therefore reuse an asyncpg connection created on a different loop,
causing widespread:

`Future ... attached to a different loop`

failures.

Fixed by using the existing injected:

`self.queue.session_factory()`

for repair claims.

This keeps H3 repair claiming on the same database/session wiring as the worker's queue.

### 9.3 Queue-stub compatibility

After the session-factory fix, lightweight worker unit-test queue stubs without a
`session_factory` attribute failed even though they do not host the H3 repair lane.

Fixed by treating a queue without a session factory as not providing the H3 repair lane and
returning `False` from the repair-claim path, preserving all pre-existing media-lane behavior.

Final tested code includes all three fixes.

---

## 10. Dedicated Slice 4 CI evidence

Dedicated PR:

`#11 ci: validate Phase 5 Slice 4 provider repair runtime`

Run:

`36411037931`

Tested SHA:

`5adc140dc4808209d468cf6e8d43a3721dc8ff95`

### PostgreSQL compatibility

```text
postgres-compat: SUCCESS
608 passed, 4 warnings
```

This run also keeps the Slice 3 concurrency guarantees green, including:

- concurrent duplicate enqueue;
- atomic single-winner claim;
- concurrent provider-submission reservation;
- concurrent project call-ceiling enforcement.

### Backend integration

```text
Backend tests (integration): SUCCESS
4476 passed, 1 skipped, 88 warnings
```

The collected suite includes the Slice 4 provider repair integration cases:

- fresh repair performs one submit and advances to `REQA_RUNNING`;
- restart with persisted provider job resumes without new submit;
- cancellation before provider spend cancels cleanly without allowance consumption.

These tests use an injected fake generator/provider path. No live MiniMax call is performed.

### Backend unit

```text
Backend tests (unit):
9266 passed
19 skipped
2 failed
```

The only two failures are pre-existing Phase 4 ffmpeg-dependent runtime tests:

- `test_h3_audio_runtime.py::test_audio_runtime_remuxes_only_audio_and_preserves_video`
- `test_h3_exact_text_runtime.py::test_exact_text_runtime_repairs_only_video_window_and_preserves_audio`

Both fail because the unit-test runner lacks the `ffmpeg` executable.

The Slice 4-specific unit regressions found during acceptance
(`resource_paths` and queue-stub worker compatibility) are fixed at the final tested SHA.

---

## 11. Static / repository lint status

The repository-wide `backend-static` job remains red because of previously existing errors
outside the Slice 4 changed production files.

Reported static-error files are in older areas such as:

- `arcreel_cli.py`;
- `lib/reference_video/h3_prompt_execution.py`;
- `lib/reference_video/h3_timeline_runtime.py`;
- `lib/video_prompt_compilers/h3_director_compiler.py`;
- `lib/video_prompt_compilers/h3_prompt_compiler.py`;
- historical experiment scripts and older tests.

No Slice 4 production file is reported as a Ruff error source in the dedicated run.

The repository `test-lint` gate also remains red for five pre-existing violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

These are outside the Slice 4 delta and were intentionally not changed during this acceptance.

---

## 12. Slice 4 acceptance checklist

- persisted-ticket adapter to existing shot repair executor: PASS
- existing provider backend integration: PASS
- frozen provider request identity: PASS
- provider job identity persistence: PASS
- fresh provider submit exactly once: PASS
- restart resumes existing provider job: PASS
- checkpoint-without-job fail-closed: PASS
- no automatic resubmit: PASS
- approved shot-only prompt projection: PASS
- deterministic shot-window reassembly: PASS
- accepted source audio preserved: PASS
- intermediate/history-only provider shot storage: PASS
- repaired Unit stops at `REQA_RUNNING`: PASS
- cancellation before spend consumes zero allowance: PASS
- PostgreSQL regression: PASS
- full backend integration regression: PASS
- Slice 4-specific unit regressions: PASS
- paid MiniMax calls during acceptance: 0

---

## 13. Next permitted slice

The next permitted work is:

**Phase 5 Slice 5 — Re-QA / Formal Selection**

Slice 5 must:

- invoke the trusted Phase 4 runtime gate on the reassembled candidate;
- select formal media only on Re-QA PASS;
- keep failed repaired candidates history-only;
- create a new ticket only when the existing planner again requires provider repair;
- never inherit the previous approval;
- preserve all Slice 3 and Slice 4 exactly-once, allowance, provider identity, and
  deterministic-reassembly guarantees.
