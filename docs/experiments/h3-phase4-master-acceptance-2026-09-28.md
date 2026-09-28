# ArcReel × MiniMax H3 — Phase 4 Master Acceptance — 2026-09-28

## Verdict

**PHASE 4 AUTO-REPAIR LOOP = FINAL PASS / CLOSED**

This document closes Phase 4 only after the complete production-policy integration,
deterministic runtime repair paths, fail-closed non-deterministic escalation path,
existing-media regressions, and the Phase 4 master gate all passed.

Formal stage state after this acceptance:

```text
Phase 1  CLOSED
Phase 2  CLOSED
Phase 3  CLOSED
Phase 4  CLOSED
Phase 5  NOT DEFINED
```

No paid MiniMax generation was performed by the final Phase 4 closure run.

---

## 1. Tested branch / code / run

Repository:

`locke-peng/ArcReel`

Branch:

`phase4/h3-auto-repair-loop`

**Tested code SHA:**

`48a6db8ff3f796535daff7acb29cdd54c62cd6ec`

Primary GitHub Actions run:

`36370583579`

Workflow:

`H3 Phase 4 Auto Repair Loop`

Run conclusion:

`success`

The acceptance and handoff documents are committed after the tested code SHA.
Do not rewrite a later documentation-only branch HEAD as the tested code SHA.

---

## 2. What Phase 4 now owns

The accepted production chain is:

```text
Canonical facts
→ H3 compile
→ Preview / Runtime Prompt SHA Lock
→ Provider bytes / existing media
→ trusted Media QA
→ structured MediaQAFinding
→ existing H3FailureClass
→ existing plan_h3_media_repair()
→ deterministic repair OR fail-closed Repair Ticket
→ Re-QA
→ evidence / formal-selection metadata
→ FINAL PASS or history-only blocker
```

Phase 4 did **not** create a second Repair Policy.

The single decision owner remains:

`plan_h3_media_repair()`

---

## 3. Accepted Phase 4 components

### Core Media QA / repair infrastructure

- `lib/reference_video/media_qa_schema.py`
- `lib/reference_video/h3_failure_classifier.py`
- `lib/reference_video/h3_repair_executor.py`
- `lib/reference_video/h3_auto_repair_loop.py`
- `lib/reference_video/h3_runtime_gate.py`
- `lib/reference_video/cut_detector.py`
- `lib/reference_video/evidence_schema.py`

### Deterministic production runtimes

- `lib/reference_video/h3_timeline_runtime.py`
- `lib/reference_video/h3_exact_text_contract.py`
- `lib/reference_video/h3_exact_text_runtime.py`
- `lib/reference_video/h3_audio_contract.py`
- `lib/reference_video/h3_audio_runtime.py`

### Non-deterministic safe escalation

- `lib/reference_video/h3_repair_ticket.py`
- `lib/reference_video/h3_shot_repair_executor.py`
- `docs/schemas/h3_repair_ticket.schema.json`

### Production wiring

- `server/services/reference_video_tasks.py`
- `server/services/video_artifact_currency.py`

Provider-required runtime findings are archived history-only and emit auditable repair
tickets. They do not trigger automatic supplier spend.

---

## 4. Software gates

Run `36370583579`:

```text
Phase 4 primitive/runtime/wiring tests       58 passed
Phase 3 repair planner regression            11 passed
Six representative Unit joint regression    41 passed
H3 Compiler + Preview/Runtime Lock           13 passed
Reference Video / H3 subsystem              420 passed
Python compile                               PASS
Ruff                                         PASS
```

All software jobs completed successfully.

---

## 5. Deterministic repair closure

### E11U02 — local non-canonical surface

Accepted route:

```text
LOCAL_NONCANONICAL_SURFACE
→ DETERMINISTIC_SURFACE_REPAIR
→ provider_recalled = false
```

Current closure run revalidated the retained accepted Phase 4 media artifact.

Final SHA256:

