#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引文回查器：核验册页里"独占一行的引文"能否在语料库中找到原文。

用途
----
`65` 号册要求"引原话必须能回放"。但册页写多了，最容易出的两类错：
  一、**改顺**：原文有讹字或口误，写册页时顺手改成通顺的字（违反照录纪律）；
  二、**编造**：记不清原句，按意思重写一句，读起来像原话。
两类错都通不过本脚本——它只做一件事：把引文拿到语料里逐字找。

判据
----
- 只取**独占一行的引用块**（`> "……"` 或 `> **"……"**`），
  夹在叙述里的引号（强调、术语）不参与核验，避免误报。
- 匹配前把语料与引文都**去掉空白与换行**——逐行排版的电子本一句话常被
  换行截断，不去换行会大面积误判"未见"。
- 取引文中最长的一段连续汉字作检索键（≥10 字），避开标点差异。

「未见」要分四种，不能一律叫"待查"（v1.67.0 起）
------------------------------------------------
早前本脚本只有"命中／待查"两档，于是每次跑出来几十条待查，人看两遍就不看了。
问题在于**其中大部分本来就查不到**：那本书是扫描件、没 OCR，哪来的原文可对？
把它们和「书写得出来、语料里却没有」的真问题混在一张表上，等于让真问题淹没。

所以现在每条未见都先归因，归因读的是**引证库同一份档位**（`source_gate` 那套），
不再另立判据：

  真待查     书在库里、档位是「可逐字引」，但这句在给定语料里找不到 → **这才要看**
  本无原文   书在库里、档位是「仅指认／近空／散图／乱码」→ 没有原文可对，正常
  无电子本   白名单里的典籍（《滴天髓》《撼龙经》这类）→ 本馆没有电子本，正常
  书目存疑   引证库和白名单都没有这本书 → 先补进去，或者删掉这句
  课程引文   附近有课次／集数／转写行号（`第52课`、`L58`、`.docx.md`）→ 按课程语料核，
             不按书名；要核它得把课程转写目录一起喂进来
  无书名     引文附近三行内没有书名号，也没有课次／行号 → 说不清出自哪里

**还有一种「看不见的漏」，单独报**：`未纳入`。册页里大量原话是「」散在叙述中，
不属上面两种可核格式，本工具**根本没抽到它们**。实测全库 135 册：可核格式 98 条，
散在叙述的长引 2,548 条——只报前者的命中率，是把 4% 的覆盖说成 100% 的干净。
所以报表开头必写未纳入条数，且一条可核引文都没抽到时，结论写「没有可核对象」，
不写「无真待查」。

用法
----
    python3 verify_quotes.py <册页路径或目录> <语料目录> [更多语料目录…] [--全] [--引证库 索引.json]
    python3 verify_quotes.py --selftest

例（课程转写与网盘语料一起喂，才不会把「语料没给全」判成「句子有问题」）：
    python3 verify_quotes.py ../references .workbuddy/learning/raw .workbuddy/learning/raw-mydisk

退出码
------
  0  没有「真待查」（其余未见都归了因，属正常）
  3  有「真待查」，须逐条人工判断
  2  语料目录为空／参数不全／引证库打不开

注意
----
- **未见 ≠ 造假**。常见原因：① 语料是繁体、册页已转简体；② 引文来自别处
  语料（网盘、GitHub 语料包）不在本次给定的目录里；③ 原文 OCR 把字认错，
  册页按义理改正了（这种要**改回去并标注**，不是保留）。
