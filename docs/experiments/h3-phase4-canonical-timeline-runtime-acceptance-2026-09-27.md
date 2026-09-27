# Phase 4 H3 Auto-Repair Loop — Canonical Timeline Runtime Acceptance — 2026-09-27

## Verdict

**PHASE 4 CANONICAL TIMELINE RUNTIME GATE: FINAL PASS**

This acceptance closes the Canonical-timeline trusted Media QA producer and deterministic
A/V-retime runtime-handler slice. It does not close Phase 4 as a whole.

Stage facts remain:

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  IN PROGRESS
```

No paid MiniMax provider generation was performed by this acceptance.

## Tested branch and code

Branch:

`phase4/h3-auto-repair-loop`

Tested code SHA:

`6115d37c4bd1300f65579223ee54146c7b0847d4`

Primary GitHub Actions run:

`36284408790`

Conclusion:

`success`

Any documentation-only commit after this SHA is not the tested code SHA.

## Runtime timeline implementation

The trusted timeline producer/handler lives in:

`lib/reference_video/h3_timeline_runtime.py`

It derives target editorial boundaries from Canonical Director shot starts and evaluates
actual media cuts from the final MP4. Its production path is:

```text
Canonical Director shot starts
→ H3CanonicalTimeline
→ actual-media Cut Detector
→ MediaQAFinding(TIMELINE_ONLY_FAILURE)
→ existing H3FailureClass
→ existing plan_h3_media_repair()
→ DETERMINISTIC_AV_RETIME
→ runtime deterministic handler
→ Re-QA
→ formal selection only after PASS
```

No second timeline repair policy was created.

## Important failure discovered during integration

The first production-runtime attempt exposed a real algorithmic defect.

Failed Run:

`36282629462`

At that point all software gates passed, but E15U03 actual-media replay failed:

```text
SSIM vs formally accepted final = 0.945848
required minimum                = 0.99
```

The defect was not in the accepted supplier evidence and not in the Phase 3 repair policy.

The initial generic runtime retimer used:

```text
source boundaries =
0
→ actual cut 1
→ actual cut 2
→ physical end of provider file
```

For E15U03 the provider file contains extra tail frames after the canonical third beat.
That implementation therefore compressed those extra tail frames into the final 5-second
Canonical shot.

This changed the accepted motion timing and reduced visual equivalence.

## Corrected timeline semantics

The runtime retimer now applies this rule independently to each Canonical segment:

```text
source_frames = min(actual_available_segment_frames, canonical_target_frames)
```

Meaning:

- an early/short provider beat may be stretched to its Canonical target duration;
- an overlong provider beat is tail-trimmed to one Canonical target window;
- excess tail frames are not compressed into the Canonical shot;
- timing debt from an earlier cut is not pushed into a later shot;
- picture and matching audio are still retimed together.

This preserves the Phase 2/3 lesson:

> Timeline repair must restore Canonical editorial windows without changing already-correct
> semantic content more than necessary.

A dedicated regression now locks the E15-style final-beat case:

```text
third source beat starts at frame 222
canonical target length = 120 frames
runtime source window    = frame 222..342
video PTS factor         = 1.0
audio atempo             = 1.0
provider tail after 342  = discarded
```

## Automated software gates

Run `36284408790`:

```text
Phase 4 auto-repair/runtime tests          35 passed
Phase 3 production-policy regression      11 passed
Six representative Unit joint regression  41 passed
H3 compiler + Preview/Runtime lock         13 passed
Reference Video + H3 subsystem            405 passed
Python compile                              PASS
Ruff                                        PASS
```

## E15U03 — production runtime-gate replay

Existing immutable supplier source:

```text
supplier run      = 36009732060
supplier artifact = 10812256991
source SHA256     = 17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36
```

Formally accepted final:

```text
acceptance run      = 36201168299
acceptance artifact = 10892326037
accepted SHA256     = 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b
```

### Actual source cuts

The runtime Cut Detector again measured the source MP4 itself:

```text
actual cut 1 = frame 118 = 4.91667s
target cut 1 = frame 120 = 5.00000s

actual cut 2 = frame 222 = 9.25000s
target cut 2 = frame 240 = 10.00000s
```

Structured finding:

`TIMELINE_ONLY_FAILURE`

Existing planner decision:

`DETERMINISTIC_AV_RETIME`

Provider recall:

`false`

### Runtime-gate execution

Runtime gate result:

```text
status           = PASS
repair_passes    = 1
provider_recalled = false
```

Pass 0:

```text
finding
→ timeline_only_failure

planner
→ deterministic_av_retime

input SHA256
= 17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36

output SHA256
= 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b
```

Pass 1:

```text
findings = []
plans    = []
```

### Re-QA

Final detected cuts:

```text
frame 120 = 5.00000s
frame 240 = 10.00000s
delta     = 0 / 0
```

Final media:

```text
duration    = 15.000s
resolution  = 864x480
video       = H.264 / 24 fps
audio       = AAC / 32 kHz / stereo
size        = 4,798,939 bytes
```

Final SHA256:

`607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b`

It is byte-identical to the formally accepted E15U03 final.

Visual equivalence:

`SSIM = 1.0`

Evidence-chain head:

`8fd05c340faa24c6121f2c7546259dfee06bc03d01804d08d3eb5651e3a3f990`

**E15U03 production timeline runtime replay: FINAL PASS**

## Regression controls

The same acceptance run also reconfirmed E11U02:

```text
provider_recalled = false
final SHA256
= 7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949
SSIM vs formally accepted final = 1.0
evidence-chain head
= 45e2d79943623e8a5106fdda951b4c0dcb3bd5d4d9ed5c6b71ca8187c299e0ce
```

E13U01 exact-text E2E also remained PASS in the same workflow.

## Evidence artifacts

E11U02 + E15U03:

```text
Artifact ID
= 10920425753

Name
= phase4-auto-repair-loop-e2e-evidence

Digest
= sha256:19dbe3b16d9c31663608a530061066d2d90b4d601f7f63de6811a9ae5f1ad1fc
```

E13U01:

```text
Artifact ID
= 10920296323

Name
= phase4-e13u01-exact-text-e2e-evidence

Digest
= sha256:ca5b408038f3bb4cd92e3e4d05e88dbf6c5e98cc4a1cf27393846991bbbcf20c
```

## Gate conclusion

```text
Canonical timeline producer                 PASS
Actual-media cut detection                  PASS
Existing Phase 3 timeline policy reused     PASS
Production runtime deterministic handler    PASS
Picture + matching audio retime             PASS
Overlong provider tail trimming             PASS
Re-QA before formal selection               PASS
E15U03 actual-media runtime replay           FINAL PASS
E11U02 regression                            FINAL PASS
E13U01 regression                            FINAL PASS
Provider recalled                            false
New paid MiniMax generation                  none
```

Phase 1, Phase 2, and Phase 3 remain CLOSED.

Phase 4 remains active. The next production work should add the next trusted Media QA
producer/handler only where Canonical provides enough deterministic facts; it must not invent
a generic pixel-level semantic detector or weaken the existing fail-closed selection gate.