`7ef19e68dbf5b14defc3b68886768424e7814f6017badc7cfb6fa94650270949`

### E15U03 — canonical timeline

Accepted route:

```text
TIMELINE_ONLY_FAILURE
→ DETERMINISTIC_AV_RETIME
→ provider_recalled = false
```

Final SHA256:

`607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b`

Final cut frames:

`120 / 240`

Equivalent authored cut times at 24 fps:

`5.000s / 10.000s`

### E13U01 — exact text

Accepted route:

```text
EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE
→ Re-QA
→ PASS
```

Run `36370583579` result:

- provider recalled: `false`
- repair passes: `1`
- final cut: frame `120` / `5.000s`
- accepted-vs-replay video SSIM: `0.997278`
- final media SHA256:
  `cda5e7e7325526b2f010d47c84ac6ffbe0347d8f50e079fe11976604f3ca2373`
- evidence head:
  `0314257ed27bef34ced29a42a93b9214de8a4a0d11bfccbcee898aacb112fac8`

### E13U01 — canonical audio

Accepted route:

```text
AUDIO_ONLY_FAILURE
→ AUDIO_REPAIR_REMUX
→ Re-QA
→ PASS
```

Run `36370583579` result:

- provider recalled: `false`
- final media SHA256 equals the formally accepted E13U01 final:
  `8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12`
- accepted/final video framemd5 SHA256:
  `b81f28877358718d7457688b0a7a52dcad476de33e3303f2c4b5996287f1e9ee`
- accepted/final audio framemd5 SHA256:
  `842174439856b66ef4119f32f3ddf1052d32ca83bc3cff44d736bf281578af0b`
- accepted-vs-replay video SSIM: `1.0`
- evidence head:
  `72ea121155a59d1201597416c69a831def99bb67f16c5d0469f7eae12f560e75`

---

## 6. Non-deterministic failure safe escalation closure

Phase 4 now converts provider-required failures into immutable, shot-scoped, auditable
Repair Tickets instead of silently recalling the provider.

Ticket identity binds, where available:

- unit / shot scope;
- Canonical time range;
- existing `H3FailureClass`;
- existing planner action;
- source media SHA256;
- Provider Prompt SHA256;
- Reference SHA256 values;
- evidence frames;
- historical provider run/artifact provenance;
- ticket SHA256.

Provider execution remains disabled until a matching explicit approval is supplied to the
separate shot-scoped execution boundary.

Unknown/unscoped failures remain human-review-only.

### E12U06 existing-evidence safe escalation

Historical supplier media:

`3b1f445009afe1858fd65743d3c55ef2952140e5298246384c287fd9f164cdea`

Route:

```text
E12U06-S02
LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ PROVIDER_REPAIR_REQUIRED
→ Repair Ticket
→ no automatic provider call
```

Ticket:

- id:
  `h3rt_2a28219e0e804e63c322dbef`
- SHA256:
  `2a28219e0e804e63c322dbefae4810b3580b21a73d74f346f808fd119316e2f3`
- scope:
  `5.0s–10.0s / E12U06-S02`
- provider prompt SHA:
  `4c3e7fdcb8aedf106779e2a926242a241a9bd1048b214123c9fb0ffe32586aed`
- approval eligible:
  `true`

### E13U03 independent multi-shot escalation

Source accepted final:

`63a1238ae14161e7549fc9927adc611a3ba3aa7b6879c9050bac9a7a2fdf7b58`

Shot 07:

```text
IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
→ independent Repair Ticket
```

Ticket:

- id:
  `h3rt_e035b1205dd231007e0d5d4f`
- SHA256:
  `e035b1205dd231007e0d5d4f56527cea52db16621d4df2ea5480fa2c5dbe0856`
- scope:
  `5.0s–10.0s / E13U03-S07`

Shot 08:

```text
LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ independent Repair Ticket
```

Ticket:

- id:
  `h3rt_3ce2143407408985ceb61631`
