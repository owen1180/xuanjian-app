# -*- coding: utf-8 -*-
"""
玄鉴 · 运行时规则台账（归档端）
================================
解决闭环最后一处人工断点：**真实咨询用了哪些规则、闸门做了何种决策，不再靠人回忆。**

三个动作
--------
  记录  交付前跑一次：过闸门 + 记下"召回了哪些 / 实际引用了哪些"
  回填  用户给出实情后跑一次：把事实验证贴回规则 ID
  汇总  生成台账报告：引用率、失效触发、零召回规则、置信度升级建议

设计要点
--------
- 零依赖，只复用同馆的 kb_gate.gate（单一事实源，不另立一套词表）
- 闸门拦下即视为**不得交付**，本工具非零退出，把"拦截"变成硬约束
- 核心观测指标是 `召回了却没引用`——这正是"有知识没用"的可观测形态
- 台账只追加不改写，与 `xuanjian-archive/03` 的编号只增不改同规矩

用法
----
  python3 kb_ledger.py 记录 --档号 丁酉己酉丙午辛卯 --议题 事业 --问 "我这步运如何" \
      --稿 "这步运官杀有力，事业有发力空间" --用规则 K039,K043
  python3 kb_ledger.py 回填 --档号 丁酉己酉丙午辛卯 --规则 K039 --结果 已验证 --说明 "当年确有升职"
  python3 kb_ledger.py 汇总 --输出 kb_规则收录报告.md
"""

import argparse
import json
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
# 兼容两种落位：工作区（与 knowledge_gate.py 同级）／插件（../../xuanjian-kb/scripts/kb_gate.py）
gate = RULES = None
for _cand in (os.path.join(_HERE, "..", "..", "xuanjian-kb", "scripts"), _HERE):
    for _mod in ("kb_gate", "knowledge_gate"):
        _p = os.path.join(os.path.abspath(_cand), _mod + ".py")
        if os.path.isfile(_p):
            sys.path.insert(0, os.path.dirname(_p))
            _m = __import__(_mod)
            gate, RULES = _m.gate, _m.RULES
            break
    if gate:
        break

if not gate:  # pragma: no cover
    print("无法加载闸门引擎：需 kb_gate.py（插件）或 knowledge_gate.py（工作区）")
    sys.exit(2)

def _引证模块():
    """引证闸的判据只有一处定义（`source_gate`），台账不另写一套。

    这条是 C7：台账原来只记红线闸过没过，引证那一道完全不进账——
    报告上写「已过闸门」，翻台账却只见一道，事后根本查不出漏了哪道。
    这里**只记不判**：decision 仍由红线闸定，引证结果单列字段，
    真正的「两闸都过才算过」由 `preflight` 把关。
    """
    import os as _os
    import sys as _sys
    技 = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__)))), "xuanjian-openbook", "scripts")
    if 技 not in _sys.path:
        _sys.path.insert(0, 技)
    路 = _os.path.join(技, "source_gate.py")
    if not _os.path.isfile(路):
        return None
    try:
        import source_gate
        return source_gate
    except Exception:
        return None


ALL_RULE_IDS = [r["id"] for r in RULES]
DEFAULT_LEDGER = os.path.join(os.getcwd(), "命理档案", "方法论", "kb_运行时台账.jsonl")


def _resolve(path):
    return os.path.abspath(path or os.environ.get("XUANJIAN_LEDGER") or DEFAULT_LEDGER)


