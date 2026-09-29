# H3 doc-pack experiment v1

Baseline: 3b3bc527197bad66ac0425094036ea86b0add7e8 (H3 V6 + V6.1 preview/runtime lock).

This branch validates only deltas that can be isolated and regression-tested from the 2026-09-06 repair package.

## Included

- Persist positive VideoGenerationResult.duration_seconds as provider_duration_seconds in version metadata.
- If ffprobe/media probing cannot return a duration, presentation materialization falls back in this order:
  1. provider_duration_seconds
  2. legacy duration_seconds (requested duration compatibility only)
- Keep all existing artifact manifest, typed provenance, content digest, selection, and preview/runtime prompt-lock checks intact.
- Add a MiniMax H3 regression case for the documented 15-second upper bound.

## Explicitly excluded

- No STALE bypass.
- No content-digest bypass.
- No replacement of lib/artifact_input_claims.py from the repair ZIP.
- No optimize_scripts_v2.py / optimize_scripts_v3.py destructive text rewriting.
- No hard-coded project IDs, local Windows paths, or API keys.

## Acceptance intent

This is an experiment branch only. It should not be merged into the formal line until CI passes and representative ArcReel/H3 units are exercised against the configured provider.
