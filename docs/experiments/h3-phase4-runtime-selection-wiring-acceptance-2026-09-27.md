# Phase 4 H3 Auto-Repair Loop — Runtime Selection Wiring Acceptance — 2026-09-27

## Verdict

**PHASE 4 RUNTIME SELECTION WIRING GATE: FINAL PASS**

This acceptance connects the already-validated H3 auto-repair policy chain to ArcReel's
formal reference-video selection seam.

Project stage facts remain:

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

`0f440ef4f1683dc9552998c7aa1f842212c05411`

Primary GitHub Actions run:

`36282236247`

Conclusion:

`success`

Any documentation-only commit after this SHA is not the tested code SHA.

## Runtime seam

The production path is now:

```text
Canonical / Reference Video Task
→ Compile
→ Preview / Runtime lock
→ Provider execution
→ staged paid media bytes
→ H3 Runtime Media QA Selection Gate
→ Structured Finding
→ existing H3FailureClass
→ existing plan_h3_media_repair()
→ deterministic runtime repair when registered
→ Re-QA
→ VideoArtifactCommitter formal selection
→ current artifact only when gate passes
```

The gate runs after provider bytes exist but before the staged result can become the
current formal artifact.

Implemented modules / wiring:

- `lib/reference_video/h3_runtime_gate.py`
- `server/services/reference_video_tasks.py`
- `server/services/video_artifact_currency.py`
- `tests/unit/lib/reference_video/test_h3_runtime_gate.py`
- `tests/integration/server/services/test_h3_runtime_selection_wiring.py`

## Policy ownership remains single-source

The runtime gate does not create another repair policy.

It routes through:

```text
MediaQAFinding
→ plan_h3_auto_repair()
→ classify_h3_media_finding()
→ existing H3FailureClass / H3MediaFailure
→ existing plan_h3_media_repair()
→ existing H3RepairDecision
→ execute_h3_auto_repair()
→ execute_h3_media_repair()
```

Provider generation is never performed by `h3_runtime_gate.py`.

## Runtime fail-closed behavior

The runtime gate now locks these cases:

```text
clean media
→ PASS
→ no repair

known deterministic failure
→ existing planner
→ registered deterministic handler
→ staged bytes repaired
→ Re-QA
→ only then eligible for formal selection

provider-required failure
→ h3_provider_repair_required
→ provider_recalled = false
→ paid bytes history-only
→ never current

unknown failure
→ h3_media_qa_escalation_required
→ provider_recalled = false
→ history-only / human review

known deterministic action without runtime handler
→ h3_deterministic_repair_handler_missing
→ fail closed

repair changes no bytes
→ h3_deterministic_repair_no_progress
→ fail closed

findings remain after max passes
→ h3_media_qa_unresolved
→ fail closed
```

This preserves the Phase 3 rule that unknown failures cannot automatically spend supplier
credits.

## Formal-selection integration

`VideoArtifactCommitter.prepare_selection()` now supports a trusted internal
`preselection_media_gate`.

Important behavior:

1. The gate runs before formal current selection.
2. Successful deterministic repair can mutate the staged media only.
3. Gate evidence is persisted into version metadata under `h3_auto_repair`.
4. If the gate fails, the exception is retained as `selection_error`.
5. The gate error code becomes the restore blocker.
6. The existing paid-artifact commit path may archive the paid bytes in history, but the
   failed result cannot become current.
7. Existing TTS/currency selection behavior remains intact.

The gate is not derived from arbitrary user payload. The Media QA evaluator and deterministic
repair handlers are trusted internal dependencies.

## H3-only attachment rule

`reference_video_tasks.py` builds the preselection gate only when:

- execution is formal (`task_id` exists);
- a trusted internal Media QA evaluator is supplied;
- the reference-video request is actually on the H3 compiled path according to the existing
  `should_compile_reference_video_h3()` decision.

Therefore:

- `prompt_compiler=raw` does not receive the H3 runtime gate;
- non-H3 models do not receive the H3 runtime gate;
- normal behavior remains unchanged when no Media QA evaluator is installed.

## Automated regression results

Run `36282236247`:

```text
Phase 4 auto-repair/runtime tests             29 passed
Phase 3 production-policy regression         11 passed
Six representative Unit joint regression     41 passed
H3 compiler + Preview/Runtime lock            13 passed
Reference Video + H3 subsystem               399 passed
Python compile                               PASS
Ruff                                         PASS
```

## Existing-media regression — E11U02

Provider recall:

`false`

Latest output:

```text
duration   = 15.000s
resolution = 864x480
H.264 / 24 fps
AAC / 32 kHz / stereo
SHA256     = 4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18
```

Formally accepted reference:

`7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949`

Visual-equivalence gate:

`SSIM = 0.992575 >= 0.99`

Evidence-chain head:

`fe2c55715b5b6d75bfb02fb4d31b06757e1d3fb7d58f28f226ff26a6a5513e53`

**E11U02 replay: FINAL PASS**

## Existing-media regression — E15U03

Provider recall:

`false`

Source actual cuts:

```text
frame 118 = 4.91667s
frame 222 = 9.25000s
```

Repaired cuts:

```text
frame 120 = 5.00000s
frame 240 = 10.00000s
```

Latest output:

```text
duration   = 15.000s
resolution = 864x480
H.264 / 24 fps
AAC / 32 kHz / stereo
SHA256     = 208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de
```

Formally accepted reference:

`607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b`

Visual-equivalence gate:

`SSIM = 0.992496 >= 0.99`

Evidence-chain head:

`e42ed94a1d0f46f00f36442b893ca3146bbd2cf29b6884661d8c0c01aefcf2e1`

**E15U03 replay: FINAL PASS**

## Existing-media regression — E13U01

Provider recall:

`false`

Automatic route:

```text
EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE
```

Final media:

```text
duration   = 10.000s
resolution = 1280x720
authored cut = frame 120 = 5.000s
SHA256     = 9c304decd87bc3f2c441954a74d998d5a54b575d4975a936bf2f94ad85f5defb
```

Accepted-vs-replay video SSIM:

`0.999983`

Evidence-chain head:

`17fc9e0a4e2d6f2fdd8511f2e597316c668b51803a8414a74c2b2163d24bbf31`

**E13U01 replay: FINAL PASS**

## Evidence artifacts

E11U02 + E15U03:

```text
Artifact ID
= 10918194780

Name
= phase4-auto-repair-loop-e2e-evidence

Digest
= sha256:36abe0e4badef773c1301208dda3af64a5de00f413f98871ee3c0077b49360ce
```

E13U01:

```text
Artifact ID
= 10919202156

Name
= phase4-e13u01-exact-text-e2e-evidence

Digest
= sha256:c432624ceb3c73aec47ca883eb0555a1f7222218a29672850e9cbd58c836360d
```

## Acceptance conclusion

```text
Runtime gate core                         PASS
Formal selection seam wiring             PASS
H3-only trusted attachment               PASS
Deterministic repair before selection    PASS
Provider-required fail-closed            PASS
Unknown failure fail-closed              PASS
No-progress / iteration guards           PASS
Repair evidence in version metadata      PASS
Phase 3 policy remains sole policy       PASS
Six Unit regression                      PASS
E11U02 actual-media replay               FINAL PASS
E15U03 actual-media replay               FINAL PASS
E13U01 actual-media replay               FINAL PASS
No unintended provider call              PASS
```

Phase 4 remains active because the runtime gate intentionally accepts a trusted internal
Media QA evaluator/repair-handler bundle rather than inventing pixel-level semantics from
request payload. The next production delta should implement or connect those trusted Media
QA producers/repair handlers without weakening this selection gate.