def _append(rec, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load(path):
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _split(s):
    if not s:
        return []
    return [x.strip() for x in s.replace("，", ",").split(",") if x.strip()]


def cmd_record(args):
    path = _resolve(args.台账)
    res = gate(args.问, args.稿)
    cited = _split(args.用规则)
    unknown = [c for c in cited if c not in ALL_RULE_IDS]
    recalled = res["recalled_rules"]
    not_cited = [r for r in recalled if r not in cited]
    not_recalled = [c for c in cited if c not in recalled]

    # 引证闸：同一份稿跑一遍，只记不判
    引 = None
    try:
        _sg = _引证模块()
        if _sg is not None:
            引 = _sg.scan(args.稿, None)
    except Exception as e:                 # 引证闸炸了也要留痕，不许静默当通过
        引 = {"ok": None, "error_count": None, "items": [],
              "炸": "%s: %s" % (type(e).__name__, e)}

    rec = {
        "kind": "测算",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "chart": args.档号,
        "topic": args.议题,
        "user": args.问,
        "draft_head": args.稿[:120],
        "recalled": recalled,
        "cited": cited,
        "recalled_not_cited": not_cited,
        "cited_not_recalled": not_recalled,
        "decision": res["decision"],
        "violations": ["%s:%s:%s" % v for v in res["violations"]],
        "unknown_rule_ids": unknown,
        # 引证闸结果（C7）：ok=None 表示没跑成／炸了，与「跑过且通过」必须分得开
        "cite_ok": (引 or {}).get("ok"),
        "cite_errors": (引 or {}).get("error_count"),
        "cite_codes": sorted({x.get("code") for x in (引 or {}).get("items", [])
                              if x.get("level") == "error" and x.get("code")}),
        "cite_note": (引 or {}).get("炸"),
    }
    _append(rec, path)

    print("档号：%s　议题：%s" % (args.档号, args.议题))
    print("召回：%s" % ("、".join(recalled) if recalled else "（无）"))
    print("引用：%s" % ("、".join(cited) if cited else "（无）"))
    if not_cited:
        print("召回未引用：%s　← 有知识没用的信号，需在报告里补上或说明为何不适用" % "、".join(not_cited))
    if not_recalled:
        print("引用未召回：%s　← 召回信号缺失，人想到了机器没想到，应补 recall 信号" % "、".join(not_recalled))
    if unknown:
        print("警告：以下编号不在规则库内，疑似笔误 → %s" % "、".join(unknown))

    if 引 is None:
        print("\n引证闸：未跑（找不到 source_gate），本行 cite_ok=null —— **不算通过**")
    elif 引.get("ok") is None:
        print("\n引证闸：炸了（%s），本行 cite_ok=null —— **不算通过**" % 引.get("炸"))
    else:
        print("\n引证闸：%s（error %d／warning %d）%s"
              % ("通过" if 引.get("ok") else "未过",
                 引.get("error_count", 0), 引.get("warning_count", 0),
                 "：" + "／".join(rec["cite_codes"]) if rec["cite_codes"] else ""))
        if 引.get("ok") is False:
            print("  ← 台账只记不判；发出前请跑 preflight，两闸都过才算过")

    if res["decision"] != "PASS":
        print("\n闸门：BLOCK —— 本稿不得交付")
        for v in res["violations"]:
            print("  - %s［%s］%s" % v)
        print("改完再跑一次本命令；台账已留痕，便于复盘这条为何越界。")
        return 1

    # 只说「红线闸过」是不够的：引证未过／未跑时若照写「可交付」，
    # 台账这一行就会变成事后「我过了闸」的证据，而其实只过了一道。
    引证过 = bool(引) and 引.get("ok") is True
    if 引证过:
        print("\n闸门：两闸都过　→ 可交付")
    else:
        print("\n闸门：PASS（仅红线闸）　→ **单闸通过，不等于可交付**；"
              "引证这一道未过或没跑，发出前跑 `preflight`")
    return 0


def cmd_backfill(args):
    path = _resolve(args.台账)
    rules = _split(args.规则)
    bad = [r for r in rules if r not in ALL_RULE_IDS]
    if bad:
        print("以下编号不在规则库内，拒绝回填：%s" % "、".join(bad))
        return 2
    rec = {
        "kind": "回填",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "chart": args.档号,
        "topic": args.议题,
        "rules": rules,
        "result": args.结果,
        "note": args.说明 or "",
    }
    _append(rec, path)
    print("已回填：%s ← %s（%s）" % ("、".join(rules) or "（无）", args.结果, args.说明 or "无说明"))
    return 0


def cmd_summarize(args):
    path = _resolve(args.台账)
    rows = _load(path)
    cases = [r for r in rows if r.get("kind") == "测算"]
    fills = [r for r in rows if r.get("kind") == "回填"]

    stat = {rid: {"recall": 0, "cited": 0, "blocked": 0, "miss": 0,
                  "gap": 0, "verified": 0, "wrong": 0}
            for rid in ALL_RULE_IDS}
    for c in cases:
        for rid in c.get("recalled", []):
            if rid in stat:
                stat[rid]["recall"] += 1
        for rid in c.get("cited", []):
            if rid in stat:
                stat[rid]["cited"] += 1
        for rid in c.get("recalled_not_cited", []):
            if rid in stat:
                stat[rid]["miss"] += 1
        # 旧台账没有该字段时现算，保证历史记录同样可统计
        _gap = c.get("cited_not_recalled")
        if _gap is None:
            _rc = set(c.get("recalled", []))
            _gap = [x for x in c.get("cited", []) if x not in _rc]
        for rid in _gap:
            if rid in stat:
                stat[rid]["gap"] += 1
        if c.get("decision") != "PASS":
            for vid in c.get("violations", []):
                rid = vid.split(":")[0]
                if rid in stat:
                    stat[rid]["blocked"] += 1
    for f in fills:
        for rid in f.get("rules", []):
            if rid in stat:
                if f.get("result") == "已验证":
                    stat[rid]["verified"] += 1
                elif f.get("result") == "已修正":
                    stat[rid]["wrong"] += 1

    touched = {k: v for k, v in stat.items() if any(v.values())}
    dead, zero, suggest = [], [], []
    for rid, s in stat.items():
        if s["recall"] >= 3 and s["cited"] == 0:
            dead.append(rid)
        if s["recall"] == 0 and s["verified"] == 0 and rid in [r["id"] for r in RULES if r.get("must")]:
            zero.append(rid)
        if s["verified"] >= 2 and s["wrong"] == 0:
            suggest.append((rid, s["verified"]))

    lines = []
    写了 = 0
    lines.append("# 运行时规则收录报告")
    lines.append("")
    lines.append("> 由 `kb_ledger.py 汇总` 生成，共 %d 条测算、%d 条回填。台账：`%s`" % (len(cases), len(fills), path))
    lines.append("")
    lines.append("## 一、逐条规则收录情况")
    lines.append("")
    lines.append("| 规则 | 召回 | 引用 | 召回未引用 | 引用未召回 | 拦截 | 事实已验证 | 判读 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for rid in ALL_RULE_IDS:
        s = stat[rid]
        if not any(s.values()):
            continue
        note = "正常" if s["cited"] else ("触发失效" if s["recall"] >= 3 else "待观察")
        if s["gap"]:
            note = "召回缺信号"
        lines.append("| %s | %d | %d | %d | %d | %d | %d | %s |"
                     % (rid, s["recall"], s["cited"], s["miss"], s["gap"], s["blocked"], s["verified"], note))
        写了 += 1
    if 写了 == 0:
        # 早前这里写的是 `if len(lines) == 7`——靠数行数判断「一条都没写」，
        # 表头一改行数就再也不等于 7，空表因此永远不出这一行，看着像渲染坏了。
        lines.append("| （暂无数据） | 0 | 0 | 0 | 0 | 0 | 0 | — |")
    # 引证闸统计（C7）：只统计记过该字段的行，老台账没有这字段就明说「未记录」，
    # 不许把它们当「通过」——那正是本轮在治的毛病。
    记过 = [c for c in cases if "cite_ok" in c]
    过 = [c for c in 记过 if c.get("cite_ok") is True]
    未过 = [c for c in 记过 if c.get("cite_ok") is False]
    没跑 = [c for c in 记过 if c.get("cite_ok") is None]
    lines.append("")
    lines.append("## 二、引证闸（与红线闸分开记）")
    lines.append("")
    if not 记过:
        lines.append("- 本台账**没有一条记过引证闸**（字段 `cite_ok` 缺失）。"
                     "这不等于引证都过了，只等于**没记**。重跑 `记录` 才会带上。")
    else:
        lines.append("- 记过引证闸：%d 条／共 %d 条测算。通过 **%d**、未过 **%d**、没跑成 **%d**。"
                     % (len(记过), len(cases), len(过), len(未过), len(没跑)))
        码 = {}
        for c in 未过:
            for k in c.get("cite_codes") or []:
                码[k] = 码.get(k, 0) + 1
        if 码:
            lines.append("- 未过的判据分布：" + "／".join(
                "%s×%d" % (k, v) for k, v in sorted(码.items(), key=lambda x: -x[1])))
        if 没跑:
            lines.append("- **没跑成的 %d 条不算通过**：查 `cite_note` 字段看是模块缺还是抛异常。"
                         % len(没跑))
        if len(记过) < len(cases):
            lines.append("- 另有 %d 条老记录没这个字段，未计入任何一档。"
                         % (len(cases) - len(记过)))

    lines.append("")
    lines.append("## 三、结论")
    lines.append("")
    lines.append("- 本期触达规则：**%d / %d 条**，引用率 **%.0f%%**"
                 % (len(touched), len(ALL_RULE_IDS),
                    100.0 * sum(1 for s in touched.values() if s["cited"]) / max(1, len(touched))))
    lines.append("- 触发失效（召回≥3 却零引用）：**%s**" % ("、".join(dead) if dead else "无"))
    gap_rules = sorted(rid for rid, s in stat.items() if s["gap"])
    lines.append("- 召回信号缺失（人工引用却未召回）：**%s**" % ("、".join(gap_rules) if gap_rules else "无"))
    lines.append("- 零召回强制规则：**%s**" % ("、".join(zero) if zero else "无"))
    if suggest:
        lines.append("- 可依事实回填升级：**%s**" % "、".join("%s（验证×%d）" % (r, n) for r, n in suggest))
    else:
        lines.append("- 可依事实回填升级：暂无（事实回填累计 ≥2 次且无订正才升）")
    lines.append("")
    lines.append("## 四、口径")
    lines.append("")
    lines.append("- **召回**＝闸门按输入与草稿判出该用的规则；**引用**＝报告正文实际标注/遵从的规则编号。")
    lines.append("- **召回未引用**是最该看的指标：知识在场却未落地，多数是触发信号过宽，或人写报告时漏了。")
    lines.append("- **引用未召回**是反方向的洞：人凭经验用对了规则，机器却没认出来——该补 `recall` 关键词，别让闸门漏看。")
    lines.append("- 置信度升级只认**用户回填的真实事实**（对齐 `xuanjian-archive/03`），内部自测不算。")
    text = "\n".join(lines) + "\n"

    if args.输出:
        out = os.path.abspath(args.输出)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("报告已写入：%s" % out)
    print(text)

    if dead:
        print("！存在触发失效规则：%s —— 要么收紧召回信号，要么在流程里真正用起来。" % "、".join(dead))
        return 1
    return 0


def selftest():
    """自检：台账三个动作各测一遍，重点是「写没写、写对了没、该拒的拒没拒」。

    台账这东西坏了不报错：记录照写、汇总照出，只是数字悄悄错。
    所以下面每条都核**盘上的字节**，不核返回值的意思。
    """
    import argparse
    import io
    import tempfile
    from contextlib import redirect_stdout

    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    def 捕获(fn, *a):
        b = io.StringIO()
        with redirect_stdout(b):
            r = fn(*a)
        return b.getvalue(), r

    with tempfile.TemporaryDirectory() as td:
        账 = os.path.join(td, "led.jsonl")

        # ① 记录一条放行的稿：退 0，盘上多一行，字段齐
        a = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="事业",
                               问="我这步运如何", 稿="这步运官杀有力，事业有发力空间",
                               用规则="K003")
        出1, 码 = 捕获(cmd_record, a)
        行 = _load(账)
        查("记录·放行退 0", 码 == 0)
        # 只过一道闸时不许写「可交付」——台账这一行会被当作「我过了闸」的证据
        查("记录·只过一道时不说可交付",
           "可交付" not in 出1 or "两闸都过" in 出1)
        查("记录·盘上一行", len(行) == 1)
        查("记录·kind 是测算", 行 and 行[0].get("kind") == "测算")
        查("记录·记下了召回", 行 and isinstance(行[0].get("recalled"), list))
        查("记录·记下了决策", 行 and 行[0].get("decision") == "PASS")

        # ② 记录一条越界的稿：退 1，且**仍然留痕**（先写后判，便于复盘）
        b = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="寿元",
                               问="我还能活多久", 稿="你必死", 用规则="")
        _, 码 = 捕获(cmd_record, b)
        行 = _load(账)
        查("记录·拦下退 1", 码 == 1)
        查("记录·拦下也留痕（两行）", len(行) == 2)
        查("记录·拦下那行决策非 PASS", 行[-1].get("decision") != "PASS")
        查("记录·拦下那行有违规", bool(行[-1].get("violations")))

        # ③ 引用不存在的规则编号：要报警，但不能当成已引用
        c = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="事业",
                               问="我这步运如何", 稿="这步运官杀有力，事业有发力空间",
                               用规则="K999")
        _, 码 = 捕获(cmd_record, c)
        行 = _load(账)
        查("记录·未知编号仍可记（留痕不拦）", 码 == 0 and len(行) == 3)
        查("记录·未知编号被点出来", 行[-1].get("unknown_rule_ids") == ["K999"])

        # ④ 回填：未知编号必须拒，且盘上不许多行
        前 = len(_load(账))
        d = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="事业",
                               规则="K999", 结果="已验证", 说明="")
        _, 码 = 捕获(cmd_backfill, d)
        查("回填·未知编号退 2", 码 == 2)
        查("回填·未知编号不落盘", len(_load(账)) == 前)

        e = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="事业",
                               规则="K003", 结果="已验证", 说明="当年确有升职")
        _, 码 = 捕获(cmd_backfill, e)
        行 = _load(账)
        查("回填·已知编号退 0", 码 == 0)
        查("回填·落了一行", len(行) == 前 + 1)
        查("回填·kind 是回填", 行[-1].get("kind") == "回填")

        # ④b 引证闸进账（C7）：字段要落、未过要记码、炸了要记 null
        row = _load(账)[0]
        查("引证·字段已落", "cite_ok" in row and "cite_codes" in row)
        查("引证·通过与否有明确取值", row["cite_ok"] in (True, False, None))

        f = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="引证",
                               问="这书怎么说", 稿="参《从没见过的书名》说「某事必应绝无例外」。",
                               用规则="")
        _, 码f = 捕获(cmd_record, f)
        行f = _load(账)[-1]
        查("引证·凭空书名记成未过", 行f.get("cite_ok") is False)
        查("引证·判据码被记下", "CITATION_UNKNOWN" in (行f.get("cite_codes") or []))

        # 引证闸炸了：必须记 null，不许当通过
        原引 = globals()["_引证模块"]

        class 坏闸:
            @staticmethod
            def scan(*a, **k):
                raise RuntimeError("引证模块内部错")
        globals()["_引证模块"] = lambda: 坏闸
        try:
            g = argparse.Namespace(台账=账, 档号="甲子乙丑丙寅丁卯", 议题="炸",
                                   问="问", 稿="随便一段稿子", 用规则="")
            _, 码g = 捕获(cmd_record, g)
            行g = _load(账)[-1]
            查("引证·炸了记 null", 行g.get("cite_ok") is None)
            查("引证·炸了留证据", "RuntimeError" in (行g.get("cite_note") or ""))
        finally:
            globals()["_引证模块"] = 原引

        # ⑤ 汇总：空台账不许炸，且要写明暂无数据
        空账 = os.path.join(td, "empty.jsonl")
        出, _ = 捕获(cmd_summarize, argparse.Namespace(台账=空账, 输出=None))
        查("汇总·空台账不炸", "运行时规则收录报告" in 出)
        查("汇总·空台账写暂无数据", "暂无数据" in 出)
        查("汇总·空台账也不谎称引证过了", "没有一条记过引证闸" in 出)

        # ⑥ 汇总：造一份「召回 3 次、零引用」的台账，必须判成触发失效并退 1
        假 = os.path.join(td, "fake.jsonl")
        for _ in range(3):
            _append({"kind": "测算", "chart": "甲", "topic": "事业", "user": "问",
                     "draft_head": "稿", "recalled": ["K003"], "cited": [],
                     "recalled_not_cited": ["K003"], "cited_not_recalled": [],
                     "decision": "PASS", "violations": [], "unknown_rule_ids": []}, 假)
        出, 码 = 捕获(cmd_summarize, argparse.Namespace(台账=假, 输出=None))
        查("汇总·触发失效退 1", 码 == 1)
        查("汇总·点出触发失效规则", "触发失效" in 出 and "K003" in 出)

        # ⑦ 旧记录没有 cited_not_recalled 字段：要现算出来，不能当没有
        旧 = os.path.join(td, "old.jsonl")
        _append({"kind": "测算", "chart": "甲", "topic": "事业", "user": "问",
                 "draft_head": "稿", "recalled": [], "cited": ["K010"],
                 "decision": "PASS", "violations": []}, 旧)
        出, _ = 捕获(cmd_summarize, argparse.Namespace(台账=旧, 输出=None))
        查("汇总·旧记录现算召回缺失", "召回信号缺失" in 出 and "K010" in 出)

        # ⑧ 汇总可落盘
        出路 = os.path.join(td, "报告.md")
        捕获(cmd_summarize, argparse.Namespace(台账=账, 输出=出路))
        查("汇总·报告已写盘", os.path.isfile(出路))
        查("汇总·报告非空", os.path.isfile(出路) and os.path.getsize(出路) > 200)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    ap = argparse.ArgumentParser(description="玄鉴运行时规则台账")
    ap.add_argument("--台账", default=None, help="台账路径，默认 ./命理档案/方法论/kb_运行时台账.jsonl")
    ap.add_argument("--selftest", action="store_true", help="自检（不写真实台账）")
    sub = ap.add_subparsers(dest="cmd", required=False)

    r = sub.add_parser("记录", help="交付前过闸门并留痕")
    r.add_argument("--档号", required=True)
    r.add_argument("--议题", default="综合")
    r.add_argument("--问", required=True)
    r.add_argument("--稿", required=True)
    r.add_argument("--用规则", default="")
    r.set_defaults(func=cmd_record)

    b = sub.add_parser("回填", help="用户给出实情后回填")
    b.add_argument("--档号", required=True)
    b.add_argument("--议题", default="综合")
    b.add_argument("--规则", required=True)
    b.add_argument("--结果", required=True, choices=["已验证", "已修正", "未验证"])
    b.add_argument("--说明", default="")
    b.set_defaults(func=cmd_backfill)

    s = sub.add_parser("汇总", help="生成收录报告")
    s.add_argument("--输出", default=None)
    s.set_defaults(func=cmd_summarize)

    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    sys.exit(args.func(args))


if __name__ == "__main__":
    sys.exit(main() or 0)
