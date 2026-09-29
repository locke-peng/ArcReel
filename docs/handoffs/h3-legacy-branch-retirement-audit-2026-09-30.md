# ArcReel × MiniMax H3 — Legacy Branch Retirement Audit — 2026-09-30

## 0. Scope and authority

This audit is repository hygiene only. It does **not** open a new Phase and does not change any Phase 1–6 acceptance authority.

Current audited `main` baseline:

- `main`: `0fdc554cb54ead78082a56d309cf580cb16dc6eb`
- Phase 6 authoritative tested code remains: `da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`
- Canonical Director rich-field compatibility port is already merged at: `f9a3e9bd64c8b61f5db8630f8406a16b4e513670`

All pull requests are closed at the start of this audit.

## 1. Interpretation of compare status

For comparisons performed as `<legacy branch>...main`:

- `ahead / behind_by=0` means current `main` fully contains the branch history; the branch has no unique commits left.
- `diverged` means the branch still has commits not reachable from `main`; deletion requires an explicit archive/supersession decision rather than assumption.

## 2. SAFE-DELETE candidates

The following branches were confirmed to have **no unique commits outside current `main`** and are safe branch-ref deletion candidates once a delete-ref capable GitHub connection is available:

### Phase / CI integration branches

- `phase3/h3-production-policy`
- `phase4/h3-auto-repair-loop`
- `phase5/h3-production-orchestration`
- `phase6/h3-production-control-plane`
- `ci/phase5-slice3-base`
- `ci/phase5-slice4-base`
- `ci/phase5-slice5-base`
- `ci/phase5-slice6-base`
- `ci/phase5-slice7-base`

### Closed documentation / maintenance branches

- `maintenance/h3-canonical-director-rich-fields`
- `docs/phase1-phase6-main-integration-handoff`
- `docs/canonical-director-legacy-resolution`

### Fully absorbed historical baselines / experiments

- `qa/golden-3b3bc`
- `experiment/h3-docpack-v1-3b3bc527`
- `h3-v6-v6-1-preview-lock`
- `feat/minimax-h3-prompt-integration-v5`

### Fully absorbed representative-unit fixes

- `fix/e4u02-h3-v3-c03-identity-lock`
- `fix/e4u02-h3-visible-text-v2-3b3bc527`
- `fix/e11u02-h3-v1-multiscene-dialogue-detached`
- `fix/e11u02-h3-v2-zero-text-physical-state`
- `fix/e11u02-h3-v3-deterministic-text-scrub`
- `fix/e13u01-h3-v1-screen-identity-continuity`
- `fix/e13u03-h3-v1-multiscene-identity-logguard`
- `fix/e15u03-h3-v2-deterministic-timeline`

Deleting these branch refs would not remove accepted code from `main`.

## 3. ARCHIVE-ONLY / SUPERSEDED diverged branches

These branches retain unique historical commits but are known to be old QA, live-test, prototype, or superseded work. They must **not** be merged directly into current `main`.

### Canonical Director prototypes

- `phase-a/canonical-director-v1-contract`
  - head: `c14bd2550b07aa9d389522f122af07abfb009ae8`
  - corresponding PR #3 was closed as superseded.
  - its own Backend unit run had six CanonicalDirectorV1 validation failures.
  - do not resurrect this as a second Canonical Director authority.

- `test/canonical-director-adapter-v1-3b3bc527`
  - head: `af36de8889589265362fe999df086565e321a6e9`
  - corresponding PR #2 was closed as superseded after PR #18 ported the valid rich-field behavior to current `main`.

### Delivery / QA evidence branches

- `qa/formal-v33-package-exact`
  - head: `9b6426d4e86b0b6796c5f802512476a38f36afe2`
- `qa/lihunhou-e01-import`
- `qa/lihunhou-import-e01`
- `qa/lihunhou-v33-delivery-compat`
  - head: `a69c209498b06d24632ce00c1e43cb3ca8c1f7f7`
- `qa/v33-formal-package-exact`
- `h3-e01-real-test-3b3bc527`
- `h3-e01-real-test-v3-4ac53d2e`
- `h3-prompt-preview-v3-exact`
- `test/v3-3-director-compat-3b3bc527`

These branches are evidence/history, not merge candidates.

### Superseded representative-unit live-test branches

Examples confirmed as diverged historical experiments include:

