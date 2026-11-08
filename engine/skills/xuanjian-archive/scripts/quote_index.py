#!/usr/bin/env python3
"""引证库 —— 整本书立卡，不拆句进册页。

用法：
    python3 quote_index.py 建 <采集目录> [--类 类甲,类乙] [--out 目录]    # 不给 --类 则全库
    python3 quote_index.py 查 <索引.json> <关键词>
    python3 quote_index.py 统计 <索引.json>
    python3 quote_index.py 白名单 --册 目录1,目录2 --索引 索引.json --out 书目白名单.json
    python3 quote_index.py --selftest

**为什么整本书不能拆句进册页**：册页（`xuanjian-kb/references/`）的每条都是
「可复用、可裁、可归到某个十神／某个关系」的规则句。整本书不是规则集合，
是一本书——它有自己的章节、自己的论证顺序、自己的语境。把一本 60 万字的
《黄帝内经》拆成句子塞进册页，会有三个后果：

1. **定位失效**。册页靠 `簿号#L行号` 定位，句子一散，页码页码全断，
   `verify_quotes.py` 再也查不回原处；
2. **语境丢失**。「脉浮者，病在表」离开上下文就不再是那个意思，
   而册页是要拿去做断语依据的；
3. **裁决淹死**。一个 60 万字的文件能抽出上万句，册页只有 99 册——
   抽出来的东西 99% 会被驳回，而人已经为此花了几十个小时。

所以整本书的正确位置是**引证库**：书在库里、卡片在索引里、引用时按
`书名 + 段落号` 回查原文件。册页只收「从书里提炼出来的规则」，且提炼是**另一步**，
要人做、要有裁决记录——不是把书倒进册页。

**可引性三档**（这是本册最要紧的一件事）：

| 档 | 判据 | 能做什么 |
|---|---|---|
| `可逐字引` | 有文字层且正文够长 | 可引原文，须附「书名 + `#L行号`」，可反查 |
| `仅指认` | 扫描件无文字层（需 OCR） | 只能说「该书有此说」+ 书名，**不许写原文引用** |
| `近空` | 有页码层但正文近乎为零 | 同「仅指认」，且注明「实为扫描本」 |
| `散图` | 单张图片（.jpg／.bmp／.png） | **不成书**，不立书卡；只能记「有一张图，内容未知」 |
| `乱码` | 正文超 20% 是字体编码乱码（PDF 无 ToUnicode） | **不可引**：看着有字，抽出来是 `/G3C`，须换版本 |

第二档不是保守，是必需：扫描件没 OCR 就没原文，「据《神农本草》第 88 页云……」这种
引法在没看见那页之前就是编的。宁可写「该书此说待核」，不许造一句引文。

**版权边界**：这批书是倪师著作（部分语料 CC BY-NC-SA 4.0 非商用），
全量只放工作区，**不入插件包**（`xuanjian-kb` 铁律 13）。
"""
import json
import os
import re
import sys

类默认 = None          # None = 全库都收（v1.66.0 起）
可引字数下限 = 500          # 低于此数，即便有文字层也不足以逐字引
_页数 = re.compile(r"（(\d+) 页）")


def 抠页数(note):
    m = _页数.search(note or "")
    return int(m.group(1)) if m else None


图类 = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif", ".webp")


乱码上限 = 0.20        # 超过这个比例，抽出来的就不是文字，是字体编码


