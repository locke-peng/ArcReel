# ArcReel × MiniMax H3 — Phase 6 Slice 1 Production State Projection Acceptance — 2026-09-28

## Verdict

**PHASE 6 SLICE 1 — PRODUCTION STATE PROJECTION = PASS / CLOSED**

Phase 6 remains IN PROGRESS.

---

## 1. Tested state

Repository:

`locke-peng/ArcReel`

Branch:

`phase6/h3-production-control-plane`

Tested SHA:

`a62418bd23c91463ebcd0b77c61cff6cc77e5ba2`

Draft PR:

`#15 feat: begin Phase 6 production control plane`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 6 Slice 1 Projection`

Run:

`36445417573`

Job:

`109006345889 production-projection`

Result:

`SUCCESS`

Test result:

```text
18 passed, 1 warning in 2.51s
```

No live or paid MiniMax call was used.

---

## 3. Accepted architecture

Slice 1 deliberately introduces no second production-state database.

The projection is derived from existing authoritative facts:

```text
project.json
→ episodes[].script_file
→ episode_N.json
→ resolve_items(...)=video_units/unit_id
→ VersionManager(reference_videos).current_version
→ H3RepairTicketStore persisted lifecycle
→ deterministic project / episode / Unit production projection
```

Authoritative sources remain unchanged.

---

## 4. Delivered implementation

Pure deterministic read model:

`lib/reference_video/h3_production_projection.py`

Authoritative IO resolver:

`server/services/h3_production_control.py`

Unit coverage:

`tests/unit/lib/reference_video/test_h3_production_projection.py`

Integration coverage:

`tests/integration/server/services/test_h3_production_control.py`

---

## 5. Production state contract

The accepted Unit projection states are:

```text
not_started
ready
awaiting_approval
queued
running
blocked
human_review_required
accepted
failed_history_only
complete
```

They are descriptive projections over existing state and do not create repair authority.

---

## 6. Readiness / blocker mapping

The acceptance suite proves the Phase 5 lifecycle maps deterministically into production readiness.

Examples:

```text
awaiting_approval       → awaiting_approval / approval_required
approved                → ready
queued                  → queued
running                 → running
provider_completed      → running
reassembling            → running
reqa_running            → running
accepted                → accepted
rejected                → failed_history_only / repair_rejected
cancelled               → blocked / cancelled
expired                 → blocked / expired
human_review_required   → human_review_required
no current video        → not_started / no_current_reference_video
```

Human review has fail-closed priority over simultaneously active repair state.

---

## 7. Rebuild / idempotency

The integration test resolves the same project twice from the persisted source-of-truth records and proves:

```text
rebuilt_projection == original_projection
```

No projection state is persisted between reads.

This means restart/rebuild does not depend on a shadow control-plane lifecycle database.

---

## 8. Isolation / integrity checks

The projection fails closed when:

- a Repair Ticket belongs to another project;
- a Repair Ticket references a Unit absent from project inventory;
- Unit inventory contains duplicates;
- episode metadata is invalid;
- a project is not in `reference_video` generation mode;
- an episode script does not resolve as `video_units / unit_id`.

---

## 9. Phase 1–5 invariants preserved

Slice 1 does not modify:

- `H3FailureClass`;
- `plan_h3_media_repair()`;
- Media QA;
- Repair Ticket lifecycle;
- approval binding;
- provider allowance;
- repair queue;
- MiniMax transport;
- Re-QA;
- formal selection.

The control-plane projection remains read-only.

---

## 10. Slice status

```text
Phase 6                 IN PROGRESS
Slice 1 Projection      CLOSED
Slice 2 Batch Contract  NOT STARTED
Slice 3 Capacity        NOT STARTED
Slice 4 Budget Ledger   NOT STARTED
Slice 5 Operator API    NOT STARTED
Slice 6 Dashboard       NOT STARTED
Slice 7 Acceptance      NOT STARTED
```

Next implementation slice:

**Slice 2 — Batch Coordination Contract**
