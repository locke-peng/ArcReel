# ArcReel × MiniMax H3 — Phase 5 Slice 5 Re-QA / Formal Selection Acceptance — 2026-09-28

## Verdict

**PHASE 5 SLICE 5 — RE-QA / FORMAL SELECTION = PASS / CLOSED**

This acceptance closes Slice 5 only. It does not close Phase 5.

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
  Slice 6  NOT STARTED
```

No paid MiniMax provider generation was performed for this acceptance.

---

## 1. Repository / branch / tested code

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 4 CLOSED base:

`73ae87578df4ceba19543745378f6e5554e10842`

Final tested Slice 5 code SHA:

`4fa732754d787df187eb91469c1360a0f8f76fd9`

Dedicated Slice 5 validation PR:

`#12 ci: validate Phase 5 Slice 5 Re-QA formal selection`

PR base:

`ci/phase5-slice5-base` → `73ae87578df4ceba19543745378f6e5554e10842`

Primary GitHub Actions run:

`36416608915`

The validation PR is a draft PR used only to validate the Slice 5 delta. It is not intended to
merge and does not invoke live MiniMax generation.

---

## 2. Slice 5 charter mapping

The Phase 5 charter requires Slice 5 to deliver:

1. invoke the trusted Phase 4 runtime gate on repaired media;
2. accept only PASS;
3. retain failures history-only;
4. create a bounded new Repair Ticket only when the existing planner again requires provider repair;
5. never inherit the prior approval.

All five requirements are present in the tested code.

Primary implementation:

- `server/services/h3_repair_reqa.py`
- `server/services/h3_repair_tasks.py`
- `lib/reference_video/h3_repair_ticket_store.py`
- `lib/reference_video/h3_provider_repair_runtime.py`
- `server/services/reference_video_tasks.py`

Primary tests:

- `tests/integration/server/services/test_h3_repair_reqa.py`
- `tests/integration/server/services/test_h3_repair_tasks.py`
- `tests/unit/lib/reference_video/test_h3_provider_repair_runtime.py`

---

## 3. Accepted execution chain

The accepted Slice 5 chain is:

```text
Slice 4 reassembled repair
→ REQA_RUNNING
→ verify persisted repair-output SHA
→ recover exact accepted source/provenance
→ trusted Phase 4 H3 runtime gate
→ PASS?
    yes → existing formal artifact-selection boundary
          → current formal Unit updated
          → Repair Ticket ACCEPTED
    no  → repaired candidate committed history-only
          → provider repair required?
              yes → bounded fresh Repair Ticket(s), no inherited approval
              no  → HUMAN_REVIEW_REQUIRED
```

Restart from `REQA_RUNNING` enters Re-QA directly and does not replay or resubmit provider repair.

---

## 4. Trusted Phase 4 gate reuse

Slice 5 does not implement a second Media QA policy.

It calls the existing:

`run_h3_runtime_selection_gate()`

with the trusted evaluator and deterministic repair handlers recovered from the original execution
provenance.

The gate remains the single authority for:

- structured Media QA findings;
- existing `H3FailureClass` classification;
- existing repair planner behavior;
- deterministic repair handlers;
- provider-required escalation;
- unknown/fail-closed handling.

A returned gate result represents PASS. Non-PASS conditions are represented by
`H3RuntimeSelectionError` and are never selected formally.

---

## 5. Reassembled candidate integrity

Before Re-QA:

- the candidate file must exist;
- its SHA must equal the persisted `repair_output_sha256`;
- the Repair Ticket must still resolve to the exact accepted source/provenance;
- provider prompt and reference provenance remain locked.

Any mismatch fails closed before formal selection.

---

## 6. Formal selection only after PASS

PASS selection uses ArcReel's existing `VideoArtifactCommitter` formal-selection boundary.

The repaired work file is first prepared against current artifact currency. Selection then:

