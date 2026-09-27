# Phase 4 H3 Auto-Repair Loop — Exact-Text Runtime Acceptance — 2026-09-27

## Verdict

**PHASE 4 EXACT-TEXT RUNTIME GATE: FINAL PASS**

This gate promotes exact visible text from an experiment-specific deterministic replay into a
trusted production runtime capability.

It does not close Phase 4 as a whole.

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  IN PROGRESS
```

No paid MiniMax generation was performed by this acceptance.

## Tested branch and code

Branch:

`phase4/h3-auto-repair-loop`

Tested code SHA:

`0cb22ae49ef27a815c863e01917b40d6dd58a3f9`

Primary GitHub Actions run:

`36286739774`

Conclusion:

`success`

A later documentation-only commit must not be represented as the tested code SHA.

## Production contract

The v1 exact-text contract is defined by:

- `lib/reference_video/h3_exact_text_contract.py`
- `docs/schemas/h3_exact_text_plate.schema.json`

Runtime execution is implemented by:

- `lib/reference_video/h3_exact_text_runtime.py`

The v1 contract intentionally supports only deterministic full-frame plate ownership.

Required plate facts are:

```text
schema_version = 1
ownership      = deterministic_plate
compositing    = full_frame_replace
asset_path     = project-relative
asset_sha256   = lowercase SHA256
region         = normalized full frame
typography.authority = asset_pixels
ssim_threshold = 0.98..1.0, default 0.99
```

The full-frame limitation is deliberate. Phase 4 does not infer text boxes, fonts, alignment,
or local pixel regions from natural language or OCR.

## Provider boundary

For a Canonical `screen_text` item with:

```text
legibility = exact
plate_spec = deterministic plate contract
```

the exact string is **not delegated to the video provider**.

Instead, the H3 Director compiler validates the Canonical plate contract and inserts a
contract digest into the Provider Prompt:

```text
ArcReel post-production owns this full-frame exact-text plate;
contract_sha256=<digest>.
Do not render readable text, pseudo-text, subtitles, labels,
letters, digits, logos, or typography for this plate in provider pixels.
```

The digest binds:

- unit id;
- shot id;
- shot interval;
- text kind;
- exact text;
- complete plate specification.

Therefore changing the exact text or its plate contract changes the Provider Prompt hash even
though the exact string itself is not exposed to the provider.

The existing Preview/Runtime Provider Prompt SHA lock remains the trust boundary.

Legacy exact text without a `plate_spec` keeps the previous provider-owned behavior.

## Pre-provider fail-loud asset validation

Automatic exact-text runtime construction occurs after the Provider Prompt lock has been
verified but before paid provider submission.

The runtime resolves the declared plate through the project-safe path boundary and requires:

```text
actual plate SHA256 == Canonical asset_sha256
```

A missing plate, unsafe path, or SHA drift fails before provider execution.

The runtime does not trust request-supplied failure classes or repair actions.

## Media QA producer

Exact-text QA does not use OCR.

For each deterministic exact-text plate, the producer compares the actual Canonical shot
window against the SHA-pinned plate pixels using decoded-video SSIM.

If:

```text
observed SSIM < Canonical ssim_threshold
```

it emits:

```text
H3FailureClass.EXACT_TEXT_REQUIRED
repairability = deterministic
provider_result_usable = true
audio_is_accepted = true
```

The existing Phase 3 planner then chooses:

```text
EXACT_TEXT_REQUIRED
→ plan_h3_media_repair()
→ DETERMINISTIC_TEXT_PLATE
```

No second repair policy was created.

## Runtime repair

The v1 deterministic handler:

1. preserves video before the Canonical plate window;
2. replaces only the exact-text Canonical window with the trusted full-frame plate;
3. preserves video after that window;
4. preserves the existing audio stream;
5. re-runs Media QA through the normal H3 runtime selection gate.

Provider recall remains disabled.

## Production composition with Timeline QA

The production trusted runtime resolver now composes:

```text
Canonical Timeline QA
+
Canonical Exact-Text Plate QA
↓
one composite trusted evaluator
↓
existing H3 classifier
↓
existing plan_h3_media_repair()
↓
registered deterministic handlers
↓
Re-QA
↓
formal selection
```

Automatic runtime construction still requires:

- Canonical Director;
- H3 compiler applied;
- verified Preview/Runtime Provider Prompt SHA lock.

Explicit trusted evaluator injection still has priority.

## Software gates

Run `36286739774`:

```text
Phase 4 primitive/runtime/wiring tests       45 passed
Phase 3 production-policy regression        11 passed
Six representative Unit joint regression    41 passed
H3 compiler + Preview/Runtime lock           13 passed
Reference Video + H3 subsystem              409 passed
Python compile                                PASS
Ruff                                          PASS
```

## E13U01 production exact-text runtime replay

Existing supplier evidence was reused. No provider was called.

Pinned inputs:

```text
exact plate SHA256
= 6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57

