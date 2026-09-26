# ADR 0083: H3 post-provider repair is a local evidence-bound production task

Status: Accepted  
Date: 2026-09-26

## Context

MiniMax H3 supplier acceptance established three distinct outcomes:

1. provider output is content-correct and can be selected directly;
2. provider output has a bounded deterministic defect (for example localized invented text or exact editorial timing drift);
3. provider output has a semantic defect (identity, scene, action, missing story fact) and must return to regeneration/review.

Phase 3 real-evidence migration proved that deterministic repairs can be reproduced by generic executors without another provider call. The remaining architecture question was where those executors belong in ArcReel's production task chain.

Running repair inside `execute_reference_video_task()` is incorrect: the provider call owns request projection, submission checkpoint, polling and paid-output recovery. QA observations only exist after provider/runtime evidence exists, and a repair plan must be bound to the exact reviewed source bytes.

## Decision

H3 deterministic post-processing is a separate queued task:

```text
reference_video provider task
→ Provider / Runtime Evidence
→ dense QA / normalized observations
→ shared H3 repair planner
→ h3_media_repair (local lane)
→ deterministic executor
→ VersionManager selection
→ extended Evidence Chain
```

### Local lane

`h3_media_repair` uses `media_type=local` and `provider_id=local`.

It does not consume a video-provider concurrency slot and has no provider client, API key, generation backend or polling dependency. `LOCAL_MAX_WORKERS` controls local deterministic concurrency (default 2).

### Fail-closed source binding

Every repair request must include `expected_source_sha256`.

The worker checks:

- the current formal video exists;
- its SHA equals the reviewed SHA;
- the SHA is present in the persisted H3 Evidence Chain;
- the current reference-video version is tracked;
- the version and source SHA are still current when selection occurs.

If any check fails, the repaired output is not selected.

### QA planner owns action selection

The request carries normalized QA observations. The shared planner decides the repair class.

The production task currently executes only:

- `deterministic_pixel_sanitization`;
- `deterministic_av_retime`.

Semantic observations resolve to `regenerate_shot` and are rejected by the local task. The local task never converts semantic defects into pixel/timeline edits.

`deterministic_text_plate` remains a lower-level executor primitive. It is not exposed as a whole-current-video repair action because exact text plates normally participate in a multi-source authoring plan rather than replacing an entire current clip.

### Evidence and version selection

The repair output becomes a derived reference-video version only through the normal VersionManager selection transaction.

The persisted H3 Evidence Chain is extended with the deterministic repair node and parent SHA. The evidence sidecar is written only when the derived version is selected.

A local repair task orphaned by process restart is marked fail-closed rather than automatically replayed. The operator/client re-reviews the current source and submits a fresh SHA-bound plan.

## Legacy executor retirement

After production integration passed, the Unit-specific E11U02 v3 and E15U03 v2 repair executors were removed from the active tree:

- `scripts/experiments/run_e11u02_v3_deterministic_repair.py`;
- `scripts/experiments/run_e15u03_v2_deterministic_timeline.py`;
- their dedicated GitHub workflows, trigger files and contract tests.

They remain recoverable from Git history and their final acceptance documents remain in `docs/experiments/`.

The E13U01 provider-generation scripts are retained because they are historical provider evidence generators, not superseded repair executors.

## Consequences

Positive:

- bounded defects no longer require Unit-specific production scripts;
- deterministic repair cannot silently operate on a newer regenerated clip;
- repair work cannot consume or accidentally call a paid provider;
- VersionManager and Evidence Chain remain the production truth sources;
- semantic defects still fail closed to regeneration.

Trade-offs:

- dense QA/review must produce normalized observations and deterministic coordinates/timeline facts;
- exact-text multi-source authoring needs a future production authoring-plan task if it is to be exposed beyond current accepted workflows;
- local CPU repair now has its own worker capacity setting.
