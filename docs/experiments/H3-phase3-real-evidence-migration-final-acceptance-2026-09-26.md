# H3 Phase 3 real supplier evidence migration — FINAL PASS

Date: 2026-09-26 (UTC+8)

## Scope

Phase 3 second-stage migration replaces Unit-specific deterministic repair execution with the generic production executors in:

- `lib/reference_video/h3_media_pipeline.py`
- `lib/reference_video/h3_repair_executors.py`

The migration uses immutable historical paid supplier evidence for:

- E11U02 — three MiniMax H3 visual plates + detached canonical soundtrack;
- E15U03 — original paid MiniMax H3 15-second supplier video;
- E13U01 — paid H3 C01 entrance plate + canonical exact-text screen plate + detached canonical audio.

No provider client, provider credential, API key, or paid generation call is available in the migration runner.

## Production executor delta required by real evidence

Real E11U02 exposed capabilities that the synthetic Phase 3 executor test did not cover:

1. moving typography contamination requires a keyframed repair region;
2. soft side-media sanitization requires weighted/opacity repair regions;
3. one Unit may have multiple immutable provider roots plus canonical assets;
4. final deterministic authoring may depend on several repaired parents and one canonical audio parent.

Phase 3 therefore added:

- `RepairRegionKeyframe`;
- `RepairRegionTrack`;
- per-region `blur_radius` and `opacity`;
- multi-root `EvidenceChain` support for `provider_output` and `canonical_asset`;
- `VisualAuthoringSegment`;
- deterministic sequence authoring with still-plate support and deterministic fade-in;
- multi-parent final authoring evidence.

Semantic repair remains excluded. `REGENERATE_SHOT` is still not executable by the deterministic repair layer.

## CI execution

Final migration run:

- workflow: `H3 Phase 3 Real Evidence Migration`
- GitHub Actions run: `36236871884`
- tested commit: `9e95598ab259ec1969c9d83243e9d76f45e276ac`
- conclusion: **success**
- artifact ID: `10904223723`
- artifact name: `h3-phase3-real-evidence-migration`
- artifact digest: `sha256:936981a3b5d10b766a4d292a038ae07c7726833e7f978183f71dce8e21fcb393`
- provider calls: **0**

Pre-media gates:

- Phase 3 executor tests: PASS
- Python compile: PASS
- Ruff: PASS
- E11U02 historical artifact download: PASS
- E15U03 historical artifact download: PASS
- E13U01 historical artifact download: PASS
- immutable source SHA verification: PASS
- provider-dependency grep gate: PASS

## E11U02 migration

Immutable roots:

- Shot 03 provider: `aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48`
- Shot 04 provider: `7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507`
- Shot 05 provider: `ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751`
- canonical soundtrack: `dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2`

Production evidence chain contains eight nodes:

```text
3 × provider_output
+ 1 × canonical_asset
+ 3 × deterministic_pixel_sanitization
+ 1 × deterministic_sequence_authoring
```

Final migrated media:

- SHA256: `381e73ea63ee244ebfe9d8501231a267c7be0a650d85c4d3fe61fdfea05c2ecb`
- duration: `15.000000s`
- resolution: `864×480`
- video: H.264, 24 fps
- audio: AAC, 32 kHz, stereo
- decoded audio vs legacy FINAL PASS: **identical**
- whole-video SSIM vs legacy FINAL PASS: **0.990387**
- per-shot SSIM:
  - 00–05: `0.992086`
  - 05–10: `0.994071`
  - 10–15: `0.985004`

The final SHA differs from the legacy experimental-script output because the production executor uses generalized weighted regions instead of the old Unit-specific feather-mask implementation. Dense review confirms the Canonical content remains intact:

- Shot 03 laboratory/model-stability beat preserved;
- screen surfaces remain sanitized while the physical green status indicator remains visible;
- Shot 04 badge placement remains intact and badge typography is defocused throughout its motion;
- Shot 05 C02/C04 rear-entry silhouettes remain readable while side-media/supporting text surfaces are sanitized;
- exact 5s + 5s + 5s structure remains;
- no dialogue is visualized.

**E11U02 migration: PASS.**

## E15U03 migration

Immutable provider root:

`17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36`

Evidence chain:

```text
provider_output
→ deterministic_av_retime
```

Final migrated media:

- SHA256: `208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de`
- duration: `15.000000s`
- resolution: `864×480`
- video: H.264, 24 fps
- audio: AAC, 32 kHz, stereo
- decoded audio vs legacy FINAL PASS: **identical**
- whole-video SSIM vs legacy FINAL PASS: **0.992496**
- per-shot SSIM:
  - 00–05: `0.991714`
  - 05–10: `0.991802`
  - 10–15: `0.993972`

Dense review confirms:

- 00–05 remains the product-launch reveal with exact `TIANSHU NEXT`;
- 05–10 remains the audience/media beat through 9.75s;
- C01 entrance begins after the canonical 10s boundary;
- C01 remains the solo white-suit entrance;
- no additional readable story text is introduced.

**E15U03 migration: PASS.**

## E13U01 migration

Immutable roots:

- H3 C01 entrance provider plate: `e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f`
- canonical exact screen plate: `6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57`
- canonical detached audio: `cbda309d698046b6ab185f5d36fdf23ee1a112f6f1f9d39a37368b6f985a7b33`

Evidence chain:

```text
provider_output
+ canonical exact-text asset
+ canonical audio asset
→ deterministic_sequence_authoring
```

Final migrated media:

- SHA256: `8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12`
- legacy FINAL PASS SHA256: `8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12`
- byte-equivalent to legacy accepted final: **YES**
- duration: `10.000000s`
- resolution: `1280×720`
- video: H.264, 24 fps
- audio: AAC, 32 kHz, stereo

Dense review confirms the exact two-line screen:

```text
沈知意
天枢联合创始人
```

for the complete first five seconds, followed by the accepted C01 side-door / spotlight entrance for the complete second five seconds.

**E13U01 migration: PASS / byte-identical.**

## Final verdict

**Phase 3 second stage = FINAL PASS.**

The migration demonstrates that the generic production path can consume real historical H3 outputs without provider recall:

```text
immutable provider/canonical roots
→ validated deterministic repair plan
→ production repair executor
→ deterministic sequence authoring
→ ffprobe + SHA
→ hash-linked Evidence Chain
→ dense visual QA
```

The old Unit-specific repair scripts are no longer required as production executors. They should be retained only as historical acceptance fixtures until repository cleanup removes or archives them in a separate maintenance change.

The production rule remains:

> deterministic post-processing may remove model-invented material or restore Canonical timing from validated source media; it must never invent missing Canonical story facts.
