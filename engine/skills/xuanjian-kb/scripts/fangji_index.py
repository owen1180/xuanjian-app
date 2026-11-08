#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方剂抽取器：从语料里把「方名／出处／主治／组成／用法」抽成结构化条目。

为什么要这个
------------
`86` 号册留了 partial：271 万字的方剂语料只做了盘点与分级，没有索引。
没有索引，问"甘草泻心汤由什么组成"就得全文搜，且搜到的是一段散文，
不是一条可核对的结构。

本脚本只做**抽取**，不做判断：
  - 不判这个方对不对、能不能用（那是 `86` §4 六要素里"人"的部分）
  - 不补全、不纠错、不改写原字（`65` §3 保真门禁）
  - 抽不出的就留空，**不猜**

两种输入格式
------------
1. **编号式**（《经方秘方大全 260 方》）：
      1、治疗XX的方（出自《伤寒杂病论》--四逆散） 柴胡 6克 枳实 6克 ...
      注：……
2. **标题式**（秘方文本那 150 篇「治XX秘方」）：
      正文里散落"组成：……""用法：……"，需按关键词抓。

用法
----
    python3 fangji_index.py <文件或目录> [--格式 编号|标题|自动] [--输出 前缀]

    python3 fangji_index.py ../../data/x.md --格式 编号
    python3 fangji_index.py ../../data/秘方文本/ --格式 标题 --输出 秘方索引

输出
----
  <前缀>.jsonl  逐条结构化（机器用）
  <前缀>.md     人读的索引表（按方名排序，带出处与组成摘要）
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 中药与剂量

# 药名后面跟数量与单位。单位含克/钱/两/枚/片/个/只/条/斤/毫升
剂量 = re.compile(
    r"([\u4e00-\u9fa5]{1,6})\s*"
    r"([0-9一二三四五六七八九十百半]+(?:\.[0-9]+)?)\s*"
    r"(克|钱|两|枚|片|个|只|条|斤|毫升|调羹|小块|把|支|朵|瓣|粒|颗|束|寸)")

# 药名里不该出现的词（防止把"用法""每日""每次"当药名）
非药 = {"每日", "每次", "每服", "一日", "分服", "水煎服", "温服", "饭后", "空腹",
        "以上", "共", "研末", "为末", "冲服", "另煎", "先煎", "后下", "包煎"}

# 编号式：1、治疗××的方（出自《书》--方名） 组成...
条目_编号 = re.compile(
    r"(\d{1,3})\s*[、.．]\s*"           # 编号
    r"([^（(\n]{2,60})"                  # 主治描述
    r"(?:[（(]\s*出自\s*《([^》]+)》\s*-{1,2}\s*([^）)]+)[）)])?"  # 可选出处与方名
)

# 标题式：文件名本身常是"治XX秘方"，正文里找"组成/处方/用法"
标题式_段 = re.compile(r"(组成|处方|方药|药物|用法|服法|主治|功效)\s*[:：]")


def 抽药(doc: str):
    """从一段文字里抽药名与剂量，按出现顺序。"""
    out = []
    for m in 剂量.finditer(doc):
        name = m.group(1).strip()
        if name in 非药:
            continue
        # 药名去掉开头可能粘连的动词/虚词
        for junk in ("用", "取", "加", "入", "以"):
            if name.startswith(junk) and len(name) > 2:
                name = name[len(junk):]
        out.append({"药": name, "量": m.group(2), "单位": m.group(3)})
    return out


def 解析编号式(text: str, src: str):
    """解析《260 方》那一类编号体。"""
    items = []
    marks = list(条目_编号.finditer(text))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)

        # 主治捕获常把后面的药名一起吃掉（"[^（(\n]{2,60}" 太宽）。
        # 遇到第一个"药名＋剂量"就截断，前半是主治，后半并回组成。
        主治raw = m.group(2)
        first = 剂量.search(主治raw)
        if first:
            主治 = 主治raw[:first.start()].strip(" ·　")
            组成前缀 = 主治raw[first.start():]
        else:
            主治 = 主治raw.strip(" ·　")
            组成前缀 = ""
        block = 组成前缀 + text[start:end]
        # 主体与"注"分开
        注 = ""
        if "注" in block:
            idx = block.find("注")
            if idx > 0:
                注 = block[idx:].strip()
                block = block[:idx]
        items.append({
            "编号": m.group(1),
            "主治": 主治,
            "方名": (m.group(4) or "").strip(),
            "出处": (m.group(3) or "").strip(),
            "组成": 抽药(block),
            "用法注": 注[:200],
            "原文": block.strip()[:400],
            "来源": src,
            "格式": "编号",
        })
    return items


