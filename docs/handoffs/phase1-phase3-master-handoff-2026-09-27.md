# ArcReel × MiniMax H3 — Phase 1–3 总交接索引

日期：2026-09-27

> 本文用于把此前并未统一命名为 Phase 1 / Phase 2 的历史工作，按照已经真实完成且有仓库/CI/供应商证据的边界重新归档。它不是重新定义项目事实，而是为后续新对话建立稳定阶段索引。

---

# 0. 总览

当前 ArcReel × MiniMax H3 演进应理解为：

```text
Phase 1
H3 Native Integration Foundation
        ↓
Phase 2
Representative Supplier Validation
        ↓
Phase 3
Production Policy + Regression Generalization
        ↓
Phase 4
Auto-Repair Loop Integration
```

当前状态：

```text
Phase 1  ✅ CLOSED
Phase 2  ✅ CLOSED
Phase 3  ✅ CLOSED
Phase 4  ⏭ NEXT
```

---

# 1. Phase 1 — H3 Native Integration Foundation

## 1.1 阶段目标

Phase 1 的核心不是“某个 Unit 生成成功”，而是让 ArcReel 从：

```text
中文导演描述
→ 直接塞给 H3
```

升级成：

```text
Canonical Story / Director IR
→ H3 Native Rewrite
→ Native Ref2VA / T2VA
→ Native Validator
→ Prompt Preview
→ Preview/Runtime SHA Lock
→ Provider Adapter
→ Media QA
```

也就是说，Phase 1 解决的是**基础执行架构是否成立**。

## 1.2 Phase 1 的主要完成项

已经落地并经过测试的能力包括：

- H3 Native Prompt Compiler；
- Ref2VA / T2VA 分流；
- Canonical Director 编译；
- reference_image_labels；
- prompt_compiler 选项；
- 一键预览最终 Provider Prompt；
- provider_prompt_sha256；
- Preview / Runtime byte-exact lock；
- Speaker ID 按 Unit 当前发声顺序分配；
- Dialogue 绑定具体 Shot；
- ShotWindowMechanicalSubtitleTiming；
- Reference Picture / Subject 语义分离；
- Reference 必须真正落到具体 Shot；
- Native Validator fail-closed；
- Provider route / model alias / endpoint / schema 分层；
- Ambiguous Submit 禁止自动重试；
- provider_duration_seconds 持久化实验；
- 480p横 Validation Resolution 路径；
- deterministic scan 在付费 Provider 之前执行。

## 1.3 Phase 1 基线

正式真机验证基线：

`3b3bc527197bad66ac0425094036ea86b0add7e8`

该基线在仓库文档中被明确描述为：

`H3 V6 + V6.1 preview/runtime lock`

相关文档：

`docs/experiments/h3-docpack-v1.md`

该文档记录：

- baseline = `3b3bc527...`
- provider_duration_seconds 实验；
- ffprobe 失败时 provider duration fallback；
- 保留 typed provenance / manifest / digest / selection / preview-runtime prompt lock；
- 不允许 STALE bypass；
- 不允许 content-digest bypass；
- 不接受 destructive script rewriting；
- 必须 CI + representative provider tests 后才能正式进入下一阶段。

## 1.4 Phase 1 关键结论

Phase 1 最重要的工程结论：

1. **Canonical 是事实源，Prompt 不是事实源。**
2. **H3 Prompt 是执行程序，不是描述性作文。**
3. **T2VA 与 Ref2VA 是两套执行语义。**
4. **Preview Prompt 必须与 Runtime Prompt byte-exact 一致。**
5. **Native Validator 不能代替 Canonical Validator。**
6. **错误输入必须 fail-closed，尤其是在付费 Provider 之前。**
7. **Provider SUCCESS 不能作为 Content PASS。**

## 1.5 Phase 1 关闭标准

Phase 1 可以视为 CLOSED，因为后续 Phase 2 的六个代表 Unit 已经实际通过这套基础设施完成真实供应商调用和媒体验收。

