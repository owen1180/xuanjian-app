#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发出前 —— 把「两道闸」合成一道，只有真跑过的才算过。

为什么要有这件
--------------
`TR117` 把引证闸立起来之后，馆里有两道闸：`kb_gate`（红线／禁词／十八条约束）
与 `source_gate`（书目、可引档位、定位、行号）。规矩是「发出前两道都跑」。
问题在**没人保证「都跑了」**：人跑了一道，看见 PASS，就以为另一道也过了。

更坏的一种是本馆真栽过的：闸门缺席时 `all([])` 为真，脚本把「没跑」报成「通过」。
`evolve.两道闸()` 就是这么绿的。**所以本脚本的第一原则不是「跑闸」，
是把「跑没跑」单独记成一种状态，且它不算通过。**

三种状态，各有各的处置
----------------------
  已跑      跑完拿到了结论。放行／拦下都算有结论。
  未跑      闸门模块不在、缺必需输入，根本没执行。**不算通过**。
  炸了      执行了但抛异常，结论不可知。**不算通过**。
  没核到    跑了，但因为缺引证库／语料，该核的没核。**不算通过**。
            （这一条是 `source_gate` 的 `NO_QUOTE_INDEX` warning 的另一种说法：
              闸说「我没法核」，汇总处若只看 `ok: true` 就会把它当绿灯。）

退出码
------
  0  所有闸都「已跑」且放行
  1  至少一闸明确拦下（不得发出）
  2  没有拦下，但至少一闸未跑／炸了／没核到（**同样不得当成通过**）

用法
----
  python3 preflight.py --稿 草稿.md --问 "用户原问题"
  python3 preflight.py --稿 - --问 "..." < 草稿.md      # 从 stdin 读
  python3 preflight.py --稿 草稿.md --问 "..." --json
  python3 preflight.py --稿 草稿.md --问 "..." --回执 回执.json
  python3 preflight.py --selftest

回执
----
给了 `--回执` 就落一份 JSON：时间、稿件指纹（sha1 前 8）、稿面字数、
每闸状态与说明、最终退出码。**这张纸是给交账用的**——事后能回答
「当时发出去的那一版，究竟过了哪两闸」，而不是凭记忆。
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

此处 = os.path.dirname(os.path.abspath(__file__))
技能们 = os.path.dirname(os.path.dirname(此处))
包根 = os.path.dirname(技能们)

已跑, 未跑, 炸了, 没核到 = "已跑", "未跑", "炸了", "没核到"


def 载(技能, 模):
    """按技能目录找模块；找不到返回 None（**不抛**，由调用方记「未跑」）。"""
    目录 = os.path.join(技能们, 技能, "scripts")
    if not os.path.isfile(os.path.join(目录, 模 + ".py")):
        return None
    if 目录 not in sys.path:
        sys.path.insert(0, 目录)
    return __import__(模)


def 找引证库(稿路=None):
    """引证库交给 `source_gate` 找——**一处定义，两处用**。

    早前这里自己写了一份「向上找／工作区同级找」，`source_gate` 里只有环境变量那一层。
    两份实现迟早会分叉：一处修了中文环境变量传不进来的问题，另一处没修，
    于是同一份稿在这道闸里能核、在那道闸里不能核。找库只有一个去处。
    """
    m = 载("xuanjian-openbook", "source_gate")
    if m is None:
        return None
    return m.找引证库(稿路)


def 指纹(文):
    return hashlib.sha1(文.encode("utf-8")).hexdigest()[:8]


# 「返工级 warning」：不构成硬拦（不改判语对错），但报告类稿件出现就必须改。
# 为什么单列一档：这三条都是「话说了等于没说」，混在 `warning 4` 里没人看得见——
# 加了判据、汇总处不显示，等于没加（本馆栽过的「错得安静」）。
返工码 = {"YEAR_VAGUE", "NOWHERE", "HEALTH_VAGUE"}


