# ArcReel × MiniMax H3 — Phase 5 Slice 6 Operator / API Surface Acceptance — 2026-09-28

## Verdict

**PHASE 5 SLICE 6 — OPERATOR / API SURFACE = PASS / CLOSED**

This acceptance closes Slice 6 only. It does not close Phase 5.

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
  Slice 5  CLOSED
  Slice 6  CLOSED
  Slice 7  NOT STARTED
```

No paid MiniMax provider generation was performed for this acceptance.

---

## 1. Repository / branch / tested code

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 5 CLOSED base:

`efd12dcc362e861d307c6c99d835a6be60f50b13`

Final tested Slice 6 code SHA:

`f1adc6b0cc5fe4fc7c999a568a98789e8df1f13a`

Dedicated Slice 6 validation PR:

`#13 ci: validate Phase 5 Slice 6 repair operator API`

PR base:

`ci/phase5-slice6-base` → `efd12dcc362e861d307c6c99d835a6be60f50b13`

Primary GitHub Actions run:

`36419752878`

The draft PR exists only to validate the Slice 6 delta. It is not intended to merge and does not
invoke live MiniMax generation.

---

## 2. Slice 6 charter mapping

The Phase 5 charter requires a minimal operator/API surface for:

1. pending ticket query;
2. ticket detail;
3. approve;
4. reject/cancel;
5. execution status;
6. repair result / Re-QA result.

All six requirements are present in the tested code.

Primary implementation:

- `server/routers/h3_repairs.py`
- `server/services/h3_repair_operator.py`
- `server/app.py`

Primary tests:

- `tests/integration/server/routers/test_h3_repairs.py`
- `tests/unit/server/services/test_h3_repair_operator.py`

No new repair policy, approval model, queue, provider path, state machine, or formal-selection
mechanism was introduced.

---

## 3. API surface

The authenticated API is mounted under:

`/api/v1/projects/{project_name}/reference-videos/repairs`

Accepted endpoints:

```text
GET  /pending
GET  /
GET  /{ticket_id}
POST /{ticket_id}/approve
POST /{ticket_id}/reject
POST /{ticket_id}/cancel
GET  /{ticket_id}/execution
GET  /{ticket_id}/result
```

The generic list endpoint supports lifecycle-state and Unit filtering.

The dedicated `/pending` endpoint returns `AWAITING_APPROVAL` tickets only.

---

## 4. Operator read model

Ticket list/detail responses expose the fields required by the Slice 6 charter:

- Unit;
- Shot;
- failure class;
- repair action;
- approved time range;
- source-media SHA provenance;
- provider-prompt SHA provenance;
- reference SHA provenance;
- provider-call allowance and used count;
- current lifecycle state.

Additional auditable fields include:

- ticket ID and ticket SHA;
- canonical violation;
- planner reason;
- approval identity/time;
- execution identity/task ID;
- attempt count;
- Repair output SHA;
- Re-QA outcome;
- selected artifact/version identity.

The API therefore provides the mandatory operator/UI facts without creating a second source of
truth.

A separate frontend workflow is not introduced in Slice 6; the authenticated API read model is
the accepted minimal operator surface and contains every field a later UI may render.

---

## 5. Approval semantics

`POST /{ticket_id}/approve` is not a local state toggle.

It performs the accepted production chain:

```text
load persisted Repair Ticket
→ resolve exact current/history source provenance
→ build current H3RepairApprovalFacts
→ H3RepairApprovalService.approve()
→ persist immutable approval binding
→ H3RepairQueueService.enqueue_approved_ticket()
→ QUEUED
```

Approval therefore reuses:

- Slice 2 approval binding;
- Slice 3 deterministic execution identity;
- Slice 3 queue admission;
- Slice 3 exactly-once enqueue behavior.

The API does not bypass approval validation or directly mutate lifecycle state.

---

## 6. Authenticated actor identity

Operator identity is derived from ArcReel's existing authenticated `CurrentUser`.

The request body cannot supply or override:

- `approved_by`;
- `rejected_by`;
- `cancelled_by`.

The authenticated `user.id` is written to the accepted approval/decision services.

For approved work, the same user ID is also passed into the existing repair queue task's
`user_id`.

This prevents the client from forging audit actor identity.

---

## 7. Reject / cancel semantics

Reject and cancel operations delegate to the existing
`H3RepairApprovalService` lifecycle operations.

They do not add new transitions.

For a cancellation with an existing active execution task, the operator service also invokes the
existing shared generation queue cancellation path.

The API returns only a sanitized cancellation summary:

```text
task_id
status
```

It never forwards the raw shared-task cancellation payload.

---

## 8. Execution-status privacy boundary

The execution endpoint exposes only operator-safe execution facts:

- task ID;
- task status;
- provider ID;
- persisted provider job ID;
- provider endpoint identifier;
- queued/started/finished timestamps;
- ticket lifecycle;
- execution identity;
- attempt count;
- provider-call count.

It intentionally does **not** expose:

- `execution_checkpoint_json`;
- frozen provider request internals;
- raw task payload;
- internal approval JSON.

A dedicated unit regression proves that a task carrying an internal execution checkpoint is
serialized without that checkpoint.

---

## 9. Repair / Re-QA result surface

The result endpoint exposes:

