# Phase 3 H3 Production Policy — Regression Acceptance — 2026-09-27

## Verdict

**PHASE 3 REGRESSION GATE: PASS**

Tested code SHA: `05cfb415a59f0972eb3c603807c4ff64dc79bbb5`

Primary GitHub Actions run: `36267589882`

Media replay artifact:
- artifact id: `10914193204`
- name: `phase3-deterministic-media-replay`
- artifact digest: `sha256:9fddcb6fd9c0ad9a3cee5a1352f47f548ad25a4f86e15c7115829329913cf056`

No MiniMax provider generation was performed by the deterministic media replay job.

## Gate history

1. Run `36249344504` — FAIL before policy tests because the focused workflow installed
   only pytest/ruff and ArcReel's root conftest required SQLAlchemy.
   Fix: use the repository's normal `uv sync` environment.
2. Run `36267148167` — PASS: 11 Phase 3 policy tests + compile + Ruff.
3. Run `36267279237` — 40 PASS / 1 FAIL in the six-unit joint regression.
   The only failure was a newly-added E12U06 test asserting an incorrect exact wording
   (`no readable language...`) while the accepted prompt says
   `never by readable language...`. Production prompt was unchanged.
4. Run `36267369818` — PASS: 11 policy + 41 six-unit + 13 compiler/preview tests.
5. Run `36267458777` — PASS: previous gates plus 373 Reference Video/H3 subsystem tests.
6. Run `36267589882` — PASS: all software gates plus deterministic media replay.

## Automated regression results

Run `36267589882`:

- Phase 3 production policy: **11 passed**
- six representative Unit joint regression: **41 passed**
- H3 compiler + preview/runtime lock: **13 passed**
- Reference Video + H3 subsystem regression: **373 passed**
- total pytest assertions in the run: **438 passed**
- Python compile: **PASS**
- Ruff: **PASS**

Representative Unit contract set:
- E12U06
- E4U02
- E13U01
- E13U03
- E11U02
- E15U03

## Deterministic media replay

### E11U02

Source supplier evidence:
- run: `36148270693`
- artifact: `10870732082`
- artifact digest:
  `sha256:958e1f625f48acb46701b28f6e353de9841532012fdf3db88ff6792a0b3ffabc`

Replay:
- repair: `v3_deterministic_text_surface_scrub`
- provider recalled: **false**
- final duration: **15.000000s**
- final resolution: **864x480**
- video: **H.264 / 24 fps**
- audio: **AAC / 32 kHz / stereo**
- final video SHA256:
  `4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18`

Visual review:
- Shot 1: screen surfaces are defocused while the foreground physical status module remains visible.
- Shot 2: the hallucinated badge typography region is locally scrubbed while the hand/badge action remains.
- Shot 3: side media / exit-sign regions are defocused while the central canonical pair remains readable as subjects.
- frame 119 -> 120 is the Shot 1 / Shot 2 boundary.
- frame 239 -> 240 is the Shot 2 / Shot 3 boundary.
- no full-frame masking or unrelated scene replacement was observed.

**E11U02 Phase 3 replay: PASS**

### E15U03

Source supplier evidence:
- run: `36009732060`
- artifact: `10812256991`
- artifact digest:
  `sha256:e08dd2437e963d496cfeabc9962d6518df7ac2a1845271b8422ae964ab95f308`

Replay:
- repair: `v2_deterministic_5_5_5_av_retime`
- provider recalled: **false**
- source cuts: frame 118 and frame 222
- target shot frames: 120 / 120 / 120
- final duration: **15.000000s**
- final resolution: **864x480**
- video: **H.264 / 24 fps**
- audio: **AAC / 32 kHz / stereo**
- final video SHA256:
  `208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de`

Visual review:
- Shot 1 remains the TIANSHU NEXT summit stage.
- Shot 2 remains the audience reaction.
- Shot 3 remains C01 entering from the stage-wing door.
- frame 119 is still Shot 1 and frame 120 is Shot 2.
- frame 239 is still Shot 2 and frame 240 is Shot 3.
- therefore authored boundaries are exactly 5.000s and 10.000s at 24 fps.
- the repair retimes picture and matching audio together; it does not freeze the previous
  shot's tail to fill the target window.

**E15U03 Phase 3 replay: PASS**

## Phase 3 conclusion

The first production-policy delta is now validated at four levels:

1. pure repair-decision policy;
2. six representative Unit contracts;
3. Reference Video/H3 subsystem regression;
4. actual MP4 deterministic repair replay from SHA-pinned paid supplier evidence.

The core production rule is accepted:

> Repair granularity must match failure granularity.

The next implementation gate is to connect structured Media QA findings to
`plan_h3_media_repair()` and add the cut detector/evidence schema without weakening the
existing fail-closed provider gate.
