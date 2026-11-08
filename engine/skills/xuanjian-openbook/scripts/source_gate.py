#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玄鉴命理馆 · 发出前机械闸门（本馆自撰，零依赖）

核对：引文出处 / 绝对化措辞 / 四化白名单 / 工具外数值 / 未判说成定格 /
      唯一最好 / 健康寿元红线 / 免责声明 / 口径卡版本 / 紫微六亲局限注 / 白话篇幅。

用法:
  python3 source_gate.py --draft draft.txt --facts facts.json [--引证库 索引.json]
  cat draft.txt | python3 source_gate.py --draft -
  python3 source_gate.py --selftest
  python3 source_gate.py --quotes      # 逐条回查「引文逐字可查清单」

facts.json 可选字段:
  {"mode": "light|full", "tool_numbers": ["81.0", "110.5"], "kauding_hash": "...",
   "quote_index": "/path/to/命理档案/引证库/索引.json"}

引证库（v1.65.0 起）：草稿里出现《书名》时，按引证库索引核对四件事——
书目存不存在、该版能不能引原文、引原文有没有给定位、同名多版本是否须指明。
索引三处找：--引证库 ／ facts.quote_index ／ 环境变量 命理档案 下的 引证库/索引.json。
退出码: 有 error -> 1；仅 warning 或全通过 -> 0。
**通过不等于语义正确**，分寸仍归主理人；本闸门只报告，不替你改结论。
"""
import argparse
import json
import os
import re
import sys

try:
    from kauding import SIHUA
except ImportError:  # 允许脱离同目录被导入时降级
    SIHUA = {
        "甲": ["廉贞", "破军", "武曲", "太阳"], "乙": ["天机", "天梁", "紫微", "太阴"],
        "丙": ["天同", "天机", "文昌", "廉贞"], "丁": ["太阴", "天同", "天机", "巨门"],
        "戊": ["贪狼", "太阴", "右弼", "天机"], "己": ["武曲", "贪狼", "天梁", "文曲"],
        "庚": ["太阳", "武曲", "太阴", "天同"], "辛": ["巨门", "太阳", "文曲", "文昌"],
        "壬": ["天梁", "紫微", "左辅", "武曲"], "癸": ["破军", "巨门", "太阴", "贪狼"],
    }

ABSOLUTE_RE = re.compile(
    r"必发|必离|必病|必死|必吉|必凶|注定|必然|绝对|哪一年一定|一定发生|百分之百|铁口直断"
)
QUOTE_CLAIM_RE = re.compile(r"倪师说|师父说|古书云|命书有言|古籍上说|经书云|古书载")
QUOTE_PROOF_RE = re.compile(r"《天纪》|BV[0-9A-Za-z]+|bilibili|\?t=|出处|第.{1,4}集|§|册\s*\d|\d{1,2}:\d{2}")
SIHUA_RE = re.compile(r"([\u4e00-\u9fff]{2})(化禄|化权|化科|化忌)")
NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*分")
UNIQUE_BEST_RE = re.compile(r"唯一最好|最吉|排名第一|第一名|最优选")
HEALTH_RE = re.compile(r"确诊为|活不过|享年|死于|寿命为|本人.{0,6}寿元|断生死")
# 健康提示的「具体度」闸（`OB100`）：本馆已不满足于「注意身体、建议体检」——
# 那种话说了等于没说，客户不会因为一句空话去查。要求写到病名级＋检查项。
# 只报 warning 不报 error：措辞分寸归主理人，但**空话必须被点出来**。
HEALTH_VAGUE_RE = re.compile(r"注意身体|多注意身体|注意健康|保重身体|身体要当心|"
                            r"留意健康|建议体检|注意休息|好好调养")
# 断年与去留（`61` §3.4／§3.5，v1.73.0）：用户定案「全部分析要求给年份、去留」。
# 这两条只抓「空话」，不抓「分寸」：
#   · YEAR_VAGUE —— 给了时间却不给年份，客户拿不到任何可执行的点；
#   · NOWHERE    —— 把去留推回给客户，等于什么都没说。
# 都是 warning：措辞与取舍仍归主理人，但空话必须被点出来。
YEAR_VAGUE_RE = re.compile(r"这几年|近年来|今后|将来|未来几年|过几年|某个时候|迟早|早晚会|"
                           r"往后几年|接下来几年")
YEAR_ANY_RE = re.compile(r"(?:19|20)\d{2}")          # 行内有任意四位公历年即放过
# 只收「纯推脱」四种；**不含「自己决定」**——「去留由当事人自己决定」是本馆合规收尾句，
# 把它算违规会把对的判成错的（误杀比漏判更难发现）。
NOWHERE_RE = re.compile(r"顺其自然|看情况|不好说|视情况而定|因人而异|到时候再说")
HEDGE_OK_RE = re.compile(r"宜留|宜走|宜转|宜守|宜缓|窗口|分水岭|建议|代价|自主决定|"
                         r"由当事人|由你自己")

HEALTH_SPECIFIC_RE = re.compile(r"需排查|排查|病名|筛查|"
                                r"查[^，。；\n]{0,12}(?:超声|CT|核磁|镜|常规|功能|五项|"
                                r"血糖|血压|心电|抗体|激素|B超)|"
                                r"(?:内科|外科|妇科|眼科|耳鼻喉|皮肤科|心内科|消化科|"
                                r"内分泌科|泌尿科|骨科|神经内科|精神心理科)")
UNJUDGED_RE = re.compile(r"未判|给不出|没判|不判")
AS_FINAL_RE = re.compile(r"定为|确认为|定格|就是|必是")
DISCLAIMER_RE = re.compile(r"供参考|不构成|决策权")
INFER_RE = re.compile(r"归纳|推断|推测")
INFER_TAG = "〔本馆归纳〕"
CARD_RE = re.compile(r"kauding_hash|口径卡|engine_version|card_version")
SIX_REL_RE = re.compile(r"父母|兄弟|子女")
SIX_NOTE_RE = re.compile(r"仅供参考|局限|比较差一点")

# ── 引证核对（v1.65.0 起）────────────────────────────────────────────
# 为什么加这一组：`OB97` 写着「引一句查一句，查不到就删掉」，但闸门原来只查
# 「声称有出处却没给链接」这种**形式**问题，从不查「这本书到底存不存在、能不能引」。
# 引证库建起来之后（358 种），这个核对才第一次可做。
QUOTED_RE = re.compile(r"[「『“\"]([^」』”\"]{6,})[」』”\"]")
LOCATOR_RE = re.compile(r"#L\d+|第\s*\d+\s*页|页\s*\d+|KB\d+|册\s*\d+")
# `#L行号` 单独抽出来：它比「第 88 页」强，可以去产物里回读那一行核内容。
LINENO_RE = re.compile(r"#L(\d+)")
最长键 = 8          # 取引文里最长的连续汉字作为检索键，避开标点与断行差异
引证档序 = {"可逐字引": 0, "仅指认": 1, "近空": 2, "散图": 3}
# 倪师三套课程语料不是「书」，按 `OB97` 用「集数 + 分秒」核，不按引证库核。
课程语料 = {"天纪", "人纪", "地纪", "天纪实录", "人纪实录"}


def sihua_legal(star, kind):
    """星+化X 是否在任何天干四化白名单的对应位置出现。"""
    idx = {"化禄": 0, "化权": 1, "化科": 2, "化忌": 3}[kind]
    return any(row[idx] == star for row in SIHUA.values())


def 找书名(text):
    """返回最外层书名：[(名字, 起, 止)]。**支持书名号嵌套**。

    为什么不用正则：库里有一批卡片的书名本身就带书名号——
    `倪海厦《神农本草》(神州医料库）`。用 `《([^》]{2,40})》` 只能截到
    `倪海厦《神农本草`，名字被切断，匹配和报错都指错地方。栈式扫描取最外层。
    """
    出, 栈 = [], []
    for i, ch in enumerate(text or ""):
        if ch == "《":
            栈.append(i)
        elif ch == "》" and 栈:
            s = 栈.pop()
            if not 栈:
                出.append((text[s + 1:i], s, i + 1))
    return 出


def 汉字片(s):
    """只取汉字。书名匹配用——标点、书名号、括注、版本后缀都不该影响「是不是同一本」。"""
    return "".join(re.findall(r"[\u4e00-\u9fff]", s or ""))


def 找引证库(起路=None):
    """自己把引证库索引找出来，找不到给 None。

    **为什么不靠环境变量**：本馆一直用中文变量名 `命理档案` 传档案根，
    但实测 `命理档案=/x python3 …` 在本机 shell 里根本传不进去
    （`os.environ.get('命理档案')` 取到 None）。中文变量名不是所有 shell、
    所有调用链都认。只认它＝静默失效，闸门于是报 `NO_QUOTE_INDEX`，
    汇总处再当绿灯放过去。**所以除了它，还要向上找、还要看工作区同级。**
    """
    候选 = []
    环 = os.environ.get("命理档案")
    if 环:
        候选.append(os.path.join(环, "引证库", "索引.json"))
    for 起 in (起路, os.getcwd()):
        if not 起:
            continue
        起 = (os.path.dirname(os.path.abspath(起)) if os.path.isfile(起)
              else os.path.abspath(起))
        while True:
            候选.append(os.path.join(起, "命理档案", "引证库", "索引.json"))
            父 = os.path.dirname(起)
            if 父 == 起:
                break
            起 = 父
    import glob
    候选.extend(sorted(glob.glob(os.path.expanduser(
        os.path.join("~", "WorkBuddy", "*", "命理档案", "引证库", "索引.json"))),
        key=lambda p: -os.path.getmtime(p)))
    for p in 候选:
        if p and os.path.isfile(p):
            return p
    return None


def 载引证库(路=None):
    """读引证库索引，返回 {汉字键: [卡片…]}；找不到给 None。

    三处找：显式 `--引证库`／facts 里的 `quote_index` → 环境变量 `命理档案` 下的
    `引证库/索引.json` → 当前工作区同名路径。
    **找不到不报 error**：闸门允许在没库的环境里跑（比如 CI），但要出一条 warning，
    说「引了书名却没法核」——静默跳过正是本馆栽过跟头的地方。
    """
    import os
    候选 = []
    if 路:
        if not os.path.exists(路):
            return None          # 显式给了库却不存在：不许换别的库顶上
        候选.append(路)
    环 = os.environ.get("命理档案")
    if 环:
        候选.append(os.path.join(环, "引证库", "索引.json"))
    候选.append(os.path.join(os.getcwd(), "命理档案", "引证库", "索引.json"))
    # 兜底：向上找／工作区同级找。中文环境变量传不进来时，前三条全落空，
    # 不补这一步就会「有库却报没库」，把可核的引文全判成没法核。
    自找 = 找引证库()
    if 自找:
        候选.append(自找)
    for p in 候选:
        if p and os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                # **显式指定的库坏了，不许偷偷换下一个**：换掉之后「人指的那个库」
                # 与「实际核的库」不是一回事，人以为核过了，其实核的是别处那份。
                if 路 and p == 路:
                    return None
                continue
            索 = {}
            for c in d.get("cards", []):
                键 = 汉字片(c.get("书名"))
                if len(键) < 3:
                    continue      # 纯数字名的散图不算书名键，否则 "" 会吞掉一切
                索.setdefault(键, []).append(c)
            return 索
    return None


def 载白名单(路=None):
    """读书目白名单：本馆无电子本、但册页里确实引用过的书名。

    **为什么需要它**：引证库只覆盖网盘里那五类语料。而册页引用最多的是
    《撼龙经》《青囊经》《协纪辨方书》《滴天髓》这类古籍，我们根本没有电子本。
    实测：册页里出现过的 204 个书名，有 176 个（86%）不在引证库里——
    只认引证库，等于把绝大多数正常引用判成「伪造书目」。
    """
    import os
    候选 = []
    if 路:
        候选.append(路)
    环 = os.environ.get("命理档案")
    if 环:
        候选.append(os.path.join(环, "引证库", "书目白名单.json"))
    候选.append(os.path.join(os.getcwd(), "命理档案", "引证库", "书目白名单.json"))
    for p in 候选:
        if p and os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            return d.get("items", {})
    return {}


def 查白名单(名, 白):
    """在白名单里找这个名字：全等优先，再找互相包含（≥3 汉字）。"""
    净 = (名 or "").strip()
    if 净 in 白:
        return 白[净]
    键 = 汉字片(净)
    if len(键) < 3:
        return None
    for k, v in 白.items():
        kb = 汉字片(k)
        if len(kb) >= 3 and (键 in kb or kb in 键):
            return v
    return None


def 取行(路, 号, 上下文=2):
    """读产物第 `号` 行及其上下几行。读不到给 None。

    为什么要带上下文：语料是按 80 字左右硬换行的，一句话常被拆成两三行，
    引文也可能跨行。只看单行会大面积误判「对不上」。
    """
    try:
        with open(路, encoding="utf-8", errors="replace") as f:
            行们 = f.readlines()
    except (OSError, ValueError):
        return None
    if 号 < 1 or 号 > len(行们):
        return None
    lo = max(0, 号 - 1 - 上下文)
    hi = min(len(行们), 号 + 上下文)
    return "".join(行们[lo:hi])


def 最长连续汉(文):
    """取最长的一段连续汉字。引文里带标点、书名号、括注都不影响比对。"""
    段们 = re.findall(r"[\u4e00-\u9fff]+", 文 or "")
    return max(段们, key=len) if 段们 else ""


def 校行号(卡, 引文, 号):
    """按 `#L号` 回读产物，核引文是否真在那一带。

    返回 (结论, 说明)：
      ("对")      原文在该行附近，正常
      ("不符")    该行附近找不到这段原文 —— **报错**，这是「引文与出处对不上」
      ("读不到")  产物不在盘上或行号越界 —— 只警告，因为可能是采集根搬了家
    """
    路 = (卡 or {}).get("产物绝对") or (卡 or {}).get("产物")
    if not 路 or not os.path.exists(str(路)):
        return "读不到", "产物不在盘上（%s）" % (卡 or {}).get("产物")
    窗 = 取行(str(路), 号)
    if 窗 is None:
        return "读不到", "第 %d 行超出产物范围" % 号
    键 = 最长连续汉(引文)
    if len(键) < 最长键:
        return "对", "引文太短（%d 字），不做逐字比对" % len(键)
    if 键 in 汉字片(窗):          # 键与窗口都只取汉字，标点断行差异一概不管
        return "对", ""
    return "不符", "第 %d 行附近找不到「%s…」" % (号, 键[:12])


def 找卡(名, 索):
    """按汉字键找：先全等，再互相包含（都要求 ≥3 字）。

    为什么允许包含：草稿里写《神农本草》，库里那张卡叫「倪海厦《神农本草》(神州医料库）」，
    全等永远对不上，而它确实是同一本书。

    **全等优先**：有全等键就只认它，不再往外扩。因为「双版丁」与「双版丁扫描本」
    在库里是两本书，草稿写前者就该按前者算，不该因为后者也叫这名而报歧义。
    """
    键 = 汉字片(名)
    if len(键) < 2:
        return []
    if 键 in 索:
        return 索[键]
    中 = []
    for k, 卡们 in 索.items():
        if len(k) >= 3 and (键 in k or k in 键):
            中.extend(卡们)
    return 中


def 核对引证(text, 索, 白=None):
    """逐条查《书名》：在不在库、能不能引、引原文有没有给定位。

    四条判据（方向都是「不许编」）：
      ① 库里没有这本书 → error。凭记忆引一本不存在的书，是本馆最不能出的东西；
      ② 档位是「仅指认／近空／散图」却出现了引号内原文 → error。
         扫描件没 OCR 就没原文，那句话只能是人补的；
      ③ 可逐字引、也给了引号内原文，却没给 `#L行号`／页号／册号 → error，无法反查；
      ④ 同名多版本且档位不同 → warning，须写明是哪一版。

    再加一层**白名单**（v1.66.0）：本馆没有电子本、但册页里确实引用过的书
    （《撼龙经》《青囊经》《滴天髓》之类）。这类书永远进不了引证库，
    若只认引证库就会把它们全判成「伪造」。白名单分五类处置：
      - 非书／馆内文件 → 根本不按书判（`《乾为天》`是卦名、`《档案卡片》`是本馆文件）
      - 典籍／丛书／篇名 → 允许引用；因无电子本，引原文**不可反查**，
        只报 warning 要求给篇／卷，不报 error。报 error 会逼人删掉正经引用。

    **本函数第一版是坏的，值得记一笔**：改成 `for 名 in 书名们` 之后，
    循环里还在用上一版遗留的 `行` 变量，一跑就 NameError——
    而自检照样绿，因为旧自检的草稿只引了《天纪》（课程语料，在 `continue` 那里就跳过了），
    这一整段从未被执行过。**没跑到就等于没测**。现在每条判据都有独立用例。
    """
    items = []
    书名们 = 找书名(text)
    if not 书名们:
        return items
    if 白 is None:
        白 = {}
    if 索 is None:
        items.append({"level": "warning", "code": "NO_QUOTE_INDEX",
                      "message": "草稿引了书名，但没有引证库索引，无法核对书目能否引用；"
                                 "用 --引证库 指定，或设环境变量 命理档案", "line": 0})
        return items
    for 原名, 起, 止 in 书名们:
        名 = (原名 or "").strip()
        if 汉字片(名) in 课程语料:
            continue              # 课程语料按集数与分秒核，不按书核
        行首 = text.rfind("\n", 0, 起) + 1
        行尾 = text.find("\n", 止)
        行 = text[行首: 行尾 if 行尾 >= 0 else len(text)]
        号 = text.count("\n", 0, 起) + 1
        显示 = 名.replace("《", "").replace("》", "")   # 显示用：去内层书名号
        卡们 = 找卡(显示, 索)
        if not 卡们:
            条 = 查白名单(显示, 白)
            if 条 is not None:
                类 = 条.get("类别")
                if 类 in ("非书", "馆内文件"):
                    continue          # 不是书，不按书判（卦名、篇名、馆内文件、电影名）
                引2 = [q for q in QUOTED_RE.findall(行) if 汉字片(显示) not in 汉字片(q)]
                if 引2 and 条.get("原文可核") is False:
                    items.append({"level": "warning", "code": "CITATION_CLASSIC_UNVERIFIED",
                                  "message": "《%s》是%s，本馆无电子本、引原文无法逐字反查："
                                             "须给篇／卷／段，或改为转述" % (显示, 类),
                                  "line": 号})
                continue
            items.append({"level": "error", "code": "CITATION_UNKNOWN",
                          "message": "引用《%s》但引证库与白名单里都没有：不许凭记忆引，"
                                     "先补进引证库／白名单，或删掉这一句" % 显示, "line": 号})
            continue
        档们 = {c.get("可引") for c in 卡们}
        档 = sorted(档们, key=lambda x: 引证档序.get(x, 9))[0]
        引文 = [q for q in QUOTED_RE.findall(行) if 汉字片(显示) not in 汉字片(q)]
        有引文 = bool(引文)
        有定位 = bool(LOCATOR_RE.search(行))
        if 有引文 and 档 == "可逐字引" and not 有定位:
            items.append({"level": "error", "code": "CITATION_NO_LOCATOR",
                          "message": "引《%s》原文却没给定位：可逐字引者须写「书名 + #L行号」，"
                                     "否则 verify_quotes 反查不回来" % 显示, "line": 号})
        if 有引文 and 档 in ("仅指认", "近空", "散图"):
            items.append({"level": "error", "code": "CITATION_INVENTED",
                          "message": "《%s》在引证库里是「%s」，没有原文可引："
                                     "只能写「据该书有此说」，不许出现引号内内容" % (显示, 档),
                          "line": 号})
        # 给了 `#L行号` 就去产物里回读，核引文是不是真在那一带
        号们 = LINENO_RE.findall(行)
        if 引文 and 号们 and 档 == "可逐字引":
            # 校验对象要挑对版本：优先「首选」，其次可逐字引，最后才轮到别的。
            # 以前直接取 卡们[0]，可能正好是乱码版或插空格版——**核对了错的文件**。
            序 = lambda c: (c.get("取舍") == "首选", c.get("可引") == "可逐字引")
            卡 = max(卡们, key=序)
            结, 说 = 校行号(卡, 引文[0], int(号们[0]))
            if 结 == "不符":
                items.append({"level": "error", "code": "CITATION_LOCATOR_MISMATCH",
                              "message": "《%s》引文与出处对不上：%s。要么改行号，要么改引文"
                                         % (显示, 说), "line": 号})
            elif 结 == "读不到":
                items.append({"level": "warning", "code": "CITATION_LOCATOR_UNREADABLE",
                              "message": "《%s》给了 #L%s 但%s：无法回读核对，须人工确认"
                                         % (显示, 号们[0], 说), "line": 号})
        实档 = {d for d in 档们 if d != "散图"}
        if len(实档) > 1:
            items.append({"level": "warning", "code": "CITATION_AMBIGUOUS",
                          "message": "《%s》在引证库有多个版本、可引档位不同（%s）：须写明是哪一版"
                                     % (显示, "、".join(sorted(实档))), "line": 号})
    return items


def scan(text, facts):
    items = []

    def add(level, code, msg, line=0):
        items.append({"level": level, "code": code, "message": msg, "line": line})

    lines = text.splitlines()

    # --- errors ---
    for i, line in enumerate(lines, 1):
        m = ABSOLUTE_RE.search(line)
        if m:
            add("error", "ABSOLUTE", "绝对化/期限措辞「%s」：改为倾向与条件，禁给期限" % m.group(0), i)
        if QUOTE_CLAIM_RE.search(line) and not QUOTE_PROOF_RE.search(line):
            add("error", "UNSOURCED_QUOTE", "声称有出处但无集数/秒级链接/册号：删掉或换成逐字可查的原话", i)
        for sm in SIHUA_RE.finditer(line):
            star, kind = sm.group(1), sm.group(2)
            if not sihua_legal(star, kind):
                add("error", "ILLEGAL_SIHUA", "白名单外四化「%s%s」：生成阶段即须丢弃" % (star, kind), i)
        if UNIQUE_BEST_RE.search(line):
            add("error", "UNIQUE_BEST", "把并列说成唯一最好 / 排名：照说并列，不排先后", i)
        hm = HEALTH_RE.search(line)
        if hm:
            add("error", "HEALTH_LONGEVITY", "健康诊断或本人寿元红线「%s」：转就医提醒，寿元只提关口" % hm.group(0), i)
        if UNJUDGED_RE.search(line) and AS_FINAL_RE.search(line):
            add("error", "UNJUDGED_AS_FINAL", "把「未判/给不出」说成定格：照说未判，不补判", i)

    # 工具外数值（无 facts 时跳过并提示）
    if facts and "tool_numbers" in facts:
        allowed = {str(x) for x in facts["tool_numbers"]}
        for i, line in enumerate(lines, 1):
            for nm in NUMBER_RE.finditer(line):
                if nm.group(1) not in allowed:
                    add("error", "NUMBER_NOT_FROM_TOOL", "工具未给出的分值「%s分」：只从工具输出取数" % nm.group(1), i)
    else:
        add("warning", "NO_FACTS", "未提供 facts.json，工具数值核对未执行；需人工确认分数来源")

    if not DISCLAIMER_RE.search(text):
        add("error", "NO_DISCLAIMER", "缺固定免责声明：补「供参考／不构成专业建议／决策权在你」")

    # --- warnings ---
    if INFER_RE.search(text) and INFER_TAG not in text:
        add("warning", "NO_INFER_TAG", "含归纳/推断但未标〔本馆归纳〕：归纳一律显式标注")
    if not CARD_RE.search(text):
        add("warning", "NO_CARD", "未标口径卡版本/hash：归档结论须绑定 engine_version + 口径卡 hash")
    if "紫微" in text and SIX_REL_RE.search(text) and not SIX_NOTE_RE.search(text):
        add("warning", "NO_SIX_REL_NOTE", "紫微册涉及父母/兄弟/子女，须附「斗数批六亲本来就比较差一点」局限注；"
            "但本馆六亲仍照 R-033 敢断有无厚薄，此注不降成色")
    # 引证核对：查《书名》是否在引证库、档位是否允许引原文、引原文有没有定位
    items.extend(核对引证(text,
                          载引证库((facts or {}).get("quote_index")),
                          载白名单((facts or {}).get("quote_whitelist"))))

    # 断年空话：写了模糊时间词、这一行却没有四位年份 → 点出来（`61` §3.4）
    for i, line in enumerate(lines, 1):
        if YEAR_VAGUE_RE.search(line) and not YEAR_ANY_RE.search(line):
            add("warning", "YEAR_VAGUE",
                "只写「这几年／将来／某个时候」而无四位年份：按 `61` §3.4 补"
                "「区间＋主年＋引动依据」，或明说「本盘只能指到段」", i)
            break          # 一份稿只报一次

    # 去留空话：把取舍推回给客户、没给窗口与代价 → 点出来（`61` §3.5）
    for i, line in enumerate(lines, 1):
        if NOWHERE_RE.search(line) and not HEDGE_OK_RE.search(line):
            add("warning", "NOWHERE",
                "去留停在「顺其自然／看情况」：按 `61` §3.5 补象、年份窗口与"
                "两条路各自要撑住什么；签字权仍归当事人，但窗口必须给", i)
            break

    # 健康空话：只写「注意身体／建议体检」，没有病名或检查项 → 点出来（`OB100`）
    for i, line in enumerate(lines, 1):
        if HEALTH_VAGUE_RE.search(line) and not HEALTH_SPECIFIC_RE.search(line):
            add("warning", "HEALTH_VAGUE",
                "健康提示停在「注意身体／建议体检」：按 `OB100` 补 2–4 个需排查的病名"
                "＋对应检查项，或删掉这句空话", i)
            break          # 同一份稿只报一次，避免满屏重复

    if facts and facts.get("mode") == "light" and len(text) > 600:
        add("warning", "LIGHT_TOO_LONG", "轻量白话答复超过 600 字；完整报告按 61 四册不受此限")

    errors = [x for x in items if x["level"] == "error"]
    warnings = [x for x in items if x["level"] == "warning"]
    return {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "items": items,
        "summary": ("有 error，先改再发；warning 须在成品中说明未核内容。通过不等于语义正确。"
                    if errors else
                    ("无 error；%d 条 warning 须在成品中说明未核内容。分寸仍归主理人。" % len(warnings))),
    }


def 载引文清单(路=None):
    路 = 路 or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "quotes_manifest.json")
    if not os.path.isfile(路):
        return None
    with open(路, encoding="utf-8") as f:
        return json.load(f)


def 核对引文清单(表=None, 根=None):
    """逐条回查「引文逐字可查清单」——只核登记过的条目，零外部语料依赖。

    吸收 DSH dsh-metaphysics「引文索引由测试校验原文子串」的机制
    （2026-11-07 实证订正：该库实测 99 条＝CITATIONS 58＋CLASSICS 41；
     旧文档写的「94 条」无一手断言支撑，按 OB95 不进定案级规则，见 KB103 §二）：
    **引文清单与册页正文必须自动对拍**，册页改了一个字、删了一句就红。
    与 `verify_quotes.py` 分工：那个拿外部语料核「引文有没有出处」，
    这个核「登记过的引文有没有被改字／删掉／误标语境」。

    另外把 `OB97`／`TR101` 落成机械判据：含白名单外四化字面（七杀化权／
    紫微化忌）的条目，必须标「古籍引证」并写误用警示——古籍引证原文不是
    盘面四化断言，不许拿全文固定串命中当四化残留。

    2026-11-07 三次加强（`KB104` §七）：借 `voidforall/fengshui.skill`
    `references/sources.md` 的**引证核对状态五档**，本馆补一档「本馆自撰」。
    原文类语境必须是「原文已逐字回查」，自撰类语境必须标「本馆自撰」，
    防止把本馆自撰的规矩句冒充成古籍原文。
    """
    根 = 根 or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "..", ".."))
    表 = 表 if 表 is not None else 载引文清单()
    if 表 is None:
        return {"ok": False, "条数": 0, "通过": 0, "失败": ["引文清单不存在"]}
    允许 = set(表.get("语境允许值", []))
    状态允许 = set(表.get("核对状态允许值", []))
    字面 = 表.get("白名单外四化字面", [])
    失败, 通过 = [], 0
    for x in 表.get("条目", []):
        id_ = x.get("id", "?")
        f = os.path.join(根, x.get("文件", ""))
        if not os.path.isfile(f):
            失败.append("%s 文件不存在：%s" % (id_, x.get("文件")))
            continue
        with open(f, encoding="utf-8") as fp:
            正文 = re.sub(r"\s+", "", fp.read())
        键 = re.sub(r"\s+", "", x.get("引文", ""))
        if not 键 or 键 not in 正文:
            失败.append("%s 引文未逐字命中（可能被改字或删掉）：%s" % (id_, 键[:30]))
            continue
        if x.get("语境") not in 允许:
            失败.append("%s 语境非法：%s" % (id_, x.get("语境")))
            continue
        if any(s in 键 for s in 字面):
            if x.get("语境") != "古籍引证" or not x.get("误用警示"):
                失败.append("%s 含白名单外四化字面，却没标「古籍引证＋误用警示」" % id_)
                continue
        if not x.get("误用警示"):
            失败.append("%s 缺误用警示" % id_)
            continue
        # 核对状态与语境联动：原文类不许降级，自撰类不许冒充原文（KB104 §七）。
        态 = x.get("核对状态")
        if 态 not in 状态允许:
            失败.append("%s 核对状态非法或缺字段：%s" % (id_, 态))
            continue
        if x.get("语境") in ("古籍引证", "课程原话", "讲义原文") and 态 != "原文已逐字回查":
            失败.append("%s 属原文类语境，核对状态必须是「原文已逐字回查」" % id_)
            continue
        if x.get("语境") in ("册页自述", "本馆规矩") and 态 != "本馆自撰":
            失败.append("%s 属本馆自撰语境，不许标成原文已核（防自撰冒充原文）" % id_)
            continue
        通过 += 1
    return {"ok": not 失败, "条数": len(表.get("条目", [])),
            "通过": 通过, "失败": 失败}


def selftest():
    good = (
        "这一 step 大运财上顺，倾向稳中有进；条件是有贵人帮着把事分出去。\n"
        "〔本馆归纳〕依据 `01` 与 `03`，命主实况待验证。\n"
        "倪师在《天纪》2上 00:25:27 说过斗数批六亲本来就比较差一点，紫微册父母项仅供参考；"
        "但六亲有力者仍按四柱敢断。\n"
        "壬干紫微化权、天梁化禄，落在官禄宫。\n"
        "口径卡 kauding_hash=abc123 / engine_version=xuanjian-1.51.0。\n"
        "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n"
    )
    bad = (
        "倪师说你今年必发，注定大富大贵，绝对没错。\n"
        "七杀化权、紫微化忌同宫，定为上格，最吉，排名第一。\n"
        "这个盘 99.5 分，确诊为肝病，活不过六十。\n"
    )
    facts = {"mode": "light", "tool_numbers": ["81.0"]}
    g = scan(good, facts)
    b = scan(bad, facts)
    虚 = ("这步运注意身体，建议体检，别太累。\n"
          "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n")
    实 = ("日主庚金无根，月令火旺：需排查过敏性鼻炎、慢性咽炎，查鼻内镜与过敏原；\n"
          "若长期吸烟，加做低剂量胸部 CT。以上为排查方向，不是诊断，须由医生确认。\n"
          "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n")
    虚r = scan(虚, {})
    实r = scan(实, {})
    # 断年与去留（`61` §3.4／§3.5）：四条用例，正负各二
    年虚 = ("这步运是守成之运，这几年宜稳住，将来再说。\n"
            "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n")
    年实 = ("这步运是守成之运（留）。2027–2029（主年 2028）：大运庚合住乙、"
            "2028 戊申冲寅解合。宜留到 2028，代价是这两年收入不涨。\n"
            "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n")
    去虚 = "这段关系成色薄，要不要继续，看情况吧。\n以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n"
    去实 = ("这段关系 2028–2029 是分水岭，2029 是能谈清的窗口；宜守到 2029，"
            "若已涉及人身安全则不必等年份。离或不离由当事人自己决定。\n"
            "以上为传统术数文化分析，供参考；不构成专业建议，决策权在你。\n")
    年虚r, 年实r = scan(年虚, {}), scan(年实, {})
    去虚r, 去实r = scan(去虚, {}), scan(去实, {})
    # ── 引文清单逐条回查（2026-11-07）：真库 + 两种篡改都要有独立用例 ──
    清单真表 = 载引文清单() or {"条目": [], "语境允许值": [], "白名单外四化字面": []}
    清单真 = 核对引文清单(清单真表)
    清单伪改字 = json.loads(json.dumps(清单真表))
    if 清单伪改字["条目"]:
        清单伪改字["条目"][0]["引文"] = "被改过的一个句子"
    清单伪误标 = json.loads(json.dumps(清单真表))
    if 清单伪误标["条目"]:
        清单伪误标["条目"][0]["语境"] = "盘面四化断言"
    清单伪状态 = json.loads(json.dumps(清单真表))
    if 清单伪状态["条目"]:
        清单伪状态["条目"][0]["核对状态"] = "随便写的状态"
    清单伪冒充 = json.loads(json.dumps(清单真表))
    for y in 清单伪冒充["条目"]:
        if y.get("语境") in ("册页自述", "本馆规矩"):
            y["核对状态"] = "原文已逐字回查"
            break
    清单伪降级 = json.loads(json.dumps(清单真表))
    if 清单伪降级["条目"]:
        清单伪降级["条目"][0]["核对状态"] = "公认出处待核"
    checks = [
        ("健康·空话被点出", any(x["code"] == "HEALTH_VAGUE" for x in 虚r["items"])),
        ("健康·带病名与检查项不报空话",
         not any(x["code"] == "HEALTH_VAGUE" for x in 实r["items"])),
        ("健康·空话只报一次",
         sum(1 for x in 虚r["items"] if x["code"] == "HEALTH_VAGUE") == 1),
        ("断年·模糊时间被点出", any(x["code"] == "YEAR_VAGUE" for x in 年虚r["items"])),
        ("断年·带年份与依据不报", not any(x["code"] == "YEAR_VAGUE" for x in 年实r["items"])),
        ("去留·推脱被点出", any(x["code"] == "NOWHERE" for x in 去虚r["items"])),
        ("去留·合规收尾不误杀（含「自己决定」）",
         not any(x["code"] == "NOWHERE" for x in 去实r["items"])),
        ("断年·一份稿只报一次",
         sum(1 for x in 年虚r["items"] if x["code"] == "YEAR_VAGUE") == 1),
        ("合规草稿零 error", g["error_count"] == 0, json.dumps(g["items"], ensure_ascii=False)),
        ("违规草稿有 error", b["error_count"] > 0, ""),
        ("绝对化被拦", any(x["code"] == "ABSOLUTE" for x in b["items"]), ""),
        ("无出处引文被拦", any(x["code"] == "UNSOURCED_QUOTE" for x in b["items"]), ""),
        ("七杀化权被拦", any(x["code"] == "ILLEGAL_SIHUA" and "七杀化权" in x["message"] for x in b["items"]), ""),
        ("紫微化忌被拦", any(x["code"] == "ILLEGAL_SIHUA" and "紫微化忌" in x["message"] for x in b["items"]), ""),
        ("工具外分数被拦", any(x["code"] == "NUMBER_NOT_FROM_TOOL" for x in b["items"]), ""),
        ("健康寿元被拦", any(x["code"] == "HEALTH_LONGEVITY" for x in b["items"]), ""),
        ("缺免责被拦", any(x["code"] == "NO_DISCLAIMER" for x in b["items"]), ""),
        ("合法四化不误伤", sihua_legal("紫微", "化权") and sihua_legal("天梁", "化禄"), ""),
        ("白名单外四化判否", not sihua_legal("七杀", "化权") and not sihua_legal("紫微", "化忌"), ""),
    ]
    # ── 引证核对（v1.65.0）：每条判据都要有独立用例 ─────────────────────
    # 上一版这里只借 good 草稿的《天纪》顺带过了一遍，而那是课程语料、
    # 在 continue 处就跳走，整段逻辑从没执行过，藏着 NameError 也没人知道。
    import os
    import tempfile
    根 = tempfile.mkdtemp(prefix="gate-")
    索引路 = os.path.join(根, "索引.json")
    # 造一个真产物文件：第 12 行含那句引文，第 1 行是头，够 30 行
    产物 = os.path.join(根, "产物.md")
    with open(产物, "w", encoding="utf-8") as f:
        for i in range(1, 31):
            f.write(("第 %d 行：黄芪味甘微温，主痈疽久败疮。\n" % i)
                    if i == 12 else ("第 %d 行：别的本草条文。\n" % i))
    json.dump({"cards": [
        {"id": "Q1", "书名": "可书甲", "可引": "可逐字引", "产物绝对": 产物},
        {"id": "Q2", "书名": "可书甲的另一版本", "可引": "可逐字引"},
        {"id": "Q3", "书名": "仅书乙", "可引": "仅指认"},
        {"id": "Q4", "书名": "近书丙", "可引": "近空"},
        {"id": "Q5", "书名": "双版丁", "可引": "可逐字引"},
        {"id": "Q6", "书名": "双版丁扫描本", "可引": "仅指认"},
        {"id": "Q7", "书名": "10", "可引": "散图"},
        {"id": "Q8", "书名": "倪海厦《本草备要》(神州医料库）", "可引": "可逐字引"},
    ]}, open(索引路, "w", encoding="utf-8"), ensure_ascii=False)
    索 = 载引证库(索引路)

    def 码们(文, 库=索):
        return [x["code"] for x in 核对引证(文, 库)]

    引 = lambda a: "「%s」" % a
    checks += [
        ("引证·索引装载跳过纯数字名", "10" not in 索 and "可书甲" in 索),
        ("引证·无书名不报", 码们("这段没有任何书名号。") == []),
        ("引证·无索引只警告", 码们("《可书甲》说了一句。", None) == ["NO_QUOTE_INDEX"]),
        ("引证·未入库要拦", 码们("《没入过库的书》说了" + 引("某事必应")) == ["CITATION_UNKNOWN"]),
        ("引证·可逐字引+引文+无定位要拦",
         码们("《可书甲》写着" + 引("黄芪味甘微温主痈疽")) == ["CITATION_NO_LOCATOR"]),
        ("引证·可逐字引+引文+行号对得上→放行",
         码们("《可书甲》写着" + 引("黄芪味甘微温主痈疽久败疮") + "（#L12）") == []),
        ("引证·行号指错地方→CITATION_LOCATOR_MISMATCH",
         码们("《可书甲》写着" + 引("黄芪味甘微温主痈疽久败疮") + "（#L3）")
         == ["CITATION_LOCATOR_MISMATCH"]),
        ("引证·行号越界→只警告不拦",
         码们("《可书甲》写着" + 引("黄芪味甘微温主痈疽久败疮") + "（#L9999）")
         == ["CITATION_LOCATOR_UNREADABLE"]),
        ("引证·引文不足 8 汉字不做逐字比对（免误报）",
         码们("《可书甲》写着" + 引("短句六个汉字") + "（#L12）") == []),
        ("引证·引文含标点但汉字够 8 仍要比对",
         码们("《可书甲》写着" + 引("黄芪，味甘；微温，主痈疽") + "（#L12）") == []),
        ("引证·距行号两行内仍算对（语料硬换行）",
         码们("《可书甲》写着" + 引("黄芪味甘微温主痈疽久败疮") + "（#L14）") == []),
        ("引证·可逐字引+有页号放行",
         码们("《可书甲》第 88 页云" + 引("凡药之用各有专长")) == []),
        ("引证·只提书名不引原文放行", 码们("《可书甲》这本书讲过此事。") == []),
        ("引证·仅指认+引文要拦",
         码们("《仅书乙》云" + 引("某某症状三日必愈")) == ["CITATION_INVENTED"]),
        ("引证·仅指认+只指认放行", 码们("据《仅书乙》有此说，具体待核。") == []),
        ("引证·近空+引文要拦", 码们("《近书丙》载" + 引("某方治某病有奇效")) == ["CITATION_INVENTED"]),
        ("引证·多版本档不同要提示（无全等键时）",
         "CITATION_AMBIGUOUS" in 码们("《双版》这本书的说法。")),
        ("引证·多版本取可引那一档判引文（要定位，不判编造）",
         (lambda c: "CITATION_NO_LOCATOR" in c and "CITATION_INVENTED" not in c)(
             码们("《双版》书中写着" + 引("某句原文若干字")))),
        ("引证·有全等键时以全等为准，不报歧义",
         码们("《双版丁》这本书的说法。") == []),
        ("引证·课程语料不按书核",
         码们("《天纪》第 3 集 00:12:30 说过" + 引("斗数批六亲比较差一点")) == []),
        ("引证·嵌套书名号取最外层", [x[0] for x in 找书名("《甲《乙》丙》")] == ["甲《乙》丙"]),
        ("引证·报错行号指对",
         [x["line"] for x in 核对引证("第一行\n《没入过库的书》说" + 引("某事必应"), 索)] == [2]),
        ("引证·白名单典籍引原文只警告不拦",
         [x["code"] for x in 核对引证("《撼龙经》云" + 引("龙脉到头结穴处必有回环"), 索,
                                    {"撼龙经": {"类别": "典籍", "原文可核": False}})]
         == ["CITATION_CLASSIC_UNVERIFIED"]),
        ("引证·白名单典籍只提书名放行",
         [x["code"] for x in 核对引证("《撼龙经》讲过这个看法。", 索,
                                    {"撼龙经": {"类别": "典籍", "原文可核": False}})] == []),
        ("引证·白名单非书（卦名）完全跳过",
         [x["code"] for x in 核对引证("《乾为天》这一卦" + 引("潜龙勿用见龙在田"), 索,
                                    {"乾为天": {"类别": "非书", "原文可核": None}})] == []),
        ("引证·白名单馆内文件跳过",
         [x["code"] for x in 核对引证("见《档案卡片》记录" + 引("癸卯年冬月有一条"), 索,
                                    {"档案卡片": {"类别": "馆内文件", "原文可核": None}})] == []),
        ("引证·两处都没有才报未入库",
         [x["code"] for x in 核对引证("《从没见过的书名》说" + 引("某事必应"), 索,
                                    {"撼龙经": {"类别": "典籍"}})] == ["CITATION_UNKNOWN"]),
        ("引证·白名单简称能命中全称",
         [x["code"] for x in 核对引证("《撼龙经》讲过。", 索,
                                    {"图解撼龙经全本": {"类别": "典籍", "原文可核": False}})] == []),
        ("引证·带括注的全称可被简称命中（《本草备要》）",
         码们("《本草备要》这本书讲过。") == []),
        ("引证·引文里含书名不算引文",
         码们("《可书甲》写道" + 引("详见可书甲所载之条目")) == []),
        ("引文清单·真库逐条可查", 清单真["ok"], str(清单真["失败"][:2])),
        ("引文清单·改一个字即红", not 核对引文清单(清单伪改字)["ok"]),
        ("引文清单·白名单外四化误标语境即红", not 核对引文清单(清单伪误标)["ok"]),
        ("引文清单·核对状态非法即红", not 核对引文清单(清单伪状态)["ok"]),
        ("引文清单·自撰冒充原文即红", not 核对引文清单(清单伪冒充)["ok"]),
        ("引文清单·原文降级为待核即红", not 核对引文清单(清单伪降级)["ok"]),
    ]

    failed = 0
    for name, passed, *rest in checks:      # 旧条目是三元组，新条目省了 detail
        detail = rest[0] if rest else ""
        print("%s  %s%s" % ("PASS" if passed else "FAIL", name, ("  " + detail) if (not passed and detail) else ""))
        failed += 0 if passed else 1
    print("\n%d/%d passed" % (len(checks) - failed, len(checks)))
    return 1 if failed else 0


def main():
    p = argparse.ArgumentParser(description="玄鉴发出前机械闸门")
    p.add_argument("--draft", help="草稿文件路径，或 - 表示 stdin")
    p.add_argument("--facts", help="可选 facts.json")
    p.add_argument("--引证库", dest="quote_index", help="引证库索引.json（不给则自动找）")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--quotes", action="store_true", help="逐条回查引文清单")
    args = p.parse_args()

    if args.selftest:
        return selftest()
    if args.quotes:
        r = 核对引文清单()
        print("引文逐字可查清单：%d 条，通过 %d，失败 %d" %
              (r["条数"], r["通过"], len(r["失败"])))
        for x in r["失败"]:
            print("  ✗", x)
        if r["ok"]:
            print("结论：登记过的引文都能在册页里逐字找到，语境标注也合规。")
        return 0 if r["ok"] else 1
    if not args.draft:
        p.print_help()
        return 2
    text = sys.stdin.read() if args.draft == "-" else open(args.draft, encoding="utf-8").read()
    facts = None
    if args.facts:
        with open(args.facts, encoding="utf-8") as f:
            facts = json.load(f)
    if args.quote_index:
        facts = dict(facts or {})
        facts["quote_index"] = args.quote_index
    r = scan(text, facts)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 1 if not r["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
