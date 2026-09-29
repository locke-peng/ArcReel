# H3 Legacy Code Archaeology — `feat/h3-six-unit-regression-pipeline-validator` — 2026-09-30

## 0. Scope

This audit covers only the legacy branch:

`feat/h3-six-unit-regression-pipeline-validator`

Legacy head:

`34055a0682908a211f77fd78f33b0d45e42d4801`

At audit time the branch is diverged from current `main` with 81 unique legacy commits. This audit does not open a new Phase and does not change Phase 1–6 acceptance authority.

## 1. Executive conclusion

**Disposition: SUPERSEDED IMPLEMENTATION / ARCHIVE-ONLY**

The branch should not be merged or rebased onto current `main`.

Its useful production concepts have either:

1. been absorbed by the accepted Phase 3–6 architecture with stronger trust/approval boundaries; or
2. been intentionally left out of production wiring because the old implementation accepted repair geometry/semantics from a request payload rather than from a trusted internal Media-QA producer.

No production code migration from this branch is required now.

## 2. Capability-by-capability parity

### A. Production repair policy

Legacy:

- `MediaIssueCode`
- `RepairAction`
- `plan_h3_media_repair(issues)`

Current main:

- `H3FailureClass`
- `H3RepairAction`
- `H3MediaFailure`
- the authoritative `plan_h3_media_repair(failure)`
- `h3_failure_classifier.py`

Result: **SUPERSEDED / COVERED**

Current policy is richer and is already the single accepted repair authority. Reintroducing the legacy taxonomy would violate the no-second-policy invariant.

### B. Post-provider QA classification

Legacy:

- `ObservationKind`
- `MediaObservation`
- observation-to-issue mapping inside `h3_media_pipeline.py`

Current main:

- `MediaQAFinding`
- `MediaQASeverity`
- `MediaQARepairability`
- `classify_h3_media_finding()`

Result: **SUPERSEDED / COVERED**

Current structured findings carry unit/shot/time-range/region/evidence-frame facts and route into the single Phase 3 planner.

### C. Deterministic A/V retime

Legacy:

- request-supplied timeline segments
- generic deterministic AV executor

Current main:

- `h3_timeline_runtime.py`
- canonical shot boundaries are resolved from trusted Canonical Director facts
- actual cuts are detected from real media
- picture/audio are retimed together
- Re-QA occurs before formal selection

Result: **COVERED WITH STRONGER TRUST BOUNDARY**

The current implementation is preferable because timing facts are derived from Canonical + actual media rather than arbitrary request-supplied segment plans.

### D. Exact text authoring

Legacy:

- low-level `DETERMINISTIC_TEXT_PLATE` repair primitive

Current main:

- `h3_exact_text_contract.py`
- `h3_exact_text_runtime.py`
- SHA-pinned deterministic plate contracts
- SSIM verification
- full-frame bounded replacement
- audio preservation
- automatic Re-QA

Result: **COVERED WITH STRONGER CONTRACT**

### E. Audio repair

Legacy branch did not have the final accepted canonical full-unit audio contract.

Current main adds:

- `h3_audio_contract.py`
- `h3_audio_runtime.py`
- SHA-pinned canonical soundtrack
- deterministic AAC/M4A generation
- decoded-audio fingerprint QA
- picture-preserving remux

Result: **CURRENT MAIN IS STRICTLY MORE COMPLETE**

### F. Provider-required semantic repair

Legacy:

- local deterministic worker explicitly rejected semantic repairs.
- provider recall was only a boolean planning outcome.

Current main:

- immutable shot-scoped Repair Ticket
- source-media SHA binding
- provider-prompt SHA binding
- reference SHA binding
- explicit approval
- provider-call reservation
- duplicate execution protection
- provider repair runtime
- deterministic reassembly
- mandatory Re-QA
- formal-selection gate
- Phase 6 project capacity/budget/operator controls

Result: **SUPERSEDED BY PHASE 5–6**

### G. Separate local repair worker lane

Legacy:

`reference_video provider task → QA → h3_media_repair local queue task → VersionManager selection`

with:

- `expected_source_sha256`
- local provider id
- isolated local worker capacity
- current-version CAS
- orphaned-task fail-closed behavior

Current main:

For trusted deterministic repairs:

