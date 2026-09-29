# Phase 4 H3 Auto-Repair Loop — First End-to-End Acceptance — 2026-09-27

## Verdict

**PHASE 4 FIRST AUTO-REPAIR E2E GATE: FINAL PASS**

This document closes the first Phase 4 implementation/acceptance slice only. It does not
reopen or redefine earlier phases, and it does not claim that all later Phase 4 work is
finished.

Stage facts remain:

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  IN PROGRESS
```

The six representative Units remain closed regression baselines, not unfinished cases.

## Branch and tested code

Branch:

`phase4/h3-auto-repair-loop`

Tested code SHA:

`e4a43254382b2783a2ce22ddf12109d1fc7ba8bd`

Primary GitHub Actions run:

`36271305282`

Workflow conclusion:

`success`

The acceptance document is added after the tested code SHA as documentation-only history.
Do not rewrite the documentation commit as the tested code SHA.

## Phase 4 first-batch implementation

Implemented in the requested order:

1. `lib/reference_video/media_qa_schema.py`
2. `lib/reference_video/h3_failure_classifier.py`
3. `lib/reference_video/h3_repair_executor.py`
4. `lib/reference_video/cut_detector.py`
5. `lib/reference_video/evidence_schema.py`

Supporting E2E integration:

- `scripts/experiments/run_phase4_auto_repair_e2e.py`
- `tests/unit/lib/reference_video/test_h3_auto_repair_loop.py`
- `.github/workflows/h3-phase4-auto-repair-loop.yml`

No second repair taxonomy or repair planner was created.

The Phase 4 classifier imports and emits the existing Phase 3 `H3FailureClass`.
The only repair-decision owner remains:

`plan_h3_media_repair()`

The executor consumes the resulting `H3RepairDecision`; it does not reimplement repair
policy. Provider-required decisions fail closed unless provider execution is explicitly
enabled. The first E2E workflow does not inject a MiniMax API key and contains no provider
Create step.

## Software gates

Run `36271305282`:

```text
Phase 4 auto-repair primitive tests          8 passed
Phase 3 repair-planner regression           11 passed
6 representative Unit joint regression      41 passed
H3 compiler + Preview/Runtime lock           13 passed
Reference Video + H3 subsystem              381 passed
Python compile                               PASS
Ruff                                         PASS
```

An earlier run, `36271174199`, reached all functional gates successfully but failed the
final Ruff step on three style-only findings. The E2E job was therefore correctly skipped.
Only those style findings were changed; no repair-policy behavior was modified. Run
`36271305282` is the acceptance run.

## Phase 4 evidence artifact

Artifact:

```text
ID
= 10915817437

Name
= phase4-auto-repair-loop-e2e-evidence

Digest
= sha256:f0c3d42822a07ea67a7849a982765d3644070272b6a794f79c91a58b41489407
```

The artifact contains both final MP4 files, repair/evidence JSON, evidence hash chains, and
targeted review frames.

## End-to-end chain

The accepted first-slice chain is:

```text
Media QA
→ Structured Finding
→ Failure Classifier
→ existing plan_h3_media_repair()
→ Repair Executor
→ Re-QA
→ Evidence Hash Chain
→ FINAL PASS
```

For both accepted Units:

`provider_recalled = false`

No new MiniMax paid generation was performed.

---

## E11U02 — automatic deterministic surface repair

### Existing supplier evidence

```text
supplier run
= 36148270693

supplier artifact
= 10870732082
```

Pinned source media:

```text
Shot 1
aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48

Shot 2
7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507

Shot 3
ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751