def 跑一闸(名, 件):
    """件() → (放行 bool, 说明 str)。件 为 None 表示闸门不在。"""
    if 件 is None:
        return {"闸": 名, "状态": 未跑, "放行": None,
                "说明": "闸门模块不在，本闸未执行", "码": []}
    try:
        三 = 件()
        放行, 说明 = 三[0], 三[1]
        码们 = list(三[2]) if len(三) > 2 else []
    except Exception as e:          # 闸门自己炸了，结论不可知——不记通过
        return {"闸": 名, "状态": 炸了, "放行": None,
                "说明": "%s: %s" % (type(e).__name__, e), "码": []}
    # 放行 None 不能用 bool() 压成 False：那是「没法核」，不是「拦下」，
    # 两者在回执里处置不同（拦下要改稿，没法核要补库）。
    return {"闸": 名, "状态": 已跑,
            "放行": None if 放行 is None else bool(放行), "说明": 说明, "码": 码们}


# ---------------------------------------------------------------- 两道闸

def 红线闸(问, 稿):
    """kb_gate：禁词、十八条约束、方药剂量。没给问句时召回不收窄，须在说明里讲明。"""
    m = 载("xuanjian-kb", "kb_gate")
    if m is None:
        return None

    def 件():
        r = m.gate(问, 稿)
        放行 = r["decision"] == "PASS"
        细 = "决策 %s；召回 %d 条" % (r["decision"], len(r.get("recalled_rules", [])))
        if r.get("violations"):
            细 += "；违规 %d 条：%s" % (
                len(r["violations"]),
                "／".join("%s[%s]" % (v[0], v[1]) for v in r["violations"][:3]))
        if not (问 or "").strip():
            细 += "（未给问句，仅按稿面判，召回规则未按问题收窄）"
        return 放行, 细

    return 件


def 引证闸(稿, 引证库=None, 稿路=None):
    """source_gate：书目在不在库、能不能逐字引、给了定位没有。

    **`NO_QUOTE_INDEX` 必须被翻译成「没核到」**：闸门允许在没库的环境里跑，
    只出一条 warning 说「引了书名却没法核」。若汇总处只看 error_count==0，
    这道闸在最该拦的地方会是绿的。
    """
    m = 载("xuanjian-openbook", "source_gate")
    if m is None:
        return None
    库 = 引证库 or 找引证库(稿路)

    def 件():
        facts = {"quote_index": 库} if 库 else None
        r = m.scan(稿, facts)
        项 = r.get("items", [])
        原码 = [x.get("code") for x in 项]
        细 = "error %d／warning %d" % (r.get("error_count", 0), r.get("warning_count", 0))
        错码 = sorted({x.get("code") for x in 项 if x.get("level") == "error" and x.get("code")})
        警码 = sorted({x.get("code") for x in 项 if x.get("level") == "warning" and x.get("code")})
        if 错码:
            细 += "：" + "／".join(错码)
        # warning 码也要露出来：只报「warning 4」等于让人自己去翻，
        # 而「须返工」的那几条恰恰都藏在 warning 里。
        if 警码:
            细 += "；warning：" + "／".join(警码)
        码们 = [("error", c) for c in 错码] + [("warning", c) for c in 警码]
        # 用 原码 判、不用 码们：码们 下面被改成了 (级别, 码) 元组，
        # 拿它比字符串永远 False——**改名后残留旧名**，本馆栽过的同族错。
        if "NO_QUOTE_INDEX" in 原码:
            # 闸门说「我没法核」，那就不能算核过了
            return None, "缺引证库索引（已自动找过档案根与包内路径），草稿里的书名一条都没核到。" + 细, 码们
        return bool(r.get("ok")), 细, 码们

    return 件


# ---------------------------------------------------------------- 汇总

