# Phase 4 H3 Auto-Repair Loop — Six-Unit Routing + Exact-Text Acceptance — 2026-09-27

## Verdict

**PHASE 4 SECOND INTEGRATION GATE: FINAL PASS**

This acceptance extends the first Phase 4 E11U02/E15U03 auto-repair gate with:

- one unified auto-repair orchestration entry point;
- automatic routing contracts covering all six representative Units;
- provider-required routes that fail closed by default;
- a real-media E13U01 deterministic exact-text replay;
- a corrected deterministic-output equivalence rule that pins immutable inputs while
  validating re-encoded output by Canonical/media semantics rather than unstable encoder bytes.

Project stage facts remain:

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  IN PROGRESS
```

The six representative Units remain FINAL PASS regression baselines. No Unit was reopened
for prompt tuning and no paid MiniMax generation was performed.

## Tested branch and code

Branch:

`phase4/h3-auto-repair-loop`

Tested code SHA:

`3dab2d3b7c7fb6c0653e5a08d3adca62dcbdb273`

Primary GitHub Actions run:

`36281464195`

Conclusion:

`success`

Any documentation commit after this SHA is not the tested code SHA.

## New orchestration layer

Added:

`lib/reference_video/h3_auto_repair_loop.py`

The orchestration is intentionally policy-free:

```text
MediaQAFinding
    ↓
classify_h3_media_finding()
    ↓
existing H3FailureClass / H3MediaFailure
    ↓
existing plan_h3_media_repair()
    ↓
existing H3RepairDecision
    ↓
execute_h3_media_repair()
```

No second failure taxonomy, repair enum, or repair planner was created.

Provider-required decisions remain disabled unless provider execution is explicitly enabled.
Therefore unknown / regeneration-required routes cannot silently spend supplier credits.

## Six representative Unit routing matrix

The Phase 4 routing regression now locks these representative paths:

```text
E12U06
invented content / topology semantic failure
→ LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ provider required
→ fail closed by default

E4U02
dialogue visual leakage
→ DIALOGUE_VISUALIZATION
→ RECOMPILE_DIALOGUE_DETACHED
→ provider required
→ fail closed by default

E4U02
identity drift
→ IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
→ provider required
→ fail closed by default

E13U01
exact canonical typography
→ EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE
→ provider recall false

E13U03
actual local non-canonical surface pollution
→ LOCAL_NONCANONICAL_SURFACE
→ DETERMINISTIC_SURFACE_REPAIR
→ provider recall false

E13U03
semantic-only log state without a recognized concrete media failure
→ UNKNOWN
→ ESCALATE
→ provider recall false

E11U02
local non-canonical surface
→ LOCAL_NONCANONICAL_SURFACE
→ DETERMINISTIC_SURFACE_REPAIR
→ provider recall false

E15U03
actual cut timing failure
→ TIMELINE_ONLY_FAILURE
→ DETERMINISTIC_AV_RETIME
→ provider recall false
```

This matrix is a routing contract over the existing Phase 3 policy. It does not replace it.

## Software regression results

Run `36281464195`:

```text
Phase 4 auto-repair + six-unit routing tests    19 passed
Phase 3 production-policy regression           11 passed
Six representative Unit joint contracts        41 passed
H3 compiler + Preview/Runtime lock              13 passed
Reference Video + H3 subsystem                 392 passed
Python compile                                  PASS
Ruff                                            PASS
```

## E13U01 — real deterministic exact-text replay

Existing accepted supplier evidence:

```text
supplier run       = 36098803663
supplier artifact  = 10848054150
```

Pinned source evidence:

```text
exact screen plate
6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57

accepted H3 entrance plate
e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f

detached canonical audio
cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33

