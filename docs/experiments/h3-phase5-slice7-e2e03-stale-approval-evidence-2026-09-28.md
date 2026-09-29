# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-03 Stale Approval Evidence — 2026-09-28

## Verdict

**E2E-03 — STALE APPROVAL REJECTION = PASS**

This evidence proves that an approved H3 Repair Ticket cannot spend provider allowance or create provider submission state after the approved source provenance becomes stale.

No live or paid MiniMax request was performed.

---

## 1. Tested repository state

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Tested SHA:

`059cac276133de6629cb1d6c5613c49ee64c784f`

Dedicated Slice 7 PR:

`#14 ci: validate Phase 5 Slice 7 production lifecycle evidence`

Workflow:

`.github/workflows/h3-phase5-slice7-e2e03.yml`

E2E source:

`tests/e2e/reference_video/test_h3_phase5_stale_approval_e2e.py`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 5 Slice 7 E2E-03`

Run:

`36437611608`

Job:

`108979484729 stale-approval-e2e`

Result:

```text
SUCCESS
1 passed, 1 warning
```

---

## 3. Uploaded machine-readable artifact

Artifact ID:

`10976481483`

Artifact name:

`h3-phase5-slice7-e2e03-059cac276133de6629cb1d6c5613c49ee64c784f`

Artifact digest:

`sha256:934aca7832ea5f4134873f2c6feb9e3bf6b178604b4c8f65af4697a372881ee8`

Artifact size:

`658 bytes`

Retention expiry:

`2026-10-28T14:40:17Z`

Contained evidence file:

`e2e03-stale-approval.json`

---

## 4. Scenario

The scenario uses the real Phase 5 persistence, approval, queue and claim services:

```text
Repair Ticket
→ persist
→ explicit approval against source SHA A
→ queue admission
→ atomic claim
→ current source facts changed to SHA B
→ reserve_provider_submission()
→ H3RepairApprovalStaleError
```

The stale field is:

`source_media_sha256`

The approved and current source SHA values are intentionally different.

---

## 5. Fail-closed result

Final ticket lifecycle:

`EXPIRED`

Final shared task status:

`failed`

Task error:

`h3_repair_stale_approval_pre_submit`

Provider-call count:

`0`

Execution checkpoint present:

`false`

Provider job identity present:

`false`

Provider submit calls:

`0`

Provider resume calls:

`0`

Paid MiniMax calls:

`0`

This proves stale approval is rejected before any paid provider submission state is created.

---

## 6. Preserved execution identity

The ticket is approved, queued and atomically claimed before the stale revalidation.

The stale rejection does not create a second execution path.

The same persisted ticket / task / execution identity is transitioned into the fail-closed state.

---

## 7. Static / hygiene evidence

At the tested SHA:

### test-lint

No Slice 7-specific violation is reported.

The gate contains only the same five historical violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

### workflow-static

`.github/workflows/h3-phase5-slice7-e2e03.yml` is audited without a Slice 7 finding.

The remaining failure is the historical unpinned action in the closed Phase 4 workflow.

### backend-static

`test_h3_phase5_stale_approval_e2e.py` appears only in test collection statistics and is not a Ruff error source.

---

## 8. E2E-03 acceptance checklist

- ticket persisted: PASS
- explicit approval persisted: PASS
- queue admission: PASS
- atomic claim: PASS
- approval source facts become stale: PASS
- stale field detected: PASS
- stale approval raises before submit: PASS
- ticket lifecycle = EXPIRED: PASS
- task status = failed: PASS
- provider-call allowance consumed = 0: PASS
- execution checkpoint created = no: PASS
- provider job identity created = no: PASS
- provider submit calls = 0: PASS
- provider resume calls = 0: PASS
- paid MiniMax calls = 0: PASS
- fail-closed = true: PASS

**E2E-03 = PASS**

---

## 9. Next Slice 7 evidence

The next required negative evidence is:

**E2E-04 — Duplicate Execution / Single-Winner**

It must prove that concurrent workers competing for the same Repair Ticket yield one durable execution identity, one winning claim, and at most one provider-call allowance consumption.