- 因此本脚本给的是**待查清单**，不是判决书。逐条人工判断后再定性。
"""

import os
import re
import sys
import glob
import json

CJK = re.compile(r"[\u4e00-\u9fff]+")
QUOTE_LINE = re.compile(r'^\s*>\s*(?:(?:原文|原话|原句)[：:]\s*)?\**\s*"([^"]{8,})"')
# 行内引用：带"原文／原话／原句"引导语的引号句
# 引导语后面的引号三种都认：「」是册页里最常见的，早前只写 " 与 “ ，
# 于是 `原文：「……」` 这种一行都抽不出来——**判据漏了一种写法，等于那类引文没核过**。
INLINE_LEAD = re.compile(r'(原文|原话|原句)[：:]\s*["\u201c「]([^"\u201d」\n]{8,})["\u201d」]')
书名号 = re.compile(r"《([^》]{2,40})》")
# 用来量「有多少引文根本不进统计」——只统计算得出来的那 98 条、
# 然后报「无真待查」，是把小比例覆盖说成 100% 的通过。所以这一档要单独报。
#
# **这个正则改过两次，第一次是错的，值得记**：
#   第一版写 `"([^"]{12,})"`，允许跨行。册页里 ASCII 双引号大量用作**术语强调**
#   （`把"得令得地得势"凭感觉`、`"另一套"`），一句话里出现的双引号数是奇数时，
#   配对就落到两个不相干的引号上，**把标题、表格、整段正文一起吞进来**。
#   于是量出「未纳入 2,548 条」——这个数不是引文，是「引号之间的跨度」。
#   实测同一批册子按不跨行重算只有 901 条，其中绝大多数仍是强调不是原话。
#   现在只认「」与“”——册页里真用来标原话的两种；ASCII 双引号不再计入。
#   **一个统计口径错了，不报错，只会把结论说大 2.8 倍。**
长引 = re.compile(r"「([^」\n]{12,})」|“([^”\n]{12,})”")

此处 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(os.path.dirname(此处)))
引证模块目录 = os.path.join(包根, "skills", "xuanjian-openbook", "scripts")

# 归因档：读引证库的「可引」字段，取值与 `quote_index.py 判可引` 一致
真待查, 本无原文, 无电子本, 书目存疑, 课程引文, 无书名 = (
    "真待查", "本无原文", "无电子本", "书目存疑", "课程引文", "无书名")
# 课程语料不按书名核（`OB97`：按集数与分秒／转写行号核）。册页里这类引文常写成
# 「第 52 课」「L58」「raw/xxx.docx.md」，没有书名号——早前一律归「无书名」，
# 一次跑出 43 条，把真正的「说不出出处」全盖住了。
课程标记 = re.compile(r"第\s*\d+\s*课|天纪|人纪|地纪|曾仕强|\.docx\.md|\.pdf|L\d+")


def _引证():
    """拿 source_gate 的引证库读法——**判据只有一处定义**，这里不另写一套。"""
    if 引证模块目录 not in sys.path:
        sys.path.insert(0, 引证模块目录)
    try:
        import source_gate
        return source_gate
    except Exception:
        return None


def 汉字数(s):
    """数的是**汉字个数**，不是「连续汉字段数」。

    这里踩过一个哑巴坑：原来写 `len(CJK.findall(q)) >= 8`，`findall` 返回的是
    匹配段的列表，一句没标点的引文只算 1 段，于是 `1 >= 8` 为假，整句被静默丢掉。
    长得像「八个字」，意思却是「八段」——只有逗号多的长句碰巧够八段才漏过去，
    所以这脚本一直「能跑」、只是悄悄少收了大半引文。
    """
    return sum(len(x) for x in CJK.findall(s or ""))


def collect_books(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "*.md")))
    return [path]


def extract_quotes(md_path):
    """抽取两类引用：独占一行的引用块、带引导语的行内引用。返回 [(行号, 引文, 类型)]"""
    out = []
    with open(md_path, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh, 1):
            raw = line.rstrip("\n")
            m = QUOTE_LINE.match(raw)
            if m:
                q = m.group(1).strip().strip("*").strip()
                if 汉字数(q) >= 8:
                    out.append((i, q, "块"))
                continue
            for mm in INLINE_LEAD.finditer(raw):
                q = mm.group(2).strip()
                if 汉字数(q) >= 8:
                    out.append((i, q, "行内"))
    return out


def load_corpus(root):
    """读语料。**`.md` 也要读**：`harvest.py` 把采集来的 PDF／DOCX 统一定出成 `.md`，
    只认 `.txt` 的话，对着本馆自己采的那一千多份语料跑，永远得到「语料为空」——
    不是没语料，是没认出来。
    """
    buf = []
    文件们 = []
    for 后缀 in ("*.txt", "*.md"):
        文件们 += glob.glob(os.path.join(root, "**", 后缀), recursive=True)
    for p in sorted(set(文件们)):
        try:
            buf.append(open(p, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
    return re.sub(r"\s+", "", "\n".join(buf))


def 近书名(行们, 行号):
    """从引文所在行往上找三行内的《书名》。

    为什么往上找：册页的写法几乎都是「《滴天髓》云：」下一行才引用文。
    只看本行会漏掉绝大多数出处；找太远又会串到上一段的另一本书——
    三行是踩出来的经验值，宁缺勿错（找不到就归「无书名」，不硬指）。
    """
    for k in range(行号 - 1, max(-1, 行号 - 5), -1):
        if k < 0 or k >= len(行们):
            continue
        m = 书名号.search(行们[k])
        if m:
            return m.group(1).strip()
    return ""


def 近标记(行们, 行号):
    """引文附近有没有课程／文件标记（课次、集数、转写行号、文件名）。"""
    for k in range(行号 - 1, max(-1, 行号 - 5), -1):
        if 0 <= k < len(行们) and 课程标记.search(行们[k]):
            return 课程标记.search(行们[k]).group(0)
    return ""


def 册级标记(行们):
    """整册的语料来源标记，只看抬头八行。

    册页几乎都在第 3 行写「> 来源：四柱理学第五十二课……（… .docx.md）」。
    引文本身附近三行常只有正文，没有课次——靠抬头补，才能把「按课次引的」
    与「真说不出出处」分开。

    **只在抬头取课次，不取书名**：抬头里出现的书名常是「本册对比的那本书」，
    不是引文出处，拿来认领会把出处张冠李戴；课次是整册共用的，不存在认错。
    """
    for l in 行们[:8]:
        m = 课程标记.search(l)
        if m:
            return m.group(0)
    return ""


def 归因(书, 索, 白, sg, 标记=""):
    """给一条「未见」定性。返回 (类, 说明)。"""
    if not 书:
        if 标记:
            return 课程引文, ("按课程语料引的（附近见「%s」），不按书名核；"
                              "给定语料里没找到这句，须核那一课／那一行" % 标记)
        return 无书名, "引文附近三行内没有书名号，也没有课次／行号，说不清出自哪里"
    if sg is None:
        return 书目存疑, "无法加载引证判据（source_gate 不在），本条的档位判不了"
    卡们 = sg.找卡(书, 索) if 索 else []
    if 卡们:
        可引 = {c.get("可引") for c in 卡们}
        if "可逐字引" in 可引:
            return 真待查, "《%s》可逐字引，但这句在给定语料里没找到" % 书
        return 本无原文, "《%s》档位=%s，本就没有原文可对（未见属正常）" % (
            书, "／".join(sorted(x for x in 可引 if x)))
    if 白:
        条 = sg.查白名单(书, 白)
        if 条 is not None:
            类 = 条.get("类别", "典籍")
            if 类 in ("非书", "馆内文件"):
                return 本无原文, "《%s》是%s，不按书核" % (书, 类)
            return 无电子本, "《%s》是%s，本馆无电子本，无法逐字核（须给篇／卷）" % (书, 类)
    return 书目存疑, "《%s》不在引证库也不在白名单：先补进去，或删掉这句" % 书


def 核查(册页, 语料根, 引证库路=None, 白名单路=None):
    """跑一遍，返回结构化结果（不打印）。测试与主程序走同一条路。"""
    sg = _引证()
    索, 白 = {}, {}
    if sg:
        索 = sg.载引证库(引证库路) or {}
        白 = sg.载白名单(白名单路) or {}

    根们 = [语料根] if isinstance(语料根, str) else list(语料根)
    段们 = [load_corpus(r) for r in 根们 if os.path.isdir(r)]
    语料 = "".join(x for x in 段们 if x)
    if not 语料:
        return {"ok": False, "错": "语料目录为空或不存在：%s" % "、".join(根们),
                "total": 0, "hit": 0, "items": []}

    条们 = []
    for b in collect_books(册页):
        行们 = open(b, encoding="utf-8", errors="ignore").read().split("\n")
        册标 = 册级标记(行们)
        for ln, q, kind in extract_quotes(b):
            段 = CJK.findall(q)
            键 = max(段, key=len)[:16]
            命中 = 键 in 语料
            类, 说明 = (("命中", "") if 命中
                       else 归因(近书名(行们, ln), 索, 白, sg,
                                近标记(行们, ln) or 册标))
            条们.append({"册页": os.path.basename(b), "行": ln, "类": kind,
                         "引文": q, "键": 键, "命中": 命中,
                         "归因": 类, "说明": 说明})
    # 未纳入：长引但格式不可核（散在叙述里的「」引号）。**必须单独报出来**，
    # 否则「共 0 条引文，命中 0」读起来像「一句都没问题」，其实是「一句都没查」。
    未纳入 = {}
    for b in collect_books(册页):
        文 = open(b, encoding="utf-8", errors="ignore").read()
        已收 = {x["引文"] for x in 条们 if x["册页"] == os.path.basename(b)}
        漏 = []
        for m in 长引.finditer(文):
            q = next(g for g in m.groups() if g).strip()
            if 汉字数(q) >= 12 and q not in 已收:
                漏.append(q)
        if 漏:
            未纳入[os.path.basename(b)] = len(漏)

    真 = [x for x in 条们 if x["归因"] == 真待查]
    return {"ok": True, "语料字数": len(语料), "total": len(条们),
            "hit": sum(1 for x in 条们 if x["命中"]),
            "items": 条们, "真待查": len(真), "未纳入": 未纳入,
            "未纳入数": sum(未纳入.values()),
            "有引证库": bool(索), "有白名单": bool(白)}


def 报表(果, 详=False):
    行 = []
    if not 果.get("ok"):
        return "语料目录为空或不存在：%s" % 果.get("错", "")
    总, 中 = 果["total"], 果["hit"]
    行.append("本表只统计可核格式（`> \"原文\"` 块引、`原文：\"…\"` 引导语）："
              "共 %d 条引文，命中 %d，未见 %d（命中率 %d%%）"
              % (总, 中, 总 - 中, 中 * 100 // max(1, 总)))
    if 果.get("未纳入数"):
        行.append("！另有 %d 条长引（「」散在叙述里）不属可核格式，**未纳入统计**。"
                  "这不是「全过」，是「没查」——要核就把它们改成块引或加原文引导语。"
                  % 果["未纳入数"])
    if not 果["有引证库"]:
        行.append("！ 没读到引证库：档位判不了，所有未见都会归「书目存疑」。"
                  "用 --引证库 指定，或把档案根放到工作区。")
    分组 = {}
    for x in 果["items"]:
        if x["命中"]:
            continue
        分组.setdefault(x["归因"], []).append(x)
    序 = [真待查, 书目存疑, 无书名, 课程引文, 本无原文, 无电子本]
    for 类 in 序:
        们 = 分组.get(类, [])
        if not 们:
            continue
        行.append("")
        行.append("── %s（%d 条）──" % (类, len(们)))
        if 类 == 真待查:
            行.append("   这一档才是要看的东西：书可逐字引，句子却对不上。"
                      "改回原文、删掉这句，或说明取自别处语料。")
        for x in 们:
            行.append("  [%s] %s:%d　%s" % (x["类"], x["册页"], x["行"], x["键"]))
            if 详 or 类 in (真待查, 书目存疑, 无书名, 课程引文):
                行.append("      ← %s" % x["引文"][:60])
                if x["说明"]:
                    行.append("      %s" % x["说明"])
    if 分组.get(课程引文):
        行.append("   ↑ 这 %d 条按课程语料核（课次／转写行号），不按书名。"
                  "若本次没把课程转写目录（`.workbuddy/learning/raw`）一起给上，"
                  "它们必然全未见——不是句子有问题，是语料没喂全。"
                  % len(分组[课程引文]))
    行.append("")
    if 总 == 0:
        # 一条都没抽到，不能写「无真待查」——那是「没有可核对象」，不是「核过且干净」
        行.append("结论：本次一条可核引文都没抽到 → **不是通过，是没有可核对象**。"
                  "册页若确有原话，须写成 `> \"原文\"` 或 `原文：\"…\"` 才核得到。")
        return "\n".join(行)
    if 果["真待查"]:
        行.append("结论：真待查 %d 条 → 逐条人工判断后再定性，不得直接发出。"
                  % 果["真待查"])
    else:
        它 = [x for x in 果["items"] if not x["命中"]]
        行.append("结论：无真待查（其余 %d 条未见均已归因：本无原文／无电子本／"
                  "书目存疑／课程引文／无书名）。" % len(它))
    return "\n".join(行)


def selftest():
    """自检：四类归因各造一条，外加固有名/白名单/无书名三条边界。"""
    import tempfile
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    with tempfile.TemporaryDirectory() as td:
        语料 = os.path.join(td, "corpus")
        os.makedirs(语料)
        # 特意用 .md：harvest 采来的语料就是这个后缀，只认 .txt 的版本会「命中 0」
        open(os.path.join(语料, "a.md"), "w", encoding="utf-8").write(
            "这一句是语料里真实存在的原文用来做命中测试不能少字\n")

        json.dump({"cards": [
            {"书名": "甲书全名", "可引": "可逐字引"},
            {"书名": "乙书全名", "可引": "仅指认"},
        ]}, open(os.path.join(td, "索引.json"), "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"items": {"丙经": {"类别": "典籍", "原文可核": False}}},
                  open(os.path.join(td, "白.json"), "w", encoding="utf-8"), ensure_ascii=False)

        稿 = os.path.join(td, "册.md")
        open(稿, "w", encoding="utf-8").write(
            "# 测\n\n"
            "《甲书全名》云：\n"
            '> "甲书里的一句原文甲乙丙丁戊己庚辛"\n'          # 真待查
            "《乙书全名》云：\n"
            '> "乙书扫描件里的一句甲乙丙丁戊己庚辛"\n'        # 本无原文
            "《丙经》有言：\n"
            '> "丙经古籍里的一句甲乙丙丁戊己庚辛"\n'          # 无电子本
            "《没听说过的怪书》里：\n"
            '> "怪书里的一句甲乙丙丁戊己庚辛壬"\n'            # 书目存疑
            "\n\n\n\n"                                     # 隔开四行，书名不再算「附近」
            '> "孤零零一句没有出处甲乙丙丁戊"\n'              # 无书名
            "原文：「这一句是语料里真实存在的原文用来做命中测试不能少字」\n"  # 命中
        )

        果 = 核查(稿, 语料, os.path.join(td, "索引.json"), os.path.join(td, "白.json"))
        查("核查·跑得通", 果["ok"] is True)
        查("核查·读到引证库", 果["有引证库"] is True)
        查("核查·抽到六条引文", 果["total"] == 6)
        查("核查·命中一条", 果["hit"] == 1)

        # 按引文前三个字认条目——不按行号，行号一改测试就假红，测试该盯行为不盯排版
        按文 = {x["引文"][:3]: x["归因"] for x in 果["items"]}
        查("归因·可逐字引的书判真待查", 按文.get("甲书里") == 真待查)
        查("归因·仅指认的书判本无原文", 按文.get("乙书扫") == 本无原文)
        查("归因·白名单典籍判无电子本", 按文.get("丙经古") == 无电子本)
        查("归因·无名之书判书目存疑", 按文.get("怪书里") == 书目存疑)
        查("归因·没书名判无书名", 按文.get("孤零零") == 无书名)
        查("归因·命中那条标命中", 按文.get("这一句") == "命中")
        查("归因·真待查只数这一条", 果["真待查"] == 1)

        文 = 报表(果)
        查("报表·写清真待查条数", "真待查 1 条" in 文)
        查("报表·四类分节都在", all(k in 文 for k in (本无原文, 无电子本, 书目存疑, 无书名)))
        # 有真待查时，结论只点真待查；「本无原文」那几条不能算进待查数里
        查("报表·结论只数真待查", "真待查 1 条" in 文 and "真待查 5 条" not in 文)
        查("报表·本无原文不进待查段",
           "── 本无原文（1 条）──" in 文 and "── 真待查（1 条）──" in 文)

        # 未纳入口径（v1.68.0 勘误）：ASCII 双引号不算引号，且不许跨行
        混稿 = os.path.join(td, "混.md")
        open(混稿, "w", encoding="utf-8").write(
            '把"得令得地得势"凭感觉定强弱，这句是强调不是引文。\n'
            '另一处"也是强调"而已。\n'
            '「这一句才是真原话甲乙丙丁戊己庚」\n')
        混果 = 核查(混稿, 语料, os.path.join(td, "索引.json"), os.path.join(td, "白.json"))
        查("未纳入·只认「」与“”，ASCII 双引号不算", 混果["未纳入数"] == 1)

        # 「」跨行不许算成一条（跨行多半是配对错，不是引文）
        跨稿 = os.path.join(td, "跨.md")
        open(跨稿, "w", encoding="utf-8").write('「上一行开头\n下一行结尾甲乙丙丁戊」\n')
        跨果 = 核查(跨稿, 语料, os.path.join(td, "索引.json"), os.path.join(td, "白.json"))
        查("未纳入·不跨行", 跨果["未纳入数"] == 0)

        # 课程语料：附近没有书名号、但有课次／行号 → 不得算进「无书名」
        课稿 = os.path.join(td, "课.md")
        open(课稿, "w", encoding="utf-8").write(
            "（第52课 L58）\n> \"课上一句转写甲乙丙丁戊己庚辛\"\n")
        课果 = 核查(课稿, 语料, os.path.join(td, "索引.json"), os.path.join(td, "白.json"))
        查("归因·课次引文单列一类", 课果["items"][0]["归因"] == 课程引文)
        查("归因·课次引文不进无书名", 课果["items"][0]["归因"] != 无书名)

        # 负向：一条可核引文都抽不到时，结论不许说「无真待查」
        空稿 = os.path.join(td, "空.md")
        open(空稿, "w", encoding="utf-8").write("「这一句虽然长但散在叙述里所以核不到」\n")
        空果 = 核查(空稿, 语料, os.path.join(td, "索引.json"), os.path.join(td, "白.json"))
        空文 = 报表(空果)
        查("空覆盖·明说没有可核对象", "没有可核对象" in 空文)
        查("空覆盖·不说无真待查", "无真待查" not in 空文)
        查("空覆盖·报出未纳入条数", 空果["未纳入数"] == 1)

        # 负向：语料目录为空必须报错，不能「零条引文、零命中」当作通过
        空 = 核查(稿, os.path.join(td, "不存在"), None, None)
        查("核对·空语料报错", 空["ok"] is False)
        查("核对·空语料不给零通过", "语料目录" in 空.get("错", ""))

        # 负向：显式给了不存在的引证库，不许偷偷用别的库顶上
        sg = _引证()
        查("判据·能找到 source_gate", sg is not None)
        if sg:
            查("判据·坏库路径返回 None",
               sg.载引证库(os.path.join(td, "没有这个.json")) is None)

        # 书名往回找：本行没有、上一行有，也要认
        行们 = ["《丁书》云：", '> "一句甲乙丙丁戊己庚辛"', ""]
        查("近书名·往上一行找", 近书名(行们, 2) == "丁书")
        查("近书名·三行外不算", 近书名(["《戊书》云：", "x", "y", "z", "《己书》云：",
                                     '> "句甲乙丙丁戊己庚辛"'], 6) == "己书")

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    详 = "--全" in sys.argv or "--all" in sys.argv
    引 = None
    for i, a in enumerate(sys.argv):
        if a == "--引证库" and i + 1 < len(sys.argv):
            引 = sys.argv[i + 1]
            args = [x for x in args if x != 引]
        elif a.startswith("--引证库="):
            引 = a.split("=", 1)[1]

    if "--selftest" in sys.argv:
        return selftest()
    if len(args) < 2:
        print(__doc__)
        return 2
    果 = 核查(args[0], args[1:], 引)
    if not 果["ok"]:
        print(果["错"])
        return 2
    print(报表(果, 详))
    return 3 if 果["真待查"] else 0


if __name__ == "__main__":
    sys.exit(main())