def 解析标题式(path: str):
    """解析「治××秘方」那一类散体。文件名当主治，正文抓组成与用法。"""
    text = open(path, encoding="utf-8", errors="ignore").read()
    base = os.path.basename(path)
    主 = re.sub(r"\.(doc|docx|txt|pdf)$", "", base)
    # 抓"组成/处方"到下一个关键词之间的段落
    组成段 = ""
    m = re.search(r"(?:组成|处方|方药|药物)\s*[:：]\s*(.{4,400}?)(?=(?:用法|服法|功效|主治|加减|注|$))",
                  text, re.S)
    if m:
        组成段 = m.group(1)
    用法段 = ""
    m2 = re.search(r"(?:用法|服法)\s*[:：]\s*(.{2,200}?)(?=(?:功效|主治|加减|注|$))", text, re.S)
    if m2:
        用法段 = m2.group(1)
    return [{
        "编号": "",
        "主治": 主.replace("治", "", 1)[:40],
        "方名": "",
        "出处": "",
        "组成": 抽药(组成段) if 组成段 else 抽药(text[:1500]),
        "用法注": 用法段.strip()[:200],
        "原文": (组成段 or text[:300]).strip()[:400],
        "来源": base,
        "格式": "标题",
    }]


def 组成摘要(组成):
    if not 组成:
        return "（未抽出）"
    return "、".join(f"{c['药']}{c['量']}{c['单位']}" for c in 组成[:14]) + ("…" if len(组成) > 14 else "")


def 去重(条目们):
    """同方名＋同组成摘要只留第一条。

    **只对「有方名」的条目去重**：编号式里方名常抽空，那些条目一律保留——
    同名不同书的方子本来就该并排，宁多勿少（抽错一条比漏一条好查）。
    """
    seen, 出 = set(), []
    for it in 条目们:
        key = (it["方名"], 组成摘要(it["组成"]))
        if it["方名"] and key in seen:
            continue
        seen.add(key)
        出.append(it)
    return 出


