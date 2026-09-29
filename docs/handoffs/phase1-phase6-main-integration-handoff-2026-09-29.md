# ArcReel × MiniMax H3 — Phase 1–6 Main Integration Handoff — 2026-09-29

## 0. Final repository state

The accepted ArcReel × MiniMax H3 work stack through Phase 6 is integrated into `main`.

Phase ledger:

```text
Phase 1 = CLOSED
Phase 2 = CLOSED
Phase 3 = CLOSED
Phase 4 = CLOSED
Phase 5 = CLOSED
Phase 6 = CLOSED
```

This handoff does **not** define or start a new Phase.

Post-closure compatibility maintenance has also been integrated without reopening any Phase:

- Canonical Director rich-field compatibility port: `f9a3e9bd64c8b61f5db8630f8406a16b4e513670`
- source maintenance PR: #18

## 1. Immutable integration anchors

### Phase 6 authoritative tested code

`da8b32226bd44bcf33f2a29cc5dcf0bd42a95b9f`

This is the authoritative Phase 6 tested-code identity.

### Phase 6 documentation closure

`f7b07fdfd7563c8235b91361842e5655d2fc8c3e`

This documentation commit must not replace the tested-code SHA.

### Phase 6 merge into its parent branch

`2d43d2afbe61d34b1202a2429eb1ac731a440569`

PR #15 merged the Phase 6 branch into `phase5/h3-production-orchestration`.

### Phase 1–6 merge into main

`3fb3596e25779bfb5d19dc63f32003a8dd4c14ed`

PR #16 merged the already CLOSED Phase 1–6 stack into `main`.

The merge commit explicitly preserves the tested-code and documentation-closure identities in its message.

## 2. Main-integration acceptance evidence

PR #16:

- title: `feat(h3): integrate closed Phase 1–6 stack into main`
- head before merge: `2d43d2afbe61d34b1202a2429eb1ac731a440569`
- base: `main`
- merge result: SUCCESS
- main-integration merge SHA: `3fb3596e25779bfb5d19dc63f32003a8dd4c14ed`

### Phase 6 Master Gate on PR #16

- workflow: `H3 Phase 6 Master Acceptance`
- run: `36558573360`
- result: SUCCESS
- `phase6-backend-master`: SUCCESS
- `phase6-frontend-master`: SUCCESS
- `phase6-postgres-migration`: SUCCESS
- `phase6-master-evidence`: SUCCESS

Artifacts:

- `11028847976`
  - name: `h3-phase6-master-backend-2d43d2afbe61d34b1202a2429eb1ac731a440569`
  - digest: `sha256:78573149402d2a78f98ac44a4af2ea38969bbe2a2fd77eb2273e07c35b98f5c0`
- `11028836959`
  - name: `h3-phase6-master-2d43d2afbe61d34b1202a2429eb1ac731a440569`
  - digest: `sha256:b215b7a09b6094a524ef99f900e1d67f0c0e534c203360a975efff618ea493d2`

### Phase 5 regression on PR #16

- workflow: `H3 Phase 5 Master Acceptance`
- run: `36558573415`
- result: SUCCESS
- artifact: `11028566620`
- digest: `sha256:658874faac7fd34539aea23256136835c7c2f61c38e919d66db748cbc12ab1b4`

The Phase 5 Slice 7 E2E workflows triggered by the integration PR also passed.

### Security / repository cross-check

- CodeQL run `36558573422`: SUCCESS
- generic `Tests` run `36558573426`: overall FAILURE

The generic Tests failure is recorded rather than hidden. Its successful jobs include:

- `postgres-compat`: SUCCESS
- backend integration tests: SUCCESS
- frontend tests: SUCCESS
- docker verification: SUCCESS
- website checks: SUCCESS

Its failing repository-wide jobs are broader hygiene/tooling gates:

- workflow security audit (`zizmor`);
- frontend static lint;
- backend Ruff/format check;
- test inventory hygiene;
- generic unit job, including the known missing-`ffmpeg` environment failure;
- aggregate `ci-required` as a consequence.

These repository-wide failures are separate from the dedicated H3 Phase 5/6 acceptance gates, which are green.

## 3. Preserved architecture authorities

The main integration preserves the accepted authorities and safety boundaries:

1. Canonical Shot IR remains factual authority.
2. Provider Prompt remains a compiled execution artifact.
3. Preview/runtime Prompt SHA lock remains mandatory.
4. Phase 4 Media QA remains the structured QA boundary.
5. `H3FailureClass` remains the failure taxonomy.
6. `plan_h3_media_repair()` remains the only repair policy.
7. Phase 5 Repair Ticket remains the provider-repair scope primitive.
8. Approval remains immutable and scope-bound.
9. Stale approval blocks before spend.
10. Provider-call allowance is reserved before submission.
11. Duplicate execution cannot duplicate provider spend.
12. Re-QA remains mandatory before formal selection.
13. Failed candidates remain history-only.
14. UNKNOWN remains human-review-only.
15. Phase 6 batch coordination is not a second approval primitive.
16. Phase 6 does not introduce a second repair queue or MiniMax transport.
17. No live paid MiniMax call is required for the Phase 6 CI acceptance chain.

## 4. Pull-request cleanup

Evidence-only / temporary validation PRs that explicitly were not intended to merge have been closed without merge:

- #1
- #4
- #5
- #6
- #7
- #8
- #9
- #12
- #13
- #14

The two remaining Canonical Director legacy drafts have now been resolved:

- #3 — closed without merge as **superseded**. Its own Backend unit run had six CanonicalDirectorV1 validation failures, and adopting it would have introduced a second strict internal contract beside the accepted CanonicalDirectorBundle/raw Canonical Shot IR ingress.
- #2 — closed without merge as **superseded** after its still-valid rich-field rendering behavior was ported onto current `main` through PR #18.

PR #18 acceptance on the current lineage:

- head commit: `b0eaa4fc6de490b0791217254e6de3af1ea00fa4`
- merge commit: `f9a3e9bd64c8b61f5db8630f8406a16b4e513670`
- H3 Phase 5 Master Acceptance run `36591052727`: SUCCESS
- CodeQL run `36591052892`: SUCCESS
- Backend integration: SUCCESS
- PostgreSQL compatibility: SUCCESS
- Backend unit suite: `9305 passed`; only the same two missing-`ffmpeg` failures seen on the accepted integration baseline
- backend-static: 36 errors, unchanged from PR #16 baseline
- test-lint: 5 existing violations, unchanged from PR #16 baseline

The compatibility port preserves the existing CanonicalDirectorBundle ingress and only enriches H3 prompt rendering for already-authored Canonical facts such as framing, angle, composition, lighting, color grade, environment, subject state, continuity, transition, negative constraints, SFX/diegetic sound, and authored dialogue delivery state.

No branches were deleted as part of this cleanup.

## 5. Handoff rule for future work

Future work must begin from the current `main` lineage and must preserve the identities above.

Do not:

- relabel a documentation-only commit as the Phase 6 tested SHA;
- reopen closed paid-provider acceptance without an explicit reason;
- resurrect legacy PR #2/#3 directly; their resolution is recorded above and #18 is the accepted compatibility port;
- start a new Phase implicitly.

A new Phase requires an explicit charter before implementation starts.

## 6. Stop boundary

At this handoff boundary:

**Phase 1–6 are CLOSED and integrated into `main`.**

The Canonical Director legacy audit is also CLOSED: #2/#3 are resolved, and the accepted rich-field compatibility port is in `main` at `f9a3e9bd64c8b61f5db8630f8406a16b4e513670`.

No Phase 7 or other new Phase has been opened.