因此，不应在 Phase 4 重新设计另一套 H3 Compiler / Preview Lock。

---

# 2. Phase 2 — Representative Supplier Validation

## 2.1 阶段目标

Phase 2 的目标是：

> 用有代表性的真实 Canonical Unit 去验证 Phase 1 架构是否经得起 MiniMax H3 的真实供应商输出，并把失败回流成生产方法。

最终代表集：

```text
E12U06
E4U02
E13U01
E13U03
E11U02
E15U03
```

最终：

```text
6 / 6 FINAL PASS
```

Phase 2 不是简单的“六段视频测试”，而是覆盖六类生产风险。

---

## 2.2 E12U06 — Screen State / Spatial Topology / Invented Content

早期真实供应商测试：

`docs/experiments/E12U06-live-supplier-test-2026-09-24.md`

最初证明：

- ArcReel → AutoDL → MiniMax H3 provider execution PASS；
- `480p横` → 864×480；
- provider duration persistence PASS；
- Preview == Runtime PASS；
- 但内容出现：
  - pseudo-readable glyph；
  - 陌生男性；
  - 侧门空间关系偏差。

由此形成：

> 对生成模型，正向定义唯一允许状态，比无限追加 Negative Prompt 更稳定。

最终 E12U06 已关闭为 FINAL PASS，并成为 screen-state / topology / invented-content 的代表 Gate。

---

## 2.3 E4U02 — Dialogue Visualization + Cross-Age Identity

最终验收：

`docs/experiments/E4U02-v4-final-acceptance-2026-09-25.md`

关键问题：

- 手机 UI 唯一合法文字：
  `给念念打电话`
- Dialogue 被 H3 视觉化成字幕；
- C03/陆念跨年龄身份漂移。

最终架构：

```text
Picture 1 = approved phone UI
Picture 2 = C03 two-age identity bridge
Audio 1   = detached canonical dialogue
Visual Provider Prompt = ZERO dialogue transcript
```

供应商 Run：

`36037865914`

最终：

```text
C03 identity                PASS
sole legal visible text     PASS
dialogue non-visualization  PASS
```

由此形成：

- Dialogue-Detached；
- Identity Bridge；
- visual prompt 不承载 spoken transcript。

---

## 2.4 E13U01 — Exact Typography + Exact Editorial Timing

最终验收：

`docs/experiments/E13U01-v2-final-acceptance-2026-09-25.md`

v1 虽 Provider SUCCESS，但：

- screen beat 没有保持完整 5s；
- AI 自己增加 sponsor/logo-like text。

最终 v2 架构：

```text
Shot 1
deterministic exact screen plate

Shot 2
H3 entrance-only motion plate

Audio
detached canonical audio

Final
ArcReel deterministic composition
```

最终 Run：

`36098803663`

最终视频：

`8eabe44a9f9b8cbbfdc00a8bf5b2da107fa526489f3cfa9ea7342336a6a2ac12`

由此形成：

> Exact typography / exact editorial timing 如果软件能 100% 完成，就不要交给概率模型。

---

## 2.5 E13U03 — Multi-Shot / Semantic-Only Screen / Fail-Closed

最终验收：

`docs/experiments/E13U03-v1-final-acceptance-2026-09-25.md`

Canonical：

```text
5s school C03 reaction
5s C01 control console + dialogue
5s scrolling logs
```

Canonical 只说“日志滚动”，没有 literal log strings。

最终架构：

```text
Audio seed
+ Shot 1 H3 plate
+ Shot 2 H3 plate
+ Shot 3 semantic-only log plate
+ deterministic 5+5+5
```

Paid run：

`36128343054`

Final SHA256：

`63a1238ae14161e7549fc9927adc611a3ba3aa7b6879c9050bac9a7a2fdf7b58`

前三次静态/CI 失败全部在 Provider Create 前 stop。

由此形成：