def 跑全部(稿, 问="", 闸门们=None):
    闸门们 = 闸门们 if 闸门们 is not None else [
        ("kb_gate 红线闸", 红线闸(问, 稿)),
        ("source_gate 引证闸", 引证闸(稿)),
    ]
    果 = []
    for 名, 件 in 闸门们:
        r = 跑一闸(名, 件)
        if r["状态"] == 已跑 and r["放行"] is None:
            r["状态"] = 没核到          # 闸门自报「没法核」
        r["放行"] = None if r["状态"] in (未跑, 炸了, 没核到) else r["放行"]
        果.append(r)
    return 果


def 返工项(果):
    """列出「须返工」的判据码（去重保序）。"""
    出 = []
    for r in 果:
        for lv, c in r.get("码") or []:
            if lv == "warning" and c in 返工码 and c not in 出:
                出.append(c)
    return 出


def 判退出(果):
    """0 全过／1 硬拦／2 没跑成／3 放行但有须返工项。

    **3 是必须单独一档的**：硬拦（1）改判语，没跑成（2）补条件，
    须返工（3）改内容——三者处置不同。把 3 并进 0，等于「加了判据不生效」；
    并进 1，等于 warning 冒充 error，人会开始忽略这道闸。
    """
    if any(r["放行"] is False for r in 果):
        return 1
    # 一道闸都没跑（空表）也归这里：没有结论就不许说通过。
    # `all([])` 为真是本馆栽过的坑，这里用「至少一道」显式挡掉。
    if not 果 or any(r["状态"] != 已跑 for r in 果):
        return 2
    if 返工项(果):
        return 3
    return 0


def 报表(果, 指纹值, 字数):
    行 = []
    行.append("== 发出前 · 两道闸 ==")
    行.append("稿件指纹 %s　字数 %d" % (指纹值, 字数))
    行.append("")
    行.append("%-22s %-6s %-6s %s" % ("闸门", "状态", "结论", "说明"))
    for r in 果:
        结论 = "—" if r["放行"] is None else ("放行" if r["放行"] else "拦下")
        行.append("%-22s %-6s %-6s %s" % (r["闸"][:22], r["状态"], 结论, r["说明"]))
    码 = 判退出(果)
    行.append("")
    工 = 返工项(果)
    if 工:
        行.append("须返工 %d 项：%s" % (len(工), "／".join(工)))
    if 码 == 0:
        行.append("结论：两闸都跑过且都放行 → 可以发出。")
    elif 码 == 3:
        行.append("结论：两闸放行，但有 %d 项内容空话（%s）→ **不得直接发出**，"
                  "按提示改写后重跑（这类不改判语对错，改的是「说了等于没说」）。"
                  % (len(工), "／".join(工)))
    elif 码 == 1:
        行.append("结论：有闸拦下 → **不得发出**，改完重跑。")
    else:
        缺 = [r["闸"] for r in 果 if r["状态"] != 已跑]
        行.append("结论：%s 没有跑成（%s）→ **不得当成通过**，补齐条件重跑。"
                  % ("、".join(缺), "／".join(sorted({r["状态"] for r in 果 if r["状态"] != 已跑}))))
    return "\n".join(行), 码


def 落回执(路, 果, 指纹值, 字数, 稿路, 问, 码):
    据 = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "draft": 稿路,
        "sha1_8": 指纹值,
        "chars": 字数,
        "question": 问 or None,
        "gates": [{"gate": r["闸"], "state": r["状态"],
                   "verdict": "—" if r["放行"] is None else ("pass" if r["放行"] else "block"),
                   "detail": r["说明"]} for r in 果],
        "exit": 码,
    }
    目录 = os.path.dirname(os.path.abspath(路))
    if 目录:
        os.makedirs(目录, exist_ok=True)
    with open(路, "w", encoding="utf-8") as f:
        json.dump(据, f, ensure_ascii=False, indent=2)
    return os.path.abspath(路)


# ---------------------------------------------------------------- 自检