- `fix/e11u02-h3-v3-deterministic-sanitization`
- `fix/e11u02-h3-v3-targeted-shot2-blank-token`
- `fix/e11u02-h3-v4-c04-rear-identity-lock`
- `test/e13u01-h3-v1-identity-screen-continuity`
- `fix/e13u01-h3-v1-identity-screen-continuity`

Their unique commits are dominated by live-test workflows, experiment scripts, fixtures, or evidence contracts. Current Phase 3–6 accepted runtime and representative-unit regression are authoritative instead.

## 4. CODE-ARCHAEOLOGY required before branch deletion

The following diverged branches contain substantial unique production implementation and must not be deleted merely because later Phases are closed.

### `feat/h3-six-unit-regression-pipeline-validator`

- head: `34055a0682908a211f77fd78f33b0d45e42d4801`
- unique commits vs current main: 81
- contains historical implementations touching:
  - `lib/generation_queue.py`
  - `lib/generation_worker.py`
  - `lib/reference_video/h3_media_pipeline.py`
  - `lib/reference_video/h3_production_policy.py`
  - `lib/reference_video/h3_repair_executors.py`
  - `lib/reference_video/h3_repair_task.py`
  - routers/services and associated tests
- much of this architecture was later redesigned into the accepted Phase 3–6 stack.
- disposition: **archive until a semantic parity audit proves every still-useful behavior is represented in current main**.

### `delta/h3-native-compliance-ref2va-t2va`

- head: `c95336955b59518ced5afcf17870cc7fee4919f3`
- unique commits vs current main: 149
- contains broad historical provider/live-test integration, workflows, supplier bundle artifacts, compiler changes, and test infrastructure.
- disposition: **do not merge; archive pending security cleanup and targeted archaeology**.

### Other diverged code-bearing branches requiring the same caution

- `fix/e1u02-h3-leakage-shot-subtitles-3b3bc527`
- `fix/e4u02-h3-v2-ui-dialogue-guard`
- `feat/h3-production-policy-six-unit-regression`
- `feat/h3-six-unit-regression-pipeline-validator`

These branches may contain obsolete implementations that were conceptually superseded, but their unique code must be reviewed before branch-ref deletion if preservation of historical implementation detail matters.

## 5. P0 security-hygiene branches

Two audited diverged branches expose **sensitive-looking supplier bundle material** in publicly reachable branch history:

### `delta/h3-native-compliance-ref2va-t2va`

Observed unique paths include supplier bundles for representative Units, including certificate/fingerprint material and files named like encrypted private-key payloads.

### `fix/e13u01-h3-v1-identity-screen-continuity`

- head: `bb823319996faa7f8a05fb47eda2ed1a550002a2`
- observed unique paths include `.github/supplier-bundles/E13U01/` with certificate/fingerprint material and an encrypted private-key payload filename.

This audit does **not** conclude that a usable secret has been exposed: the observed private-key payloads are named as encrypted data. However, these branches should be prioritized for ref removal / repository security review because they unnecessarily keep supplier credential artifacts publicly reachable.

If any underlying key material was ever used outside disposable test-only scope, revoke/rotate it independently of Git branch cleanup.

Deleting a branch ref alone does not guarantee immediate physical purge of unreachable Git objects. If confirmed sensitive credentials or secret-bearing history exists, use the appropriate history-rewrite / GitHub secret-remediation process rather than relying only on branch deletion.

## 6. Connector limitation

The current GitHub connection exposes branch creation/update and commit APIs but **does not expose branch/ref deletion**.

Therefore, this audit does not claim that any branch above has been deleted.

The next destructive cleanup step requires either:

1. a GitHub connection/tool with delete-ref capability, or
2. manual branch deletion in GitHub after reviewing this manifest.

## 7. Recommended retirement order

1. Remove P0 sensitive-artifact branch refs first after recording their head SHAs.
2. Delete SAFE-DELETE candidates.
3. Delete/archive QA/live-test branches whose evidence is already captured in merged docs/artifacts.
4. Keep CODE-ARCHAEOLOGY branches until semantic parity review is completed.
5. Do not touch `main` or rewrite accepted Phase 1–6 merge history as part of branch cleanup.

## 8. Stop boundary

At this audit boundary:

- Phase 1–6 remain CLOSED.
- Canonical Director legacy audit remains CLOSED.
- Open PR count remains zero before this documentation PR.
- Branch cleanup is **audited but not physically executed** because delete-ref capability is unavailable.
- No Phase 7 or other new Phase has been opened.
