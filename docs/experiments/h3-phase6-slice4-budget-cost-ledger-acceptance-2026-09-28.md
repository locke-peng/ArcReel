# ArcReel × MiniMax H3 — Phase 6 Slice 4 Budget / Cost Ledger Acceptance — 2026-09-28

## Verdict

**PHASE 6 SLICE 4 — BUDGET / COST LEDGER = PASS / CLOSED**

Phase 6 remains IN PROGRESS.

---

## 1. Tested state

Repository:

`locke-peng/ArcReel`

Branch:

`phase6/h3-production-control-plane`

Tested SHA:

`3fbadf0a6e69ca904a7eb276b307d7b59cd074bc`

Draft PR:

`#15 feat: begin Phase 6 production control plane`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 6 Slice 4 Budget Ledger`

Run:

`36448480848`

Job:

`109016821684 budget-ledger`

Result:

`SUCCESS`

Test result:

```text
18 passed, 1 warning in 4.80s
```

No live or paid MiniMax call was used.

---

## 3. Accepted budget architecture

Phase 6 Slice 4 deliberately separates two different truths:

```text
pre-spend safety:
  Phase 5 provider-call allowance / project call ceiling

post-call actual spend:
  api_calls.cost_amount + api_calls.currency
```

The control plane does not infer actual spend from model names, prompts, generated duration,
or static pricing tables.

Actual historical cost is sourced only from the shared ArcReel usage ledger.

---

## 4. Delivered implementation

Read model:

`lib/reference_video/h3_repair_ledger.py`

Authoritative DB resolver:

`server/services/h3_repair_budget_ledger.py`

Integration acceptance:

`tests/integration/server/services/test_h3_repair_budget_ledger.py`

Existing pre-spend budget regression:

`tests/integration/lib/reference_video/test_h3_repair_queue.py`

---

## 5. Repair-to-cost lineage

H3 repair provider execution already passes the existing repair task identity into:

- `generate_video_async(... task_id=...)`
- `resume_video_async(... task_id=...)`

The shared Ledger persists this as:

`api_calls.task_id`

Therefore the accepted cost lineage is:

```text
Repair Ticket
→ execution_task_id
→ Task.task_id
→ ApiCall.task_id
→ settled provider/model/status/cost_amount/currency
```

No parallel cost attribution scheme is introduced.

---

## 6. Project call-budget ledger

The project ledger reports:

- configured provider-call ceiling;
- reserved provider-call count;
- remaining calls;
- per-ticket provider-call count;
- per-ticket actual provider calls;
- actual cost by currency;
- pricing state;
- unpriced/zero-cost successful-call count.

The project budget row counter must reconcile exactly with the sum of persisted Repair Ticket
`provider_call_count` values.

Counter drift fails loud.

---

## 7. Pre-spend gate

The enforceable pre-spend budget boundary remains the accepted Phase 5 provider-call reservation.

The Slice 4 CI reruns the full H3 repair queue integration suite and proves:

- allowance is reserved before provider submission;
- duplicate reservation cannot spend twice;
- configured project provider-call ceiling blocks before spend;
- ticket-level max provider calls remain enforced;
- resume does not consume a second provider call.

This is the authoritative configured budget gate for the current H3 repair path.

---

## 8. Actual cost evidence

Acceptance creates one real ledger record through ArcReel's existing `Ledger.backfill()` test seam,
bound to the actual repair task ID.

The control-plane ledger resolves:

```text
provider_call_ceiling = 2
reserved_provider_calls = 1
remaining_provider_calls = 1
budget_counter_reconciled = true
actual_cost_by_currency = {"USD": 1.25}
```

The amount is read back from `api_calls`; it is not recalculated by the Phase 6 ledger.

---

## 9. Pricing state

Per-ticket pricing state is explicit:

```text
no_provider_call
pending
settled
unpriced_or_zero
```

A successful call with a stored zero amount is not silently presented as definitely free.
It remains `unpriced_or_zero` because the persisted record alone cannot distinguish a true
zero-price provider call from missing/incomplete pricing information.

---

## 10. Monetary hard-gate boundary

ArcReel has a shared declarative pricing system and `CostCalculator`, including MiniMax-H3 base
video pricing.

However, the current MiniMax-H3 registry explicitly documents a supplemental reference-media fee
that is not represented by the current per-second pricing shape: reference images after the first
five may add a separate per-image charge.

Therefore Slice 4 does **not** promote the incomplete base-price estimate into an authoritative
full monetary pre-spend hard gate.

Doing so could understate supplier cost.

Current safe behavior is:

```text
complete authoritative call-count budget available
→ enforce before spend

complete authoritative actual monetary settlement available
→ report from api_calls after settlement

pricing estimate incomplete for full supplier bill
→ do not fabricate a hard monetary ceiling
```

A future monetary ceiling may be added only after all billable dimensions required for the relevant
provider request are represented by an accepted pricing contract.

---

## 11. Reconciliation / fail-closed behavior

Acceptance proves the ledger fails loud when:

```text
H3RepairProjectBudget.provider_call_count
!=
sum(RepairTicket.provider_call_count)
```

This prevents the studio control plane from displaying a plausible-looking but internally
inconsistent remaining budget.

---

## 12. Phase invariants preserved

Slice 4 does not modify:

- `H3FailureClass`;
- `plan_h3_media_repair()`;
- Repair Ticket scope;
- approval binding;
- provider checkpoint/resume;
- provider transport;
- Re-QA;
- formal selection.

It does not create a second accounting system.

---

## 13. Slice status

```text
Phase 6                 IN PROGRESS
Slice 1 Projection      CLOSED
Slice 2 Batch Contract  CLOSED
Slice 3 Capacity        CLOSED
Slice 4 Budget Ledger   CLOSED
Slice 5 Operator API    NOT STARTED
Slice 6 Dashboard       NOT STARTED
Slice 7 Acceptance      NOT STARTED
```

Next implementation slice:

**Slice 5 — Studio Operator API**
