# E11U02 MiniMax H3 acceptance — v3 final PASS

Date: 2026-09-26 (UTC+8)

## Canonical scope

E11U02 is Episode 11 shots 03–05, exactly 15 seconds:

- Shot 03, 00:00–00:05 — research team executes; the model becomes stable; researcher says `通过了`; brief cheer.
- Shot 04, 00:05–00:10 — 江屿 places a formal summit guest badge beside 沈知意's hand; he says `明天见真章`.
- Shot 05, 00:10–00:15 — 陆予深 and 苏晚 enter the AI summit media area; camera translates laterally; reporter asks `陆氏会合作吗`; camera flashes.

Canonical does not require readable laboratory UI strings or readable guest-badge typography in these three shots.

## Why v2 was not accepted

The E11U02 v2 supplier workflow itself succeeded:

- Run: `36148270693`
- Tested commit: `e3d5e8abd053442c5981ca76ff4e57a6a84beae4`
- v2 final video SHA256:
  `edff353aa05833b3fb523f2ec48b7b58adbd6e7aba1bdccd71f5a0142dde5055`

However dense visual review found two Content QA failures even though the visual prompts explicitly required zero readable text:

1. Shot 1 still contained multiple generated laboratory UI/display surfaces with text-like interface detail.
2. Shot 2 generated a clearly readable English/logo-style block on the guest badge, despite a prompt contract asking for the blank backside.

Therefore:

```text
Provider SUCCESS
+ Contract PASS
+ zero-text prompt wording
!= Content PASS
```

E11U02 v2 remained **CONTENT FAIL**.

## v3 repair strategy

No additional paid H3 generation was performed.

The accepted motion, scene structure, identity-safe framing and audio from the exact pinned v2 video were reused. ArcReel v3 performs deterministic text-surface sanitization only:

```text
pinned E11U02 v2 final video
        ↓
verify exact SHA256
        ↓
Shot 1: pixelate known monitor/UI surfaces
Shot 2: time-scoped pixelation of moving badge label / microprint
Shot 3: pixelate corridor exit/signage surface
        ↓
preserve original timeline
preserve original AAC audio bitstream
        ↓
H.264 re-encode of video only
        ↓
dense 30-frame Content QA
```

The sanitizer does not regenerate, concatenate, retime, replace dialogue, or call the provider.

## v3 deterministic run

- Repository: `locke-peng/ArcReel`
- Branch: `fix/e11u02-h3-v3-deterministic-sanitization`
- Run: `36200372226`
- Tested commit: `4a9995ec962e1306ce56f0ce0e317e83678e4223`
- Workflow: `H3 E11U02 v3 Deterministic Sanitization`
- Workflow conclusion: **success**
- Unit tests: **8 passed**
- Python compile: **PASS**
- Ruff: **PASS**
- New paid provider calls: **0**
- Source v2 artifact digest:
  `958e1f625f48acb46701b28f6e353de9841532012fdf3db88ff6792a0b3ffabc`

## Deterministic sanitizer contract

Shot 1 masks:

- left wall display
- rear center display
- front-left display
- front-right display
- far-right display/reflection
- inner status-screen region while preserving the physical green indicator ring

Shot 2 masks:

- badge-label entry position
- badge-label turn position
- badge-label lowering position
- badge-label resting position
- lower badge microprint area

Shot 3 mask:

- corridor exit/signage surface

All masks are time-scoped and frame-bounded. They transform linguistic surfaces into non-linguistic mosaic geometry without changing the canonical actions.

## Final media

```text
duration        = 15.000000 s
resolution      = 864 × 480
video codec     = H.264
audio codec     = AAC
audio rate      = 32000 Hz
audio channels  = 2
```

Hashes:

```text
v2_source_video_sha256
= edff353aa05833b3fb523f2ec48b7b58adbd6e7aba1bdccd71f5a0142dde5055

v3_final_video_sha256
= d9c9c74d2e8de02f60d5aae88f70f6c947b0bd8b309b323d0fe2e30abe2064cd

v2_audio_elementary_stream_sha256
= b2bc9bf042aa7a79c40b9a8ca4c52903302e5e3c62da70600c1ea4585c494764

v3_audio_elementary_stream_sha256
= b2bc9bf042aa7a79c40b9a8ca4c52903302e5e3c62da70600c1ea4585c494764
```

The matching audio elementary-stream hashes prove the accepted v2 AAC soundtrack is preserved bit-for-bit in v3.

Artifact:

- ID: `10891314612`
- Name: `e11u02-v3-deterministic-sanitization-evidence`
- ZIP SHA256:
  `60dfe9e1ddefc3e4ab9dad488c98c0c247592f0536aca9a28df0fe0651b66850`

## Dense 30-frame visual review

Review frames were extracted every 0.5 seconds from 0.25s through 14.75s.

### Gate A — Shot 1: team executes / model stable

00:00–00:05:

- laboratory environment and supporting research team remain intact;
- system-state action remains readable through the hardware change and final steady green indicator;
- generated monitor/UI detail has been deterministically reduced to non-linguistic mosaic blocks;
- no readable laboratory UI string, subtitle, dialogue transcription, logo or watermark is visible at delivery resolution;
- no named principal face is newly established.

**PASS**

### Gate B — Shot 2: formal guest badge placement

00:05–00:10:

- male hand/forearm places the formal badge beside the woman's white-sleeved hand;
- hands-only identity-safe framing is preserved;
- badge silhouette, lanyard and placement action remain readable;
- the v2 English/logo-style badge content is no longer readable after time-scoped deterministic sanitization;
- no subtitle/dialogue transcription is visible.

**PASS**

### Gate C — Shot 3: summit media entry

00:10–00:15:

- one dark-suited man and one warm ivory/champagne-suited woman enter together;
- pair remain rear / three-quarter rear and do not establish replacement canonical faces;
- black-drape media corridor, camera crowd and flash behavior remain intact;
- corridor exit/signage surface is deterministically sanitized;
- no readable dialogue caption or event-sign string is observed in the 30-frame review at delivery resolution.

**PASS**

### Gate D — dialogue/audio preservation

Canonical dialogue remains in the accepted audio soundtrack:

```text
通过了
明天见真章
陆氏会合作吗
```

v3 performs no dialogue regeneration. The AAC elementary-stream SHA is identical to v2.

**PASS**

### Gate E — exact editorial structure

```text
00:00–00:05  Shot 03
00:05–00:10  Shot 04
00:10–00:15  Shot 05
```

v3 does not trim, concatenate or retime the source. Final duration remains exactly 15 seconds.

**PASS**

## Final verdict

**E11U02 v3 = FINAL PASS**

Closed gates:

```text
Shot 03 model-stable story beat             PASS
Shot 04 guest-badge placement               PASS
Shot 05 summit media entry                  PASS
identity-safe framing                       PASS
canonical dialogue/audio preservation       PASS
zero readable non-canonical text            PASS
5s + 5s + 5s exact editorial structure      PASS
864×480 H.264 + AAC final media             PASS
```

## Production lesson

E11U02 adds a new production rule:

> When generated motion and acting are already acceptable but localized text surfaces remain wrong, do not pay to regenerate the whole shot. Reuse the pinned provider result and deterministically sanitize only the failing pixels.

This creates a three-level response to unwanted generated text:

```text
1. remove text source from visual prompt
2. remove / exclude text-bearing surfaces during generation
3. if motion is already accepted, deterministically sanitize the remaining text surface
```

The third level is especially useful when the unwanted text is local while the rest of the generated shot has already passed.