- Repair output SHA;
- Re-QA outcome;
- whether the repaired artifact is formally selected;
- selected artifact ID;
- selected version ID;
- reassembled output media path;
- provider-shot history path;
- persisted Re-QA result object when available.

Formal-current status remains derived from the accepted Slice 5 lifecycle and selection identity;
the operator API does not perform selection itself.

---

## 10. Fail-closed source approval

Before operator approval, the service resolves the exact source/version provenance through the
accepted Slice 4 source resolver.

If the required source media no longer exists, approval is converted to a state conflict instead
of being misreported as a missing project.

Other source/provenance mismatches continue to fail through the existing approval and source
validation boundaries.

Provider submission is not performed by the API request itself; it only admits the approved ticket
to the already accepted Slice 3 queue.

---

## 11. Acceptance defects found and fixed

Strict Slice 6 acceptance surfaced the following scoped issues.

### 11.1 Client-forgeable operator identity

Initial API request bodies included `approved_by` / `actor`.

This allowed a caller to claim an arbitrary audit identity.

Fixed by deriving all decision actors from authenticated `CurrentUser.id`.

### 11.2 Test-hygiene violations

The first Slice 6 test set introduced:

- one duplicated generic `client` fixture name;
- two tests patching private production helpers.

Fixed by:

- renaming the fixture to `h3_repairs_client`;
- exposing explicit public project/ticket lookup seams;
- updating tests to patch those public seams only.

The final test-lint run returns to the repository's existing five historical violations.

### 11.3 Raw cancellation payload exposure

The first cancel implementation returned the raw shared queue cancellation payload.

That payload could include internal task fields such as execution checkpoints.

Fixed by returning only a whitelist summary containing task ID and status.

A dedicated regression proves the checkpoint cannot leak through this surface.

---

## 12. Dedicated Slice 6 CI evidence

Dedicated PR:

`#13 ci: validate Phase 5 Slice 6 repair operator API`

Run:

`36419752878`

Tested SHA:

`f1adc6b0cc5fe4fc7c999a568a98789e8df1f13a`

### PostgreSQL compatibility

```text
postgres-compat: SUCCESS
608 passed, 4 warnings
```

This preserves the Slice 3 atomic enqueue/claim/allowance guarantees.

### Backend integration

```text
Backend tests (integration): SUCCESS
4486 passed, 1 skipped, 88 warnings
```

This is five tests above the Slice 5 integration baseline and includes the Slice 6 router
acceptance cases for:

- pending query;
- approve + queue admission;
- provider-call-limit request validation;
- detail/execution/result read surfaces;
- reject/cancel command routing.

### Backend unit

```text
Backend tests (unit):
9271 passed
19 skipped
2 failed
```

This is four passing tests above the Slice 5 unit baseline.

The only two failures are the existing Phase 4 ffmpeg-dependent runtime tests:

- `test_h3_audio_runtime.py::test_audio_runtime_remuxes_only_audio_and_preserves_video`
- `test_h3_exact_text_runtime.py::test_exact_text_runtime_repairs_only_video_window_and_preserves_audio`

Both fail because the unit runner lacks the `ffmpeg` executable.

No Slice 6 unit failure remains.

---

## 13. Static / repository lint status

The repository-wide `backend-static` job remains red because of historical errors outside the
Slice 6 delta.

At the final tested SHA, these Slice 6 production files have no Ruff error match:

- `server/routers/h3_repairs.py`;
- `server/services/h3_repair_operator.py`;
- `server/app.py`.

The Slice 6 test files appear only in test collection statistics, not as Ruff error sources.

The repository `test-lint` gate remains red for exactly the same five historical violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

No Slice 6-specific test-hygiene violation remains.

---

## 14. Slice 6 acceptance checklist

- pending ticket query: PASS
- generic ticket list/filter: PASS
- ticket detail: PASS
- explicit approve endpoint: PASS
- approve uses existing approval service: PASS
- approve enters existing Slice 3 queue: PASS
- max provider calls remains fixed to one: PASS
- reject endpoint: PASS
- cancel endpoint: PASS
- authenticated actor identity: PASS
- execution-status endpoint: PASS
- execution checkpoint redaction: PASS
- repair/Re-QA result endpoint: PASS
- required Unit/Shot/failure/action/time-range display fields: PASS
- Prompt/Reference provenance display: PASS
- provider-call allowance display: PASS
- lifecycle-state display: PASS
- no second repair policy: PASS
- no second approval model: PASS
- no second queue: PASS
- no new provider path: PASS
- no new formal-selection mechanism: PASS
- PostgreSQL regression: PASS
- full backend integration regression: PASS
- Slice 6-specific unit regressions: PASS
- paid MiniMax calls during acceptance: 0

---

## 15. Next permitted slice

The next permitted work is:

**Phase 5 Slice 7 — Phase 5 Evidence / Acceptance**

Slice 7 must deliver the charter's final Phase 5 evidence:

- production lifecycle E2E;
- interruption/resume E2E;
- stale approval negative test;
- duplicate execution negative test;
- multi-ticket project isolation test;
- full subsystem regression;
- formal master acceptance;
- Phase 5 final handoff.

Slice 7 must not expand product scope. It is evidence and closure of the production orchestration
already implemented and accepted in Slices 1-6.