`provider staged bytes → trusted Media QA → deterministic handler → Re-QA → formal selection`

For provider-required repairs:

`Repair Ticket → approval → queue → provider execution → Re-QA → selection`

Result: **INTENTIONALLY SUPERSEDED**

The current deterministic path repairs the staged artifact before it becomes formal, eliminating the need to mutate a previously selected current artifact through a second local queue. Provider-required work uses the Phase 5 persisted queue/ticket model instead.

### H. Evidence chain / source binding

Legacy:

- `EvidenceNode`
- artifact-parent SHA DAG
- multiple immutable roots
- provider output / canonical asset roots
- repair output parent binding
- provider prompt hash
- sidecar JSON

Current main:

Phase 4:

- `H3EvidenceRecord`
- record SHA
- previous-record SHA
- `source_media_sha256[]`
- `reference_sha256[]`
- provider task/run/artifact provenance
- pre/post media SHA
- actual-cut facts / media probe / evidence frames

Phase 5–6:

- immutable Repair Ticket SHA
- approval snapshot
- execution identity
- execution checkpoint digest
- provider-call ledger
- repair output SHA
- Re-QA outcome
- selected artifact/version
- deterministic project evidence bundle SHA

Canonical deterministic assets additionally carry their own contract SHA / asset SHA.

Result: **SEMANTICALLY COVERED; DATA MODEL CHANGED**

The old explicit multi-root artifact DAG was not preserved verbatim. Its required provenance semantics are represented across source/reference SHA arrays, canonical contract hashes, record chaining, ticket lineage, execution checkpoint digest and selected artifact/version lineage.

Do not reintroduce the old evidence DAG as a second evidence authority.

## 3. One intentionally non-productionized capability

### Generic keyframed pixel/surface repair

Legacy branch supported:

- explicit rectangular repair regions;
- keyframed moving regions;
- blur radius / opacity;
- weighted pixel sanitization;
- a local worker accepting those coordinates from the repair request.

Current repair policy still contains:

`LOCAL_NONCANONICAL_SURFACE → DETERMINISTIC_SURFACE_REPAIR`

and Phase 4 retained E11U02 as accepted deterministic-surface evidence.

However, current production runtime intentionally does **not** register a generic surface-repair handler.

The Phase 4 runtime acceptance explicitly established that:

- Media-QA evaluators and deterministic handlers must be trusted internal dependencies;
- the runtime gate must not derive pixel-level repair semantics from arbitrary request payload;
- missing trusted handlers fail closed.

Therefore the absence of the old request-driven region/keyframe worker is **not a migration defect**.

It is an intentionally unproductionized capability until a trusted internal producer can generate bounded repair geometry from authoritative evidence.

### Future rule

If generic surface repair is ever productionized, it must:

1. preserve `H3FailureClass` and `plan_h3_media_repair()` as the only policy authority;
2. obtain geometry from a trusted internal Media-QA producer, not user/request assertions;
3. bind geometry to exact source-media SHA;
4. remain deterministic and provider-free;
5. run Re-QA after repair;
6. preserve immutable evidence of input SHA, repair facts and output SHA;
7. never bypass the formal-selection gate.

That work would require an explicit maintenance charter or future Phase charter; it should not be smuggled in by reviving this legacy branch.

## 4. Historical artifacts worth retaining

The branch remains useful as archaeology for:

- early Phase 2 provider-evidence root experiments;
- early Phase 3 deterministic repair executors;
- keyframed pixel sanitization prototype;
- multi-root evidence DAG prototype;
- local repair worker / CAS selection prototype;
- Phase 3 real-evidence migration scripts and acceptance records.

These are historical references, not active production authorities.

## 5. Branch retirement status

The branch may now be reclassified from:

`CODE-ARCHAEOLOGY`

to:

`ARCHIVE-ONLY / SUPERSEDED IMPLEMENTATION`

It is safe to exclude from future merge candidates.

Physical branch-ref deletion is still not performed because the current GitHub connection does not expose delete-ref capability.

Legacy head to preserve in the audit record before any future ref deletion:

`34055a0682908a211f77fd78f33b0d45e42d4801`

## 6. Stop boundary

- No code from this legacy branch is migrated.
- No second repair policy/evidence authority/local queue is created.
- Phase 1–6 remain CLOSED.
- No Phase 7 is opened.
