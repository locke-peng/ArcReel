# ArcReel × MiniMax H3 — Phase 4 Final Handoff — 2026-09-28

## 1. Formal phase state

```text
Phase 1 — H3 Native Integration Foundation             CLOSED
Phase 2 — Representative Supplier Validation           CLOSED
Phase 3 — Production Policy + Regression Generalization CLOSED
Phase 4 — Auto-Repair Loop Integration                 CLOSED
Phase 5                                                NOT DEFINED
```

Phase 4 must not be reopened unless a real regression, missing acceptance artifact, or
new requirement is demonstrated.

---

## 2. Authoritative Phase 4 closure anchors

Repository:

`locke-peng/ArcReel`

Branch:

`phase4/h3-auto-repair-loop`

**Tested code SHA:**

`48a6db8ff3f796535daff7acb29cdd54c62cd6ec`

Primary final GitHub Actions run:

`36370583579`

Conclusion:

`success`

Master acceptance:

`docs/experiments/h3-phase4-master-acceptance-2026-09-28.md`

Master gate artifact:

- ID: `10948939029`
- name: `phase4-master-gate`
- digest:
  `sha256:4bd6eca3f50a0821ac2982f23ab4016bda17a4adb0fadd1b03d95620601bb0d4`

Documentation commits after the tested code SHA are not tested-code SHAs.

---

## 3. Phase 4 accepted production behavior

The closed production loop is:

```text
Canonical
→ H3 Compile
→ Preview / Runtime Prompt Lock
→ Provider / Existing Media
→ trusted Media QA
→ MediaQAFinding
→ existing H3FailureClass
→ existing plan_h3_media_repair()
→ deterministic repair OR fail-closed provider escalation
→ Re-QA
→ Evidence / Formal Selection
```

There is still one and only one repair-policy owner:

`plan_h3_media_repair()`

Do not create a second failure taxonomy, repair planner, or shadow provider policy.

---

## 4. Deterministic paths accepted in production

```text
LOCAL_NONCANONICAL_SURFACE
→ DETERMINISTIC_SURFACE_REPAIR

EXACT_TEXT_REQUIRED
→ DETERMINISTIC_TEXT_PLATE

TIMELINE_ONLY_FAILURE
→ DETERMINISTIC_AV_RETIME

AUDIO_ONLY_FAILURE
→ AUDIO_REPAIR_REMUX
```

All deterministic runtime repairs are followed by Media QA again before formal selection.

Representative accepted regressions remain:

- E11U02 — local surface repair
- E15U03 — actual-cut detection + A/V retime
- E13U01 — exact-text deterministic plate
- E13U01 — canonical-audio deterministic remux

---

## 5. Non-deterministic paths accepted in production

Provider-required failures no longer trigger implicit provider regeneration.

```text
LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ Repair Ticket
→ explicit approval required

DIALOGUE_VISUALIZATION
→ RECOMPILE_DIALOGUE_DETACHED
→ Repair Ticket
→ explicit approval required

IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
→ Repair Ticket
→ explicit approval required

UNKNOWN
→ HUMAN_REVIEW_REQUIRED
→ no automatic provider call
```

Key modules:

- `lib/reference_video/h3_repair_ticket.py`
- `lib/reference_video/h3_shot_repair_executor.py`
- `docs/schemas/h3_repair_ticket.schema.json`

The execution boundary requires approval to bind to the exact ticket ID/SHA, source media
SHA, and shot scope. Source media is rehashed before the provider runner may execute.

Shot-scoped findings must remain shot-scoped. Multi-shot failures require independent
tickets rather than one blind whole-Unit regeneration.

---

## 6. Final closure regression

Run `36370583579`:

```text
Phase 4 primitive/runtime/wiring             58 passed
Phase 3 repair-planner regression             11 passed
Six representative Unit joint regression     41 passed
H3 Compiler + Preview/Runtime Lock            13 passed
Reference Video / H3 subsystem               420 passed
Python compile                                PASS
Ruff                                          PASS
```

