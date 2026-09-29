# Phase 3 — H3 Production Policy

Phase 3 turns the six representative MiniMax H3 supplier-unit lessons into reusable
ArcReel production policy.

## Gate

The representative acceptance set is closed:

- E12U06 — FINAL PASS
- E4U02 — FINAL PASS
- E13U01 — FINAL PASS
- E13U03 — FINAL PASS
- E11U02 — FINAL PASS
- E15U03 — FINAL PASS

## First system-level delta

The first Phase 3 delta introduces a pure, fail-closed repair planner:

```text
Media QA failure
    ↓
H3FailureClass
    ↓
plan_h3_media_repair()
    ├─ regenerate_shot
    ├─ deterministic_surface_repair
    ├─ deterministic_text_plate
    ├─ deterministic_av_retime
    ├─ audio_repair_remux
    ├─ recompile_dialogue_detached
    ├─ regenerate_with_identity_bridge
    └─ escalate
```

The planner follows one core rule:

> Repair granularity should match failure granularity.

It does not call a provider. Unknown failures fail closed and require review.

## Representative lessons encoded

- E12U06: broad semantic / invented-content failure → regenerate the shot.
- E4U02: dialogue visualization → recompile with a dialogue-detached visual channel;
  identity continuity failure → regenerate with an identity bridge.
- E13U01: exact canonical screen text → deterministic text plate.
- E13U03: multi-scene semantic failures remain shot-scoped rather than unit-wide.
- E11U02: small local non-canonical text/UI contamination → deterministic surface repair
  while preserving accepted audio when possible.
- E15U03: correct content with wrong cut points → deterministic A/V retime, never video-only padding.

## Next gates

1. Wire structured Media QA findings into the planner.
2. Add a deterministic cut detector and media evidence schema.
3. Convert the six accepted units into a joint regression suite.
4. Run full project regression before enabling policy-driven repair in production.