def 正文(路):
    """读采集产物「---头---」之后的正文。头里有源路径与字符数，不能算进统计。"""
    try:
        t = open(路, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    if t.startswith("---"):
        k = t.find("\n---", 3)
        if k > 0:
            t = t[k + 4:]
    return t


def 乱码率(文):
    """估一份产物里「抽成乱码」的比例。

    为什么必须看：PDF 内嵌字体没有 ToUnicode 映射时，解出来是 `/G3C/G3D/G95`
    这类 CID 码，或 Unicode 私有区字符。它们长度可观、看起来「有字」，
    于是一本 6 万字的书会被判成「可逐字引」——**而引它等于引垃圾**。
    实测《零起点学中医》PDF 版 86.5% 是这种码，却一直挂在可引档上。
    """
    t = 文 or ""
    if not t:
        return 0.0
    cid = len(re.findall(r"/G[0-9A-F]{2}", t))
    pua = len(re.findall(r"[\ue000-\uf8ff]", t))
    return min(1.0, (cid * 4 + pua) / max(len(t), 1))


def 判可引(x, 文=None):
    """返回 (档, 理由)。五档见模块说明。`文` 给了就查乱码。"""
    状 = x.get("status")
    字 = x.get("chars") or 0
    if 文 is not None:
        率 = 乱码率(文)
        if 率 > 乱码上限:
            return "乱码", "正文 %.0f%% 是字体编码乱码（PDF 无 ToUnicode），抽取失败" % (率 * 100)
    if (x.get("ext") or "").lower() in 图类:
        # 单张图片不是一本书。实测这堆图叫 `10.jpg`、`11.jpg`、`12.jpg`，
        # 放进「仅指认」会让索引里冒出几百个书名是数字的条目，把真书淹没。
        return "散图", "单张图片（%s），未 OCR，判不出属哪本书" % (x.get("ext") or "").lower()
    if 状 == "ok" and 字 >= 可引字数下限:
        return "可逐字引", "有文字层，%d 字，可按行号回查" % 字
    if 状 == "ok":
        return "近空", "有文字层但仅 %d 字，疑扫描本，不可当原文引" % 字
    if 状 == "thin":
        return "近空", "正文仅 %d 字，实为扫描本" % 字
    页 = 抠页数(x.get("note"))
    if 页:
        return "仅指认", "扫描件无文字层（%d 页），未 OCR，只能指认不能引原文" % 页
    return "仅指认", (x.get("note") or "未取到正文")[:40]


def 取类(x, 采集根=None):
    """这条采集账属于哪一类（顶层目录名）。

    为什么要分类而不是只收一类：v1.65.0 只收了「倪师书籍扫描版本」358 种，
    而全库还有中医电子书 90、曾仕强 62、命理课程 525、电子文案 371——
    **引到那四类的书，闸门会一律判「库里没这本」**。误拦比不拦更坏：
    人被误拦几次就会绕过闸门，闸门一旦被绕过就等于没有。
    """
    源 = x.get("src") or ""
    if "/文档/" in 源:
        return 源.split("/文档/")[-1].split("/")[0]
    产 = x.get("out") or ""
    if "/" in 产:
        return 产.split("/")[0]
    # 兜底：取源文件的父目录名。测试夹具与「直接给一个子目录」都走这条。
    import os as _os
    return _os.path.basename(_os.path.dirname(源)) or "（未分类）"


def 汉字片(s):
    """只取汉字。书名比对用——标点、书名号、括注、版本后缀都不该影响「是不是同一本」。"""
    return "".join(re.findall(r"[\u4e00-\u9fff]", s or ""))


def 书名(路):
    b = os.path.basename(路 or "")
    b = os.path.splitext(b)[0]
    # 只去纯数字副本号，不动（第4次）这类有意义括注
    b = re.sub(r"(?:\s*[-_－]?\s*副本|\((\d+)\)|（(\d+)）)$", "", b)
    return b.strip()


def 库文(册目录):
    """把册库全文拼成一个大字符串，用来判「这本书是否已被册页引用过」。

    为什么不用逐句匹配：358 本书 × 17,599 句是 600 万次比较；
    拼成一个大串后每个书名只需一次 `in`。
    """
    块 = []
    if not os.path.isdir(册目录):
        return ""
    for f in sorted(os.listdir(册目录)):
        if f.endswith(".md"):
            try:
                with open(os.path.join(册目录, f), encoding="utf-8", errors="replace") as h:
                    块.append(h.read())
            except OSError:
                continue
    return "\n".join(块)


def 查引(题, 全库):
    """这本书是否已在册页里被引过。判据：书名去掉书名号后，前 8 字出现在册库正文里。

    前 8 字是折中：太短会撞（《神农本草》与《神农本草经》），太长会漏
    （册页里可能只写了简称）。命中的结果只作提示，不作结论——
    本函数回答的是「可能引过」，不是「一定引过」。
    """
    # 只取汉字做键：`1-14` 这类纯数字题名，去掉题名号后仍是 `1-14`，
    # 会撞上正文里任何一处「1-14」，判成「已引」。实测 Q001 就这样误报过。
    汉 = re.findall(r"[\u4e00-\u9fff]", 题 or "")
    if len(汉) < 4:
        return False
    return "".join(汉)[:8] in 全库


def _档案根():
    """档案根统一问 `study_state`。**中文环境变量在本机 shell 传不进去**，
    只认它的脚本会在插件目录里静默落到别的工作区（实测落到 2026-10-26 那个）。"""
    import sys as _sys
    技 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "xuanjian-evolve", "scripts")
    if 技 not in _sys.path:
        _sys.path.insert(0, 技)
    try:
        import study_state
        return study_state.状态根()
    except Exception:
        return os.environ.get("命理档案")


