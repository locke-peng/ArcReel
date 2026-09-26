# H3 Phase 3 production integration and legacy retirement — FINAL PASS

Date: 2026-09-26 (UTC+8)

## Verdict

**Phase 3 third stage = FINAL PASS.**

The generic H3 deterministic repair layer is now connected to ArcReel's production queue as an independent post-provider task, and the E11U02/E15U03 Unit-specific repair executors have been retired from the active tree.

No MiniMax H3 provider call was made during this stage.

## Production architecture

The production chain is now:

```text
Reference Video Request Projection
→ Queue / Checkpoint
→ Provider / Runtime Evidence
→ dense QA / normalized observations
→ shared H3 repair planner
→ h3_media_repair (local worker lane)
→ deterministic repair executor
→ VersionManager guarded selection
→ extended SHA-linked Evidence Chain
```

The repair task is intentionally downstream of provider generation. It does not modify `execute_reference_video_task()` and does not alter request projection, provider submission, polling, paid-output recovery, or H3 prompt compilation.

## New production task

Task type:

`h3_media_repair`

Worker routing:

- `media_type=local`
- `provider_id=local`
- default local concurrency: `LOCAL_MAX_WORKERS=2`
- provider client dependency: none
- provider credential dependency: none
- paid generation call: none

API entry:

`POST /api/v1/projects/{project_name}/reference-videos/episodes/{episode}/units/{unit_id}/media-repair`

The endpoint validates the repair plan before enqueue and verifies that the reviewed source SHA still matches the current formal video.

## Executable repair classes

The production task currently permits only repair classes that are deterministic against the current reviewed video:

- `deterministic_pixel_sanitization`
- `deterministic_av_retime`

Normalized semantic observations such as identity, scene, action, or story-fact failures resolve to `regenerate_shot` in the shared planner and are rejected by the local repair task.

`deterministic_text_plate` remains an executor primitive but is not exposed as a whole-current-video repair operation; exact text plates normally belong to a multi-source authoring plan.

## Source/version concurrency guard

Every production repair request requires:

`expected_source_sha256`

The worker proves:

1. current formal reference video exists;
2. current SHA equals the reviewed SHA;
3. current SHA is present in the persisted H3 Evidence Chain;
4. the current reference-video version is tracked;
5. the same source SHA and version are still current when VersionManager selects the derived result.

If the source changes during repair, the derived output is not selected.

## Evidence

`EvidenceChain.from_json()` now reloads and revalidates persisted hash graphs.

A successful repair appends a deterministic repair node whose parent is the exact reviewed source SHA. Evidence metadata records:

- normalized QA observations;
- planner-selected action;
- `provider_recalled=false`.

The evidence sidecar is updated only when VersionManager selects the repaired version.

## Local worker restart policy

A running local repair has no remote provider job to resume.

If the worker process is restarted while a local repair task is marked running, ArcReel fails that task closed instead of automatically replaying it. The caller re-reviews the current source and submits a fresh SHA-bound repair plan.

This avoids selecting a stale repair if the previous process completed the version transaction but exited before writing the queue terminal state.

## Legacy executor retirement

Removed from the active branch:

- `scripts/experiments/run_e11u02_v3_deterministic_repair.py`
- `scripts/experiments/run_e15u03_v2_deterministic_timeline.py`
- `.github/workflows/h3-e11u02-v3-repair.yml`
- `.github/workflows/h3-e15u03-v2-repair.yml`
- `.github/live-tests/e11u02-v3-request.txt`
- `.github/live-tests/e15u03-v2-request.txt`
- `tests/unit/test_e11u02_v3_repair_contract.py`
- `tests/unit/test_e15u03_v2_timeline_contract.py`

Their historical acceptance evidence remains recoverable from Git history and the existing E11U02/E15U03 final acceptance documents.

E13U01 provider-generation scripts remain active historical evidence because they are not superseded repair executors.

## ADR

Architecture decision:

`docs/adr/0083-h3-post-provider-repair-local-evidence-bound-task.md`

## Final CI

Workflow:

`H3 Phase 3 Production Integration`

Final run:

`36242557538`

Tested commit:

`0077e37de65c4ef46bd17cd2f3fcf1ed98b0aeac`

Result:

**SUCCESS**

Gates:

- production repair integration tests: PASS
- 27 tests passed
- production integration compile: PASS
- Ruff: PASS
- provider-dependency gate: PASS
- provider calls: 0

The integration test performs real FFmpeg media generation/repair against a temporary ArcReel project, writes a provider Evidence Root, runs the production repair worker, commits the derived version through VersionManager, and verifies that the Evidence Chain extends from the original provider SHA.

Additional tests verify:

- semantic regeneration cannot enter the local repair executor;
- declared action cannot disagree with the shared QA planner;
- persisted Evidence Chains are revalidated when loaded;
- stale reviewed SHA fails closed;
- API enqueue uses only the local lane;
- worker provider projection resolves `h3_media_repair` to `local`;
- enqueue identity resolves to local without loading a project/provider configuration.

## Production conclusion

The following distinction is now enforced by production code rather than Unit-specific acceptance scripts:

```text
bounded deterministic defect
→ local deterministic repair
→ no provider recall

semantic defect
→ regenerate_shot
→ normal provider generation path
```

The production invariant remains:

> deterministic repair may remove model-invented local material or restore validated timing; it must never invent missing Canonical story facts.