- preserves the original formal parent baseline;
- creates a paid-version record with Re-QA metadata;
- updates current formal media only when selection succeeds;
- records selected artifact/version identities on the Repair Ticket;
- transitions the ticket to `ACCEPTED`.

If Re-QA passes but artifact selection is blocked by current state, the ticket becomes
`HUMAN_REVIEW_REQUIRED`; the candidate is not silently selected.

---

## 7. Failure path is history-only

For every non-PASS Re-QA path, Slice 5 commits the repaired candidate with:

`select_current=False`

The failed repaired candidate therefore remains history-only and cannot replace formal current
media.

This applies to:

- provider-repair-required recurrence;
- unknown/unresolved Re-QA findings;
- trusted Re-QA runtime errors;
- follow-up ticket creation failure.

Runtime-gate failures are archived with the Re-QA report/evidence attached to the version record.

---

## 8. Bounded provider-repair recurrence

When the existing Phase 4 planner again requires provider repair, the runtime-gate report carries
fresh Repair Ticket payloads.

Slice 5 validates that every follow-up ticket:

- is provider-recall-required;
- is approval-eligible;
- starts in `AWAITING_APPROVAL`;
- has a new ticket identity;
- is not the parent ticket;
- does not exceed the configured `max_followup_tickets` bound.

Duplicate ticket identities or excess follow-ups fail closed.

The previous repair ticket is completed as `REJECTED` only after the bounded follow-up ticket
set is persisted successfully.

---

## 9. No approval inheritance

A newly created follow-up Repair Ticket does not inherit:

- `approval_json`;
- `approval_identity`;
- provider-call allowance.

A fresh explicit operator approval is required before another provider execution may enter the
Slice 3 queue.

Crash recovery also preserves a later explicit approval that may already have been issued to the
new follow-up ticket; recovery does not overwrite it with the prior approval.

---

## 10. History-source recurrence support

A second provider-required repair may target bytes that are not the current formal Unit because
the previous failed repaired candidate is intentionally history-only.

Slice 5 therefore extends source resolution to:

1. prefer a matching current source;
2. otherwise resolve one unique history-only version whose SHA matches the new Repair Ticket.

This preserves exact source identity without promoting the failed candidate to current media.

Ambiguous or missing history matches fail closed.

---

## 11. Re-QA restart safety

`server/services/h3_repair_tasks.py` recognizes `REQA_RUNNING` and continues directly with
`execute_h3_repair_reqa()`.

It does not:

- call `generate_video_async()`;
- call `resume_video_async()`;
- consume another provider allowance;
- recreate the provider repair shot.

This preserves Slice 3/4 exactly-once and provider-spend guarantees across a crash between
reassembly and formal Re-QA completion.

---

## 12. Acceptance defects found and fixed

Strict Slice 5 acceptance surfaced and closed several integration issues before the final tested
SHA.

### 12.1 Trusted Re-QA provenance recovery

Re-QA initially depended too directly on current task state. Recovery was hardened to reconstruct
the trusted Canonical/runtime bundle from persisted execution-task provenance.

### 12.2 History-only follow-up source resolution

Provider-required recurrence initially could not safely use a failed repaired candidate retained
outside current formal media. Source resolution was extended to a unique SHA-matching history
version.

### 12.3 Formal parent baseline preservation

Repair history must not become the formal-current parent coordinate. Slice 5 preserves the
original submission artifact-currency `parent_version`, so a valid later PASS can still select
when the real formal baseline has not changed.

### 12.4 Explicit follow-up approval preservation on recovery

Crash recovery no longer treats an independently approved follow-up ticket as inherited approval.
A later explicit approval remains valid and is not overwritten.

### 12.5 Re-QA runtime failure archival

Unexpected trusted Re-QA runtime failures are persisted history-only and transition the ticket to
`HUMAN_REVIEW_REQUIRED` rather than leaving ambiguous state.

### 12.6 Scoped static cleanup

Final acceptance also fixed Slice 5-specific Ruff issues in
`server/services/h3_repair_reqa.py` and the Slice 5 integration test import block.

