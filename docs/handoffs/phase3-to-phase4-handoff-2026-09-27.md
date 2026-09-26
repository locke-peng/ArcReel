# ArcReel × MiniMax H3 — Phase 3 → Phase 4 新对话交接包

日期：2026-09-27

> 用途：当当前 ChatGPT 对话结束或上下文不足时，新对话必须先读取本文件，再继续 ArcReel 的 H3 自动修复闭环工作。不要依赖旧聊天记忆猜测项目状态。

---

## 1. 当前项目位置

Repository:

`locke-peng/ArcReel`

当前工作分支：

`phase3/h3-production-policy`

当前分支 HEAD：

`8c95873239c50abe0f4209678f8dcee038bcd191`

该 HEAD 是 Phase 3 正式验收文档提交：

`docs(h3): record Phase 3 regression acceptance`

注意：

- Phase 3 **真实受测代码 SHA** 是：
  `05cfb415a59f0972eb3c603807c4ff64dc79bbb5`
- 当前 HEAD `8c958732...` 只是在受测代码之后增加正式验收文档。
- 不要把“文档提交 HEAD”误写成“真实回归受测代码 SHA”。

历史 ArcReel 真机基线：

`3b3bc527197bad66ac0425094036ea86b0add7e8`

Phase 3 是在已经完成六个代表 Unit 修复/验收的后续代码线上继续推进，不应退回旧基线重新做一遍。

---

## 2. 六个代表 Unit 的最终状态

```text
E12U06  ✅ FINAL PASS
E4U02   ✅ FINAL PASS
E13U01  ✅ FINAL PASS
E13U03  ✅ FINAL PASS
E11U02  ✅ FINAL PASS
E15U03  ✅ FINAL PASS

6 / 6 CLOSED
```

这些 Unit 现在是**系统回归基线**，不是待继续人工调 Prompt 的实验案例。

---

## 3. Phase 3 已经完成什么

Phase 3 的目标是把前面六个代表 Unit 的人工经验转成 ArcReel 的系统级 Production Policy。

已新增：

- `lib/reference_video/h3_production_policy.py`
- `tests/unit/lib/reference_video/test_h3_production_policy.py`
- `tests/unit/test_e12u06_contract.py`
- `.github/workflows/h3-phase3-production-policy.yml`
- `docs/experiments/h3-phase3-production-policy.md`
- `docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md`

核心抽象：

```text
Media QA failure
    ↓
H3FailureClass
    ↓
plan_h3_media_repair()
    ├─ regenerate_shot
    ├─ deterministic_surface_repair
    ├─ deterministic_text_plate
    ├─ deterministic_av_retime
    ├─ audio_repair_remux
    ├─ recompile_dialogue_detached
    ├─ regenerate_with_identity_bridge
    └─ escalate
```

核心原则：

> Repair granularity must match failure granularity.

未知失败必须 fail-closed；Repair Planner 自己不能偷偷调用 Provider。

---

## 4. Phase 3 正式真实回归结果

正式验收 Run：

`36267589882`

真实受测代码：

`05cfb415a59f0972eb3c603807c4ff64dc79bbb5`

自动回归：

```text
Phase 3 Production Policy                  11 passed
6 个代表 Unit 联合合同回归                 41 passed
H3 Compiler + Preview/Runtime Lock         13 passed
Reference Video / H3 子系统               373 passed

TOTAL                                      438 passed
Python compile                             PASS
Ruff                                       PASS
```

正式结论：

`PHASE 3 REGRESSION GATE = PASS`

正式验收文档：

`docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md`

---

## 5. Phase 3 真实媒体重放证据

Run `36267589882` 同时执行了 deterministic media replay。

Artifact：

```text
ID
= 10914193204

Name
= phase3-deterministic-media-replay

Digest
= sha256:9fddcb6fd9c0ad9a3cee5a1352f47f548ad25a4f86e15c7115829329913cf056
```

这个 Artifact 的 workflow retention 是 14 天；如果新对话开始时 Artifact 已过期，应让用户重新上传之前下载的：

`phase3-deterministic-media-replay.zip`

不要因为 Artifact 过期就自动重新调用 MiniMax。

### E11U02 replay

```text
repair
= v3_deterministic_text_surface_scrub

provider_recalled
= false

duration
= 15.000000s

resolution
= 864×480

video
= H.264 / 24fps

audio
= AAC / 32kHz / stereo

replay final SHA256
= 4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18
```

视觉复核结论：