def 读取舍(路=None):
    """读版本取舍表：同一本书有多个格式时，哪一版为准。找不到给 {}。"""
    候选 = []
    if 路:
        候选.append(路)
    根 = _档案根()
    if 根:
        候选.append(os.path.join(根, "引证库", "版本取舍.json"))
    候选.append(os.path.join(os.getcwd(), "命理档案", "引证库", "版本取舍.json"))
    for p in 候选:
        if p and os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8")).get("items", {})
            except (OSError, ValueError):
                continue
    return {}


def 标取舍(卡, 取舍):
    """给卡片打上「首选／备用」标记。

    为什么值得单独一步：同名两版若都标「可逐字引」，闸门校验行号时取的是
    列表第一个——可能正好是乱码那版或插了空格那版，于是**核对了错的文件**。
    定了版，校验才有确定对象。
    """
    if not 取舍:
        return
    for 书名, 条 in 取舍.items():
        取 = 条.get("取") or ""
        舍 = 条.get("舍") or []
        for c in 卡:
            if 汉字片(c.get("书名")) != 汉字片(书名) and 汉字片(书名) not in 汉字片(c.get("书名")):
                continue
            产 = c.get("产物") or ""
            if 取 and 产.endswith(取):
                c["取舍"] = "首选"
            elif any(产.endswith(x) for x in 舍):
                c["取舍"] = "备用"
                c["理由"] = (c.get("理由") or "") + "｜已定版为备用，勿引"


