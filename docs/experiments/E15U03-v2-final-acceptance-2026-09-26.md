# E15U03 MiniMax H3 acceptance — v2 final PASS

Date: 2026-09-26 (UTC+8)

## Canonical scope

E15U03 is Episode 15 shots 06–08, exactly 15 seconds:

- Shot 06, 00:00–00:05 — three months later, the large Tianshu product-launch venue lights up with the giant-screen title `TIANSHU NEXT`; slow pull-back; electronic music.
- Shot 07, 00:05–00:10 — invited industry guests and media fill the launch venue; lateral camera movement; crowd ambience.
- Shot 08, 00:10–00:15 — C01 沈知意 walks alone from backstage onto the main stage; slow push-in; applause.

Canonical visible text for this Unit is exactly `TIANSHU NEXT`. No dialogue is authored in these three shots.

## Upstream paid supplier render

- Supplier workflow run: `36009732060`
- Supplier head commit: `a5c192427d47c94fe9e60c9c0e5ca62aa35b4be8`
- Supplier task ID: `53944e96-e4b3-465f-b046-a8b6f111de3b`
- Artifact ID: `10812256991`
- Artifact name: `supplier-e15u03-evidence`
- Artifact SHA256: `e08dd2437e963d496cfeabc9962d6518df7ac2a1845271b8422ae964ab95f308`
- Source prompt SHA256: `b8143dfe1e500a83d6f45f0ca133cf3fed9ab55c7ab6739686c11b0f1eb87dd0`
- Source video SHA256: `17bc973ab13f9a3186c673dd24fa8aaafe6b6aa29f2e6a9b41596e18ea96ff36`
- Launch-venue reference SHA256: `87d54ccd76abd21e2a03e83036cac6af9469b6de50614a44c67196d0e8b9674a`
- C01 identity reference SHA256: `50893f22ed6e38bd3764f088ec2cd7e1f5ccecaaadd707e0d63ee2e217782bb9`

The original supplier result had strong content: exact `TIANSHU NEXT`, coherent premium venue, full crowd beat, and a solo C01 entrance in white professional tailoring with tied-back dark hair and gray structured handbag.

## Why the original supplier render was Content FAIL as-is

Dense boundary inspection of the exact supplier bytes found hard visual cuts at:

- frame 118 / 24 fps = 4.916666... s
- frame 222 / 24 fps = 9.25 s

So the source visual allocation was approximately Shot 06 = 4.9167 s, Shot 07 = 4.3333 s, and Shot 08 began at 9.25 s. Canonical requires 5 s + 5 s + 5 s. The main failure was the C01 entrance starting about 0.75 s early, shortening the audience/media beat.

Therefore: supplier SUCCESS + good visual content != canonical timeline PASS.

## v2 repair strategy

No new MiniMax H3 generation was requested. The exact paid supplier artifact was downloaded and SHA-verified, then ArcReel deterministically retimed both picture and sound per canonical beat.

Source segment frame counts:
- Shot 06 source = 118 frames
- Shot 07 source = 104 frames
- Shot 08 source = 120 frames
- target each = 120 frames

Video PTS factors:
- Shot 06 = 1.0169491525423728
- Shot 07 = 1.153846153846154
- Shot 08 = 1.0

Audio tempo factors:
- Shot 06 = 0.9833333333333334
- Shot 07 = 0.8666666666666666
- Shot 08 = 1.0

This avoids freezing the last picture frame while letting the original soundtrack cross the wrong editorial boundary. Picture and sound are retimed together as one authored beat.

## v2 deterministic repair run

- Branch: `fix/e15u03-h3-v2-deterministic-timeline`
- Workflow: `H3 E15U03 v2 Deterministic Timeline Repair`
- Run: `36201168299`
- Tested commit: `17b29826b5b947fa09f25478912369229b3fa75c`
- Workflow conclusion: **success**
- Deterministic tests: **6 passed**
- Python compile: **PASS**
- Ruff: **PASS**
- Original supplier artifact download + digest verification: **PASS**
- Provider recalled: **false**
- New paid provider calls: **0**

## Final media evidence

- duration = `15.000000 s`
- resolution = `864 × 480`
- frame rate = `24 fps`
- video codec = `H.264`
- audio codec = `AAC`
- audio rate = `32000 Hz`
- audio channels = `2`
- final v2 video SHA256 = `607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b`
- repair artifact ID = `10892326037`
- repair artifact name = `e15u03-v2-deterministic-timeline-evidence`
- repair ZIP SHA256 = `20e365dff6c1711158bafdaf386ab1a84494a6ac1a7bc044fe44b6ba01b27663`

## Dense 30-frame manual visual review

Review frames were inspected every 0.5 seconds from 0.25 s through 14.75 s.

### Gate A — Shot 06 / product-launch reveal

- 00:00–00:05 remains the launch reveal.
- `TIANSHU NEXT` is clearly and exactly readable.
- No additional readable headline, subtitle, logo text, or dialogue caption is observed.
- 4.75 s is still the title shot.

**PASS**

### Gate B — Shot 07 / audience and media

- 5.25 s through 9.75 s remain on the audience/media beat.
- Invited guests fill the venue and the lateral crowd composition remains intact.
- The backstage C01 entrance no longer appears early.
- 9.75 s is still the audience/media shot.

**PASS**

### Gate C — Shot 08 / C01 solo entrance

- 10.25 s is the intended backstage-to-stage C01 entrance.
- C01 walks alone toward the main stage.
- White professional pantsuit, tied-back dark hair, gray structured handbag, silhouette and face family remain consistent with the pinned C01 reference.
- No second principal woman or replacement identity appears.
- Entrance remains clean through 14.75 s.

**PASS**

### Gate D — exact visible-text whitelist

Canonical visible text is `TIANSHU NEXT`. Dense review found that exact title in Shot 06 and no other readable story text that needs to be accepted as Canonical.

**PASS**

### Gate E — exact editorial boundaries

- 4.75 s = Shot 06
- 5.25 s = Shot 07
- 9.75 s = Shot 07
- 10.25 s = Shot 08
- final ffprobe duration = `15.000000`

**PASS**

## Final verdict

**E15U03 v2 = FINAL PASS**

Closed gates:

- exact TIANSHU NEXT visible text — PASS
- Shot 06 full five-second reveal — PASS
- Shot 07 full five-second audience beat — PASS
- Shot 08 starts at canonical 10 s — PASS
- C01 solo identity / wardrobe continuity — PASS
- no extra readable story text — PASS
- picture + audio 5 s + 5 s + 5 s structure — PASS
- 864×480 H.264 + AAC final media — PASS

## Production lesson

When a provider render already contains the correct visual beats but cuts them at the wrong times, do not automatically regenerate. Measure the actual cut frames, pin the supplier bytes, and deterministically retime both picture and corresponding sound to the Canonical timeline.

Retiming only picture can create hidden audio/visual boundary drift. The timeline repair layer must treat visual beat + audio beat as one authored editorial unit.

With E15U03 v2 closed, the complete representative supplier-validation set is now closed:

- E12U06 — FINAL PASS
- E4U02 — FINAL PASS
- E13U01 — FINAL PASS
- E13U03 — FINAL PASS
- E11U02 — FINAL PASS
- E15U03 — FINAL PASS
