# E13U01 MiniMax H3 supplier acceptance — v1 failure → v2 final PASS

Date: 2026-09-25 (UTC+8)

## Canonical scope

E13U01 is the first 10 seconds of Episode 13:

- Shot 1, 00:00–00:05: giant screen reveals exactly `沈知意 / 天枢联合创始人`; host says `欢迎沈知意`; applause erupts.
- Shot 2, 00:05–00:10: 沈知意 enters from the stage-wing side door into the spotlight; no dialogue; applause continues.

E13U03 is not included in this acceptance.

## Required Content Gates

1. Screen text: exact canonical strings, correct spelling, no extra readable screen copy.
2. Timing: exactly two authored five-second shots.
3. Character identity: canonical C01 沈知意, no recast / face drift / third principal person.
4. Continuity: Shot 2 continues the accepted E12U06 v4 side-door / immediate-stage-edge / spotlight geometry.
5. Dialogue/text separation: host dialogue remains audio-only; no subtitle/caption transcription.

## v1 supplier result — CI success, Content FAIL

- GitHub Actions run: `36087814437`
- Tested commit: `93bdfa33554842a731da24b394d8d0bc420dad64`
- Contract tests: `10 passed`
- Workflow conclusion: `success`
- Provider: AutoDL / MiniMax H3 `minimax_h3_zm_u24`

Visual review found two blocking defects:

1. The screen-identification shot lasted only about two seconds before the model transitioned to the stage, so the canonical 5s + 5s authorship was not preserved.
2. The distant stage LED screen invented additional sponsor/logo-like blocks above the canonical identity strings, violating the exact screen-text contract.

C01 entrance identity and E12U06 side-door / spotlight continuity were otherwise usable.

**v1 verdict: CONTENT FAIL.**

The failure demonstrates again that provider success and prompt-contract success do not imply final-video acceptance.

## v2 repair architecture

v2 removes exact typography and shot timing from H3 responsibility.

### Shot 1 — deterministic ArcReel authoring

The first five seconds are authored deterministically from an exact 1280×720 screen plate:

```text
沈知意
天枢联合创始人
```

No AI model is allowed to redraw this typography.

This guarantees:

- exact spelling,
- exactly two lines,
- no sponsor/logo invention,
- exact five-second duration.

### Shot 2 — H3 entrance-only visual plate

H3 receives only a derived continuity/identity reference:

- E12U06 accepted stage-wing side door + immediate stage-edge spotlight geometry,
- canonical C01 woman in white professional suit,
- main LED screen removed from the visual reference,
- readable exit/signage seed suppressed.

The H3 entrance provider prompt contains:

- no Chinese/CJK text,
- no `<d>`,
- no host dialogue transcript,
- no identity-screen strings.

It explicitly requires the LED screen to remain outside frame and requires zero readable text.

### Audio — detached from visual generation

A separate audio seed carries:

```text
主持人：欢迎沈知意
掌声
```

ArcReel post-production muxes that canonical audio onto the authored 10-second visual sequence.

## v2 paid supplier run

- Branch: `fix/e13u01-h3-v1-screen-identity-continuity`
- Tested commit: `900db094a8c3be418be8e0576cd232505cb39d7f`
- GitHub Actions run: `36098803663`
- Workflow: `H3 E13U01 v2 Live Supplier Test`
- Workflow conclusion: **success**
- Deterministic contract tests: **10 passed**
- Python compile: **PASS**
- Ruff: **PASS**
- Provider: `autodl`
- Audio seed model: `minimax_h3_zm_u24`
- Entrance visual model: `minimax_h3_zm_u24`
- Requested duration: 10s
- Final authored duration: **10.000000s**
- Final resolution: **1280×720**
- Final video: H.264
- Final audio: AAC, 32kHz, stereo

Hashes:

```text
audio_seed_prompt_sha256
= 6380a6dff62765b4ef3ee0061ff8095557395bc091091c581a7bf3ea78c4a4e4

entry_provider_prompt_sha256
= 938d9588ade693f7b6ee8feb7007fd0cdb3b9b9cb2dd56062f56cb642be8a831

source_bridge_sha256
= fceffda195129d618ef9e7320c11409ab34663477335b24ef0f8b6eaecf22135

entry_reference_sha256
= c6e78a59dd0db3c3cfbab821c3e069d351f1ce7e7455e7b72709733858171bcd

exact_screen_sha256
= 6054ad83540f888caf8b8ceec76cdf20e6047c124fef81144860d1db36105d57

entry_provider_video_sha256
= e408e2bf93e3b0bbbc02495ecb6500ea5390facfe69b8e43b1a4873c420c246f

final_video_sha256
= 8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12
```

## Dense visual review

20 review frames were inspected at 0.5-second intervals from 0.25s through 9.75s.

### Gate A — exact screen text

Frames 0.25s through 4.75s:

- `沈知意` is stable and correctly spelled.
- `天枢联合创始人` is stable and correctly spelled.
- No third line.
- No sponsor/logo block.
- No time digits.
- No subtitle/caption/watermark.
- Shot remains the identity screen for the full first five seconds.

**PASS**

### Gate B — authored timing

- 00:00–00:05 = exact deterministic identity screen.
- Hard cut occurs at 00:05.
- 00:05–00:10 = stage-wing entrance.
- Final ffprobe duration = exactly 10.000000s.

**PASS**

### Gate C — C01 identity

In Shot 2:

- one principal woman only,
- white professional pantsuit,
- dark tied-back hair consistent with canonical C01,
- gray structured handbag retained,
- facial / silhouette identity remains consistent through the reviewed entrance frames,
- no alternate actress / third face.

**PASS**

### Gate D — E12U06 continuity

Shot 2 preserves:

- the same stage-wing side-door topology,
- an immediate short threshold into the stage edge,
- blue-black summit lighting,
- the same stage-edge spotlight relationship.

The main LED screen is excluded from the v2 Shot 2 composition, preventing unrelated screen regeneration while preserving the physically relevant continuity.

**PASS**

### Gate E — dialogue non-visualization

- H3 entrance prompt contains no CJK.
- H3 entrance prompt contains no `<d>`.
- H3 entrance prompt contains no host dialogue.
- No subtitle / caption / dialogue card is visible in the final frames.
- Final MP4 retains AAC audio.

**PASS**

## Final verdict

**E13U01 v2 = FINAL PASS**

All required production dimensions are closed:

```text
exact screen typography        PASS
5s + 5s authored timing        PASS
C01 沈知意 identity            PASS
E12U06 → E13U01 continuity     PASS
dialogue remains non-visual    PASS
final 10s H.264 + AAC artifact PASS
```

E13U03 was not entered during this acceptance.

## Production lesson

E13U01 confirms a production rule that should be kept beyond this unit:

> Exact typography and exact editorial timing should not be delegated to a probabilistic video model when ArcReel can author them deterministically.

For hybrid shots:

```text
deterministic graphic / UI plate
+
H3 motion / character plate
+
detached canonical audio
+
ArcReel final composition
```

is more reliable than asking one H3 generation to satisfy typography, character identity, stage continuity, dialogue, and exact cut timing simultaneously.