No Slice 5 production file remains in the final Ruff error list.

---

## 13. Dedicated Slice 5 CI evidence

Dedicated PR:

`#12 ci: validate Phase 5 Slice 5 Re-QA formal selection`

Run:

`36416608915`

Tested SHA:

`4fa732754d787df187eb91469c1360a0f8f76fd9`

### PostgreSQL compatibility

```text
postgres-compat: SUCCESS
608 passed, 4 warnings
```

The run keeps the Slice 3 atomic queue/claim/allowance concurrency regressions green.

### Backend integration

```text
Backend tests (integration): SUCCESS
4481 passed, 1 skipped, 88 warnings
```

Slice 5 integration coverage includes:

- Re-QA PASS selects the repaired Unit and accepts the ticket;
- provider-required Re-QA failure archives history-only and creates a fresh unapproved ticket;
- follow-up creation is bounded and fails closed;
- trusted Canonical/runtime facts can be recovered from source execution provenance;
- restart from `REQA_RUNNING` does not replay provider repair.

No live provider is used in these tests.

### Backend unit

```text
Backend tests (unit):
9267 passed
19 skipped
2 failed
```

The only two failures are the existing Phase 4 ffmpeg-dependent runtime tests:

- `test_h3_exact_text_runtime.py::test_exact_text_runtime_repairs_only_video_window_and_preserves_audio`
- `test_h3_audio_runtime.py::test_audio_runtime_remuxes_only_audio_and_preserves_video`

Both fail because the unit runner lacks the `ffmpeg` executable.

No Slice 5 unit failure remains.

---

## 14. Static / repository lint status

The repository-wide `backend-static` job remains red because of pre-existing errors outside the
Slice 5 production delta.

At the final tested SHA:

- `server/services/h3_repair_reqa.py`: no Ruff error;
- `lib/reference_video/h3_provider_repair_runtime.py`: no Ruff error;
- `lib/reference_video/h3_repair_ticket_store.py`: no Ruff error;
- `server/services/h3_repair_tasks.py`: no Ruff error;
- `server/services/reference_video_tasks.py`: no Ruff error.

The repository `test-lint` gate remains red for the same five historical violations:

- two frontend tests under `__tests__`;
- two private-symbol patches in `test_h3_auto_repair_loop.py`;
- one private-symbol patch in `test_h3_timeline_runtime.py`.

These are outside the Slice 5 delta and were intentionally not modified.

---

## 15. Slice 5 acceptance checklist

- trusted Phase 4 runtime gate invoked: PASS
- no second Media QA / Repair Policy introduced: PASS
- repaired candidate SHA revalidated: PASS
- formal selection only after Re-QA PASS: PASS
- PASS records selected artifact/version identity: PASS
- PASS selection uses existing artifact boundary: PASS
- non-PASS candidate history-only: PASS
- provider-required recurrence uses existing planner output: PASS
- follow-up ticket creation bounded: PASS
- follow-up ticket identity fresh: PASS
- prior approval not inherited: PASS
- follow-up provider allowance not inherited: PASS
- explicit follow-up approval preserved across recovery: PASS
- history-only source recurrence supported by exact SHA: PASS
- ambiguous history source fails closed: PASS
- Re-QA runtime error fails closed/history-only: PASS
- restart from REQA_RUNNING performs no provider replay: PASS
- PostgreSQL regression: PASS
- full backend integration regression: PASS
- Slice 5-specific unit regressions: PASS
- paid MiniMax calls during acceptance: 0

---

## 16. Next permitted slice

The next permitted work is:

**Phase 5 Slice 6 — Operator / API Surface**

Slice 6 may expose only the persisted production lifecycle already accepted in Slices 1–5.

Minimum surface:

- pending ticket query;
- ticket detail;
- approve;
- reject/cancel;
- execution status;
- repair result / Re-QA result.

Any UI/API must display the authoritative persisted facts and must not create a second repair
policy, approval model, queue, provider path, or selection mechanism.