Detached soundtrack
dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2
```

### Automatic route

Structured finding:

```text
local screen / badge / side-media non-canonical text pollution
affected_fraction = 0.05
provider_result_usable = true
audio_is_accepted = true
```

Classifier:

`LOCAL_NONCANONICAL_SURFACE`

Existing planner decision:

`DETERMINISTIC_SURFACE_REPAIR`

Provider recall:

`false`

### Actual final MP4

Independent post-artifact probe:

```text
duration    = 15.000000s
resolution  = 864x480
video       = H.264 / 24 fps
audio       = AAC / 32 kHz / stereo
size        = 2,847,562 bytes
```

Final media SHA256:

`4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18`

This is byte-identical to the Phase 3 visually accepted deterministic replay:

`4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18`

Targeted visual re-review from the new Phase 4 artifact also confirmed:

- laboratory physical-state beat remains visible while target screen surfaces are defocused;
- the badge placement action remains visible while the typography-risk area is locally scrubbed;
- the media-zone beat begins after the second boundary and preserves the intended central action;
- frame 119 → 120 is the first authored boundary;
- frame 239 → 240 is the second authored boundary;
- the repair remains local rather than replacing the whole scene.

Evidence-chain head SHA256:

`f3d3f4b1d56b8b79e1b9797af03a602fc5d91965f0dc939751d042ab258adf40`

**E11U02 Phase 4 first E2E: FINAL PASS**

---

## E15U03 — automatic actual-cut detection + deterministic A/V retime

### Existing supplier evidence

```text
supplier run
= 36009732060

supplier artifact
= 10812256991

supplier task
= 53944e96-e4b3-465f-b046-a8b6f111de3b
```

Pinned source video SHA256:

`17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36`

Pinned prompt SHA256:

`b8143dfe1e500a83d6f45f0ca133cf3fed9ab55c7ab6739686c11b0f1eb87dd0`

### Actual-media cut detection

The Phase 4 detector read the real source MP4 with ffmpeg scene-score evidence rather than
trusting prompt timestamps or the old hard-coded acceptance constants.

Detected source cuts:

```text
cut 1
actual frame = 118
actual time  = 4.91667s
target frame = 120
target time  = 5.00000s
delta        = -2 frames / -0.08333s
scene score  = 0.421828

cut 2
actual frame = 222
actual time  = 9.25000s
target frame = 240
target time  = 10.00000s
delta        = -18 frames / -0.75000s
scene score  = 0.343444
```

Structured finding:

`actual hard cuts do not land on canonical 5s / 10s boundaries`

Classifier:

`TIMELINE_ONLY_FAILURE`

Existing planner decision:

`DETERMINISTIC_AV_RETIME`

Provider recall:

`false`

### Re-QA of actual final MP4

Detected final cuts:

```text
frame 120 = 5.000s
frame 240 = 10.000s
delta = 0 / 0
```

Independent post-artifact probe:

```text
duration    = 15.000000s
resolution  = 864x480
video       = H.264 / 24 fps
audio       = AAC / 32 kHz / stereo
size        = 4,798,830 bytes
```

Final media SHA256:

`208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de`

This is byte-identical to the Phase 3 visually accepted deterministic replay:

`208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de`

Targeted visual re-review from the new Phase 4 artifact confirmed:

- frame 119 is still the TIANSHU NEXT main-stage shot;
- frame 120 is the audience shot;
- frame 239 is still the audience shot;
- frame 240 begins the C01 stage-wing entrance shot;
- the three visible beats remain stage → audience → C01 entrance;
- no tail-frame freeze is used to fake the target timing.

Evidence-chain head SHA256:

`f4f2785bb4ac8cbfb8d5160634ef23c003175a5576b931bd930ec1e285f52118`

**E15U03 Phase 4 first E2E: FINAL PASS**

---

## Acceptance conclusion

The requested first Phase 4 integration slice is now proven against actual media:

```text
Media QA Schema       PASS
Failure Classifier    PASS
Repair Executor       PASS
Cut Detector          PASS
Evidence Schema       PASS

E11U02 existing-evidence auto-repair E2E  FINAL PASS
E15U03 existing-evidence auto-repair E2E  FINAL PASS

provider_recalled                         false
new paid MiniMax generation               none
actual final MP4 probe                    PASS
targeted visual boundary review           PASS
evidence hash chain                       PASS
artifact upload                           PASS
```

Phase 1, Phase 2, and Phase 3 remain CLOSED.

Phase 4 is now active with its first end-to-end auto-repair gate accepted. Later Phase 4
work should build on this branch and evidence chain rather than re-running the closed
supplier-validation phases.
