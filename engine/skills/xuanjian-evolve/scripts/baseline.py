#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基线流水线：把「一册一册手跑」做成一次铺开二十册以上。

为什么要有它
------------
`mastery.py` 一次只能测一册：出题、作答、判卷各一条命令，落到掌握度里也只有一册。
六十七册按这个速度铺不完，于是进度里长期只有「已测 1 册」——平均掌握度 0.62 这种数
没有统计意义，报出去反而误导。

三条纪律
--------
1. **卷子不带答案**。出卷导出两个文件：`paper.json` 只有题面，`key.json` 锁答案。
   作答时只给 `paper.json`；`判题` 要用 `a` 字段，判卷时再把两份合起来。
   把答案跟题面放一个文件，等于闭卷考试把答案印在卷头。
2. **盲测要标**。模型对四柱基础本来就有先验，"闭卷"只能保证「没看答案」，
   保证不了「没学过」。已读过、参与撰写过的册必须标 `blind=False`，
   报告里分档统计；混在一起算平均，就是把背书当成掌握。
3. **出不了题的册要登记**。方剂、风水、手相这类散文体册页挖不出空，
   硬出题只会出「『原因』指的是什么」这种废题。这类册不是「已掌握」，
   是**永久盲区**，必须单列，不能从分母里悄悄消失。

用法
----
    python3 baseline.py 覆盖                      # 全册出题能力盘点
    python3 baseline.py 出卷 --books 01,39,43 --per 8 --out 目录 [--nonblind 96,97,38]
    python3 baseline.py 判卷 --paper 卷.json --key 答案.json --answers 答.json [--落册]
    python3 baseline.py 基线                      # 已测覆盖与分档统计