- SHA256:
  `3ce2143407408985ceb6163174c6946bb27f7d7b8087080d7b244da2473f800a`
- scope:
  `10.0s–15.0s / E13U03-S08`

The two failures were not collapsed into one 15-second Unit regeneration.

Final safe-escalation E2E result:

```text
status               FINAL_PASS
provider_recalled    false
paid_provider_calls  0
```

---

## 7. Six representative Unit routing remains closed

```text
E12U06
semantic / invented content
→ LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ approval-gated provider path

E4U02
dialogue visual leakage
→ DIALOGUE_VISUALIZATION
→ RECOMPILE_DIALOGUE_DETACHED
→ approval-gated provider path

E4U02
identity drift
→ IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
→ approval-gated provider path

E13U01
exact visible canonical text
→ EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE

E13U01
canonical full-unit soundtrack mismatch
→ AUDIO_ONLY_FAILURE
→ AUDIO_REPAIR_REMUX

E13U03
multi-shot semantic failure
→ independent shot-scoped tickets / repairs

E11U02
local non-canonical surface
→ DETERMINISTIC_SURFACE_REPAIR

E15U03
cut timing only
→ DETERMINISTIC_AV_RETIME
```

The six representative Units remain regression baselines. They are not reopened.

---

## 8. Final Phase 4 closure artifacts

Primary run:

`36370583579`

### Master gate

- Artifact ID: `10948939029`
- name: `phase4-master-gate`
- digest:
  `sha256:4bd6eca3f50a0821ac2982f23ab4016bda17a4adb0fadd1b03d95620601bb0d4`

### Safe escalation

- Artifact ID: `10948993658`
- name: `phase4-safe-escalation-e2e-evidence`
- digest:
  `sha256:7ae5e94ddb716148007d0ca0410560359ae55fa00c18aad934717c7abae90ba6`

### Existing deterministic evidence regression

- Artifact ID: `10948508527`
- name: `phase4-existing-evidence-regression`
- digest:
  `sha256:23d4d530aeffc41ff5288547c345c167acd2517ed4d6b4239b56adf56c526f7c`

The original E15 supplier source artifact had reached retention expiry by the final closure
run. The closure therefore revalidated the latest accepted Phase 4 E11/E15 evidence from
run `36287909253` and simultaneously reran the current software regression suite. No
supplier regeneration was substituted for the expired artifact.

### Exact text

- Artifact ID: `10949166837`
- name: `phase4-e13u01-exact-text-e2e-evidence`
- digest:
  `sha256:76d213ad6dfcffbbc71aac78abb0625c15a58741eae27ffe9760e9178c8de3b7`

### Canonical audio

- Artifact ID: `10948418658`
- name: `phase4-e13u01-audio-repair-e2e-evidence`
- digest:
  `sha256:e39f4a227c1833f673cc83de74772e8fdee5a73a5e5f29fc8ea16243a1697e7b`

---

## 9. Phase 4 closure statement

The following are now accepted production invariants:

1. Canonical remains the fact source.
2. Prompt remains a compiler output.
3. `H3FailureClass` and `plan_h3_media_repair()` remain the single policy taxonomy/planner.
4. Deterministic failures are repaired locally at the narrowest safe granularity.
5. Deterministic repair is followed by Media QA again before formal selection.
6. Provider-required failures do not automatically spend supplier credits.
7. Provider-required failures emit auditable Repair Tickets.
8. Provider repair scope must remain shot-scoped where the finding is shot-scoped.
9. Multi-shot semantic failures remain independently addressable.
10. Unknown or insufficiently scoped failures fail closed for human review.
11. Paid provider bytes that fail runtime QA remain history-only.
12. Repair evidence and formal-selection metadata preserve immutable SHA identities.
13. No expired historical artifact may be replaced by an unapproved fresh supplier call merely to keep CI green.

With run `36370583579` and master-gate artifact `10948939029` successful:

**Phase 4 is CLOSED.**

Phase 5 has not yet been formally defined.