- multi-scene Unit 优先拆 Shot plate；
- semantic-only screen 不得创造 literal text；
- pytest / compile / Ruff / asset hash 应位于 paid Provider Gate 前。

---

## 2.6 E11U02 — Local Non-Canonical Surface Repair

最终验收：

`docs/experiments/E11U02-v3-final-acceptance-2026-09-26.md`

v2 已经具备正确：

- motion；
- staging；
- dialogue audio；
- timeline。

但仍存在：

- 屏幕文字污染；
- badge typography/logo hallucination。

因此 v3 不重新调用 Provider：

```text
SHA-pinned paid provider plates
→ deterministic local surface defocus
→ exact soundtrack reuse
→ 5+5+5
```

正式 Phase 2 验收结论：

`E11U02 v3 = FINAL PASS`

由此形成：

> 修复粒度应等于失败粒度。

以及：

> 当只有局部非 Canonical surface 错误时，不要重新随机化已经正确的 95% 内容。

---

## 2.7 E15U03 — Actual Cut Detection + A/V Retime

最终验收：

`docs/experiments/E15U03-v2-final-acceptance-2026-09-26.md`

原供应商成片内容正确，但真实 cut：

```text
frame 118 = 4.9167s
frame 222 = 9.25s
```

不是 Canonical：

```text
5.000s
10.000s
```

最终不重新调用 Provider，而是：

```text
actual segment detection
→ video PTS retime
→ matching audio atempo
→ exact 120 / 120 / 120 frames
```

正式 Run：

`36201168299`

Final SHA256：

`607f3ac349f9fa9e5871fc45b825208ff6434fd4bb83fc4ad1fd19d24de3d23b`

由此形成：

> Timeline Repair 必须同时修改 picture + matching audio，不能只补视频尾帧。

---

# 3. Phase 2 最终关闭状态

```text
E12U06  ✅ FINAL PASS
E4U02   ✅ FINAL PASS
E13U01  ✅ FINAL PASS
E13U03  ✅ FINAL PASS
E11U02  ✅ FINAL PASS
E15U03  ✅ FINAL PASS

6 / 6 CLOSED
```

Phase 2 结束时，已经不再需要继续增加“代表 Unit”。

后续正确方向是把经验系统化。

---

# 4. Phase 3 — Production Policy + Regression Generalization

Phase 3 不再调具体 Unit，而是把 Phase 2 的经验编码成系统策略。

核心新增：

`lib/reference_video/h3_production_policy.py`

核心抽象：

```text
H3FailureClass
    ↓
plan_h3_media_repair()
    ↓
H3RepairAction
```

支持：

- regenerate_shot；
- deterministic_surface_repair；
- deterministic_text_plate；
- deterministic_av_retime；
- audio_repair_remux；
- recompile_dialogue_detached；
- regenerate_with_identity_bridge；
- escalate。

未知失败 fail-closed。

---

# 5. Phase 3 正式验收

真实受测代码：

`05cfb415a59f0972eb3c603807c4ff64dc79bbb5`

正式验收 Run：

`36267589882`

回归结果：

```text
Production Policy                 11 passed
6 Unit Joint Regression           41 passed
Compiler + Preview/Runtime        13 passed
Reference Video/H3 Subsystem     373 passed

TOTAL                            438 passed
py_compile                        PASS
Ruff                              PASS
```

真实媒体 replay：

Artifact：

`10914193204`

Digest：

`sha256:9fddcb6fd9c0ad9a3cee5a1352f47f548ad25a4f86e15c7115829329913cf056`

### E11U02 replay

```text
provider_recalled = false
15.000s
864×480
H.264 + AAC
SHA256 =
4b039b25b22c5662caa62cc2f631eaf55d9d267a2b139f952dd786fe4dc2cb18
```

### E15U03 replay