def 建(采集根, 输出目录, 类们=类默认, 册目录=None, 取舍路=None):
    """读采集账，一本书一张卡片，写出 索引.json 与 索引.md。

    `类们` 给 None 表示全库都收；给元组则只收这几类。每张卡记下它属于哪一类，
    便于日后按类统计、也便于「哪一类还没立卡」一眼看出来。
    """
    账路 = os.path.join(采集根, "_index.json")
    if not os.path.exists(账路):
        raise SystemExit("找不到采集账：%s" % 账路)
    账 = json.load(open(账路, encoding="utf-8")).get("entries", [])
    条 = [x for x in 账
        if 类们 is None or 取类(x, 采集根) in 类们]
    全库 = 库文(册目录 or os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "xuanjian-kb", "references"))

    卡们 = []
    for i, x in enumerate(sorted(条, key=lambda t: (取类(t, 采集根), 书名(t["src"]))), 1):
        题 = 书名(x["src"])
        文 = ""
        if x.get("status") == "ok" and x.get("out"):
            路 = os.path.join(采集根, x["out"])
            if os.path.exists(路):
                文 = 正文(路)
        档, 因 = 判可引(x, 文 if 文 else None)
        卡们.append({
            "id": "Q%04d" % i,
            "类": 取类(x, 采集根),
            "书名": 题,
            "源": x["src"],
            "产物": x.get("out"),
            # 绝对路径：闸门要按 `#L行号` 回读产物核内容，只给相对路径它找不到。
            # 采集根换地方时这里会失效，但闸门对「读不到」只报 warning 不报 error。
            "产物绝对": (os.path.join(os.path.abspath(采集根), x["out"])
                        if x.get("out") else None),
            "类型": x.get("ext"),
            "字数": x.get("chars") or 0,
            "页数": 抠页数(x.get("note")),
            "可引": 档,
            "理由": 因,
            "定位": ("产物 .md 的 #L行号（可用 verify_quotes.py 反查）"
                    if 档 == "可逐字引" else "只到书名，无段号（未 OCR）"),
            "册页已引": 查引(题, 全库),
        })

    标取舍(卡们, 读取舍(取舍路))

    计, 类计 = {}, {}
    for c in 卡们:
        计[c["可引"]] = 计.get(c["可引"], 0) + 1
        类计.setdefault(c["类"], {}).setdefault(c["可引"], 0)
        类计[c["类"]][c["可引"]] += 1

    os.makedirs(输出目录, exist_ok=True)
    报 = {"artifact": "引证库索引（整本书立卡，不拆句进册页）",
          "source_dir": 采集根,
          "category": (list(类们) if 类们 else "全库"),
          "counts": 计, "by_category": 类计, "total": len(卡们),
          "rule": "可逐字引者，引用须写「书名 + #L行号」；仅指认者，"
                  "只许写「据《书名》有此说」，不许出现原文引号内内容；"
                  "近空者视同仅指认。整本书一律不拆句入册页。",
          "cards": 卡们}
    json.dump(报, open(os.path.join(输出目录, "索引.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    行 = ["# 引证库索引 —— %s" % (
             "全库" if not 类们 else "、".join(类们)), "",
         "> 整本书立卡，**不拆句进册页**。共 %d 种，%s。" % (
             len(卡们), "；".join("%s %d" % (k, v) for k, v in sorted(计.items()))),
         ">", "> 引用纪律：`可逐字引` 须写「书名 + `#L行号`」；`仅指认`／`近空` 只许写",
         "> 「据《书名》有此说」，**不许出现引号内的原文**。", "",
         "## 〇、各分类立卡情况", "",
         "| 分类 | 立卡 | 可逐字引 | 仅指认 | 近空 | 散图 |", "|---|---|---|---|---|---|"]
    for k in sorted(类计):
        v = 类计[k]
        行.append("| %s | %d | %d | %d | %d | %d |" % (
            k, sum(v.values()), v.get("可逐字引", 0), v.get("仅指认", 0),
            v.get("近空", 0), v.get("散图", 0)))
    行 += ["", "## 一、可逐字引（%d 种）" % 计.get("可逐字引", 0), "",
          "| 编号 | 分类 | 书名 | 字数 | 册页已引 |", "|---|---|---|---|---|"]
    for c in 卡们:
        if c["可引"] == "可逐字引":
            行.append("| %s | %s | %s | %d | %s |" % (
                c["id"], c["类"][:16], c["书名"][:42], c["字数"],
                "是" if c["册页已引"] else ""))
    行 += ["", "## 二、仅指认（%d 种）" % 计.get("仅指认", 0), "",
          "| 编号 | 分类 | 书名 | 页数 | 原因 |", "|---|---|---|---|---|"]
    for c in 卡们:
        if c["可引"] == "仅指认":
            行.append("| %s | %s | %s | %s | %s |" % (
                c["id"], c["类"][:14], c["书名"][:40], c["页数"] or "—", c["理由"][:36]))
    行 += ["", "## 三、近空（%d 种）" % 计.get("近空", 0), "",
          "| 编号 | 分类 | 书名 | 字数 | 原因 |", "|---|---|---|---|---|"]
    for c in 卡们:
        if c["可引"] == "近空":
            行.append("| %s | %s | %d | %s |" % (
                c["id"], c["书名"][:46], c["字数"], c["理由"][:40]))
    if 计.get("乱码"):
        行 += ["", "## 四·补 抽取失败·乱码（%d 种，**不可引**）" % 计["乱码"], "",
              "> PDF 内嵌字体没有 ToUnicode 映射，解出来是 `/G3C` 一类 CID 码。",
              "> 这些书看着「有字」，实际引不出原文；须换版本或重新 OCR。", "",
              "| 编号 | 分类 | 书名 | 原因 |", "|---|---|---|---|"]
        for c in 卡们:
            if c["可引"] == "乱码":
                行.append("| %s | %s | %s | %s |" % (
                    c["id"], c["类"][:14], c["书名"][:40], c["理由"][:44]))
    散 = [c for c in 卡们 if c["可引"] == "散图"]
    if 散:
        行 += ["", "## 四、散图（%d 张，未成书）" % len(散), "",
              "> 单张图片，文件名多为页码编号。**不立书卡**，只记「有此一张」。",
              "> 待 OCR 后才可能归到某本书的某页。", "",
              "| 编号 | 文件名 | 备注 |", "|---|---|---|"]
        for c in 散[:60]:
            行.append("| %s | %s | %s |" % (c["id"], c["书名"][:40], c["理由"][:38]))
        if len(散) > 60:
            行.append("| … | 另 %d 张见 索引.json | |" % (len(散) - 60))
    open(os.path.join(输出目录, "索引.md"), "w", encoding="utf-8").write("\n".join(行) + "\n")
    return 报


# ── 书目白名单（v1.66.0）────────────────────────────────────────────
# 为什么必须有这一层：引证库只覆盖**本馆有电子本**的书（网盘五类）。而册页里
# 引用最多的是《撼龙经》《青囊经》《协纪辨方书》《滴天髓》这类古籍——我们**没有**
# 它们的电子本，也就永远进不了引证库。若闸门只认引证库，实测 204 个书名里
# 有 176 个（86%）会被判「库里没这本」，等于把正常引用全拦掉。
#
# 更麻烦的是「《》里装的并不都是书」：`《乾为天》`是卦名、`《系辞上》`是篇名、
# `《四库全书》`是丛书、`《档案卡片》`是本馆自己的文件、`《红番区》`是电影名。
# 一个「在不在库里」的判据，把五种完全不同的东西当成了同一类。
#
# 所以加白名单，四类分开处置：
#   典籍／丛书／篇名 → 允许引用；因本馆无电子本，**引原文一律不可反查**，须给篇／卷，
#                      只报 warning 不报 error（报 error 会逼人删掉正经引用）
#   非书／馆内文件   → 不按书判（它们本来就不是书，引用它们不算引书）
馆内文件名 = {"档案卡片", "命主记录", "分析记录", "档案卡片.md", "命主记录.md",
             "分析记录.md", "命主记录表"}
非书名 = {"满城尽带黄金甲", "尖峰时刻2", "神奇燕尾服", "皇家威龙", "红番区",
        "十面埋伏", "安持人物琐忆", "80天环游地球", "全国姓名报告", "人间道"}
丛书名 = {"四库全书", "续修四库全书", "四部丛刊", "正统道藏", "万历续道藏",
        "续道藏", "道藏辑要"}
篇名表 = {"系辞上", "乾为天"}


def 分类名(名):
    """给一个《》里的名字分类，返回 (类别, 可否逐字反查原文)。

    四类：馆内文件／非书／丛书／篇名／典籍。前两类不按书判；
    后三类允许引用，但本馆无电子本，**引原文不可反查**。
    """
    净 = (名 or "").strip()
    if 净 in 馆内文件名 or 净.endswith(".md"):
        return "馆内文件", None
    if 净 in 非书名:
        return "非书", None
    if 净 in 丛书名:
        return "丛书", False
    if 净 in 篇名表 or "·" in 净:
        return "篇名", False
    return "典籍", False


def 读索引(路):
    """读引证库索引，返回 {汉字键: [卡片…]}。与 `source_gate.载引证库` 同键法。"""
    索 = {}
    if not 路 or not os.path.exists(路):
        return 索
    try:
        d = json.load(open(路, encoding="utf-8"))
    except (OSError, ValueError):
        return 索
    for c in d.get("cards", []):
        键 = "".join(re.findall(r"[\u4e00-\u9fff]", c.get("书名") or ""))
        if len(键) >= 3:
            索.setdefault(键, []).append(c)
    return 索


def 在索引(名, 索):
    """这个名字是否已在引证库（全等或互相包含，均要求 ≥3 汉字）。"""
    键 = "".join(re.findall(r"[\u4e00-\u9fff]", 名 or ""))
    if len(键) < 2:
        return False
    if 键 in 索:
        return True
    return any(len(k) >= 3 and (键 in k or k in 键) for k in 索)


def 扫册页书名(册目录们):
    """从册页与规格册里抽出所有 `《…》`，返回 {名字: 出现次数}。

    这是白名单的**种子**：册页里引用过的书名，都是本馆认下过的书。
    不设法从外部凑——凑出来的书单没人核过，反而更危险。
    """
    import collections
    计 = collections.Counter()
    for 目 in 册目录们:
        if not os.path.isdir(目):
            continue
        for f in sorted(os.listdir(目)):
            if not f.endswith(".md"):
                continue
            try:
                t = open(os.path.join(目, f), encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in re.finditer(r"《([^《》]{2,40})》", t):
                名 = m.group(1).strip()
                if len(re.findall(r"[\u4e00-\u9fff]", 名)) >= 3:
                    计[名] += 1
    return dict(计)


def 建白名单(输出路径, 册目录们, 索引路=None):
    """建/更新书目白名单。**已有条目的分类不覆盖**，人工改过的保留。"""
    已有 = {}
    if os.path.exists(输出路径):
        try:
            已有 = json.load(open(输出路径, encoding="utf-8")).get("items", {})
        except (OSError, ValueError):
            已有 = {}
    索 = 读索引(索引路) if 索引路 else None
    计 = 扫册页书名(册目录们)

    条 = {}
    for 名, 次 in 计.items():
        if 名 in 已有:
            条[名] = 已有[名]          # 人工分类优先，绝不覆盖
            continue
        if 索 is not None and 在索引(名, 索):
            continue                   # 已在引证库里，不必进白名单
        类, 可核 = 分类名(名)
        条[名] = {"类别": 类, "原文可核": 可核, "册页出现": 次,
                "备注": "由 quote_index.py 白名单 自动分类，可人工改"}
    os.makedirs(os.path.dirname(输出路径) or ".", exist_ok=True)
    json.dump({"artifact": "书目白名单（本馆无电子本但确有其书）",
               "rule": "典籍／丛书／篇名：允许引用、引原文不可反查，须给篇卷；"
                       "非书／馆内文件：不按书判。分类人工可改，重跑不覆盖。",
               "items": 条},
              open(输出路径, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    计类 = {}
    for v in 条.values():
        计类[v["类别"]] = 计类.get(v["类别"], 0) + 1
    return {"条数": len(条), "分类": 计类}


def 查(索引路, 词):
    报 = json.load(open(索引路, encoding="utf-8"))
    中 = [c for c in 报["cards"] if 词 in c["书名"] or 词 in (c["源"] or "")]
    return 中


# ---------------------------------------------------------------- 自检
def 自检():
    """引证库自己的体检。

    它错的方式只有一种方向：**把不可引的标成可引**——那会直接产出假引文，
    而假引文是本馆最不能出的东西（`OB97`：不许以「古书云」代替出处）。
    所以这里专测分档、页数、以及「已引」判定不误报。
    """
    通过, 失败 = [], []

    def 查x(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查x("乱码·全正常为 0", 乱码率("黄芪味甘微温，主痈疽久败疮。") == 0.0)
    查x("乱码·CID 码能算出来", 乱码率("/G3C/G3D/G95/G40/G9D/G39" * 20) > 0.5)
    查x("乱码·私有区字符能算出来", 乱码率("\ue001\ue002\ue003" * 30) > 0.5)
    查x("乱码·空文给 0", 乱码率("") == 0.0)
    查x("乱码·超阈值判「乱码」档",
        判可引({"status": "ok", "chars": 5000}, "/G3C/G3D" * 400)[0] == "乱码")
    查x("乱码·未超阈值仍是可逐字引",
        判可引({"status": "ok", "chars": 5000}, "黄芪味甘" * 400)[0] == "可逐字引")
    查x("乱码·理由里写了百分比",
        "%" in 判可引({"status": "ok", "chars": 5000}, "/G3C" * 400)[1])
    查x("分档·单张图片 → 散图（不立书卡）",
        判可引({"status": "skipped", "ext": ".jpg", "note": "图片未识别出文字"})[0] == "散图")
    查x("分档·图片即便有文字层也算散图",
        判可引({"status": "ok", "ext": ".bmp", "chars": 3000})[0] == "散图")
    查x("分档·散图理由里带扩展名",
        ".jpg" in 判可引({"status": "skipped", "ext": ".jpg", "note": "x"})[1])
    查x("分档·有文字层且够长 → 可逐字引",
        判可引({"status": "ok", "chars": 5000})[0] == "可逐字引")
    查x("分档·有文字层但太短 → 近空",
        判可引({"status": "ok", "chars": 80})[0] == "近空")
    查x("分档·扫描件 → 仅指认",
        判可引({"status": "skipped", "note": "扫描版·无文字层（243 页），需 OCR"})[0] == "仅指认")
    查x("分档·thin → 近空", 判可引({"status": "thin", "chars": 12})[0] == "近空")
    查x("分档·无页数的跳过件也给仅指认",
        判可引({"status": "skipped", "note": "textutil 未取到正文"})[0] == "仅指认")
    查x("分档·边界正好 500 字算可引",
        判可引({"status": "ok", "chars": 可引字数下限})[0] == "可逐字引")
    查x("分档·499 字不算可引",
        判可引({"status": "ok", "chars": 可引字数下限 - 1})[0] == "近空")
    查x("分档·理由里写明字数", "字" in 判可引({"status": "ok", "chars": 900})[1])
    查x("分档·扫描件理由里带页数",
        "243" in 判可引({"status": "skipped",
                       "note": "扫描版·无文字层（243 页），需 OCR"})[1])

    查x("页数·抠得出", 抠页数("扫描版·无文字层（243 页），需 OCR") == 243)
    查x("页数·抠不出给 None", 抠页数("textutil 未取到正文") is None)
    查x("页数·None 不炸", 抠页数(None) is None)

    查x("书名·去扩展名", 书名("/a/b/神农本草.pdf") == "神农本草")
    查x("书名·去数字副本号", 书名("讲义(1).pdf") == "讲义")
    查x("书名·保留年份括注", 书名("作业（2021年）.pdf") != "作业")

    查x("已引·命中", 查引("神农本草", "……见《神农本草》所载……"))
    查x("已引·未命中", not 查引("一本从没提过的书", "……只有别的内容……"))
    查x("已引·太短的题名不判（防撞）", not 查引("内经", "……只有别的内容……"))
    查x("已引·纯数字题名不判（1-14 会撞正文）",
        not 查引("1-14", "……第 1-14 讲的是甲子……"))
    查x("已引·四个汉字的题名才判", 查引("针灸大成", "……见《针灸大成》……"))
    查x("已引·汉字少于四个不判", not 查引("三妙散", "……三妙散……"))

    # 端到端：造一个假采集账
    import tempfile
    import shutil
    根 = tempfile.mkdtemp(prefix="quote-")
    try:
        json.dump({"entries": [
            {"src": "/x/倪海厦书籍/A书.pdf", "out": "A书.md", "ext": ".pdf",
             "status": "ok", "chars": 9000, "note": "pdf·文字层"},
            {"src": "/x/倪海厦书籍/B书.pdf", "out": None, "ext": ".pdf",
             "status": "skipped", "chars": 0, "note": "扫描版·无文字层（300 页），需 OCR"},
            {"src": "/x/倪海厦书籍/C书.docx", "out": "C书.md", "ext": ".docx",
             "status": "thin", "chars": 54, "note": "正文仅 54 字"},
            {"src": "/x/别的目录/D书.pdf", "out": "D书.md", "ext": ".pdf",
             "status": "ok", "chars": 9000, "note": ""},
        ]}, open(os.path.join(根, "_index.json"), "w", encoding="utf-8"),
            ensure_ascii=False)
        报 = 建(根, os.path.join(根, "库"), 类们=("倪海厦书籍",), 册目录="/nonexistent")
        查x("端到端·只收指定类（三类）", 报["total"] == 3)
        查x("端到端·不算别类的书", all(c["书名"] != "D书" for c in 报["cards"]))
        查x("端到端·分档统计对",
           (报["counts"].get("可逐字引"), 报["counts"].get("仅指认"),
            报["counts"].get("近空")) == (1, 1, 1))
        查x("端到端·卡片带编号", all(c["id"].startswith("Q") for c in 报["cards"]))
        查x("端到端·扫描件页数进卡", any(c["页数"] == 300 for c in 报["cards"]))
        查x("端到端·索引文件都写了",
           os.path.exists(os.path.join(根, "库", "索引.json"))
           and os.path.exists(os.path.join(根, "库", "索引.md")))
        查x("端到端·md 里写明了引用纪律",
           "不许出现引号内的原文" in open(os.path.join(根, "库", "索引.md"),
                                     encoding="utf-8").read())
        查x("端到端·查得到", len(查(os.path.join(根, "库", "索引.json"), "A书")) == 1)
        查x("端到端·卡片记了所属类", all(c.get("类") == "倪海厦书籍" for c in 报["cards"]))
        查x("端到端·按类统计有数", 报["by_category"].get("倪海厦书籍", {}).get("可逐字引") == 1)
        查x("端到端·编号四位起（防过千溢出）", 报["cards"][0]["id"] == "Q0001")

        # 不给类 = 全库都收
        报2 = 建(根, os.path.join(根, "库2"), 册目录="/nonexistent")
        查x("全库·不给类则四份全收", 报2["total"] == 4)
        查x("全库·别类的书也进来了", any(c["书名"] == "D书" for c in 报2["cards"]))
        查x("全库·类字段按目录分", {c["类"] for c in 报2["cards"]} == {"倪海厦书籍", "别的目录"})

        # 只收两类
        报3 = 建(根, os.path.join(根, "库3"), 类们=("倪海厦书籍", "别的目录"),
            册目录="/nonexistent")
        查x("多类·两类都收", 报3["total"] == 4)
        报4 = 建(根, os.path.join(根, "库4"), 类们=("不存在的类",), 册目录="/nonexistent")
        查x("多类·类名对不上则空", 报4["total"] == 0)
        查x("多类·空表不炸", 报4["counts"] == {})
    finally:
        shutil.rmtree(根, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def 主():
    参 = sys.argv[1:]
    if not 参:
        print(__doc__)
        return 1
    if 参[0] == "--selftest":
        return 自检()
    命 = 参[0]
    位 = [a for a in 参[1:] if not a.startswith("--")]
    if 命 == "建":
        if not 位:
            print("用法：python3 quote_index.py 建 <采集目录> [--类 X] [--out 目录]")
            return 2
        根 = 位[0]
        取舍 = 参[参.index("--取舍") + 1] if "--取舍" in 参 else None
        类 = None
        if "--类" in 参:
            类 = tuple(x for x in 参[参.index("--类") + 1].split(",") if x)
        出 = 参[参.index("--out") + 1] if "--out" in 参 else os.path.join(根, "引证库")
        报 = 建(根, 出, 类, 取舍路=取舍)
        print("== 引证库索引 ==")
        print("  %d 种：%s" % (报["total"],
                            "；".join("%s %d" % (k, v) for k, v in sorted(报["counts"].items()))))
        for k, v in sorted(报["by_category"].items()):
            print("    %-24s %4d 种（可逐字引 %d）" % (k[:24], sum(v.values()), v.get("可逐字引", 0)))
        print("  已写 %s" % os.path.join(出, "索引.json"))
        return 0
    if 命 == "白名单":
        出 = 参[参.index("--out") + 1] if "--out" in 参 else \
            os.path.join(位[0] if 位 else ".", "书目白名单.json")
        册们 = []
        if "--册" in 参:
            册们 = [x for x in 参[参.index("--册") + 1].split(",") if x]
        索 = 参[参.index("--索引") + 1] if "--索引" in 参 else None
        报 = 建白名单(出, 册们, 索)
        print("== 书目白名单 ==")
        print("  %d 条：%s" % (报["条数"],
                            "；".join("%s %d" % (k, v) for k, v in sorted(报["分类"].items()))))
        print("  已写 %s" % 出)
        return 0
    if 命 == "查":
        for c in 查(位[0], 位[1]):
            print("%s  %-40s [%s]  %s" % (c["id"], c["书名"][:40], c["可引"], c["理由"][:50]))
        return 0
    if 命 == "统计":
        报 = json.load(open(位[0], encoding="utf-8"))
        print("共 %d 种" % 报["total"])
        for k, v in sorted(报["counts"].items()):
            print("  %-6s %d" % (k, v))
        print("  册页已引 %d 种" % sum(1 for c in 报["cards"] if c.get("册页已引")))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(主() or 0)
