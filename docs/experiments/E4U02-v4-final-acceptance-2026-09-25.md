# E4U02 v4 final supplier acceptance — C03 identity + visible-text + dialogue separation

Date: 2026-09-25 (UTC+8)

## Scope

This acceptance remains limited to **E4U02**. E13U01 is not included.

Final acceptance gates:

1. Canonical character **C03 陆念** is visually locked across the younger/later memory shots.
2. The smartphone UI has exactly one legal readable string: **给念念打电话**.
3. Spoken dialogue is not visualized as subtitles, captions, transcription, dialogue cards, or other readable on-screen text.

## Final repair architecture

The v4 repair uses an H3 image+audio reference path instead of leaving dialogue transcript tokens in the visual provider prompt.

- Picture 1: exact phone/alarm reference containing the approved label.
- Picture 2: two-age C03 identity bridge:
  - LEFT = official younger C03/幼年陆念 reference.
  - RIGHT = official later-age C03/陆念 reference.
- Audio 1: supplier-generated E4U02 dialogue soundtrack reused as the synchronized audio reference.
- The visual provider prompt contains **no `<d>` tags and no dialogue transcript strings**.
- The final prompt explicitly prohibits subtitles/captions/transcription and all readable text other than the approved phone label.

This removes the failure mode in which H3 interprets dialogue transcript tokens as text it should typeset into the picture.

## Supplier run

- Repository: `locke-peng/ArcReel`
- Branch: `fix/e4u02-h3-v3-c03-identity-lock`
- Tested commit: `1378bb93b83ea7c52a8c28e77da42dfde4657f9f`
- GitHub Actions run: `36037865914`
- Workflow: `H3 E4U02 v4 Dialogue-Detached Live Supplier Test`
- Workflow conclusion: **success**
- Contract tests: **10 passed**
- Provider: `autodl`
- Model/workflow: `minimax_h3_image_audio_to_video_v2_15s`
- Requested duration: 15 s
- Provider duration: 15 s
- ffprobe duration: 15.083333 s
- Aspect ratio: 16:9
- Resolution: 480p横
- Image references: 2
- Audio references: 1
- Provider prompt SHA-256: `723569a26d4b377c4b0471eef09b948ac3dc6837471cef7d0cd9874261d30b41`
- Output video SHA-256: `259d22a31b986ae6260a712298edc83313ff9630e80f765d29cd044f04da7e97`
- Output streams: H.264 video + AAC audio.

## Dense visual review

25 review frames were inspected from 0.5 s through 14.75 s.

### Gate A — smartphone readable text

Reviewed 0.5 s, 1.5 s, and 2.5 s phone frames.

- The approved label **给念念打电话** is readable.
- No readable time digits are present.
- No secondary readable UI label is present.
- No other readable text is present.

**PASS**

### Gate B — C03 character identity

Reviewed the complete memory interval from 3.5 s through 14.75 s.

- The younger memory uses the younger/left C03 identity reference.
- The later memory uses the later/right C03 identity reference.
- The transition is an authored age change within the C03 identity bridge rather than a generic child recast.
- No unrelated third child face appears in the reviewed frames.

**PASS**

### Gate C — dialogue non-visualization

Reviewed dense 0.5-second sampling throughout the speaking interval, including 5.25–14.75 s.

- No burned-in subtitle is present.
- No caption strip is present.
- No speech bubble, dialogue card, lower-third, karaoke line, or dialogue transcription is present.
- The provider visual prompt contains neither `<d>` nor the two spoken dialogue strings.
- The final output retains an AAC audio stream.

**PASS**

## Final verdict

**E4U02 v4: PASS**

The E4U02 gate is now closed for all three required production dimensions:

- C03/陆念 identity lock — PASS
- sole legal phone UI text `给念念打电话` — PASS
- dialogue never visualized as subtitles — PASS

E13U01 was not entered during this acceptance.
