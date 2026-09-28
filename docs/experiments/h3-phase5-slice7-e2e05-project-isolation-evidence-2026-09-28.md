# ArcReel × MiniMax H3 — Phase 5 Slice 7 E2E-05 Project Isolation Evidence — 2026-09-28

## Verdict

**E2E-05 — MULTI-PROJECT / PROJECT ISOLATION = PASS**

This evidence proves that identically shaped H3 Repair Tickets in separate ArcReel projects remain isolated across persistence, approval, queue execution identity, provider-call allowance, and execution checkpoint state.

No live or paid MiniMax request was performed.

---

## 1. Tested repository state

Repository:

`locke-peng/ArcReel`

Branch:

`phase5/h3-production-orchestration`

Slice 7 PR:

`#14 ci: validate Phase 5 Slice 7 production lifecycle evidence`

**Tested SHA:**

`842cf175c9530e3fdde0e19c6265298e665a8b6f`

Workflow:

`.github/workflows/h3-phase5-slice7-e2e05.yml`

E2E source:

`tests/e2e/reference_video/test_h3_phase5_project_isolation_e2e.py`

---

## 2. GitHub Actions evidence

Workflow:

`H3 Phase 5 Slice 7 E2E-05`

Run:

`36438948627`

Job:

`108984090920 project-isolation-e2e`

Result:

```text
SUCCESS
```

The workflow runs the project-isolation E2E and then independently validates the emitted machine-readable evidence.

---

## 3. Uploaded machine-readable artifact

Artifact ID:

`10976129651`

Artifact name:

`h3-phase5-slice7-e2e05-842cf175c9530e3fdde0e19c6265298e665a8b6f`

Artifact digest:

`sha256:648fe69da08e712a00c8af21e8adfe0b0dcaad0dfcb3c85795219e448c2f1a9a`

Artifact size:

`641 bytes`

Retention expiry:

`2026-10-28T14:51:15Z`

Contained evidence file:

`e2e05-project-isolation.json`

---

## 4. Isolation scenario

The E2E intentionally persists the same immutable Repair Ticket identity in two projects:

```text
project-a / shared ticket ID
project-b / shared ticket ID
```

The projects then proceed independently through:

```text
persist
→ approve
→ enqueue
→ claim
→ provider-call reservation
```

Approval identities are distinct:

```text
project-a → operator:a
project-b → operator:b
```

Queue execution is also distinct:

- project A and project B receive different task IDs;
- project A and project B receive different execution identities;
- both tickets can be claimed independently.

---

## 5. Provider allowance / checkpoint isolation

The test reserves a provider submission only for project A.

Final facts:

```text
project-a provider_call_count = 1
project-b provider_call_count = 0

project-a execution checkpoint = present
project-b execution checkpoint = absent
```

Neither project has a provider job ID because the E2E stops at the controlled reservation boundary.

This proves that a reservation in one project does not consume the other project's provider-call allowance and does not create execution checkpoint state in the other project.

Paid MiniMax calls:

`0`

---

## 6. Lookup isolation

A lookup of the same ticket ID under a third project returns no ticket:

```text
project-c lookup = None
```

The ticket ID therefore has meaning only together with its project scope; a matching ticket ID in another project cannot be used to read or mutate the original project's repair lifecycle.

---

## 7. E2E-05 acceptance checklist

- same immutable ticket ID may coexist in separate projects: PASS
- project-specific approval identities remain isolated: PASS
- task IDs are distinct: PASS
- execution identities are distinct: PASS
- both projects can be claimed independently: PASS
- project A reservation consumes only project A allowance: PASS
- project B provider_call_count remains 0: PASS
- project A checkpoint does not leak into project B: PASS
- third-project lookup returns no ticket: PASS
- paid MiniMax calls: 0

**E2E-05 = PASS**

---

## 8. Slice 7 state after E2E-05

The following Slice 7 evidence scenarios are now locked:

```text
E2E-01 Production Lifecycle                PASS
E2E-02 Interruption / Resume               PASS
E2E-03 Stale Approval Rejection            PASS
E2E-04 Duplicate Execution / Single Winner PASS
E2E-05 Multi-Project Isolation             PASS
```

E2E-05 does not by itself close Slice 7 or Phase 5.

The next step is to reconcile the remaining Phase 5 Charter acceptance scenarios against existing tests/evidence, then build the consolidated Slice 7 / Phase 5 master acceptance gate without reopening already-passed scenarios or making paid provider calls.
