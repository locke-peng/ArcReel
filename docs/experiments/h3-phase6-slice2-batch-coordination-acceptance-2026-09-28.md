# ArcReel × MiniMax H3 — Phase 6 Slice 2 Batch Coordination Acceptance — 2026-09-28

## Verdict

**PHASE 6 SLICE 2 — BATCH COORDINATION CONTRACT = PASS / CLOSED**

Phase 6 remains IN PROGRESS.

---

## 1. Tested state

Repository:

`locke-peng/ArcReel`

Branch:

`phase6/h3-production-control-plane`

Tested SHA:

`ace222a9ddd8e5508736ea36283274d63c623bca`

Draft PR:

`#15 feat: begin Phase 6 production control plane`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 6 Slice 2 Batch Coordination`

Run:

`36446620200`

Job:

`109010465862 batch-coordination`

Result:

`SUCCESS`

Test result:

```text
21 passed, 1 warning in 2.40s
```

No live or paid MiniMax call was used.

---

## 3. Accepted batch architecture

A batch is only a coordination envelope around existing Phase 5 Repair Tickets.

The accepted path is:

```text
batch ticket IDs
→ per-ticket preview
→ per-ticket existing operator/domain service
→ independent success/failure result
```

The batch layer does not create:

- a second Repair Ticket type;
- a second approval primitive;
- a second queue;
- a provider submission path;
- a cross-ticket transaction;
- a merged execution identity.

---

## 4. Delivered implementation

Preview contract:

`lib/reference_video/h3_repair_batch.py`

Batch coordinator:

`server/services/h3_repair_batch_operator.py`

Existing operator surface extended with separate thin commands:

- `approve_h3_repair()`
- `enqueue_h3_repair()`

The accepted Phase 5 combined contract remains preserved:

`approve_and_enqueue_h3_repair()`

and still performs approval + enqueue in the original single-session path.

---

## 5. Supported batch actions

```text
approve
reject
cancel
enqueue
```

Each ticket is evaluated and executed independently.

Batch approve does **not** implicitly enqueue.

Batch enqueue only delegates to the existing Phase 5 queue service and therefore preserves existing deterministic execution identity and dedupe behavior.

---

## 6. Preview contract

For every ticket, preview returns:

- ticket ID;
- Unit ID;
- shot ID;
- current lifecycle state;
- requested batch action;
- eligibility;
- descriptive reason;
- existing execution task ID when present.

Preview is deterministic, read-only, and does not mutate approval, queue, execution, or provider state.

---

## 7. Partial success / failure

The acceptance tests prove that one ticket may fail while later independent tickets continue.

Example accepted behavior:

```text
ticket A  approve → SUCCESS
ticket B  approve → stale/conflict failure
ticket C  approve → SUCCESS
```

The batch returns per-ticket results rather than rolling back A or skipping C.

This is deliberate: the batch is not an atomic multi-ticket transaction.

---

## 8. Existing Phase 5 compatibility

An intermediate implementation accidentally changed the old combined approve+enqueue helper into two separate session calls.

The Phase 5 operator regression caught this immediately:

```text
test_approve_operator_reuses_approval_service_then_enqueues
→ FAILED
```

The implementation was corrected by restoring the original single-session combined path while keeping the new independent Phase 6 commands.

Final Slice 2 CI includes the existing Phase 5 operator tests and is green.

---

## 9. Safety / isolation guarantees

The batch contract now proves:

- duplicate ticket IDs are rejected before any write;
- cross-project preview input is rejected;
- approval-ineligible tickets remain blocked;
- terminal lifecycle states are not silently re-approved/rejected/cancelled;
- enqueue on an existing execution delegates to existing dedupe;
- no ticket IDs are merged;
- no shot scopes are expanded;
- no batch action directly invokes provider execution;
- each ticket retains its own approval and execution identity;
- one item failure does not corrupt independent successful items.

---

## 10. Phase invariants preserved

Slice 2 does not modify:

- `H3FailureClass`;
- `plan_h3_media_repair()`;
- Media QA classification;
- immutable Repair Ticket identity;
- provider-call allowance semantics;
- provider transport;
- Re-QA;
- formal selection.

No second Repair Policy or provider scheduler was introduced.

---

## 11. Slice status

```text
Phase 6                 IN PROGRESS
Slice 1 Projection      CLOSED
Slice 2 Batch Contract  CLOSED
Slice 3 Capacity        NOT STARTED
Slice 4 Budget Ledger   NOT STARTED
Slice 5 Operator API    NOT STARTED
Slice 6 Dashboard       NOT STARTED
Slice 7 Acceptance      NOT STARTED
```

Next implementation slice:

**Slice 3 — Capacity / Scheduling Control**