def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    稿 = "这步运官杀有力，事业有发力空间。"

    # ① 正路：两闸都造一个放行件，应退 0
    果 = 跑全部(稿, "我这步运如何", [("好闸", lambda: (True, "ok")),
                                     ("也好", lambda: (True, "ok"))])
    查("两闸放行·状态都是已跑", all(r["状态"] == 已跑 for r in 果))
    查("两闸放行·退出码 0", 判退出(果) == 0)

    # ② 任一拦下 → 1（另一闸放行也不能救）
    果 = 跑全部(稿, "", [("好闸", lambda: (True, "ok")),
                         ("坏闸", lambda: (False, "违规 2 条"))])
    查("一闸拦下·退出码 1", 判退出(果) == 1)
    查("一闸拦下·拦的那闸记拦下", [r["放行"] for r in 果 if r["闸"] == "坏闸"] == [False])

    # ③ 闸门不在 → 未跑 → 2，**这是本脚本存在的理由**
    果 = 跑全部(稿, "", [("缺席", None), ("好闸", lambda: (True, "ok"))])
    查("闸门缺席·状态未跑", 果[0]["状态"] == 未跑)
    查("闸门缺席·退出码 2 不是 0", 判退出(果) == 2)
    查("闸门缺席·全空表也退 2（防 all([]) 为真）", 判退出(跑全部(稿, "", [])) == 2)

    # ④ 闸门抛异常 → 炸了 → 2
    def 抛():
        raise RuntimeError("闸门内部错")
    果 = 跑全部(稿, "", [("会炸", 抛)])
    查("闸门抛异常·状态炸了", 果[0]["状态"] == 炸了)
    查("闸门抛异常·不记放行", 果[0]["放行"] is None)
    查("闸门抛异常·退出码 2", 判退出(果) == 2)
    查("闸门抛异常·说明含异常类型", "RuntimeError" in 果[0]["说明"])

    # ⑤ 闸门自报「没法核」（返回 None）→ 没核到 → 2
    果 = 跑全部(稿, "", [("没核到", lambda: (None, "缺引证库"))])
    查("自报没法核·状态没核到", 果[0]["状态"] == 没核到)
    查("自报没法核·退出码 2", 判退出(果) == 2)

    # ⑥ 真闸：红线闸能拦住「你必死」这类绝对化／寿元断语
    件 = 红线闸("我还能活多久", "你必死，活不过今年")
    查("红线闸·真模块可载入", 件 is not None)
    if 件:
        三 = 件()
        放行, 细 = 三[0], 三[1]
        查("红线闸·拦住寿元断语", 放行 is False)
        查("红线闸·说明里有决策词", "决策" in 细)

    # ⑦ 真闸：引证闸对凭空书名的稿子应拦；指一个不存在的库时应报「没核到」而非放行
    件 = 引证闸("《从没见过的书名》说「某事必应，绝无例外」。",
               引证库="/nonexistent/索引.json")
    查("引证闸·真模块可载入", 件 is not None)
    if 件:
        三 = 件()
        放行, 细 = 三[0], 三[1]
        查("引证闸·缺库时报没核到（None）", 放行 is None)
        查("引证闸·说明提到引证库", "引证库" in 细)

    # ⑦b 找到真库时，凭空书名须判 error 而不是放过
    真库 = 找引证库()
    查("引证闸·本机能找到引证库", 真库 is not None)
    if 真库:
        件2 = 引证闸("《从没见过的书名》说「某事必应，绝无例外」。", 引证库=真库)
        三2 = 件2()
        放行2, 细2 = 三2[0], 三2[1]
        查("引证闸·凭空书名被拦", 放行2 is False)
        查("引证闸·报 CITATION_UNKNOWN", "CITATION_UNKNOWN" in 细2)

    # ⑦c 返工档：放行但有 YEAR_VAGUE／NOWHERE 时退出码必须是 3，不许混进 0
    工稿 = "这一步守成，这几年宜稳，将来再说。\n看情况吧。"
    果工 = 跑全部(工稿, "问", [("假闸", lambda: (True, "warning 2；warning：YEAR_VAGUE／NOWHERE",
                                               [("warning", "YEAR_VAGUE"), ("warning", "NOWHERE")]))])
    查("返工档·列出两项", set(返工项(果工)) == {"YEAR_VAGUE", "NOWHERE"})
    查("返工档·退出码 3", 判退出(果工) == 3)
    净 = 跑全部("2028 年（主年），宜留，代价是收入不涨。", "问",
              [("假闸", lambda: (True, "ok", [("warning", "NO_FACTS")]))])
    查("返工档·非返工码仍是 0", 判退出(净) == 0)
    查("返工档·硬拦优先于 3",
       判退出([{"闸": "x", "状态": 已跑, "放行": False, "说明": "", "码": [("warning", "YEAR_VAGUE")]}]) == 1)

    # ⑧ 指纹：定义须钉死（回执要长期可对），改一字即变，长度 8
    import hashlib
    查("指纹·就是 sha1 前 8",
       指纹("甲乙丙") == hashlib.sha1("甲乙丙".encode("utf-8")).hexdigest()[:8])
    查("指纹·改字即变", 指纹("甲乙丙") != 指纹("甲乙丁"))
    查("指纹·长度 8", len(指纹("甲乙丙")) == 8)

    # ⑨ 回执：字段齐、能落盘
    import tempfile
    果 = 跑全部(稿, "问", [("好闸", lambda: (True, "ok"))])
    码 = 判退出(果)
    with tempfile.TemporaryDirectory() as td:
        路 = 落回执(os.path.join(td, "r.json"), 果, 指纹(稿), len(稿), "a.md", "问", 码)
        查("回执·文件已落", os.path.isfile(路))
        据 = json.load(open(路, encoding="utf-8"))
        查("回执·四要素齐", {"ts", "sha1_8", "gates", "exit"} <= set(据))
        查("回执·闸门逐条记状态", len(据["gates"]) == 1 and 据["gates"][0]["state"] == 已跑)
        查("回执·退出码与判定一致", 据["exit"] == 码)

    # ⑩ 报表：拦下时必须出现「不得发出」，未跑时必须出现「不得当成通过」
    文, 码1 = 报表(跑全部(稿, "", [("坏", lambda: (False, "x"))]), 指纹(稿), len(稿))
    查("报表·拦下写不得发出", "不得发出" in 文 and 码1 == 1)
    文, 码2 = 报表(跑全部(稿, "", [("缺", None)]), 指纹(稿), len(稿))
    查("报表·未跑写不得当成通过", "不得当成通过" in 文 and 码2 == 2)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


