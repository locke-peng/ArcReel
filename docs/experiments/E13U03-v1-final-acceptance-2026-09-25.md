# E13U03 MiniMax H3 supplier acceptance — v1 final PASS

Date: 2026-09-25 (UTC+8)

## Canonical scope

E13U03 is Episode 13 shots 06–08, exactly 15 seconds:

- Shot 06, 00:00–00:05 — school livestream; C03 陆念 suddenly sits upright; slow push-in; no dialogue.
- Shot 07, 00:05–00:10 — C01 沈知意 reaches the malfunctioning summit control console; dialogue: `打开底层日志`; keyboard sound.
- Shot 08, 00:10–00:15 — system logs scroll rapidly while her gaze scans them; no dialogue; electronic sound.

Canonical provides **no literal log strings**, so no invented code/log text is permitted.

## Production architecture

E13U03 uses the hybrid method established by E4U02 and E13U01:

```text
Audio seed
+ Shot 1 H3 motion plate
+ Shot 2 H3 motion plate
+ Shot 3 H3 semantic-log plate
+ deterministic ArcReel 5s + 5s + 5s composition
+ post-production audio mux
```

Each visual provider prompt contains:

- no CJK,
- no `<d>`,
- no dialogue transcript,
- zero readable-text contract.

The only dialogue string is present in the detached audio seed.

Shot 3 represents logs only as moving horizontal luminous bars / rectangular rows. It does not invent source code, words, digits, command lines, or status labels.

## Pre-provider fail-closed history

Attempts 1–3 stopped before any paid supplier request:

- Attempt 1: static contract wording mismatch; provider skipped.
- Attempt 2: stale assertion after wording alignment; provider skipped.
- Attempt 3: contracts and compile passed, Ruff caught an async pathlib read and import ordering; provider skipped.

These failures demonstrate the intended fail-closed behavior: local/CI problems did not spend supplier generation credits.

## Paid supplier run

- Repository: `locke-peng/ArcReel`
- Branch: `fix/e13u03-h3-v1-multiscene-identity-logguard`
- Tested commit: `f58994f4a9e21a0f964e0508efd3972dcd0e79c5`
- GitHub Actions run: `36128343054`
- Workflow: `H3 E13U03 v1 Live Supplier Test`
- Workflow conclusion: **success**
- Deterministic contract tests: **10 passed**
- Python compile: **PASS**
- Ruff: **PASS**
- Provider: `autodl`
- Model: `minimax_h3_zm_u24`
- Provider resolution request: `480p横`
- Final authored resolution: **864×480**
- Final authored duration: **15.000000s**
- Final streams: **H.264 video + AAC 32kHz stereo**

## Evidence hashes

```text
audio_seed_prompt_sha256
= 43c425e0624bf876900ac7f4e63e584e0da5613b1b6d2cead10cd0bec2cd7633

shot1_provider_prompt_sha256
= e3c5a33051f56a723faf8b62ae48e373e5dcacb1f354886bd25a43ab7f38ea75

shot2_provider_prompt_sha256
= 0d446c1979e00916a3fa113ea2755d551f35469d5c986927f9929ded3b63d91c

shot3_provider_prompt_sha256
= 7584d77c759307cbc2da21376d1cddddb5677353673398553bb200cbf6179a2f

scene_bridge_sha256
= 2221bc97ca6fcc6249021f45b93f1e6107b8c9b02115a179856685dc01bfec67

C03_current_sha256
= c92b71c3fe707088dd340d41de9a202e2ab7d02392fef4913b2df6959c4932b0

C01_bridge_sha256
= fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135

school_reference_sha256
= ff586b9875d9e1dbafd7cd146ec2a8c57fed7bb1898f231c003fe7851d916fad

console_reference_sha256
= 885c2d20cc8337932c5206b1fe973b9f9c573a45158e97c8527e29019dbb29ba

log_reference_sha256
= 98b57d04ccf909451bdc172c9324f109c1f0b2cc519a2ef05220f6d3b0e6c3e6

soundtrack_sha256
= 63c054989c0903feed2bc1d69a25e88a99ae7219ff0e5057405aadf5d5804041

final_video_sha256
= 63a1238ae14161e7549fc9927adc611a3ba3aa7b6879c9050bac9a7a2fdf7b58
```

## Dense media review

30 review frames were inspected at 0.5-second intervals from 0.25s through 14.75s.

### Gate A — Shot 1 / C03 school reaction

00:00–00:05:

- environment reads as a bright technology classroom;
- projection shows the summit context without a readable identity card;
- C03/陆念 remains the foreground principal child with the canonical school-uniform / hair / facial family;
- she changes from seated watching to an abrupt upright, wide-eyed recognition reaction;
- slow push-in is present;
- no readable subtitle/caption or other readable overlay was observed.

**PASS**

### Gate B — Shot 2 / C01 control-console action

00:05–00:10:

- hard cut at the authored 5-second boundary;
- environment reads as the AI summit technical control area;
- C01/沈知意 enters/reaches the control console and begins operating the keyboard;
- white professional suit, tied-back dark hair and gray structured handbag remain consistent with the established C01 stage appearance;
- no burned-in dialogue subtitle/caption is present;
- monitor detail remains small/non-canonical interface texture; no readable canonical/invented message is required or relied upon.

**PASS**

### Gate C — Shot 3 / semantic-only logs

00:10–00:15:

- hard cut at the authored 10-second boundary;
- logs are represented exclusively as luminous horizontal bars / row geometry;
- rows visibly move/scroll across the shot;
- no readable Chinese, English, digits, code, command lines or invented log strings are visible;
- the adjacent eye/upper-face close-up maintains continuity with the C01 woman from the preceding control-console beat; no distinct alternate principal face appears;
- gaze motion is visible during the inspection.

**PASS**

### Gate D — dialogue/text separation

- visual provider prompts contain no CJK;
- visual provider prompts contain no `<d>`;
- visual provider prompts contain no `打开底层日志`;
- canonical dialogue exists only in the audio seed;
- final MP4 retains an AAC stereo audio stream;
- no dialogue transcription/subtitle is visible in the dense review frames.

**PASS**

### Gate E — exact editorial structure

```text
00:00–00:05  Shot 06
00:05–00:10  Shot 07
00:10–00:15  Shot 08
```

Final ffprobe duration: `15.000000s`.

**PASS**

## Final verdict

**E13U03 v1 = FINAL PASS**

Closed production gates:

```text
C03 identity / school reaction       PASS
C01 identity / summit console        PASS
dialogue remains audio-only          PASS
semantic-only logs / no invented text PASS
5s + 5s + 5s authored timing         PASS
864×480 H.264 + AAC final media      PASS
```

## Production lesson

E13U03 confirms a further rule for screens containing semantically meaningful but unspecified data:

> When Canonical says “logs scroll” but does not provide literal log content, compile the *state* (“rapid scrolling logs”) into non-linguistic visual geometry instead of inventing text.

This preserves story meaning while respecting the rule that the Compiler may translate Canonical facts but must not create new Canonical facts.
