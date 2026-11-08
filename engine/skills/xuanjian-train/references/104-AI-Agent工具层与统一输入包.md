# 104 · AI Agent 工具层与统一输入包（照单全学 · AI Agent 集成能力）

> 对应清单价值 ④「AI Agent 集成能力」与专家阶段「MCP/Skill 架构趋势」。
> 机制来源：`shizhilya/yuan`、`ChesterRa/mingpan`、`ShousenZHANG/chinese-fortune`、
> `ZHENYI-ORG/Mingli-AI` 的真实 SKILL.md / AGENTS.md / governance.json
> （源码研读报告 `.workbuddy/research/13-rest-source.md` §2/§4）。
> 本文件为**本馆自撰**，未复制外部代码。

## 一、可取证的最佳实践（五类）

| 类 | 取证 |
|---|---|
| 结构化输入 | `yuan/SKILL.md:29-43` 统一输入包 7 字段；`mingpan/schemas.ts:22-54` 字段级 Zod 校验（范围/枚举/默认值写进 schema）；`yuan/.../request_guard.py:39-66` 必填 6 项 + `ambiguities[]` + `recommended_actions[]` + 三态 |
| 契约化输出 | `yuan/SKILL.md:141-153` 8 段固定顺序 + 禁止栏目；`chenggu/output.schema.json` `required` 11 字段 + `additionalProperties:false` + `limitations[]`；`mingpan/schemas.ts:122-137` `textResult` 统一返回 + `isError` |
| 可追溯引证 | `chinese-fortune/classical_evidence.json` 每条含 `id/title/edition/chapter/locator/layer/url/checked_on/verification/quote/context/passage_id`，并声明「版本与出处核对 ≠ 现实预测验证」；`Mingli-AI/rule-dsl.schema.json` 规则必填 `source_refs[]` 与 `counter[]` |
| 幻觉抑制 | `Mingli-AI/governance.json` v2.5.5 43 条硬规则：「关系事实先于关系语义」「有作用不等于有做功」「规则命中数量不得直接决定第一主线」；`chinese-fortune/SKILL.md:28-38` 工具结论优先（答错主因是宿主在工具结果外自己补结论）；`mingpan/README.md:113-114` 节气与闰月归确定性计算 |
| 边界声明 | `yuan/README.md:82-91` 四条；`chinese-fortune/SKILL.md:112`「不据此诊断个人、预测死亡或下交易指令」；`ouranic.cn/terms` 第 3 条 |

**MCP 工具定义形式**（`mingpan/src/server.ts` / `baziTools.ts:57-103`）：
`server.registerTool(name, {title, description, inputSchema: ZodRawShape}, handler)`；
`inputSchema` 是「字段名 → schema」的 raw shape 而非 `z.object`；返回
`{content:[{type:'text',text}]}`，异常加 `isError:true`。
其 description 硬声明「**只输出确定性排盘量，五行强弱/格局/用神由 AI 依据盘面自行分析**」——
这正是本馆「事实归工具」的同源做法。

## 二、与「各安其位」的四点冲突裁决（不可含糊）

| yuan 做法 | 可借 | **必弃** |
|---|---|---|
| 总 skill 跑六法 | 统一输入包、按需读 references 不塞满上下文 | 一成员同跑六法；本馆十线各只做专长那条 |
| 结论先于核对 | 结论段直答 | 隐形内部核对；本馆须各线**先独立出完结论**再交叉核对 |
| 对主理人隐藏分歧 | — | **必弃**；分歧须对主理人/内部档全量保留，可借 `chinese-fortune`「分歧分别说明／保留分歧」与 `Mingli-AI`「哪里冲突就讲清楚」 |
| 统一渲染三段式 | 结果卡、版式契约、状态自报 | 让渲染层替成员改结论 |

> 独立性是合参有效的前提：**派单时不得让成员知道他人结论**。

## 三、本馆工具层（`agent_runtime.py`）

5 个 MCP-like 工具：`xuanjian.validate_input` / `dispatch` / `cross_check` /
`owner_of` / `boundary`。统一输入包含 `gender, birth_solar{y,m,d}, hour_index,
longitude?, hour_unknown, question, tech_requested[]`，返回
`runnable | partial | blocked` 三态 + `ambiguities[]` + `recommended_actions[]`。

三道机械闸门：

1. **输入闸门**：缺项先问；`hour_index` 越界（0–23 钟点）拦截；
   **不填出生地就不做真太阳时校正**，并给出提示，绝不猜。
2. **派单闸门**：每个任务包 `no_peer_results=True`、`isolation=independent`、
   不含 `tech_requested` 全表；只读参考技法只列 `rejected`，不阻断整单；
   越线派单直接拒绝。
3. **交叉核对闸门**：`cross_check()` 仅在**所有线都独立 submit 完结论后**放行；
   检测到 `peer_results_seen` 或 `no_peer_results=False` 立即 `BLOCKED`。
   放行后由主理人主持，`divergences_visible_to_host=True`，分歧全量保留、
   不加权互证、不隐藏。

**工具层只输出确定性事实**（排盘量、口径卡、闸门结论、归属、边界），
**绝不产断语**；五行强弱、格局、用神、断语一律由对应成员独立给出。

## 四、边界清单（写入每次调用）

不把术数说成科学定论／不虚构星曜宫位或排盘事实／不泄漏内部中间件与过程叙述／
**本人终点永不可断**／不诊断疾病、不预测死亡、不下交易指令。

## 五、用法

```bash
python3 agent_runtime.py tools
python3 agent_runtime.py call --tool xuanjian.owner_of --args '{"tech":"ziwei"}'
python3 agent_runtime.py --selftest      # 25/25
```

## 六、许可与风险

- `shizhilya/yuan` **无 LICENSE**（API `license:None` + 81 文件树无 LICENSE/COPYING），
  只借公开文档里描述的机制，不复制其 SKILL.md 或代码。
- `mingpan` Apache-2.0、`chinese-fortune` MIT、`MingLi-Bench` MIT；
  `totoro-sir/fortune` 账号与仓库均 404，清单里「Python/MIT/Plain-language answers」
  实为 `ShousenZHANG/chinese-fortune`。
- 本馆工具层不联网、不调外部模型、不落用户出生资料到第三方。

---
*2026-11-04 · v1.53.0「第十四轮 · 照单全学」新增。三段式合参见 `OB99`，训练守门见 `TR100`。*
