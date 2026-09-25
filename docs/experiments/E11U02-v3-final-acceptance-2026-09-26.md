# E11U02 MiniMax H3 supplier acceptance — v3 FINAL PASS

Date: 2026-09-26 (UTC+8)

## Canonical scope

E11U02 is Episode 11 shots 03–05, exactly 15 seconds:

- Shot 03, 10–15s — research team executes; model becomes stable; researcher says `通过了`; cheer.
- Shot 04, 15–20s — 江屿 places the formal summit guest badge beside 沈知意; 江屿 says `明天见真章`.
- Shot 05, 20–25s — AI summit media zone; 陆予深 and 苏晚 enter together; reporter asks `陆氏会合作吗`; camera flashes.

Canonical provides no required visible typography for these three shots.

## Failure history

### v1 — supplier execution succeeded, content remained unsafe

The first paid three-plate run demonstrated that prompt-only "ZERO readable text" constraints were not sufficient for screen- and credential-heavy imagery. The Unit was not closed.

### v2 — stronger physical / framing constraints, still CONTENT FAIL

Paid supplier run:

- GitHub Actions run: `36148270693`
- head: `e3d5e8abd053442c5981ca76ff4e57a6a84beae4`
- artifact ID: `10870732082`
- artifact digest: `958e1f625f48acb46701b28f6e353de9841532012fdf3db88ff6792a0b3ffabc`
- deterministic tests: 9 passed
- compile: PASS
- Ruff: PASS
- provider: AutoDL / MiniMax H3
- provider model: `minimax_h3_zm_u24`
- final authored duration: 15.000000s
- final authored resolution: 864×480

v2 improved the prompts by asking for:

- physical non-linguistic model-stability state,
- face-down / blank badge behavior,
- black-drape media corridor,
- dialogue detached from visual prompts.

Dense review still found one decisive failure: H3 generated a visible printed/logo-like field on the summit badge in Shot 04. Smaller screen / supporting-credential text surfaces also remained model-controlled.

Therefore:

```text
Provider SUCCESS
+ Contract PASS
+ exact timeline
!= Content PASS
```

v2 was not accepted.

## v3 architecture

v3 does **not** spend another provider generation call.

It consumes the exact paid v2 supplier outputs as immutable, SHA-pinned source material and performs deterministic ArcReel post-processing only:

```text
exact paid H3 v2 supplier plates
        ↓
verify provider-video SHA256
        ↓
Shot 03: deterministic screen-surface defocus
Shot 04: deterministic time-varying badge-typography defocus
Shot 05: deterministic side-media / exit-sign defocus
        ↓
reuse exact detached canonical soundtrack
        ↓
deterministic 5s + 5s + 5s authoring
        ↓
dense visual QA
```

This changes ownership of accidental typography from the generative layer to the deterministic composition layer.

## Immutable upstream provenance

v3 accepts only these exact source bytes:

```text
Shot 03 provider raw
aecded93bd579ea89cb65f1f7c431446f55c4eac516ce85f90964a408d027a48

Shot 04 provider raw
7effe252c0c0384a7697002d8d095b95cbade03f695949d46e014d2816091507

Shot 05 provider raw
ad6dc5cec862220754b9ba082cdf12f2fb3e569e8777873294e7231b728b9751

Canonical detached soundtrack
dd8be354040d959ff7e94b2c6e7220148373a2c10c897b88d0b8c6984d9486d2
```

Any SHA mismatch fails closed before repair.

## v3 deterministic workflow

- Branch: `fix/e11u02-h3-v3-deterministic-text-scrub`
- GitHub Actions run: `36169166450`
- tested commit: `fb14c8f3fe4cbf20e13bdccd69afaa2f622cb4c1`
- workflow: `H3 E11U02 v3 Deterministic Repair`
- workflow conclusion: **success**
- deterministic contract tests: **6 passed**
- Python compile: **PASS**
- Ruff: **PASS**
- v2 supplier artifact download digest verified: **PASS**
- provider recalled: **false**
- v3 evidence artifact ID: `10879951993`
- v3 evidence ZIP SHA256: `e8177c402d2d6c0d56080f072586e957c5c09f2e6dee1505cd4044ead12bb2db`