```text
provider_recalled = false
15.000s
864×480
H.264 + AAC
cuts = 5.000s / 10.000s
SHA256 =
208d56697ea7ea939d65bced9fdfab877a8b3e521bdb3dce10eff39a421ae2de
```

正式验收：

`PHASE 3 REGRESSION GATE = PASS`

文档：

`docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md`

---

# 6. 三阶段共同形成的生产原则

Phase 1–3 一起证明：

1. Canonical 是事实源。
2. Prompt 是编译产物。
3. Provider SUCCESS ≠ Content PASS。
4. Compiler PASS ≠ Video PASS。
5. Preview / Runtime 必须 byte-exact lock。
6. Dialogue 可以与 Visual Provider Prompt 分离。
7. Exact text 应优先 deterministic authoring。
8. Semantic-only state 不得被 Compiler 扩写成新 Canonical facts。
9. Multi-scene Unit 应允许 Shot-level generation。
10. Identity continuity 可通过 Identity Bridge 显式建模。
11. Local failure 应 local repair。
12. Timeline-only failure 应 deterministic A/V retime。
13. Actual cut 必须从媒体检测，不信 Prompt 时间戳。
14. 已付费且大部分正确的 provider bytes 应 SHA-pinned 重用。
15. 所有可本地发现的问题应尽量在 paid Provider Create 前 fail-closed。
16. 未知 Repair 类型不能自动消耗 Provider credits。
17. 最终媒体 QA 是最后事实来源。
18. 每次正式验收必须留下 prompt/reference/media/evidence hash chain。

---

# 7. Phase 4 的位置

Phase 4 不是重新做 Phase 1、2、3。

它要做的是：

> 把 Phase 3 已经通过回归的 Repair Policy 接进正式 ArcReel Media QA / Execution Pipeline。

建议分支：

`phase4/h3-auto-repair-loop`

正式链路：

```text
Canonical
→ Compile
→ Preview / Runtime Lock
→ Provider / Existing Media
→ Media QA
→ Structured Finding
→ Failure Classifier
→ plan_h3_media_repair()
→ Repair Executor
→ Re-QA
→ Evidence
→ FINAL PASS
```

第一批模块：

- Media QA Schema；
- Failure Classifier；
- Repair Executor；
- Cut Detector；
- Evidence Schema。

第一轮真实验收：

- E11U02 existing evidence → automatic deterministic surface repair；
- E15U03 existing evidence → automatic cut detect + A/V retime；
- Provider recall 必须为 false。

---

# 8. 新对话读取顺序

任何新的 ChatGPT 对话应按以下顺序读取：

1. 本文：
   `docs/handoffs/phase1-phase3-master-handoff-2026-09-27.md`
2. Phase 3 → Phase 4 详细交接：
   `docs/handoffs/phase3-to-phase4-handoff-2026-09-27.md`
3. Phase 3 正式验收：
   `docs/experiments/h3-phase3-regression-acceptance-2026-09-27.md`
4. 必要时再读取六个 Unit 的 final acceptance 文档。

不要把聊天记忆作为唯一事实源。

---

# 9. 新对话不可做的事情

除非发现真实仓库漂移或验收证据缺失，否则：

- 不重做 Phase 1；
- 不重做 Phase 2；
- 不重做 Phase 3；
- 不把 6 个代表 Unit 重新当成未完成案例；
- 不重新付费生成已有 evidence；
- 不创建第二套 H3FailureClass；
- 不创建第二套 Repair Planner；
- 不绕过 Preview / Runtime lock；
- 不降低 Validator 强度换 CI 绿灯；
- 不自动重试 ambiguous paid submit。

---

# 10. 当前正式阶段状态

```text
Phase 1 — H3 Native Integration Foundation
✅ CLOSED

Phase 2 — Representative Supplier Validation
✅ CLOSED

Phase 3 — Production Policy + Regression Generalization
✅ CLOSED

Phase 4 — Auto-Repair Loop Integration
⏭ NEXT
```

这份索引是后续阶段历史连续性的总入口。