# ---------------------------------------------------------------- 入口

def main(argv=None):
    p = argparse.ArgumentParser(description="发出前：两闸合跑，跑过的才算过")
    p.add_argument("--稿", dest="draft", help="草稿文件路径，或 - 表示 stdin")
    p.add_argument("--问", dest="question", default="", help="用户原问题（红线闸据此收窄召回）")
    p.add_argument("--引证库", dest="quote_index", default=None, help="引证库索引.json（不给则自动找）")
    p.add_argument("--回执", dest="receipt", default=None, help="把回执 JSON 落在这个路径")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)

    if a.selftest:
        return 自检()
    if not a.draft:
        p.print_help()
        return 2

    稿 = sys.stdin.read() if a.draft == "-" else open(a.draft, encoding="utf-8").read()
    果 = 跑全部(稿, a.question, [
        ("kb_gate 红线闸", 红线闸(a.question, 稿)),
        ("source_gate 引证闸", 引证闸(稿, a.quote_index)),
    ])
    文, 码 = 报表(果, 指纹(稿), len(稿))

    if a.json:
        print(json.dumps({"gates": 果, "exit": 码, "sha1_8": 指纹(稿)},
                         ensure_ascii=False, indent=2))
    else:
        print(文)

    if a.receipt:
        路 = 落回执(a.receipt, 果, 指纹(稿), len(稿), a.draft, a.question, 码)
        print("\n回执：%s" % 路)
    return 码


if __name__ == "__main__":
    sys.exit(main())