- 屏幕、胸牌、侧媒体只处理目标文字风险区域；
- 人物动作与中央物理状态模块保持；
- 没有全帧遮罩或无关场景替换；
- Phase 3 replay PASS。

### E15U03 replay

```text
repair
= v2_deterministic_5_5_5_av_retime

provider_recalled
= false

source cut frames
= 118 / 222

target frames
= 120 / 120 / 120

final authored cuts
= frame 120 / frame 240
= 5.000s / 10.000s

duration
= 15.000000s

resolution
= 864×480

video
= H.264 / 24fps

audio
= AAC / 32kHz / stereo

replay final SHA256
= 208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de
```

视觉复核结论：

- Shot 1 = TIANSHU NEXT 主舞台；
- Shot 2 = 观众/媒体；
- Shot 3 = C01 沈知意从 stage-wing 进入；
- frame 119→120 和 239→240 均正确切镜；
- 没有使用尾帧冻结冒充 5 秒；
- Video 与对应 Audio 一起 retime；
- Phase 3 replay PASS。

---

## 6. Phase 3 回归中真实遇到的问题

不要删除这些失败历史，因为它们本身是生产经验。

### 第一次 CI

Run：

`36249344504`

失败原因：

- workflow 只安装 pytest/ruff；
- ArcReel root `tests/conftest.py` 需要 SQLAlchemy；
- 测试主体尚未真正执行。

修复：

- 使用仓库标准 `uv sync` 环境。

### 六 Unit 第一次联合回归

Run：

`36267279237`

结果：

`40 passed / 1 failed`

唯一失败不是 Production Prompt 回退，而是新增 E12U06 test 把英文 Prompt 措辞写得过死：

- test 错误要求 `no readable language...`
- 实际已验收 Prompt 是 `never by readable language...`

修复原则：

> Contract test 应锁语义事实，不应无理由锁死自然语言表面措辞。

修复后 Run：

`36267369818`

PASS。

扩大 Reference Video/H3 子系统后：

Run：

`36267458777`

PASS。

加入真实媒体 replay 后：

Run：

`36267589882`

PASS。

---

## 7. 已经形成的关键生产规则

新对话不得重新推翻以下已经通过真实供应商/媒体验证的规则：

1. Canonical 是事实源，Prompt 只是编译产物。
2. Provider SUCCESS 不等于 Content PASS。
3. 最终验收对象是实际媒体，不是 Prompt、CI 绿灯或 Provider 状态。
4. exact text 优先 deterministic plate，不交给概率视频模型。
5. ZERO TEXT 必须由媒体 QA 证明，不能只由 Prompt 声明。
6. Dialogue Visual Leakage 应走 Dialogue-Detached。
7. Identity Continuity Failure 应使用 Identity Bridge/明确 Reference 重新生成。
8. 局部非 Canonical 文字/UI 污染优先 deterministic surface repair。
9. 修复粒度应等于失败粒度。
10. Timeline-only failure 应对 picture + matching audio 一起做 deterministic A/V retime。
11. Provider Request Resolution、Working Resolution、Final Authored Resolution 必须分别验证。
12. pytest / compile / Ruff / asset hash 必须尽量在付费 Provider Gate 之前。
13. 已经通过的大部分 Provider 输出应作为 SHA-pinned immutable evidence source 重用。
14. 未知失败必须 fail-closed，不能自动烧供应商额度。
15. 任何付费 Create 状态不明确时禁止盲目自动重试。

---

## 8. 下一阶段：Phase 4

下一步不要继续堆更多代表 Unit。

建议创建：

`phase4/h3-auto-repair-loop`

Phase 4 目标：

> 把已经通过实测的 Production Policy 从“独立策略模块”真正接入 ArcReel 的自动 Media QA → Repair → Re-QA 闭环。

目标正式流水线：

```text
Canonical
    ↓
Compile
    ↓
Preview / Runtime Lock
    ↓
Provider / Existing Media
    ↓
Media QA
    ↓
Structured Finding
    ↓
Failure Classifier
    ↓
Repair Planner
    ↓
Deterministic Repair / Provider Executor
    ↓
Media QA Again
    ↓
Evidence Hash Chain
    ↓
FINAL PASS
```

---

## 9. Phase 4 第一批应实现的模块

建议第一批落地：

```text
media_qa_schema.py
h3_failure_classifier.py
h3_repair_executor.py
cut_detector.py
evidence_schema.py
```

但在创建文件前必须先检查当前 ArcReel 目录结构和已有同类模块，避免重复实现。