## v3 output hashes

```text
processed Shot 03
ef65512af75d17ab18011ff3e93fa7277eed1d0b559a2a7c22d44f5a2ec24fd0

processed Shot 04
d0b9d399d140310d5e40c2dd92fa3a602ddef6cb6ebfadf13090841f84207aa9

processed Shot 05
c7441483ccf9abd3e09fecc198c75d1231364e95ebcc1b87897b3d825c034fbb

final video
7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949
```

Final media:

```text
duration  = 15.000000s
resolution = 864×480
video      = H.264
fps        = 24
audio      = AAC
sample rate = 32000
channels    = 2
```

## Dense 30-frame visual review

Frames reviewed every 0.5 seconds from 0.25s through 14.75s.

### Gate A — Shot 03 / model becomes stable

00:00–00:05:

- same high-end AI laboratory visual language;
- research-team execution beat remains readable;
- foreground equipment state visibly changes from amber activity to a steady green physical status indicator;
- deterministic defocus removes readable / pseudo-readable content from the SHA-pinned display surfaces;
- no canonical principal identity is invented by close facial framing.

**PASS**

### Gate B — Shot 04 / summit badge placement

00:05–00:10:

- one man's hand places the credential beside the woman's hand;
- the physical badge and lanyard action remain intact;
- H3's hallucinated printed/logo field is deterministically defocused through the entire visible trajectory;
- no readable badge typography remains;
- faces remain outside frame.

**PASS**

### Gate C — Shot 05 / summit media entry

00:10–00:15:

- one dark-suited male silhouette and one warm-ivory/champagne female silhouette enter together;
- both stay rear / three-quarter-rear, so no unsupported C02/C04 facial identity is invented;
- media presence and flash-light atmosphere remain readable;
- side-media credential surfaces and the top exit-sign area are defocused;
- no readable supporting text is relied upon.

**PASS**

### Gate D — dialogue / audio separation

The exact detached v2 soundtrack is reused without regeneration.

Canonical dialogue carried by that soundtrack:

```text
通过了
明天见真章
陆氏会合作吗
```

Visual repair never reintroduces dialogue text.

AAC stereo audio remains in the final MP4.

**PASS**

### Gate E — editorial timing

```text
00:00–00:05  Shot 03
00:05–00:10  Shot 04
00:10–00:15  Shot 05
```

ffprobe final duration: `15.000000s`.

**PASS**

## Final verdict

**E11U02 v3 = FINAL PASS**

Closed gates:

```text
Canonical shots 03–05               PASS
model-stability physical state       PASS
badge placement action               PASS
summit media-entry action            PASS
no invented principal faces          PASS
no readable non-canonical typography PASS
dialogue remains audio-only          PASS
5s + 5s + 5s authored timing         PASS
864×480 H.264 + AAC final media      PASS
```

## Production lesson

E11U02 establishes a useful escalation ladder for typography risk:

```text
Prompt negative constraint
        ↓ if still leaking
remove text-bearing semantics from visual prompt
        ↓ if still leaking
change framing / remove risky surfaces
        ↓ if the paid motion plate is otherwise good
deterministically scrub only the non-canonical text surface
```

The last step is important: when H3 has already produced correct motion, staging, wardrobe and timing, regenerating the whole plate can be both expensive and destabilizing. If the remaining defect is localized, non-canonical typography, ArcReel should repair that defect deterministically while preserving the exact supplier motion bytes and evidence chain.

This is not a license to "fix the story in post." Deterministic post-processing may remove model-invented material; it must not invent new Canonical facts.
