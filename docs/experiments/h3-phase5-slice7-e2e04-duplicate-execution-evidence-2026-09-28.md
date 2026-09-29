# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-04 Duplicate Execution Evidence — 2026-09-28

## Verdict

**E2E-04 — DUPLICATE EXECUTION / SINGLE WINNER = PASS**

This evidence proves that concurrent workers competing for one approved Repair Ticket resolve to one durable execution task, one execution identity, one winning claim, and one provider-call allowance consumption.

No live or paid MiniMax request was performed.

## Tested state

Repository: `locke-peng/ArcReel`

Branch: `phase5/h3-production-orchestration`

Tested SHA: `919aaebd3530072c3c2982ed407c7d9493bf2aa1`

PR: `#14 ci: validate Phase 5 Slice 7 production lifecycle evidence`

Workflow: `.github/workflows/h3-phase5-slice7-e2e04.yml`

Test: `tests/e2e/reference_video/test_h3_phase5_duplicate_execution_e2e.py`

## GitHub Actions evidence

Run: `36438208140`

Job: `108981535473 duplicate-execution-e2e`

Result:

```text
SUCCESS
1 passed, 1 warning
```

## Artifact

Artifact ID: `10976716231`

Name: `h3-phase5-slice7-e2e04-919aaebd3530072c3c2982ed407c7d9493bf2aa1`

Digest: `sha256:58026a96cfcdd70a440afd726bec47f7d139dcb5f6fbc3a4bef25ad0ccdf89c9`

Evidence file: `e2e04-duplicate-execution.json`

## Concurrent enqueue evidence

Two concurrent `enqueue_approved_ticket()` calls returned:

- the same task ID;
- the same execution identity;
- dedupe values `[false, true]`.

Final durable task count: `1`

Final Repair Ticket count: `1`

This proves duplicate enqueue does not create a second execution record.

## Atomic claim evidence

Two concurrent `claim_next()` calls produced:

`winner_count = 1`

Final attempt count:

`1`

The winning claim references the same task/execution identity produced by enqueue.

## Provider reservation evidence

Two concurrent `reserve_provider_submission()` calls produced exactly:

```text
1 × SUBMIT_ALLOWED
1 × RESERVED_WITHOUT_PROVIDER_ID
```

Final provider-call count:

`1`

Checkpoint present:

`true`

Provider job ID present:

`false`

The second contender therefore observes the already-reserved paid-call state instead of consuming another allowance.

Paid MiniMax calls:

`0`

## Static / hygiene evidence

- test-lint contains only the existing five historical violations;
- the Slice 7 E2E-04 workflow has no workflow-static finding;
- backend-static reports the E2E-04 file only in collection statistics, not as a Ruff error source.

## Acceptance checklist

- concurrent duplicate enqueue: PASS
- one durable task: PASS
- one execution identity: PASS
- one deduped enqueue: PASS
- two workers claim same queue: PASS
- one winning claim: PASS
- attempt count = 1: PASS
- two concurrent provider reservations: PASS
- SUBMIT_ALLOWED count = 1: PASS
- duplicate reservation consumes no second allowance: PASS
- final provider-call count = 1: PASS
- paid MiniMax calls = 0: PASS

**E2E-04 = PASS**

## Next evidence

**E2E-05 — Multi-ticket / Project Isolation**

It must prove that identically shaped tickets in different projects cannot read, approve, claim, reserve, or mutate each other's persisted lifecycle or provider allowance.
