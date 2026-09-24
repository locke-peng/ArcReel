# E12U06 live supplier test — 2026-09-24

## Scope

- Branch: `experiment/h3-docpack-v1-3b3bc527`
- Tested commit: `7add3392c6ebbeccf4a20426381e233842c1a21f`
- Unit: `E12U06`
- Provider route: ArcReel `MediaGenerator.generate_video_async()` -> declarative AutoDL endpoint -> `minimax_h3_zm_u24`
- Mode: H3 Ref2VA
- Requested duration: 10 s
- Resolution: `480p横`
- Aspect intent: 16:9
- Reference count: 1
- GitHub Actions run: https://github.com/locke-peng/ArcReel/actions/runs/36013839904

## Runtime result

**Execution pipeline: PASS.**

- Credential preflight: PASS
- AutoDL submit / async generation / artifact download: PASS
- Preview provider prompt == runtime provider prompt: PASS
- Final provider prompt SHA-256: `4c3e7fdcb8aedf106779e2a926242a241a9bd1048b214123c9fb0ffe32586aed`
- Source prompt chars: 2835
- Provider prompt chars: 2835
- Version: 1
- Requested/version duration: 10 s
- Persisted `provider_duration_seconds`: 10
- ffprobe video duration: 10.125 s
- Output: H.264, 864x480, 24 fps
- Audio stream: AAC stereo, 32 kHz, 10.112 s
- Video size: 829,569 bytes
- Video SHA-256: `3b1f445009afe1858fd65743d3c55ef2952140e5298246384c287fd9f164cdea`
- Canonical E12U06 reference SHA-256 recorded for comparison: `7b296bcbd21fdc1ef4792649c6062355c568bf64c2756a9319d86048d38a3762`

## Important test limitation

The GitHub runner cannot directly read the private ChatGPT Library asset, so this supplier smoke test used a text-free summit-stage surrogate generated inside Actions. The exact canonical reference hash is recorded, but this run is not a formal visual-consistency acceptance against the canonical image.

## Frame review

Sampled at 0.5 / 2.5 / 4.5 / 5.5 / 7.5 / 9.5 s.

### Passed visual intentions

- Main-screen shot occupies the first half.
- Cut to the stage-wing side door occurs around the authored 5-second boundary.
- Side door is physically adjacent to the stage edge rather than down a long backstage corridor.
- Focused light rises around the door / stage edge.
- Two-shot spatial progression is recognizable.

### Failed / partial visual intentions

- The main screen renders pseudo-readable / glyph-like text despite the explicit no-readable-language constraint.
- After the door opens, the model introduces a suited male figure around 7.5 s and keeps him in frame by 9.5 s. The prompt specified the doorway geometry conditionally (`anyone emerging would...`) rather than authoring an entrance in this unit.
- Therefore content adherence is not acceptable as a production-final E12U06 output.

## Verdict

- ArcReel -> H3 prompt lock: **PASS**
- AutoDL / MiniMax H3 provider execution: **PASS**
- Experimental `provider_duration_seconds` persistence: **PASS**
- Downloaded playable video artifact: **PASS**
- Technical duration/resolution inspection: **PASS**
- Visual prompt compliance: **PARTIAL / FAIL for production acceptance**
- Canonical-reference visual consistency: **NOT TESTED in this GitHub-runner smoke test**

Overall: **provider-level execution path is validated, but E12U06 is not production-approved on visual adherence.**

## Earlier harness attempts

Two earlier attempts on the same branch stopped before a provider task ID was obtained:

1. Wrong endpoint family (`/v2/video_generation`) against the project's AutoDL base URL -> HTTP 405.
2. Correct AutoDL endpoint, but invalid resolution literal `480p` -> provider parameter validation rejected it.

The successful run uses the project AutoDL contract and the accepted `480p横` resolution enum.