def selftest():
    """自检：抽药、编号式切分、去重、摘要四件。不核「方对不对」（那不是抽取器的事）。"""
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    # ① 基本抽药：药名＋数量＋单位
    药 = 抽药("柴胡 6克 枳实 6克 芍药 9克")
    查("抽药·三条", len(药) == 3)
    查("抽药·药名对", [c["药"] for c in 药] == ["柴胡", "枳实", "芍药"])
    查("抽药·剂量对", [c["量"] for c in 药] == ["6", "6", "9"])
    查("抽药·单位对", {c["单位"] for c in 药} == {"克"})

    # ② 非药词不该被当药名
    查("非药·每日被排除", 抽药("每日 3克") == [])
    查("非药·水煎服被排除", 抽药("水煎服 200毫升") == [])

    # ③ 动词前缀要剥掉（"用甘草 6克" → 甘草，不是 用甘草）
    查("前缀·用字被剥", [c["药"] for c in 抽药("用甘草 6克")] == ["甘草"])
    # 两字药名带前缀不剥（"入芍药" 剥成 芍药 才对；"白术" 不能被剥成 术）
    查("前缀·两字药名不误剥", [c["药"] for c in 抽药("白术 6克")] == ["白术"])

    # ④ 编号式：两条，出处与方名各归各位
    文 = ("1、治疗头痛的方（出自《伤寒杂病论》--四逆散） 柴胡 6克 枳实 6克\n"
          "2、治疗咳嗽的方（出自《金匮要略》--小青龙汤） 麻黄 9克 桂枝 6克\n")
    条 = 解析编号式(文, "测试.md")
    查("编号式·切出两条", len(条) == 2)
    查("编号式·编号对", [x["编号"] for x in 条] == ["1", "2"])
    查("编号式·方名对", [x["方名"] for x in 条] == ["四逆散", "小青龙汤"])
    查("编号式·出处对", [x["出处"] for x in 条] == ["伤寒杂病论", "金匮要略"])
    查("编号式·主治不含药名", all("柴胡" not in x["主治"] and "麻黄" not in x["主治"] for x in 条))
    查("编号式·组成各两条", [len(x["组成"]) for x in 条] == [2, 2])

    # ⑤ 抽不出就留空，不猜
    查("留空·无剂量则组成空", 解析编号式("1、治疗怪病的方 无剂量说明\n", "x")[0]["组成"] == [])
    查("留空·摘要写未抽出", 组成摘要([]) == "（未抽出）")

    # ⑥ 去重：同方名同组成只留一条；方名为空的一条都不去
    甲 = {"方名": "四逆散", "组成": [{"药": "柴胡", "量": "6", "单位": "克"}]}
    乙 = {"方名": "四逆散", "组成": [{"药": "柴胡", "量": "6", "单位": "克"}]}
    丙 = {"方名": "四逆散", "组成": [{"药": "柴胡", "量": "9", "单位": "克"}]}
    丁 = {"方名": "", "组成": []}
    戊 = {"方名": "", "组成": []}
    果 = 去重([甲, 乙, 丙, 丁, 戊])
    查("去重·同名同组成合一", len([x for x in 果 if x["方名"] == "四逆散"]) == 2)
    查("去重·方名空的都留", len([x for x in 果 if not x["方名"]]) == 2)

    # ⑦ 摘要截断与省略号
    多 = [{"药": "药%d" % i, "量": "1", "单位": "克"} for i in range(20)]
    查("摘要·超过十四味加省略号", 组成摘要(多).endswith("…"))
    查("摘要·十四味不加省略号", not 组成摘要(多[:14]).endswith("…"))

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="文件或目录")
    ap.add_argument("--格式", default="自动", choices=["自动", "编号", "标题"])
    ap.add_argument("--输出", default="方剂索引")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.path:
        ap.print_help()
        return 2

    files = []
    if os.path.isdir(a.path):
        for root, _, fs in os.walk(a.path):
            for f in fs:
                if f.lower().endswith((".txt", ".doc", ".docx", ".pdf", ".md")):
                    files.append(os.path.join(root, f))
    else:
        files = [a.path]

    items = []
    for f in sorted(files):
        text = open(f, encoding="utf-8", errors="ignore").read()
        方式 = a.格式
        if 方式 == "自动":
            方式 = "编号" if len(条目_编号.findall(text)) >= 3 else "标题"
        if 方式 == "编号":
            got = 解析编号式(text, os.path.basename(f))
            # 编号式若一条都没抽到，退回标题式
            items.extend(got if got else 解析标题式(f))
        else:
            items.extend(解析标题式(f))

    # 去重（同方名＋同组成摘要）
    uniq = 去重(items)

    有组成 = [i for i in uniq if i["组成"]]
    print(f"扫描 {len(files)} 个文件 → 抽出 {len(uniq)} 条，其中有组成 {len(有组成)} 条")
    if uniq:
        有出处 = sum(1 for i in uniq if i["出处"])
        有名 = sum(1 for i in uniq if i["方名"])
        print(f"　带方名 {有名}　带出处 {有出处}　有用法注 {sum(1 for i in uniq if i['用法注'])}")

    with open(a.输出 + ".jsonl", "w", encoding="utf-8") as fh:
        for it in uniq:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")

    rows = ["# 方剂索引（自动抽取，供核对，不作断语）", "",
            f"> 抽取器：`scripts/fangji_index.py`　共 {len(uniq)} 条，其中有组成 {len(有组成)} 条。",
            "> **本表只做定位与核对**：方名／出处／主治／组成／用法注。条目内容为原字摘录，未改写；",
            "> **抽不出的留空，不猜**。判方、给量、定禁忌，一律回到 `86` §4 六要素与 §7 三条。", "",
            "| 方名 | 出处 | 主治（原述） | 组成（摘要） | 用法注 |",
            "|---|---|---|---|---|"]
    for it in sorted(uniq, key=lambda x: (x["方名"] == "", x["出处"], x["方名"] or x["主治"])):
        rows.append("| {} | {} | {} | {} | {} |".format(
            it["方名"] or "—", it["出处"] or "—",
            it["主治"].replace("|", "／")[:28],
            组成摘要(it["组成"]).replace("|", "／"),
            (it["用法注"] or "—").replace("|", "／")[:26]))
    open(a.输出 + ".md", "w", encoding="utf-8").write("\n".join(rows) + "\n")
    print(f"已写 {a.输出}.jsonl 与 {a.输出}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