accepted H3 entrance video SHA256
= e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f

detached canonical audio SHA256
= cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33

formally accepted final SHA256
= 8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12
```

The replay first authored an intentionally wrong shot-1 plate while preserving the accepted
H3 entrance shot and detached canonical audio.

Wrong candidate SHA256:

`96419dc53ed366fef2c329df75ba7fb17adf62f68f7e70b6b1b10f36ccb9a680`

The production runtime then measured:

```text
shot              = E13U01-S01
window            = 0.0s .. 5.0s
region            = full_frame
observed plate SSIM = 0.965539
required SSIM       = 0.990000
```

Plate contract SHA256:

`2b7630181a2c763010d3ba746beab57409f5b7fed6ffdbd4f14c7f78c315da00`

Structured route:

```text
EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE
→ provider_recalled = false
```

Runtime gate:

```text
status        = PASS
repair_passes = 1
```

Pass 0:

```text
findings = exact_text_required
plans    = deterministic_text_plate
repair   = executed
```

Pass 1:

```text
findings = []
plans    = []
```

Final runtime media SHA256:

`fd0c9d00f74d70cc12e53738e4291ed741b8b8e34b2297472c6da7e94e1293c5`

Media facts:

```text
duration   = 10.000s
resolution = 1280x720
video      = H.264 / 24 fps
audio      = AAC / 32 kHz / stereo
cut        = frame 120 / 5.000s / delta 0
```

Visual equivalence against the formally accepted E13U01 final:

`SSIM = 0.997277`

Required threshold:

`SSIM >= 0.99`

The detached-audio decoded stream digest remained:

`842174439856b66ef4119f32f3ddf1052d32ca83bc3cff44d736bf281578af0b`

Provider recalled:

`false`

Evidence-chain head:

`4aecc888bee2c0728b7e46e81647cf0c54783430aedfc8aae736c8e62cd8b294`

**E13U01 production exact-text runtime replay: FINAL PASS**

## Regression controls

The same tested SHA reconfirmed E11U02:

```text
provider_recalled = false
final SHA256
= 7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949
byte-identical to formally accepted final = true
SSIM = 1.0
evidence-chain head
= 896d41d24fecee7a6dbf4d56b9ace0de776c2949ad61a4c98d8e90193a4a1000
```

E15U03 also remained fully accepted:

```text
source cuts = 118 / 222
final cuts  = 120 / 240
provider_recalled = false
final SHA256
= 607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b
byte-identical to formally accepted final = true
SSIM = 1.0
evidence-chain head
= 4847290147885b934c606e78a9da04571c402abad370cff10f36886383a0f14e
```

## Evidence artifacts

E13U01:

```text
Artifact ID
= 10920509304

Name
= phase4-e13u01-exact-text-e2e-evidence

Digest
= sha256:6b1231d9a2e7f978ef66f1e0fd6f21a056de1a0bfa3a30e8c3450ac33e363162
```

E11U02 + E15U03:

```text
Artifact ID
= 10920950778

Name
= phase4-auto-repair-loop-e2e-evidence

Digest
= sha256:bab0e3210c8d9b8aae08a0cff0cf72a32b3249325e8844c2203c2111d20a8658
```

## Gate conclusion

```text
Canonical exact-text plate schema                 PASS
Exact text bound into Prompt SHA without leakage  PASS
Project-relative plate path validation            PASS
Plate SHA pre-provider validation                 PASS
Actual-media plate QA                             PASS
Existing EXACT_TEXT_REQUIRED taxonomy reused      PASS
Existing DETERMINISTIC_TEXT_PLATE policy reused   PASS
Video-only deterministic window replacement       PASS
Accepted audio preserved                          PASS
Re-QA before formal selection                     PASS
E13U01 production runtime replay                  FINAL PASS
E11U02 regression                                 FINAL PASS
E15U03 regression                                 FINAL PASS
provider_recalled                                 false
new paid MiniMax generation                       none
```

Phase 1, Phase 2, and Phase 3 remain CLOSED.

Phase 4 remains IN PROGRESS.

The next safe production delta should continue only where Canonical provides deterministic
authoritative facts. Generic OCR, generic semantic pixel classification, or inferred local
repair masks remain out of scope for automatic promotion.
