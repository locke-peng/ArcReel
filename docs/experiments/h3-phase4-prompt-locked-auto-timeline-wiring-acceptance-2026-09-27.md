# Phase 4 H3 Auto-Repair Loop — Prompt-Locked Automatic Timeline Wiring Acceptance — 2026-09-27

## Verdict

**PHASE 4 PROMPT-LOCKED AUTOMATIC TIMELINE WIRING GATE: FINAL PASS**

This gate connects the already-accepted Canonical timeline Media QA producer and deterministic
A/V-retime handler into the formal reference-video task path without requiring test-only
evaluator injection.

It does not close Phase 4 as a whole.

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  IN PROGRESS
```

No paid MiniMax provider generation was performed by this acceptance replay.

## Tested code

Branch:

`phase4/h3-auto-repair-loop`

Tested SHA:

`022575ff81126012d0d6084bf1ad8b30175d28d7`

Primary GitHub Actions run:

`36284812267`

Conclusion:

`success`

## Production wiring

Updated production task path:

`server/services/reference_video_tasks.py`

New trusted resolver:

`_resolve_trusted_h3_runtime_bundle()`

Automatic timeline wiring is enabled only when all of the following are true:

1. a structured `canonical_director` is present;
2. that Canonical Director actually participated in H3 compilation;
3. `prompt_compilation.compiler_applied == true`;
4. the Provider Prompt has already passed the Preview/Runtime expected-SHA lock;
5. no explicitly injected trusted evaluator has been supplied.

The resulting automatic bundle is created through:

`build_h3_timeline_runtime_bundle()`

The runtime still uses the existing chain:

```text
Canonical shot starts
→ actual-media cut detector
→ MediaQAFinding
→ existing H3FailureClass
→ existing plan_h3_media_repair()
→ existing runtime selection gate
→ deterministic A/V retime
→ Re-QA
→ formal selection
```

No second repair policy was added.

## Trust boundary

The runtime does **not** accept user-supplied failure classes, repair actions, or Media QA
findings.

The Canonical Director may travel with the task payload because it is also an input to the
H3 compiler, but automatic timeline QA is not enabled until the exact compiled Provider
Prompt has passed its expected SHA verification.

Therefore a mutable/unlocked request cannot silently change the Canonical timeline used by
the automatic runtime gate without first failing the existing Preview/Runtime lock.

These paths remain intentionally excluded from automatic timeline wiring:

- raw prompt mode;
- non-H3 generation;
- H3 path where compiler was not applied;
- missing Preview/Runtime prompt lock;
- missing Canonical Director.

Explicitly injected trusted evaluator/handlers remain higher priority than the automatic
timeline bundle.

## New trust-boundary tests

The integration suite now verifies:

- prompt-locked + H3-compiled + Canonical Director → automatic timeline evaluator/handler;
- missing prompt lock → no automatic runtime bundle;
- compiler not applied → no automatic runtime bundle;
- neither condition → no automatic runtime bundle;
- explicitly injected trusted evaluator/handlers take precedence.

## Automated software gates

Run `36284812267`:

```text
Phase 4 auto-repair/runtime/wiring tests     40 passed
Phase 3 production-policy regression        11 passed
Six representative Unit joint regression    41 passed
H3 compiler + Preview/Runtime lock           13 passed
Reference Video + H3 subsystem              405 passed
Python compile                                PASS
Ruff                                          PASS
```

## Existing-evidence media replay

The same tested SHA replayed the existing E11U02 and E15U03 evidence.

### E11U02

```text
provider_recalled = false
final duration    = 15.000s
resolution        = 864x480
video             = H.264 / 24 fps
audio             = AAC / 32 kHz / stereo

replay SHA256
= 4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18

formally accepted SHA256
= 7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949

video SSIM to formally accepted final
= 0.992575

evidence-chain head
= cd0016488ac0c8460217818191c8218b4ad00f929d8207f6206ff0730ff0b980
```

**E11U02 regression: FINAL PASS**

### E15U03

Source actual cuts:

```text
frame 118 = 4.91667s
frame 222 = 9.25000s
```

Canonical target cuts:

```text
frame 120 = 5.00000s
frame 240 = 10.00000s
```

Automatic route:

```text
TIMELINE_ONLY_FAILURE
→ plan_h3_media_repair()
→ DETERMINISTIC_AV_RETIME
→ runtime handler
→ Re-QA
```

Final detected cuts:

```text
frame 120 = 5.00000s
frame 240 = 10.00000s
delta = 0 / 0
```

Media:

```text
provider_recalled = false
duration           = 15.000s
resolution         = 864x480
video              = H.264 / 24 fps
audio              = AAC / 32 kHz / stereo

replay SHA256
= 208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de

formally accepted SHA256
= 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b

video SSIM to formally accepted final
= 0.992496

evidence-chain head
= 21b3cb8070103a1932257d09a18260d900ecd76e3ee76bd41f650d44f4cf0e92
```

The encoded MP4 bytes differ because the replay environment/ffmpeg encoder is not guaranteed
to reproduce historical encoded bytes. The accepted Phase 4 media-equivalence rule therefore
remains:

- supplier/source evidence is SHA-pinned;
- Canonical boundaries and media contracts must pass;
- output must satisfy the accepted-media visual equivalence threshold;
- cross-environment encoded byte identity is not required.

Required threshold:

`SSIM >= 0.99`

Observed:

`0.992496`

**E15U03 automatic production timeline replay: FINAL PASS**

## Exact-text regression

E13U01 exact-text deterministic replay also passed in the same workflow, confirming that the
automatic timeline wiring did not regress the already accepted exact-text route.

## Evidence artifacts

E11U02 + E15U03:

```text
Artifact ID
= 10919973369

Name
= phase4-auto-repair-loop-e2e-evidence

Digest
= sha256:1b3eb31ca3e260e88eeba665db0edb9036b4fb2ec45f40adb487f4934f8e1725
```

E13U01:

```text
Artifact ID
= 10920021981

Name
= phase4-e13u01-exact-text-e2e-evidence

Digest
= sha256:2d776530cdd023e5793fec34e3f091e4ab035e0b110a88e64d7861b87c42e0e2
```

## Gate conclusion

```text
Prompt-lock trust boundary                      PASS
Automatic Canonical timeline bundle resolution PASS
Raw/non-H3/unlocked fail-safe behavior          PASS
Existing injected trusted QA precedence         PASS
Formal selection runtime wiring                 PASS
E11U02 media regression                         FINAL PASS
E15U03 automatic timeline media replay          FINAL PASS
E13U01 exact-text regression                    FINAL PASS
provider_recalled                               false
new paid MiniMax generation                     none
```

Phase 1, Phase 2, and Phase 3 remain CLOSED.

Phase 4 remains IN PROGRESS.

The next safe production delta is not to invent generic OCR or pixel-level semantic QA.
Exact-text automatic authoring should advance only after Canonical carries an explicit trusted
plate-authoring specification (layout/region/style/ownership), rather than extrapolating the
E13U01 black title-card design to unrelated Units.