Jobs:

```text
software-gates             SUCCESS
existing-evidence-e2e      SUCCESS
audio-only-e2e             SUCCESS
exact-text-e2e             SUCCESS
safe-escalation-e2e        SUCCESS
phase4-master-gate         SUCCESS
```

Final closure run made no paid MiniMax generation calls.

---

## 7. Final artifacts

### Existing deterministic evidence regression

- Artifact ID: `10948508527`
- digest:
  `sha256:23d4d530aeffc41ff5288547c345c167acd2517ed4d6b4239b56adf56c526f7c`

### E13U01 exact text

- Artifact ID: `10949166837`
- digest:
  `sha256:76d213ad6dfcffbbc71aac78abb0625c15a58741eae27ffe9760e9178c8de3b7`

### E13U01 canonical audio

- Artifact ID: `10948418658`
- digest:
  `sha256:e39f4a227c1833f673cc83de74772e8fdee5a73a5e5f29fc8ea16243a1697e7b`

### Safe escalation

- Artifact ID: `10948993658`
- digest:
  `sha256:7ae5e94ddb716148007d0ca0410560359ae55fa00c18aad934717c7abae90ba6`

### Master gate

- Artifact ID: `10948939029`
- digest:
  `sha256:4bd6eca3f50a0821ac2982f23ab4016bda17a4adb0fadd1b03d95620601bb0d4`

---

## 8. Safe-escalation representative evidence

E12U06:

```text
E12U06-S02
LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ one approval-gated Repair Ticket
→ provider_recalled = false
```

E13U03:

```text
E13U03-S07
IDENTITY_CONTINUITY_FAILURE
→ REGENERATE_WITH_IDENTITY_BRIDGE
→ independent ticket

E13U03-S08
LARGE_SEMANTIC_FAILURE
→ REGENERATE_SHOT
→ independent ticket
```

The final safe-escalation acceptance recorded:

```text
status               FINAL_PASS
provider_recalled    false
paid_provider_calls  0
```

---

## 9. Six representative Units remain CLOSED

```text
E12U06  FINAL PASS
E4U02   FINAL PASS
E13U01  FINAL PASS
E13U03  FINAL PASS
E11U02  FINAL PASS
E15U03  FINAL PASS
```

Do not re-run paid supplier tests for these Units merely to reconfirm an already-closed
phase. Use retained SHA-pinned evidence and regression tests.

---

## 10. Artifact-retention rule learned during closure

The historical E15 raw supplier artifact expired during Phase 4 final closure.

Correct handling was:

```text
expired historical raw artifact
→ do NOT call provider again
→ use latest retained accepted Phase 4 evidence
→ verify immutable final media SHA / probe / cut facts
→ run current software regression
```

Do not use an expired CI artifact as justification for unapproved supplier spend.

---

## 11. What Phase 4 deliberately does not include

Phase 4 provides the approval-bound provider-repair execution primitive, but it does not
define a new user-facing approval product, queue UX, budget dashboard, or project-wide
production-operations phase.

Those are potential future requirements only.

**Phase 5 is not yet formally defined.**

Before starting a new phase, first write its scope, non-goals, acceptance criteria, and
evidence requirements. Do not silently extend Phase 4 after closure.

---

## 12. New-conversation startup order

A future conversation continuing this work should read, in order:

1. `docs/handoffs/phase1-phase3-master-handoff-2026-09-27.md`
2. `docs/handoffs/phase3-to-phase4-handoff-2026-09-27.md`
3. `docs/experiments/h3-phase4-master-acceptance-2026-09-28.md`
4. this file

Then verify the current repository HEAD descends from the tested code SHA and check for
post-closure code changes.

Do not infer project state from chat memory alone.

---

## 13. Closure statement

**Phase 4 is formally CLOSED.**

The authoritative tested code remains:

`48a6db8ff3f796535daff7acb29cdd54c62cd6ec`

Any later documentation-only commit is provenance history, not a replacement tested SHA.
