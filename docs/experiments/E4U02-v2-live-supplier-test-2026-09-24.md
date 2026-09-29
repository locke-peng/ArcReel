# E4U02 v2 live supplier acceptance — 2026-09-24

## Scope lock

This run evaluates only the two E4U02 v2 repair targets:

1. The phone UI may show exactly one legal readable string: `给念念打电话`.
2. Content inside `<d>` dialogue tags must remain audio-only and must not be visualized as subtitles/captions/overlays.

E13U01 is explicitly out of scope until E4U02 passes these two checks.

## Test target

- Repository: `locke-peng/ArcReel`
- Branch: `fix/e4u02-h3-visible-text-v2-3b3bc527`
- Tested HEAD: `2fae7d8a8c39ab46848a65f79fd81ffcb3b1da0b`
- Baseline ancestry: `3b3bc527197bad66ac0425094036ea86b0add7e8`
- GitHub Actions run: 36021867871
- Provider route: ArcReel `MediaGenerator.generate_video_async()` -> declarative AutoDL endpoint -> `minimax_h3_zm_u24`
- Mode: H3 Ref2VA
- Requested duration: 15 s
- Resolution: `480p横`
- Aspect: 16:9
- Reference count: 3

## v2 repair contract

The provider prompt applies a highest-priority visible-text whitelist:

- sole legal visible text: `给念念打电话`
- no readable time digits
- no secondary phone labels
- no titles / logos / watermarks
- no pseudo-readable glyph strings

The prompt also applies a highest-priority dialogue-channel contract:

- `<d>[Chinese] 妈妈，我想你</d>` is audio-only
- `<d>[Chinese] 妈妈，我在忙</d>` is audio-only
- never typeset, transcribe, caption, subtitle, echo, or otherwise visualize `<d>` content

Preview/runtime prompt equality is locked by SHA-256.

## Pipeline result

- Prompt contract tests: PASS
- Credential preflight: PASS
- Paid provider generation: PASS
- Artifact download: PASS
- Review-frame extraction: PASS
- Requested duration: 15 s
- Provider duration: 15 s
- ffprobe duration: 15.083333 s
- Video: H.264, 864x480, 24 fps
- Audio: AAC
- Provider prompt SHA-256: `123c8f0a143de62dafb73e6f333cbcf050efb1feed5685429996d02b42d8b6c8`
- Output video SHA-256: `04018d92726446209fce5afaa1aac7a678082ee736ec0494a817e5e20552d5fd`

## Visual acceptance review

### Phone/UI segment, 00:00-00:05

Reviewed the authored review frames and dense 0.5 s sampling across the complete first 5 seconds.

Result:

- `给念念打电话` remains the only readable phone/UI text.
- No readable time digits are present.
- No secondary readable labels are present.
- No extra pseudo-text string is introduced elsewhere in frame.

**Criterion 1: PASS.**

### Dialogue segment, 00:05-00:15

Reviewed the authored review frames plus dense 4 fps sampling (40 frames) across the complete dialogue interval.

Result:

- No burned-in subtitles.
- No caption bar.
- No lower-third dialogue transcription.
- No speech bubble / karaoke text.
- Neither `妈妈，我想你` nor `妈妈，我在忙` appears visually.
- No other readable text is introduced during the dialogue shots.

**Criterion 2: PASS.**

## Scoped verdict

**E4U02 v2: PASS for the two requested repair targets.**

The supplier output demonstrates that the v2 execution prompt can preserve the single legal phone UI string while keeping `<d>` dialogue audio-only without subtitle visualization.

This test intentionally uses text-focused runtime references generated inside GitHub Actions so the two requested failure modes can be isolated. It is not a separate acceptance of canonical character-image fidelity, acting quality, or other E4U02 production dimensions; those are outside the user's locked v2 scope.

E13U01 remains untouched in this run.