formally accepted final reference
8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12
```

Structured finding:

`exact canonical identity typography must not be delegated to probabilistic video generation`

Automatic route:

```text
EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE
→ provider_recalled = false
```

Exact text:

```text
沈知意
天枢联合创始人
```

Replay result:

```text
duration       = 10.000s
resolution     = 1280x720
video          = H.264 / 24 fps
audio          = AAC / 32 kHz / stereo
authored cut   = frame 120 = 5.000s
final SHA256   = 9c304decd87bc3f2c441954a74d998d5a54b575d4975a936bf2f94ad85f5defb
video SSIM vs formally accepted final = 0.999983
provider_recalled = false
```

Decoded audio equivalence digest:

`842174439856b66ef4119f32f3ddf1052d32ca83bc3cff44d736bf281578af0b`

Evidence-chain head:

`a68a6b3d197ff753c654fe5c5dfb7dc67337c0d936aeab157716316f78cf3afb`

Artifact:

```text
ID      = 10919285860
Name    = phase4-e13u01-exact-text-e2e-evidence
Digest  = sha256:9183386d515fbc07ef82ba9143c6a137f9416e4513e8bc3ccd9a29ba2ec7e769
```

Targeted visual review confirms the first five seconds retain the exact two-line identity
plate, frame 119 remains the screen plate, frame 120 changes to the stage-wing entrance,
and the following frames preserve the accepted C01 entrance composition.

**E13U01 Phase 4 exact-text replay: FINAL PASS**

## E11U02 / E15U03 replay-equivalence correction

Run `36281050961` exposed an acceptance-test defect rather than a content regression.

The old Phase 4 replay test required current output MP4 bytes to equal a prior Phase 3 replay
SHA. On a later GitHub runner/FFmpeg environment, E11U02 regenerated the exact original
formally accepted v3 final:

`7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949`

but the test incorrectly expected another valid Phase 3 replay encoding:

`4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18`

Therefore encoded-output byte identity was removed as a mandatory equivalence condition.

The corrected rule is:

> Immutable supplier inputs and accepted reference inputs are SHA-pinned exactly. A newly
> encoded deterministic output must satisfy its Canonical/media contract and compare
> successfully against the formally accepted media. Encoded container bytes are evidence,
> but are not a cross-encoder semantic identity test.

The corrected gate does **not** loosen source provenance, Canonical timing, provider recall,
or content QA.

## E11U02 corrected replay result

Source supplier evidence:

```text
run       = 36148270693
artifact  = 10870732082
```

Formally accepted reference:

```text
run       = 36169166450
artifact  = 10879951993
SHA256    = 7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949
```

Latest Phase 4 replay:

```text
repair action        = deterministic_surface_repair
provider_recalled    = false
duration             = 15.000s
resolution           = 864x480
video                = H.264 / 24 fps
audio                = AAC / 32 kHz / stereo
final SHA256         = 7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949
SSIM vs accepted     = 1.0
```

Evidence-chain head:

`b338ac92e2c7ecbe4fcbcda473ff8811e0cce41711753f13cc1008ab920ef5ce`

Targeted boundary review again confirms the laboratory, badge-placement, and media-entry
beats remain intact with local-only surface repair.

**E11U02 corrected Phase 4 replay: FINAL PASS**

## E15U03 corrected replay result

Source supplier evidence:

```text
run       = 36009732060
artifact  = 10812256991
```

Formally accepted reference:

```text
run       = 36201168299
artifact  = 10892326037
SHA256    = 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b
```

Actual source cuts detected again from source media:

```text
frame 118 = 4.91667s
frame 222 = 9.25000s
```

Latest authored cuts:

```text
frame 120 = 5.00000s
frame 240 = 10.00000s
```

Latest replay:

```text
repair action        = deterministic_av_retime
provider_recalled    = false
duration             = 15.000s
resolution           = 864x480
video                = H.264 / 24 fps
audio                = AAC / 32 kHz / stereo
final SHA256         = 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b
SSIM vs accepted     = 1.0
```

Evidence-chain head:

`6be2e355eee3ced276e6a296f13573ae923f4cc370e8306e38ad50683cc28d26`

Targeted boundary review confirms:

- frame 119 remains the TIANSHU NEXT stage;
- frame 120 is the audience/media beat;
- frame 239 remains the audience/media beat;
- frame 240 begins C01 entering from stage wing.

**E15U03 corrected Phase 4 replay: FINAL PASS**

## Latest E11U02 + E15U03 evidence artifact

```text
ID      = 10919046991
Name    = phase4-auto-repair-loop-e2e-evidence
Digest  = sha256:2b01501f2802c0e9dffee0049f9932c33f79da89558c6b6bbc77d99a74745f61
```

## Gate conclusion

```text
Unified orchestration                         PASS
Existing Phase 3 policy remains sole policy   PASS
Six representative Unit auto-routing          PASS
Provider-required routes fail closed          PASS
E13U01 exact-text actual-media replay          FINAL PASS
E11U02 deterministic surface replay            FINAL PASS
E15U03 actual-cut + A/V retime replay          FINAL PASS
No unintended provider call                    PASS
Evidence hash chains                           PASS
Targeted visual review                         PASS
```

Phase 1, Phase 2, and Phase 3 remain CLOSED.

Phase 4 remains active for the remaining production-runtime integration work. This document
is the accepted baseline for subsequent runtime wiring; later work must not reintroduce a
second repair policy or restore encoded-output byte identity as the only media-quality gate.
