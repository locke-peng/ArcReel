# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-01 Production Lifecycle Evidence — 2026-09-28

## Verdict

**E2E-01 — PRODUCTION LIFECYCLE = PASS**

This evidence proves the Phase 5 orchestration lifecycle from persisted provider-repair ticket
through explicit approval, queue admission, exactly-one execution identity, deterministic provider
execution, reassembly, mandatory Re-QA, and formal current-version advancement.

This is evidence for Slice 7. It does not close Slice 7 or Phase 5 by itself.

No live or paid MiniMax request was performed.

---

## 1. Tested repository state

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 6 CLOSED base:

`d1ac863dcbd52b5c1fdf99ae773b9cafd94f6b16`

Tested SHA:

`1dae3e88c35617e5f79e5abbe7c2e4dd92cdd08c`

Dedicated Slice 7 PR:

`#14 ci: validate Phase 5 Slice 7 production lifecycle evidence`

Dedicated workflow:

`.github/workflows/h3-phase5-slice7-e2e.yml`

E2E source:

`tests/e2e/reference_video/test_h3_phase5_production_lifecycle_e2e.py`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 5 Slice 7 E2E-01`

Run:

`36427798138`

Job:

`108945972658 production-lifecycle-e2e`

Result:

```text
SUCCESS
1 passed, 1 warning
```

The workflow separately validates the emitted evidence JSON after pytest passes.

---

## 3. Uploaded machine-readable artifact

Artifact ID:

`10973015043`

Artifact name:

`h3-phase5-slice7-e2e01-1dae3e88c35617e5f79e5abbe7c2e4dd92cdd08c`

Artifact digest:

`sha256:01896ec12dfd895d91f3d561a06dbb98f6514940a046e6ba3441e860d079b7cd`

Artifact size:

`967 bytes`

Retention expiry:

`2026-10-28T13:20:00Z`

Contained evidence file:

`e2e01-production-lifecycle.json`

---

## 4. Scenario

Project:

`ai-boss`

Unit:

`E12U06`

Shot:

`E12U06-S02`

Failure:

`large_semantic_failure`

Repair action:

`regenerate_shot`

The scenario starts from a persisted accepted Unit/version and a real Phase 4 planner output.

The exercised orchestration chain is:

```text
Media QA finding
→ plan_h3_auto_repair()
→ build_h3_repair_ticket()
→ H3RepairTicketStore.persist()
→ explicit H3RepairApprovalService.approve()
→ H3RepairQueueService.enqueue_approved_ticket()
→ H3RepairQueueService.claim_next()
→ execute_h3_repair_task()
→ provider submission checkpoint
→ persisted provider job identity
→ deterministic provider-shot result
→ deterministic shot-window reassembly
→ REQA_RUNNING
→ execute_h3_repair_reqa()
→ trusted Phase 4 runtime selection gate
→ PASS
→ formal VersionManager current-version advancement
→ ACCEPTED
```

---

## 5. Immutable ticket evidence

Ticket ID:

`h3rt_f2091f157e597ab9af15736b`

Ticket SHA:

`f2091f157e597ab9af15736bf9fa8f6ed31bc3620d85709aff715475a1314fbe`

Source media SHA:

`3c3857ef6504796d074a10b5fcc3273ab12508e56274ac65b3f605b5740d968a`

Provider prompt SHA:

`c8b5f77145937207416c1c48da083f709923ae13e886fbcca14e4e83692547f9`

Approval actor:

`e2e`

Max provider calls:

`1`

The approval is bound to the immutable ticket/source/prompt facts before queue admission.

---

## 6. Execution identity / paid-call evidence

Task ID:

`4083ca641ad44527bc14ccdc45bdca5e`

Execution identity:

`h3rx_e609394ce824e1b627900c26`

Provider job ID:

`provider-job-e2e01`

Submission checkpoint persisted:

`true`

Ticket provider-call count:

`1`

Deterministic provider generate calls:

`1`

Provider resume calls:

`0`

Paid MiniMax calls:

`0`

The E2E therefore proves one ticket produces one execution identity and consumes exactly one
provider-call allowance on the fresh path.

The provider is a deterministic in-process test double that exercises the real
`before_submit` and `on_provider_job_id` seams. It does not contact MiniMax.

---

## 7. Repair output evidence

Provider-shot history path:

`repairs/provider_shots/h3rx_e609394ce824e1b627900c26.mp4`

Reassembled Unit path:

`repairs/reassembled_units/h3rx_e609394ce824e1b627900c26.mp4`

Persisted repair-output SHA:

`f550fcdec9b4758eccc2befa9b2ecfc9d3f67f51d48ee8b772afaaf764c301c9`

The assembly implementation is deterministic test media plumbing so the E2E does not depend on
FFmpeg availability. The production Slice 4 reassembly implementation remains covered by its
existing unit/integration acceptance.

---

## 8. Mandatory Re-QA evidence

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

Final current version:

`v2`

The E2E invokes the real Phase 4 `run_h3_runtime_selection_gate()` through
`execute_h3_repair_reqa()` with a deterministic evaluator that returns no blocking findings.

The E2E uses a test selection adapter around the real `VersionManager` current-version commit.
The full `VideoArtifactCommitter` current-basis/manifest selection boundary is not duplicated
inside this E2E; that boundary is already independently covered by the accepted video-artifact
currency/integration suite and Slice 5 acceptance.

This separation prevents E2E-01 from rebuilding the entire project-script snapshot model merely
to retest an already accepted component.

---

## 9. Lifecycle trace

The machine-readable artifact records this exact ordered lifecycle:

```text
awaiting_approval
→ approved
→ queued
→ running
→ provider_completed
→ reassembling
→ reqa_running
→ accepted
```

There is no lifecycle skip from `running` directly to `accepted`.

The intermediate Slice 4 states are captured through SQLAlchemy ORM lifecycle-state events without
patching private production functions.

---

## 10. CI hygiene evidence

On the same Slice 7 code line:

### test-lint

No Slice 7-specific violation remains.

The repository gate still reports only the five historical violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

### workflow-static

The new Slice 7 workflow has no remaining workflow-static finding.

The repository job still fails only because of the historical unpinned action:

`.github/workflows/h3-e4u02-v4-dialogue-detached-live.yml: actions/download-artifact@v4`

Slice 7 intentionally does not modify that closed Phase 4 workflow.

---

## 11. E2E-01 acceptance checklist

- real Phase 4 Repair Ticket construction: PASS
- persisted ticket round-trip: PASS
- explicit approval binding: PASS
- approval provider-call limit = 1: PASS
- queue admission: PASS
- one execution identity: PASS
- one task identity: PASS
- atomic claim path entered: PASS
- immutable submission checkpoint persisted: PASS
- provider job identity persisted: PASS
- exactly one fresh provider invocation through execution seam: PASS
- provider resume count on fresh path = 0: PASS
- provider-call count = 1: PASS
- deterministic repaired candidate produced: PASS
- repair-output SHA persisted: PASS
- mandatory Re-QA entered: PASS
- trusted Phase 4 runtime gate invoked: PASS
- Re-QA outcome = PASS: PASS
- repaired artifact selected current: PASS
- current version advances v1 → v2: PASS
- lifecycle reaches ACCEPTED: PASS
- paid MiniMax calls: 0

**E2E-01 = PASS**

---

## 12. Boundary / next evidence

E2E-01 proves the happy-path production orchestration.

It does not replace the remaining Slice 7 negative/recovery evidence.

Next required Slice 7 evidence should cover:

1. interruption/resume with persisted provider task identity;
2. stale approval rejection before provider spend;
3. duplicate execution / single-winner behavior;
4. multi-ticket project isolation.

Those scenarios must preserve the same Slice 1-6 production services and must not introduce new
production behavior.
