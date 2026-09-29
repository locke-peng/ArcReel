# ArcReel × MiniMax H3 — Phase 6 Slice 5 Studio Operator API Acceptance — 2026-09-28

## Verdict

**PHASE 6 SLICE 5 — STUDIO OPERATOR API = PASS / CLOSED**

Phase 6 remains IN PROGRESS.

---

## 1. Tested state

Repository:

`locke-peng/ArcReel`

Branch:

`phase6/h3-production-control-plane`

Tested SHA:

`915e776dbe7e6ed14e33918f7689b6d662af6213`

Draft PR:

`#15 feat: begin Phase 6 production control plane`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 6 Slice 5 Operator API`

Run:

`36449137803`

Job:

`109019050350 operator-api`

Result:

`SUCCESS`

Test result:

```text
20 passed, 2 warnings in 2.41s
```

No live or paid MiniMax call was used.

---

## 3. Delivered API surface

Router:

`server/routers/h3_studio.py`

Service:

`server/services/h3_studio_operator.py`

Registered under authenticated/migration-checked ArcReel API routing:

`/api/v1/projects/{project_name}/reference-videos/studio`

Delivered operations:

```text
GET  /summary
GET  /control
PUT  /control/pause
PUT  /control/running-cap
POST /batch/preview
POST /batch/execute
GET  /evidence/{ticket_id}
```

---

## 4. Authoritative delegation

The Studio API contains no repair policy.

It delegates to the accepted domain/services:

- production projection;
- Repair Ticket store;
- Phase 5 approval services;
- Phase 5 repair queue;
- Phase 6 batch coordinator;
- Phase 6 project capacity controls;
- Phase 6 authoritative budget/cost ledger;
- existing sanitized Phase 5 ticket/operator view.

The router does not classify failures, choose repair actions, create provider requests, or perform formal selection.

---

## 5. Summary contract

The project Studio summary exposes:

- project / episode / Unit production projection;
- project pause/running-cap control;
- provider-call budget and actual cost ledger;
- pending approvals;
- active executions;
- human-review-required items.

All values are derived from server-side authoritative state.

---

## 6. Batch API

Batch preview is read-only.

Batch execute propagates the authenticated ArcReel user identity into the existing batch/domain command:

```text
CurrentUser.id
→ batch actor
→ existing per-ticket approval/reject/cancel/enqueue services
```

Batch approval does not silently become a provider submission.

Batch enqueue remains a separate action.

---

## 7. Control API

Project pause and running-cap endpoints delegate to the persisted Slice 3 admission controls.

The service validates the real project before creating/updating a control row, preventing orphan/phantom project controls.

Project controls remain admission settings, not repair approval identities.

---

## 8. Evidence API

Studio evidence lookup delegates to the existing sanitized Phase 5 Repair Ticket operator view.

It exposes ticket/approval/execution/result identities required for operations while not exposing raw:

`execution_checkpoint_json`

The accepted provider checkpoint remains an internal execution primitive.

---

## 9. Input / error boundaries

Acceptance proves API validation rejects:

- empty batch ticket lists;
- invalid running caps such as zero.

Router errors map through ArcReel's existing API error system rather than returning internal exception details.

---

## 10. Phase 5 compatibility

The Slice 5 gate reruns:

- `tests/integration/server/routers/test_h3_repairs.py`
- existing repair operator tests;
- existing batch operator tests.

The Phase 5 H3 repair API remains green.

No existing `/reference-videos/repairs` contract was replaced.

---

## 11. Application registration

The Studio router is registered in `server/app.py` with:

- authenticated access;
- project migration guard;
- the existing `/api/v1` namespace.

No new authentication mechanism was introduced.

---

## 12. Phase invariants preserved

Slice 5 does not modify:

- `H3FailureClass`;
- `plan_h3_media_repair()`;
- Media QA;
- provider repair scope;
- provider submission rules;
- provider-call allowance semantics;
- Re-QA;
- formal selection.

The API is an operator surface over accepted server-side facts.

---

## 13. Slice status

```text
Phase 6                 IN PROGRESS
Slice 1 Projection      CLOSED
Slice 2 Batch Contract  CLOSED
Slice 3 Capacity        CLOSED
Slice 4 Budget Ledger   CLOSED
Slice 5 Operator API    CLOSED
Slice 6 Dashboard       NOT STARTED
Slice 7 Acceptance      NOT STARTED
```

Next implementation slice:

**Slice 6 — Studio Dashboard**
