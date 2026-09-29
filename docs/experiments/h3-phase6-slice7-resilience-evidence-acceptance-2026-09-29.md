# ArcReel × MiniMax H3 — Phase 6 Slice 7 Resilience / Evidence Acceptance — 2026-09-29

## 0. Verdict

**FINAL PASS**

Authoritative tested code SHA:

`da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`

This acceptance closes **Slice 7 — Resilience / Evidence / Master Acceptance** against the Phase 6 charter. No new live/paid MiniMax provider call was made.

## 1. Authoritative CI evidence

- Workflow: `H3 Phase 6 Slice 7 Resilience Evidence`
- Run: `36555392681`
- Job: `109363194412` (`resilience-e2e`)
- Result: `SUCCESS`
- Artifact: `11028135940`
- Artifact name: `h3-phase6-slice7-da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`
- Artifact digest: `sha256:f18d661d01e5a549a0ba272c697ef7e1dddf7668d248b0f5efad9e54bfaa2aba`

Machine-readable evidence file:

`e2e01-control-plane-resilience.json`

It records:

- `tested_sha = da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`
- `status = PASS`
- `paid_minimax_calls = 0`

## 2. Required Slice 7 scenarios

| Charter requirement | Evidence | Result |
| --- | --- | --- |
| restart / rebuild | projection equal after restart; pause and running cap persisted | PASS |
| concurrent multi-project / multi-Unit | main and other project running independently; second claim blocked by project cap | PASS |
| partial batch failure | 2 independent successes + 1 independent failure | PASS |
| budget exhaustion | blocked ticket spent 0 provider calls; remaining project allowance = 0 | PASS |
| stale approval inside batch | stale ticket expired before spend; sibling remained valid and reserved exactly one call | PASS |
| evidence export | immutable bundle digest present; checkpoint digest exported; raw checkpoint not leaked | PASS |
| Phase 1–5 regression gate | covered again by Phase 6 Master Acceptance on same tested SHA | PASS |
| Phase 6 master acceptance artifact | produced by run `36555392414` on same tested SHA | PASS |

## 3. PostgreSQL cross-check

The first Slice 7 evidence run on the preceding SHA exposed a dialect-sensitive fixture gap that SQLite did not reveal because the SQLite test fixture disables foreign-key enforcement.

The affected E2E actors were:

- `slice7:e2e`
- `operator:a`
- `operator:b`

The test-only fix explicitly persists those test users without changing production queue, approval, repair-policy, or provider semantics.

Fix commit:

`da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f` — `test(h3): make resilience E2E PostgreSQL-safe`

Cross-check:

- Generic `Tests` workflow run: `36555392457`
- Job: `postgres-compat`
- Job ID: `109363251870`
- Result: `SUCCESS`

This confirms the Slice 7 resilience path and Phase 5 project-isolation regression are valid under PostgreSQL constraints rather than only SQLite.

## 4. Evidence invariants

The final Slice 7 evidence proves:

1. restart/rebuild does not mutate the production projection;
2. project pause and running-cap state survive persistence;
3. a partial batch failure does not corrupt successful sibling operations;
4. stale approval fails before provider spend;
5. budget exhaustion fails before provider spend;
6. capacity remains project-isolated;
7. exported evidence contains checkpoint digests but not raw internal checkpoint JSON;
8. no paid MiniMax call is required for CI acceptance.

## 5. Closure rule

This document is a documentation-only closure record.

The tested code SHA remains:

`da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`

Any later documentation-only commit must not replace it as the tested-code identity.