"""

import json
import os
import sys

try:
    import mastery
except Exception:
    mastery = None

try:
    import study_state
except Exception:
    study_state = None

# 出题能力的三个档：≥6 题算可测，3–5 题勉强，≤2 题不测（出了也是废题）
可测线 = 6
勉强线 = 3


def 扫覆盖(册目录=None):
    """逐册试出题，返回 [{book, n, tier, why}]。不改任何文件。"""
    d = 册目录 or (mastery.册目录 if mastery else "")
    rows = []
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not n.endswith(".md"):
            continue
        try:
            名, 行们 = mastery.读册(n)
            题 = mastery.出题(名, 行们, 上限=40)
            k = len(题)
            档 = "可测" if k >= 可测线 else ("勉强" if k >= 勉强线 else "不测")
            why = ""
            if 档 == "不测":
                # 说清为什么出不了题，别只报个数
                表 = sum(1 for x in 行们 if x.strip().startswith("|"))
                长句 = sum(1 for x in 行们 if 18 <= len(x.strip()) <= 160)
                if 表 > len(行们) * 0.5:
                    why = "以表格为主（%d/%d 行），无可挖空的判据句" % (表, len(行们))
                elif 长句 < 5:
                    why = "散文／短句为主，句长多不在 18–160 区间"
                else:
                    why = "有长句但缺判据单位与术语，挖不出唯一定位"
            rows.append({"book": n, "n": k, "tier": 档, "why": why})
        except Exception as e:
            rows.append({"book": n, "n": -1, "tier": "错误", "why": str(e)[:60]})
    return rows


def 出卷(册们, 每册=8, 非盲=None):
    """按册出题，拆成 paper（无答案）与 key（锁答案）两份。

    返回 (paper, key)。paper 里**不含** a/source，防止作答时顺手看见答案。
    """
    非盲前缀 = [x for x in (非盲 or []) if x]

    def 见过(名):
        """按前缀判：调用方写「96」或「96-四柱」都算，不必写全名。"""
        return any(名.startswith(p) for p in 非盲前缀)

    paper, key = [], []
    for m in 册们:
        名, 行们 = mastery.读册(m)
        if not 名:
            continue
        题 = mastery.出题(名, 行们, 上限=每册)
        for k, t in enumerate(题, 1):
            qid = "%s#L%d#%d" % (名.split("-")[0], t["line"], k)
            paper.append({"qid": qid, "book": 名, "type": t["type"],
                          "q": t["q"], "weak": bool(t.get("weak")),
                          "blind": not 见过(名)})
            key.append({"qid": qid, "answer": t["a"], "line": t["line"],
                        "source": t["source"]})
    return ({"artifact": "基线卷面（不含答案；答案在 key.json，判卷时才合）",
             "count": len(paper), "items": paper},
            {"artifact": "基线答案（判卷用；作答阶段不得打开）",
             "count": len(key), "items": key})


def 判卷(paper, key, answers):
    """合成题面与答案后逐题判，再按册聚合。

    判题要吃 `a` 字段，所以这里必须把 key 合回题目里——
    但只在内存里合，不回写 paper 文件。
    """
    键 = {k["qid"]: k for k in key}
    结 = []
    for p in paper:
        k = 键.get(p["qid"], {})
        题 = dict(p, a=k.get("answer", ""), line=k.get("line", 0))
        r = mastery.判题(题, answers.get(p["qid"], ""))
        r["blind"] = p.get("blind", True)
        结.append(r)
    按册 = {}
    for r in 结:
        按册.setdefault(r["book"], []).append(r)
    汇总 = []
    for 册, 组 in sorted(按册.items()):
        # 弱题（答案来自表格首列，可能是栏目名）不算掌握度：答错不代表不会，
        # 答对也不代表会。并入平均只会让分数既虚高又虚低，单列才看得清。
        强 = [x for x in 组 if not x.get("weak")]
        弱 = [x for x in 组 if x.get("weak")]
        基 = 强 or 组
        分 = round(sum(x["score"] for x in 基) / len(基), 4) if 基 else 0.0
        汇总.append({"book": 册, "题数": len(基), "命中": sum(1 for x in 基 if x["hit"]),
                     "有据": sum(1 for x in 基 if x["grounded"]),
                     "越界": sum(1 for x in 组 if x["boundary_violation"]),
                     "掌握度": 分, "档": mastery.档位(分),
                     "弱题": len(弱),
                     "弱题命中": sum(1 for x in 弱 if x["hit"]),
                     "blind": all(x["blind"] for x in 组)})
    return 结, 汇总


def 落册(汇总, 写=True):
    """把聚合结果写进掌握度。非盲测的册照写，但 blind 标记一并存下。"""
    掌 = mastery.读掌握度()
    今 = mastery.datetime.date.today().isoformat()
    改 = 0
    for 册 in 汇总:
        分 = 册["掌握度"]
        旧 = 掌["books"].get(册["book"], {})
        掌["books"][册["book"]] = {
            "题数": 册["题数"], "命中": 册["命中"], "有据": 册["有据"],
            "越界": 册["越界"], "掌握度": 分, "档": 册["档"],
            "弱题": 册.get("弱题", 0), "弱题命中": 册.get("弱题命中", 0),
            "blind": 册["blind"],
            "上次复核": 今,
            "下次复习": mastery.复习日(分, 旧.get("上次复核")),
        }
        掌.setdefault("history", []).append(
            {"date": 今, "book": 册["book"], "score": 分, "blind": 册["blind"]})
        改 += 1
    if 写 and 改:
        mastery.存掌握度(掌)
    return 改


def 基线(掌=None):
    """已测覆盖、分档统计、盲测与非盲测分列。"""
    掌 = 掌 or mastery.读掌握度()
    b = 掌.get("books", {})
    盲 = {k: v for k, v in b.items() if v.get("blind") is not False}
    非盲 = {k: v for k, v in b.items() if v.get("blind") is False}

    def 均(x):
        return round(sum(v["掌握度"] for v in x.values()) / len(x), 4) if x else None

    档 = {"熟": 0, "半熟": 0, "生": 0}
    for v in b.values():
        档[v.get("档", "生")] = 档.get(v.get("档", "生"), 0) + 1
    return {"已测": len(b), "盲测册": len(盲), "非盲册": len(非盲),
            "平均": 均(b), "盲测均": 均(盲), "非盲均": 均(非盲),
            "档分布": 档,
            "最薄": sorted(b.items(), key=lambda kv: kv[1]["掌握度"])[:5]}


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    if not mastery:
        print("自检：mastery 不可用")
        return 1

    卷, 答案 = 出卷(["96-四柱", "01-四柱"], 每册=4, 非盲=["96-四柱"])
    查("出卷出到题", 卷["count"] >= 4)
    查("卷面不含答案字段", all("a" not in x for x in 卷["items"]))
    查("卷面不含原文", all("source" not in x for x in 卷["items"]))
    查("答案侧有原文", all("source" in k for k in 答案["items"]))
    查("卷与答案一一对应",
       {x["qid"] for x in 卷["items"]} == {k["qid"] for k in 答案["items"]})
    查("非盲册被标 false",
       any(x["blind"] is False for x in 卷["items"] if x["book"].startswith("96")))
    查("未声明册默认盲测",
       all(x["blind"] is True for x in 卷["items"] if x["book"].startswith("01")))

    # 全对：答案直接取 key，应判全中
    全对 = {k["qid"]: k["answer"] for k in 答案["items"]}
    结, 汇 = 判卷(卷["items"], 答案["items"], 全对)
    查("全对判满分", all(x["score"] >= 0.99 for x in 结))
    查("按册聚合册数对", len(汇) == 2)
    查("聚合带盲测标记", any(x["blind"] is False for x in 汇))

    # 全错：给空串
    结2, 汇2 = 判卷(卷["items"], 答案["items"], {})
    查("未作答判零", all(x["score"] == 0.0 for x in 结2))
    查("零分档为生", all(x["档"] == "生" for x in 汇2))

    # 弱题不进掌握度：把同一册的弱题全答错，掌握度不应被拉低
    卷w, 答w = 出卷(["04-手相"], 每册=40)
    弱 = [x for x in 卷w["items"] if x.get("weak")]
    强 = [x for x in 卷w["items"] if not x.get("weak")]
    if 弱 and 强:
        只强对 = {k["qid"]: k["answer"] for k in 答w["items"]
                  if not any(w["qid"] == k["qid"] for w in 弱)}
        for w in 弱:
            只强对[w["qid"]] = ""
        _, 汇w = 判卷(卷w["items"], 答w["items"], 只强对)
        查("弱题答错不拉低掌握度", 汇w[0]["掌握度"] >= 0.99)
        查("弱题单列可查", 汇w[0]["弱题"] == len(弱))
    查("弱题有标记字段", all("weak" in x for x in 卷["items"]))

    # 越界必须压零，哪怕答对
    一 = 卷["items"][0]
    正解 = next(k["answer"] for k in 答案["items"] if k["qid"] == 一["qid"])
    结3, _ = 判卷([一], 答案["items"], {一["qid"]: 正解 + "，命主活到八十岁"})
    查("越界压零", 结3[0]["boundary_violation"] and 结3[0]["score"] == 0.0)

    覆 = 扫覆盖()
    查("覆盖扫描读到全册", len(覆) >= 90)
    查("覆盖分档合法", all(x["tier"] in ("可测", "勉强", "不测", "错误") for x in 覆))
    查("不测的册给出原因", all(x["why"] for x in 覆 if x["tier"] == "不测"))

    # ── 落册：判完卷要能真写进掌握度，且 history 只追加 ──
    import shutil
    import tempfile
    if study_state is not None:
        旧状态根 = study_state.状态根
        td = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(td, "方法论"), exist_ok=True)
            study_state.状态根 = lambda *a, **k: td
            造 = [{"book": "99-测试册.md", "题数": 4, "命中": 3, "有据": 3,
                  "越界": 0, "掌握度": 0.75, "档": "熟", "blind": True,
                  "弱题": 0, "弱题命中": 0}]
            查("落册·写入一册", 落册(造) == 1)
            路 = os.path.join(td, "方法论", "掌握度.json")
            查("落册·掌握度文件已建", os.path.isfile(路))
            掌 = json.load(open(路, encoding="utf-8"))
            查("落册·该册已登记", "99-测试册.md" in 掌.get("books", {}))
            查("落册·分数落对", 掌["books"]["99-测试册.md"]["掌握度"] == 0.75)
            查("落册·history 有一条", len(掌.get("history", [])) == 1)
            落册(造)
            掌2 = json.load(open(路, encoding="utf-8"))
            查("落册·history 只追加不覆盖", len(掌2.get("history", [])) == 2)
        finally:
            study_state.状态根 = 旧状态根
            shutil.rmtree(td, ignore_errors=True)

    print("自检：通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    if 失败:
        for f in 失败:
            print("  ✗", f)
        return 1
    return 0


def main():
    参 = sys.argv[1:]
    if not 参:
        print(__doc__)
        return 0
    if 参[0] == "--selftest":
        return 自检()

    命 = 参[0]
    选 = {"--books": None, "--per": None, "--out": None, "--nonblind": None,
          "--paper": None, "--key": None, "--answers": None}
    i = 1
    while i < len(参):
        if 参[i] in 选 and i + 1 < len(参):
            选[参[i]] = 参[i + 1]
            i += 2
        else:
            i += 1

    if 命 == "覆盖":
        覆 = 扫覆盖()
        计 = {}
        for x in 覆:
            计[x["tier"]] = 计.get(x["tier"], 0) + 1
        print("== 全册出题能力盘点 ==")
        print("  合计 %d 册：" % len(覆) +
              "／".join("%s %d" % (k, 计.get(k, 0)) for k in ("可测", "勉强", "不测", "错误")))
        print()
        for 档 in ("不测", "勉强"):
            组 = [x for x in 覆 if x["tier"] == 档]
            if 组:
                print("  【%s】%d 册" % (档, len(组)))
                for x in 组:
                    print("    %-46s %s" % (x["book"][:44], x["why"] or "%d 题" % x["n"]))
                print()
        if 选["--out"]:
            路 = 选["--out"]
            父 = os.path.dirname(路)
            if 父:
                os.makedirs(父, exist_ok=True)
            open(路, "w", encoding="utf-8").write(
                json.dumps({"artifact": "全册出题能力盘点", "count": len(覆), "items": 覆},
                           ensure_ascii=False, indent=2))
            print("  写出 %s" % 路)
        return 0

    if 命 == "出卷":
        册们 = [s.strip() for s in (选["--books"] or "").split(",") if s.strip()]
        if not 册们:
            print("用法：python3 baseline.py 出卷 --books 01,39,43 --per 8 --out 目录")
            return 2
        非盲 = [s.strip() for s in (选["--nonblind"] or "").split(",") if s.strip()]
        卷, 答案 = 出卷(册们, int(选["--per"] or 8), 非盲)
        出 = 选["--out"]
        if 出:
            os.makedirs(出, exist_ok=True)
            open(os.path.join(出, "paper.json"), "w", encoding="utf-8").write(
                json.dumps(卷, ensure_ascii=False, indent=2))
            open(os.path.join(出, "key.json"), "w", encoding="utf-8").write(
                json.dumps(答案, ensure_ascii=False, indent=2))
        print("出卷 %d 道，覆盖 %d 册%s" % (
            卷["count"], len({x["book"] for x in 卷["items"]}),
            "，写出 paper.json／key.json" if 出 else ""))
        print("  盲测 %d 道／非盲 %d 道" % (
            sum(1 for x in 卷["items"] if x["blind"]),
            sum(1 for x in 卷["items"] if not x["blind"])))
        return 0

    if 命 == "判卷":
        for k in ("--paper", "--key", "--answers"):
            if not 选[k]:
                print("用法：python3 baseline.py 判卷 --paper 卷.json --key 答案.json --answers 答.json")
                return 2
        卷 = json.load(open(选["--paper"], encoding="utf-8"))["items"]
        答案 = json.load(open(选["--key"], encoding="utf-8"))["items"]
        答 = json.load(open(选["--answers"], encoding="utf-8"))
        结, 汇 = 判卷(卷, 答案, 答)
        未答 = sum(1 for x in 卷 if not 答.get(x["qid"]))
        print("== 基线判卷 ==")
        for r in 汇:
            print("  %-44s %d/%d  %.2f %s%s%s" % (
                r["book"][:42], r["命中"], r["题数"], r["掌握度"], r["档"],
                "（非盲）" if not r["blind"] else "",
                "  弱题 %d/%d 不计" % (r["弱题命中"], r["弱题"]) if r["弱题"] else ""))
        总 = round(sum(x["score"] for x in 结) / len(结), 4) if 结 else 0
        print("  合计 %d 题，未答 %d，平均 %.3f" % (len(结), 未答, 总))
        if 选["--out"]:
            open(选["--out"], "w", encoding="utf-8").write(json.dumps(
                {"artifact": "基线判卷结果", "summary": 汇, "items": 结},
                ensure_ascii=False, indent=2))
            print("  写出 %s" % 选["--out"])
        # 落册原来只有函数、没有命令：判完卷不会自己进掌握度，得另开 python 会话 import。
        # **流水线在最后一步断了**——「判过卷」和「掌握度里记着」成了两件事，
        # 中间靠人记得手动接；漏接一次，报表就永远是上一轮的数。
        if "--落册" in 参:
            n = 落册(汇)
            print("  已落册 %d 册（写进掌握度，history 追加）" % n)
        else:
            print("  提示：加 --落册 才会写进掌握度；不加只出报表。")
        return 0

    if 命 == "落册":
        if not 选["--paper"]:
            print("用法：python3 baseline.py 落册 --paper 卷.json --key 答案.json --answers 答.json")
            return 2
        卷 = json.load(open(选["--paper"], encoding="utf-8"))["items"]
        答案 = json.load(open(选["--key"], encoding="utf-8"))["items"]
        答 = json.load(open(选["--answers"], encoding="utf-8"))
        _, 汇 = 判卷(卷, 答案, 答)
        n = 落册(汇)
        print("已落掌握度 %d 册" % n)
        return 0

    if 命 == "基线":
        b = 基线()
        print("== 掌握度基线 ==")
        print("  已测 %d 册：盲测 %d／非盲 %d" % (b["已测"], b["盲测册"], b["非盲册"]))
        print("  平均 %s（盲测 %s／非盲 %s）" % (b["平均"], b["盲测均"], b["非盲均"]))
        print("  档分布：" + "／".join("%s %d" % (k, v) for k, v in b["档分布"].items()))
        if b["最薄"]:
            print("  最薄五册：")
            for k, v in b["最薄"]:
                print("    %-46s %.2f %s" % (k[:44], v["掌握度"], v.get("档")))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