### media_qa_schema

至少结构化：

```text
unit_id
shot_id
time_range
region
failure_class
canonical_violation
severity
evidence_frames
provider_result_usable
audio_is_accepted
repairability
```

### failure classifier

把 Media QA finding 转成现有：

`H3FailureClass`

不要复制第二套 Failure Enum。

### repair executor

必须严格消费：

`plan_h3_media_repair()`

不要在 Executor 内重新发明一套判断规则。

### cut detector

至少输出：

```text
actual_cut_frame
actual_cut_time
target_cut_frame
target_cut_time
delta_frames
delta_seconds
confidence / evidence
```

### evidence schema

至少锁：

```text
source media SHA
prompt SHA
reference SHA
provider task/run/artifact
repair action
provider_recalled
pre/post media SHA
actual cuts
media probe
evidence frames
QA verdict
```

---

## 10. Phase 4 第一轮端到端验证

优先用已有 evidence，不要重新付费生成。

第一对：

### E11U02

验证：

```text
Media QA Finding
→ LOCAL_NONCANONICAL_SURFACE
→ plan_h3_media_repair()
→ DETERMINISTIC_SURFACE_REPAIR
→ Executor
→ Re-QA
→ PASS
```

### E15U03

验证：

```text
Cut Detector
→ TIMELINE_ONLY_FAILURE
→ plan_h3_media_repair()
→ DETERMINISTIC_AV_RETIME
→ Executor
→ Re-QA
→ exact 5s + 5s + 5s
→ PASS
```

第一轮必须证明：

- `provider_recalled = false`
- 不需要 MiniMax API Key
- 实际 MP4 被重新生成/验证
- Evidence Hash Chain 完整
- 结果可重复。

---

## 11. Phase 4 后续六 Unit 自动分流矩阵

第一对通过后，再把六个代表 Unit 全部映射进自动策略：

```text
E12U06
→ broad semantic / invented-content / topology risk

E4U02
→ dialogue visualization / identity continuity

E13U01
→ exact canonical text / deterministic plate

E13U03
→ multi-shot / semantic-only screen / fail-closed

E11U02
→ local non-canonical surface repair

E15U03
→ actual cut detection / deterministic A/V retime
```

目标不是再次证明“六个视频好看”，而是证明：

> 系统会把不同失败自动送到正确 Repair Strategy。

---

## 12. Phase 4 的 FINAL PASS 标准

Phase 4 不能因为 unit tests 通过就 FINAL PASS。

至少需要：

1. Schema tests PASS
2. Classifier tests PASS
3. Repair Planner regression PASS
4. Executor tests PASS
5. Cut Detector tests PASS
6. 6 Unit joint regression PASS
7. Reference Video/H3 subsystem regression PASS
8. E11U02 actual-media end-to-end replay PASS
9. E15U03 actual-media end-to-end replay PASS
10. no unintended Provider call
11. evidence artifacts uploaded
12. dense visual review / targeted boundary review PASS
13. acceptance document records tested SHA, Run ID, Artifact ID, media hashes.

只有这些关闭后，才能写：

`PHASE 4 AUTO-REPAIR LOOP = FINAL PASS`

---

## 13. 新对话启动时的操作要求

新对话第一步：

1. 读取本交接文档；
2. 读取：
   `docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md`
3. 检查 GitHub 当前 branch/HEAD 是否仍与本文件一致；
4. 如果仓库已经变化，先做 delta 分析，不要直接覆盖；
5. 然后进入 Phase 4；
6. 不要重新做 Phase 3；
7. 不要重新付费调用 MiniMax，除非 Phase 4 的失败类型明确要求 Provider regeneration，并且所有 fail-closed Gate 已通过。

---

## 14. 新对话建议首句

请在新对话直接发送：

> 继续 ArcReel × MiniMax H3 项目。先从 GitHub 仓库 locke-peng/ArcReel 读取 docs/handoffs/phase3-to-phase4-handoff-2026-09-27.md 和 docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md，核对当前 branch/HEAD、Run、Artifact 和 6 个代表 Unit 状态。不要重做 Phase 3，不要重新调用付费 Provider。确认交接状态无漂移后，直接创建 Phase 4 分支并开始 H3 Auto-Repair Loop 第一批实现：Media QA Schema → Failure Classifier → Repair Executor → Cut Detector → Evidence Schema，然后用 E11U02 + E15U03 的既有 supplier evidence 做真实端到端回放验收。

