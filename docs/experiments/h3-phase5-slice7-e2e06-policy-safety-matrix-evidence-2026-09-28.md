# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-06 Policy / Safety Matrix Evidence — 2026-09-28

## Verdict

**E2E-06 — POLICY / SAFETY MATRIX = PASS**

This evidence closes the remaining Slice 7 policy/safety gaps for the Phase 5 Charter: multi-shot independence, dialogue/identity repair routing, UNKNOWN fail-closed behavior, and project-level provider-call budget enforcement.

No live or paid MiniMax request was performed.

---

## 1. Tested repository state

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Tested SHA:

`f1ea4bf8c39625c53b690cb4cbdfed63642e0454`

Workflow:

`.github/workflows/h3-phase5-slice7-e2e06.yml`

Test:

`tests/e2e/reference_video/test_h3_phase5_policy_safety_matrix_e2e.py`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 5 Slice 7 E2E-06`

Run:

`36441915352`

Job:

`108994300151 policy-safety-matrix-e2e`

Result:

```text
SUCCESS
```

The pytest step, machine-readable evidence validation, and artifact upload all completed successfully.

---

## 3. Artifact

Artifact ID:

`10979096463`

Artifact name:

`h3-phase5-slice7-e2e06-f1ea4bf8c39625c53b690cb4cbdfed63642e0454`

Digest:

`sha256:e3f8fe8726aac4bb1f415abe68397756f3404aa7b782fe802dc7b78a35b3aed5`

Size:

`547 bytes`

Retention expiry:

`2026-10-28T15:14:05Z`

Evidence file:

`e2e06-policy-safety-matrix.json`

---

## 4. AC-09 — Multi-shot independence

Two provider-repair-required findings are created in the same Unit with different shot scopes.

The evidence proves:

- ticket IDs are independent;
- task IDs are independent;
- execution identities are independent.

No second repair policy or merged multi-shot provider request is introduced.

**AC-09 evidence = PASS**

---

## 5. AC-10 — Dialogue / identity routing

The test invokes the accepted Phase 3 planner through the Phase 4 auto-repair path.

Dialogue visualization routes to:

`recompile_dialogue_detached`

Identity continuity failure routes to:

`regenerate_with_identity_bridge`

Both remain explicit shot-scoped provider-repair candidates requiring approval.

**AC-10 evidence = PASS**

---

## 6. AC-11 — UNKNOWN fail-closed

UNKNOWN failure routing remains:

`escalate`

The resulting Repair Ticket is:

- not approval eligible;
- persisted as `HUMAN_REVIEW_REQUIRED`;
- rejected by the approval service before provider execution admission.

No provider allowance or supplier state is created.

**AC-11 evidence = PASS**

---

## 7. AC-12 — Budget / call allowance

The project-wide provider-call ceiling is configured to:

`1`

Two approved, claimed provider-repair tickets compete under that project budget.

Observed result:

```text
first ticket provider_call_count  = 1
second ticket provider_call_count = 0
second ticket lifecycle           = HUMAN_REVIEW_REQUIRED
```

The second ticket is blocked before provider submission.

Paid MiniMax calls:

`0`

**AC-12 evidence = PASS**

---

## 8. Slice 7 scenario matrix

```text
E2E-01 Production Lifecycle                 PASS
E2E-02 Interruption / Resume                PASS
E2E-03 Stale Approval Rejection             PASS
E2E-04 Duplicate Execution / Single Winner  PASS
E2E-05 Multi-Project Isolation              PASS
E2E-06 Policy / Safety Matrix               PASS
```

The remaining Phase 5 closure work is now:

1. AC-14 — current-head Phase 1–4 / H3 subsystem regression gate;
2. AC-15 — consolidated Phase 5 master gate and artifacts;
3. record the final tested code SHA separately from documentation-only closure commits;
4. issue the Phase 5 final handoff.

Phase 5 remains IN PROGRESS until those closure items pass.
