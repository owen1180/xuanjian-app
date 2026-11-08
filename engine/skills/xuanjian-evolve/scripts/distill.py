#!/usr/bin/env python3
"""提炼辅助 —— 把「读原文」到「写成册页」之间最费手的那一段变成提案。

用法：
    python3 distill.py 提炼 <原文.md|txt ...> --out 目录 [--min-score 2]
    python3 distill.py 对撞 <断言.json> [--out 目录]
    python3 distill.py 合并 <主池.json> <新批.json> --out 目录 [--只收 规程] [--只收判 CONFLICT,REVIEW]
    python3 distill.py 摘要 <断言.json>
    python3 distill.py --selftest

**为什么要有这个脚本**：摄取器只把原文取回来，提炼全靠人抄——65 份已读、107 份
未读，卡点不在「读不懂」，在「一条条摘、一条条对旧册有没有、有没有跟旧册打架」。
这一段是机械劳动，机器能做完，人只做裁决。

**它不做判断**。脚本只输出三类候选：
  NEW      库里查不到相近说法 → 可能是新知识，需人核定
  KNOWN    库里已有高度相近的说法 → 不必重写，记下对应册页即可
  CONFLICT 同术语出现不同数值，或与既有禁令相反 → **必须人看**，不许自动采用

**定位必须逐字可查**：每条候选都带 `文件#L行号` 与原句原文，供 `verify_quotes.py`
反查。抽不出定位的句子不进候选。术数的内容判断不交给脚本——这是本馆的硬规矩，
本脚本只把「抄」和「比」做掉，把「断」留给人。
"""
import json
import os
import re
import sys

册目录 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "xuanjian-kb", "references")

# 术语白名单：只认本馆确实在用的概念，避免把口语当术语抽出来
干支 = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
十神 = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]
关系 = ["六冲", "六合", "三合", "半三合", "三会", "相刑", "相害", "暗合", "伏吟", "反吟",
        "盖头", "截脚", "争合", "夺合", "合化", "拱合", "克合", "生合"]
概念 = ["月令", "大运", "流年", "原局", "用神", "忌神", "调候", "扶抑", "通关", "格局",
        "假从", "真从", "专旺", "两气成象", "寿元星", "夫妻宫", "婚姻宫", "父母宫",
        "空亡", "神煞", "藏干", "本气", "中气", "余气", "实透", "虚透", "得令",
        "身强", "身弱", "偏强", "偏弱", "太旺", "太弱", "中和", "临界值", "财库",
        "食神制杀", "伤官见官", "木火通明", "土多金埋", "金寒水冷", "阴阳转化"]

术语表 = set(十神) | set(关系) | set(概念)
术语表 |= {g + "木" for g in "甲乙"} | {g + "火" for g in "丙丁"} | \
         {g + "土" for g in "戊己"} | {g + "金" for g in "庚辛"} | {g + "水" for g in "壬癸"}
术语表 |= {"%s%s" % (a, b) for a in 干支 for b in 干支}  # 干支组合（丙午、子辰等）

数词式 = re.compile(r"(\d+(?:\.\d+)?|[一二两三四五六七八九十百千零]{1,7})\s*(分|年|岁|字|天|个月|重|个)")
中文数 = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
位权 = {"十": 10, "百": 100, "千": 1000}


def 转数(s):
    """中文数词转阿拉伯：六十→60，四十五→45，一百二十→120；纯数字原样返回。"""
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    总, 当前 = 0, 0
    for 字 in s:
        if 字 in 中文数:
            当前 = 中文数[字]
        elif 字 in 位权:
            总 += (当前 or 1) * 位权[字]
            当前 = 0
        else:
            return None
    return float(总 + 当前)


def 数词们(句):
    """[(归一化数值字符串, 单位)]，中文与阿拉伯统一成同一口径，供跨句比对。"""
    出 = []
    for 原, 单 in 数词式.findall(句):
        v = 转数(原)
        if v is None:
            continue
        出.append(("%g" % v, 单))
    return 出
断句式 = re.compile(r"[。！？；\n]+")
# 断言特征：下定义 / 表判断 / 给条件 / 立边界
谓语式 = re.compile(
    r"(是|就是|代表|指的是|属于|算作|称为|叫做|等于|意味着|"
    r"必须|不能|不要|不许|禁止|忌|怕|宜|应该|"
    r"如果|若是|只有|一旦|则|才会|就会|容易|很难|不会)")
判档单位 = {"分"}   # 打分口径：只有这一类数值不一致才算真冲突
禁令式 = re.compile(r"(不能|不要|不许|禁止|不可|切忌|不主张|不必|不予)")
条件式 = re.compile(r"(如果|若是|只有|一旦|…则|则|前提|条件)")


def 归一(s):
    """比对用：去空白与标点，只留字与数字。"""
    return re.sub(r"[^\u4e00-\u9fff0-9.]", "", s or "")


def 双字组(s):
    """比对片段：2-gram。中文改写常在字序上变，用 2-gram 比 3-gram 宽容一档。"""
    t = 归一(s)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else ({t} if t else set())


def 术语(句):
    """命中的术语，按长度降序（长词优先，丙午不被 丙 覆盖）。"""
    return sorted({t for t in 术语表 if t in 句}, key=lambda x: (-len(x), x))


def 指纹(文本):
    """提案的内容指纹：归一后取 md5 前 8 位。

    为什么要它：`ruling.py` 原用 `enumerate` 生成 `D%03d`，那是**位置号**。
    提案表一变（过滤掉一条问句、或某条对撞结果从 NEW 变 KNOWN），后面所有编号
    前移一位，已裁的 51 条就会静默指向别的提案——**裁过的东西错位，且无法察觉**。
    指纹跟内容绑定，不跟位置绑定：内容在，编号就在。
    """
    import hashlib
    return hashlib.md5(归一(文本).encode("utf-8")).hexdigest()[:8]


_问句尾 = re.compile(r"[？?]\s*$")
_疑问 = re.compile(r"(是否|能不能|会不会|要不要|多少|怎么样|为什么|是什么|对不对|好不好|行不行|可不可以)")


def 是问句(文本):
    """这一句是不是提问。课堂口语大量是问答，问句抽成「规程」是错的。

    判据从宽：句末问号，或句末 10 字内出现疑问词。只判末尾，是因为句中带
    「是否」的陈述句（「无论是否成格，都要先看月令」）是真规程，不该误杀。
    """
    s = (文本 or "").strip()
    if not s:
        return False
    if _问句尾.search(s):
        return True
    return bool(_疑问.search(s[-10:]))


def 切句(文本):
    return [s.strip() for s in 断句式.split(文本)]


def 抽断言(路径, 最低分=2):
    """从一份原文抽候选断言，每条带文件+行号逐字定位。"""
    出 = []
    try:
        行们 = open(路径, encoding="utf-8", errors="replace").read().splitlines()
    except OSError as e:
        return [{"error": str(e), "file": 路径}]
    for 号, 行 in enumerate(行们, 1):
        for 句 in 切句(行):
            净 = 句.strip(" -*>*#\t")
            if len(净) < 12 or len(净) > 220:
                continue
            术 = 术语(净)
            if not 术:
                continue
            数 = 数词们(净)
            分 = 0
            分 += min(len(术), 2)
            分 += 1 if 谓语式.search(净) else 0
            分 += 1 if 数 else 0
            分 += 1 if 禁令式.search(净) else 0
            分 += 1 if ("答：" in 净 or "总结：" in 净) else 0
            if 分 < 最低分:
                continue
            类 = "边界" if 禁令式.search(净) else ("数值" if 数 else "判断")
            出.append({
                "text": 净,
                "fp": 指纹(净),
                "terms": 术,
                "numbers": ["%s%s" % (a, b) for a, b in 数],
                "type": 类,
                "locator": "%s#L%d" % (os.path.basename(路径), 号),
                "file": 路径,
                "line": 号,
                "score": 分,
            })
    return 出


def 读册库(目录=None):
    """{(册名, 行号): 句子} —— 逐句建索引。"""
    目录 = 目录 or 册目录
    库 = []
    if not os.path.isdir(目录):
        return 库
    for 名 in sorted(os.listdir(目录)):
        if not 名.endswith(".md"):
            continue
        p = os.path.join(目录, 名)
        try:
            行们 = open(p, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for 号, 行 in enumerate(行们, 1):
            for 句 in 切句(行):
                净 = 句.strip(" -*>*#|\t")
                if len(净) >= 8:
                    库.append({"book": 名, "line": 号, "text": 净,
                               "terms": set(术语(净)), "grams": 双字组(净)})
    return 库


def 对撞(断言, 库):
    """给一条断言判 NEW / KNOWN / CONFLICT，并给最相近的册页位置。

    相似度用**包含度**（共享片段 / 本句片段）而非 Jaccard：库里的句子往往比
    课程口语长得多，Jaccard 会被长短差吃掉，导致明明讲过也判成新知识。
    """
    术 = set(断言["terms"])
    候选 = [句 for 句 in 库 if 术 & 句["terms"]]
    最佳, 最高 = None, 0.0
    g = 双字组(断言["text"])
    for 句 in 候选:
        if not g or not 句["grams"]:
            continue
        相似 = len(g & 句["grams"]) / len(g)
        # 共享术语越多，权重越高：同术语的近似句才可信
        相似 = 相似 * (1 + 0.15 * (len(术 & 句["terms"]) - 1))
        if 相似 > 最高:
            最高, 最佳 = min(相似, 1.0), 句
    判 = "NEW" if 最高 < 0.30 else ("KNOWN" if 最高 >= 0.60 else "REVIEW")
    理由 = "库中无相近说法" if 判 == "NEW" else "库中有相近说法（包含度 %.2f）" % 最高
    # 数值冲突：同术语、同单位、不同数字
    if 最佳 is not None and 断言.get("numbers"):
        自数 = set(数词们(断言["text"]))
        库数 = set(数词们(最佳["text"]))
        共单 = {u for _, u in 自数} & {u for _, u in 库数}
        自数 = {(v, u) for v, u in 自数 if u in 共单}
        库数 = {(v, u) for v, u in 库数 if u in 共单}
        if 库数 and 自数 and not (自数 & 库数):
            # 只有「分」是判档口径，数值不一致才是真冲突。
            # 年／岁／个是具体个案的年头与个数，两句话讲的根本不是同一件事，
            # 拿它判冲突只会制造噪音（首轮跑出四条全是这类误报）。
            if any(u in 判档单位 for _, u in 自数):
                判 = "CONFLICT"
                理由 = "判档分数不一致：本句 %s ／ 库中 %s" % (
                    "、".join("%s%s" % x for x in sorted(自数)),
                    "、".join("%s%s" % x for x in sorted(库数)))
            else:
                判 = "REVIEW" if 判 != "NEW" else 判
                理由 += "；数值与库中例句不同（%s），可能是个案细节而非口径冲突" % (
                    "、".join("%s%s" % x for x in sorted(自数)))
    判 = 判.strip()
    # 禁令相反：本句立禁令，库中同术语句作肯定断言
    if 判 == "KNOWN" and 禁令式.search(断言["text"]) and 最佳 is not None and not 禁令式.search(最佳["text"]):
        判 = "CONFLICT"
        理由 = "本句立禁令，库中同术语句为肯定表述，需人裁定哪一条为准"
    return {
        "verdict": 判,
        "similarity": round(最高, 3),
        "reason": 理由,
        "match": {"book": 最佳["book"], "line": 最佳["line"], "text": 最佳["text"]} if 最佳 else None,
    }


_案例标记 = re.compile(r"(答：|分析：|他说|这个八字|她是|他是|客户|我曾经|我当时)")
_判据词 = re.compile(r"(要|须|必须|不能|不可|若|如果|因为|所以|一定|千万|别|凡|一律|才是|就不)")
_年份 = re.compile(r"(19|20)\d{2}\s*年")


def 可入库(文本):
    """判断这条候选**值不值得落册**，与「库中有没有」是两件事。

    `对撞`判的是字面相似度：这条在库里找不找得到相近说法。找不到就判 NEW。
    但 NEW ≠ 该入库——226 条提案里 179 条 NEW，数字看着像大丰收，逐条看下去
    大半是课堂口语碎片（「答：戊申，己酉大运不能改变…」），脱离上下文没有价值。
    判新归相似度，判值不值归这里。2026-11-05 逐条裁了 22 条才看清这一点。
    """
    s = (文本 or "").strip()
    n = len(归一(s))
    if n < 14:
        return "碎片", "太短，多为旁注或承接语"
    if _年份.search(s) or _案例标记.search(s):
        return "案例", "含具体年份或口语标记，属个案不属规程"
    if not _判据词.search(s):
        return "碎片", "无判据词，是陈述不是规程"
    if n > 140:
        return "长段", "过长，须人工摘句再入库"
    return "规程", ""


def 提炼(路径们, 输出目录, 最低分=2):
    os.makedirs(输出目录, exist_ok=True)
    库 = 读册库()
    全部, 错误, 跳过 = [], [], []
    for p in 路径们:
        断言们 = 抽断言(p, 最低分)
        for a in 断言们:
            if "error" in a:
                错误.append(a)
                continue
            if 是问句(a.get("text", "")):
                跳过.append(a)
                continue
            a.update(对撞(a, 库))
            a["admission"], a["admission_why"] = 可入库(a.get("text", ""))
            全部.append(a)
    计 = {}
    for a in 全部:
        计[a["verdict"]] = 计.get(a["verdict"], 0) + 1
    入 = {}
    for a in 全部:
        入[a["admission"]] = 入.get(a["admission"], 0) + 1
    报 = {
        "artifact": "提炼候选（脚本只提案，裁决归人）",
        "kb_dir": 册目录,
        "kb_sentences": len(库),
        "sources": [os.path.basename(p) for p in 路径们],
        "counts": 计,
        "admission": 入,
        "skipped_questions": len(跳过),
        "skipped_samples": [a.get("text", "")[:40] for a in 跳过[:3]],
        "assertions": 全部,
        "errors": 错误,
        "rule": "CONFLICT 一条都不许自动采用；NEW 需人核定后才可落册；"
                "KNOWN 只是省去重写，不代表已掌握。admission 另判「值不值得入库」："
                "规程级才可直接进裁决，案例／碎片／长段须先摘句。",
    }
    j = os.path.join(输出目录, "distill.json")
    open(j, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=2))

    md = ["# 提炼候选 —— %s" % "、".join(报["sources"]), "",
          "> 脚本只提案：NEW %d ／ REVIEW %d ／ KNOWN %d ／ CONFLICT %d。裁决由人做。" % (
              计.get("NEW", 0), 计.get("REVIEW", 0), 计.get("KNOWN", 0), 计.get("CONFLICT", 0)),
          ""]
    for 类, 题 in [("CONFLICT", "一、必须人裁（数值／禁令相反）"),
                   ("NEW", "二、库中未见（新知识候选）"),
                   ("REVIEW", "三、疑似改写（需确认是否同一件事）"),
                   ("KNOWN", "四、库中已有（省去重写）")]:
        组 = [a for a in 全部 if a["verdict"] == 类]
        if not 组:
            continue
        md += ["## " + 题, ""]
        for a in 组[:40]:
            位 = a["match"]["book"] if a["match"] else "—"
            md += ["- **%s**〔%s〕%s" % (a["text"], a["type"], a["locator"]),
                   "  - 术语：%s｜判定：%s（%s）" % ("、".join(a["terms"][:6]), a["verdict"], a["reason"]),
                   "  - 已见：%s" % 位]
        if len(组) > 40:
            md += ["", "（其余 %d 条见 distill.json）" % (len(组) - 40)]
        md += [""]
    open(os.path.join(输出目录, "distill.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    return 报, j


def 合并(主池路, 新批路, 输出目录, 只收=None, 只收判=None):
    """把新一批提炼并进主提案池。**按内容指纹去重，主池原样不动**。

    为什么要这个命令：批次分开跑是必然的（这一次 594 份、下一次另一批），
    但提案池只能有一个——`ruling.py` 的台账是靠指纹挂靠的，两池就会两套账。

    两条规矩：
    1. **去重按 `fp`**。同一句话在两个文件里出现，只立一条提案，定位取先到的那处。
    2. **`只收`／`只收判` 只作用于新批，不碰主池**。因为主池里已有裁决，
       滤掉就等于让台账指向不存在的提案。新批被挡下的条数会写进 `filtered_out`——
       **挡下不是丢弃，是「不立提案」，要报数**。

    `只收判` 为什么要单独一个参数：`只收 规程` 实测量级仍有 4,765 条，其中
    NEW 占 4,283——那不是「待裁的规程」，是「同一批概念换个说法又说了一遍」
    （抽查「新术语」全是午亥、庚乙这类干支组合，真概念一个没有）。
    把四位数塞进台账，就是再造一批裁不完的烂尾，所以按判决分层：
    CONFLICT（与册页相反，必须裁）、REVIEW（疑似改写，需确认），NEW 先不入队。
    """
    主 = json.load(open(主池路, encoding="utf-8"))
    新 = json.load(open(新批路, encoding="utf-8"))

    池 = {}
    for a in 主.get("assertions", []):
        a.setdefault("fp", 指纹(a.get("text", "")))
        池[a["fp"]] = a
    主数 = len(池)

    挡下 = 0
    并入 = 0
    for a in 新.get("assertions", []):
        a.setdefault("fp", 指纹(a.get("text", "")))
        if 只收 and a.get("admission") not in 只收:
            挡下 += 1
            continue
        if 只收判 and a.get("verdict") not in 只收判:
            挡下 += 1
            continue
        if a["fp"] in 池:
            # 同一句已有一条：只补一处定位，不立第二条
            旧 = 池[a["fp"]]
            旧.setdefault("also_at", [])
            位 = a.get("locator")
            if 位 and 位 not in 旧["also_at"] and 位 != 旧.get("locator"):
                旧["also_at"].append(位)
            continue
        池[a["fp"]] = a
        并入 += 1

    条 = list(池.values())
    计, 入 = {}, {}
    for a in 条:
        计[a.get("verdict", "?")] = 计.get(a.get("verdict", "?"), 0) + 1
        入[a.get("admission", "?")] = 入.get(a.get("admission", "?"), 0) + 1

    os.makedirs(输出目录, exist_ok=True)
    报 = dict(主)
    报.update({
        "sources": sorted(set(主.get("sources", [])) | set(新.get("sources", []))),
        "counts": 计,
        "admission": 入,
        "merged_from": [os.path.basename(主池路), os.path.basename(新批路)],
        "filtered_out": 挡下,
        "added": 并入,
        "assertions": 条,
        "rule": 主.get("rule", ""),
    })
    j = os.path.join(输出目录, "distill.json")
    json.dump(报, open(j, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {"主池原有": 主数, "新批并入": 并入, "新批挡下": 挡下, "合并后": len(条)}, j


# ── 筛「规程×NEW」（v1.68.0）─────────────────────────────────────────
# 为什么要有这一步：上一轮把 4,283 条「规程×NEW」整批挡在池外，
# 理由是「抽查新术语全是午亥／庚乙这类干支组合，一个真概念都没有」。
# **这个理由站不住**：看的是 `terms` 字段（抽出来的关键词本来就是干支），
# 不是 `text`。翻回原句，大量是真规程——
#   「大运可以影响八字，不能影响流年」
#   「专旺必须是全局没有一个泄耗」
#   「如果是调候用神，但是是伏抑忌神，就是平运，不好不坏」
# 判定内容的活儿拿元数据当依据，是**错量**的一种：不报错，只把整批真东西丢掉。
#
# 所以这里不再问「要不要」，只做**分层**：一条一句，按四件可数的事打分。
# 「个案」不只靠第二人称。老师给客户断盘时用第三人称："她不太听长辈的话""这个原局
# 就用财""反馈：水年好点"。这些是**判语**不是**规程**——长度、语气都像规矩，
# 拿它们入册等于把一个人的盘当成所有人的律。
个案词 = re.compile(r"你|您|问的是|我看|我觉得|我认为|我讲|我们|咱们|"
                   r"她|他(?!们)|这个八字|这个原局|这个案例|这个盘|反馈|"
                   r"这个男|这个女|比如说这个|像这个")
规则词 = re.compile(r"必须|不能|不可|只要|才(?:能|算|是|会)|就(?:会|是|不)|代表|说明|定义|凡|皆|一律|一定")
具体词 = re.compile(r"\d{4}\s*年|\d+\s*分|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*[年月]|先生|女士|这个人的")
问尾词 = re.compile(r"[？?]\s*$|(?:吧|吗)[。？?]?\s*$")
# 域内闸：这批语料是整本网盘文档，混着中医、曾仕强、人文故事。
# 只靠语气词打分会把「和猪八戒沙和尚一起合作」「乌梅先泡醋泡一晚」顶到 7 分，
# 所以先过一道「有没有命理术语」，域外的不参与排序，单列计数。
命理词 = re.compile(r"正财|偏财|正官|七杀|正印|偏印|食神|伤官|比肩|劫财|日主|日元|"
                   r"月令|日支|年柱|月柱|时柱|大运|流年|格局|从格|专旺|假从|化格|"
                   r"旺衰|身强|身弱|中和|用神|忌神|喜神|引动|空亡|墓库|通根|透干|藏干|"
                   r"本气|中气|余气|神煞|寿元|食伤|官杀|印星|财星|比劫|调候|十神|"
                   r"地支|天干|八字|命盘|原局|四柱")
# 杂类词：这批语料里混着整本中医书与人文讲稿。它们偶尔会带一个命理词
# （"这个八字""大运"），只靠「有没有命理词」仍会漏进来。
# 规则：**名著人物一票否决**（讲《西游记》的段落不因为提到「八字」就成了命理规程）；
# 中医词只在命理词 ≤1 个时才判域外（经方里偶尔会借「五行」说事，不能一刀切）。
名著词 = re.compile(r"猪八戒|孙悟空|唐僧|红楼梦|贾宝玉|三国演义|水浒|西游记|沙和尚")
中医词 = re.compile(r"脉|处方|汤剂|汤药|针灸|艾灸|穴位|经络|脏腑|附子|桂枝|白芍|甘草")


def 规程分(文本):
    """0–7 分。给出 (分, 依据)。**分低不等于废**，只代表「先不看」。"""
    文 = (文本 or "").strip()
    据, 分 = [], 0
    # 长度分三档：≥24 字通常带条件与限定；16–23 是「一句能说完的规矩」；
    # ＜16 多是半截话（"但是如果甲子日那一天，天"这种）。
    if len(文) >= 24:
        分 += 2
        据.append("长句")
    elif len(文) >= 16:
        分 += 1
        据.append("中句")
    else:
        据.append("短句")
    if 规则词.search(文):
        分 += 2
        据.append("规则语气")
    if not 个案词.search(文):
        分 += 1
        据.append("无第二人称")
    else:
        据.append("含第二人称")
    if not 具体词.search(文):
        分 += 1
        据.append("无具体年份分数")
    else:
        据.append("含具体年份分数")
    if not 问尾词.search(文):
        分 += 1
        据.append("非问句")
    else:
        据.append("问句")
    # 短句封顶：＜16 字的多是半截话（"不能从""如果是假从"），语气词再全也成不了规程。
    # 不封顶的话它们会靠「无第二人称＋非问句」蹭到 5 分，混进「中」层。
    if len(文) < 16 and 分 > 4:
        分 = 4
        据.append("短句封顶")
    return 分, 据


def 筛规程(d, 首批=100):
    """把「规程×NEW」分层，并给出首批待裁清单。返回结构化结果。"""
    子 = [x for x in d.get("assertions", [])
         if x.get("verdict") == "NEW" and x.get("admission") == "规程"]
    # 同句可能来自不同文件（讲稿与笔记互抄），fp 相同；不去重，首批里会出现两条一样的
    见, 去重 = set(), []
    for x in 子:
        k = x.get("fp") or (x.get("text") or "")
        if k in 见:
            continue
        见.add(k)
        去重.append(x)
    重复 = len(子) - len(去重)
    子 = 去重
    for x in 子:
        分, 据 = 规程分(x.get("text"))
        x["筛分"] = 分
        x["筛据"] = 据
        文 = x.get("text") or ""
        命 = len(命理词.findall(文))
        if 名著词.search(文):
            域内 = False                      # 讲小说人物的段落，一律不算规程
        else:
            域内 = 命 >= 2 or (命 >= 1 and not 中医词.search(文))
        x["域内"] = 域内
    域内们 = [x for x in 子 if x["域内"]]
    域外 = [x for x in 子 if not x["域内"]]
    层 = {"高": [x for x in 域内们 if x["筛分"] >= 6],
         "中": [x for x in 域内们 if x["筛分"] == 5],
         "低": [x for x in 域内们 if x["筛分"] <= 4]}
    # 同分时先看长的：长句通常带条件与限定，短句多是半截话
    排 = sorted(域内们, key=lambda x: (-x["筛分"], -len(x["text"])))
    return {"总数": len(子), "重复": 重复, "域内": len(域内们), "域外": len(域外),
            "分层": {k: len(v) for k, v in 层.items()},
            "首批": 排[:首批], "全部": 子}


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("术语识别长词优先", 术语("食神制杀，不宜再取七杀")[0] == "食神制杀")
    查("术语识别干支组合", {"丙午", "子辰"} <= set(术语("丙午日主，子辰克合")))
    查("可入库·规程级", 可入库("假从盘若走印运把日元扶起，必须降为偏弱，用神随之转忌")[0] == "规程")
    查("可入库·个案级", 可入库("2019 年她离婚了，那年正是官杀流年，必须留意")[0] == "案例")
    查("可入库·含年份判案例", 可入库("2016年与2017年都是用神流年，那两年顺利")[0] == "案例")
    查("可入库·碎片级", 可入库("答：是的")[0] == "碎片")
    查("可入库·长段", 可入库("必须" + "很长的说明文字" * 30)[0] == "长段")
    查("短句被过滤", all(len(a["text"]) >= 12 for a in 抽断言(_夹具())))
    查("定位带行号", all("#L" in a["locator"] for a in 抽断言(_夹具())))
    查("数值断言被抽出", any(a["type"] == "数值" for a in 抽断言(_夹具())))
    查("禁令断言被抽出", any(a["type"] == "边界" for a in 抽断言(_夹具())))
    查("无术语不抽", not any("今天天气" in a["text"] for a in 抽断言(_夹具())))

    库 = [{"book": "x.md", "line": 3, "text": "庚金至少要有六十分才能算有根",
          "terms": {"庚金", "有根"}, "grams": 双字组("庚金至少要有六十分才能算有根")}]
    同 = {"text": "庚金至少要有六十分才能算有根", "terms": ["庚金", "有根"],
          "numbers": ["60分"], "type": "数值"}
    查("同句判 KNOWN", 对撞(同, 库)["verdict"] == "KNOWN")
    异 = {"text": "庚金至少要有七十分才能算有根", "terms": ["庚金", "有根"],
          "numbers": ["70分"], "type": "数值"}
    查("同术语异数值判 CONFLICT", 对撞(异, 库)["verdict"] == "CONFLICT")
    新 = {"text": "暗合的地支关系级别在三会三合六冲六合刑害之后", "terms": ["暗合"],
          "numbers": [], "type": "判断"}
    查("库中无判 NEW", 对撞(新, 库)["verdict"] == "NEW")
    反 = {"text": "大运藏怕透，财星透出容易出问题", "terms": ["大运", "财星"],
          "numbers": [], "type": "边界"}
    禁库 = [{"book": "y.md", "line": 9, "text": "大运藏怕透，财星透出容易出问题",
            "terms": {"大运", "财星"}, "grams": 双字组("大运藏怕透财星透出容易出问题")}]
    查("同句不误判冲突", 对撞(反, 禁库)["verdict"] == "KNOWN")

    # ── 合并：按指纹去重、只收只作用新批、挡下要报数 ────────────────────
    import tempfile
    根 = tempfile.mkdtemp(prefix="distill-")

    def 存(名, 条们):
        路 = os.path.join(根, 名)
        json.dump({"sources": [名], "assertions": 条们, "counts": {},
                   "rule": "r"}, open(路, "w", encoding="utf-8"), ensure_ascii=False)
        return 路

    def 条(文, 判="NEW", 入="规程", 位="a.md#L1"):
        return {"text": 文, "fp": 指纹(文), "verdict": 判, "admission": 入, "locator": 位}

    主 = 存("主.json", [条("甲句讲的是月令得令取大", 位="主.md#L1"),
                       条("乙句是一段碎话", 入="碎片")])
    新 = 存("新.json", [条("甲句讲的是月令得令取大", 位="新.md#L9"),
                       条("丙句是新的规程，必须写下来"),
                       条("丁句也是碎话", 入="碎片")])
    结, _ = 合并(主, 新, os.path.join(根, "并"))
    查("合并·主池原有 2", 结["主池原有"] == 2)
    查("合并·同句不重复立（新批 3 条里 1 条重，并入 2）", 结["新批并入"] == 2)
    查("合并·合并后 4 条", 结["合并后"] == 4)
    查("合并·不加只收时一条不挡", 结["新批挡下"] == 0)

    结2, j2 = 合并(主, 新, os.path.join(根, "并2"), 只收=("规程",))
    合 = json.load(open(j2, encoding="utf-8"))
    查("合并·只收不影响主池的碎片（主池原样保留）",
       any(a.get("admission") == "碎片" for a in 合["assertions"]))
    查("合并·新批碎片被挡下", 结2["新批挡下"] == 1 and 结2["新批并入"] == 1)
    查("合并·挡下数写进产物（可复核，不是悄悄丢）", 合.get("filtered_out") == 1)

    旧条 = next(a for a in 合["assertions"] if a["text"].startswith("甲句"))
    查("合并·同句补记第二处定位", "新.md#L9" in 旧条.get("also_at", []))
    查("合并·原定位不变（仍指主池那处）", 旧条["locator"] == "主.md#L1")
    查("合并·计数重算", 合["counts"].get("NEW", 0) >= 2)
    查("合并·记下来源两池", len(合.get("merged_from", [])) == 2)

    结3, j3 = 合并(主, 新, os.path.join(根, "并3"), 只收=("规程",),
                  只收判=("CONFLICT",))
    合3 = json.load(open(j3, encoding="utf-8"))
    查("合并·按判决筛：NEW 不进池", not any(a["text"].startswith("丙句")
                                        and a["verdict"] == "NEW"
                                        for a in 合3["assertions"] if a.get("admission") == "规程"))
    查("合并·按判决筛会把 NEW 挡下并报数", 结3["新批挡下"] >= 1)

    # ── 筛「规程×NEW」：这一组是本轮新增判据，错了会静默把真规程丢掉 ──
    好 = "如果是调候用神，但是是伏抑忌神，就是平运，不好不坏，这一点要记住"
    查("规程分·完整规则句 7 分", 规程分(好)[0] == 7)
    查("规程分·含第二人称扣 1", 规程分(好.replace("这一点", "你这一块"))[0] == 6)
    查("规程分·含年份扣 1", 规程分("1987年那条大运里，必须是先破后立，否则不作数")[0] == 6)
    查("规程分·问句扣 1", 规程分(好 + "吗？")[0] == 6)
    查("规程分·短句不封顶", 规程分("不能从")[0] <= 4)
    查("规程分·无规则语气不满分", 规程分("这是一段没有任何判断词的普通叙述文字而已呀")[0] < 7)
    查("规程分·依据条数固定 5", len(规程分(好)[1]) == 5)

    造 = {"assertions": [
        {"text": 好, "fp": "a1", "verdict": "NEW", "admission": "规程", "locator": "x.md#L1"},
        {"text": 好, "fp": "a1", "verdict": "NEW", "admission": "规程", "locator": "y.md#L2"},
        {"text": "猪八戒和沙和尚一路护送唐僧，这段讲的是团队里的角色分工与忍耐",
         "fp": "b1", "verdict": "NEW", "admission": "规程", "locator": "z.md#L3"},
        {"text": "随便一句无关的话", "fp": "c1", "verdict": "KNOWN", "admission": "规程",
         "locator": "q.md#L4"},
    ]}
    结筛 = 筛规程(造, 首批=10)
    查("筛规程·同 fp 只留一条", 结筛["总数"] == 2)
    查("筛规程·报出重复条数", 结筛["重复"] == 1)
    查("筛规程·名著人物判域外", 结筛["域外"] == 1)
    查("筛规程·只收 NEW×规程", 结筛["域内"] == 1)
    查("筛规程·分层之和等于域内",
       sum(结筛["分层"].values()) == 结筛["域内"])
    查("筛规程·首批不超过要的数", len(筛规程(造, 首批=1)["首批"]) == 1)
    查("筛规程·首批带上分数与依据", all("筛分" in x and "筛据" in x for x in 结筛["首批"]))

    import shutil
    shutil.rmtree(根, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def _夹具():
    p = "/tmp/distill-fixture.md"
    open(p, "w", encoding="utf-8").write(
        "# 夹具\n\n"
        "庚金至少要有六十分才能算有根，低于六十分即为无根。\n"
        "不要在没有根气的时候判假从，这是最容易错的地方。\n"
        "今天天气不错，适合出门走走，与命理无关。\n"
        "寿元星在原局不现，大运出现即引动。\n")
    return p


def main():
    参 = sys.argv[1:]
    if not 参 or 参[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if 参[0] == "--selftest":
        return 自检()
    命 = 参[0]
    if 命 == "提炼":
        路, 出, 分 = [], None, 2
        i = 1
        while i < len(参):
            if 参[i] == "--out":
                出 = 参[i + 1]
                i += 2
            elif 参[i] == "--min-score":
                分 = int(参[i + 1])
                i += 2
            else:
                路.append(参[i])
                i += 1
        if not 路 or not 出:
            print("用法：python3 distill.py 提炼 <原文...> --out 目录")
            return 2
        报, j = 提炼(路, 出, 分)
        print("== 提炼候选 ==")
        print("原文：%s" % "、".join(报["sources"]))
        print("册库句数：%d" % 报["kb_sentences"])
        for k in ("NEW", "REVIEW", "KNOWN", "CONFLICT"):
            print("  %-9s %d" % (k, 报["counts"].get(k, 0)))
        print("写出：%s" % j)
        print("裁决提醒：CONFLICT 必须人看，不许自动采用。")
        return 0
    if 命 == "合并":
        参2 = 参[1:]
        位 = [a for a in 参2 if not a.startswith("--")]
        if len(位) < 3:
            print("用法：python3 distill.py 合并 <主池> <新批> --out 目录 [--只收 规程] [--只收判 CONFLICT,REVIEW]")
            return 2
        出 = 位[2] if len(位) > 2 else None
        if "--out" in 参2:
            出 = 参2[参2.index("--out") + 1]
            位 = [a for a in 位 if a != 出]
        收 = None
        if "--只收" in 参2:
            收 = tuple(x for x in 参2[参2.index("--只收") + 1].split(",") if x)
        收判 = None
        if "--只收判" in 参2:
            收判 = tuple(x for x in 参2[参2.index("--只收判") + 1].split(",") if x)
        结, j = 合并(位[0], 位[1], 出, 收, 收判)
        print("== 合并提案池 ==")
        for k, v in 结.items():
            print("  %-8s %d" % (k, v))
        if 结["新批挡下"]:
            print("  注：挡下的 %d 条**未立提案**（不满足 --只收 口径），不是已处理。" % 结["新批挡下"])
        print("写出：%s" % j)
        return 0
    if 命 == "筛规程":
        位 = [a for a in 参[1:] if not a.startswith("--")]
        if not 位:
            print("用法：python3 distill.py 筛规程 <distill.json> [--out 前缀] [--首批 100]")
            return 2
        首批 = 100
        if "--首批" in 参:
            首批 = int(参[参.index("--首批") + 1])
        d = json.load(open(位[0], encoding="utf-8"))
        结 = 筛规程(d, 首批)
        print("== 筛「规程×NEW」==")
        print("去重后 %d 条（同句跨文件 %d 条已并）：域内 %d（高 ≥6：%d ／ 中 5：%d ／ 低 ≤4：%d）；"
              "域外（中医／人文／小说）%d"
              % (结["总数"], 结["重复"], 结["域内"], 结["分层"]["高"],
                 结["分层"]["中"], 结["分层"]["低"], 结["域外"]))
        print("首批待裁 %d 条（同分取长句）" % len(结["首批"]))
        if "--out" in 参:
            前 = 参[参.index("--out") + 1]
            os.makedirs(os.path.dirname(os.path.abspath(前)) or ".", exist_ok=True)
            with open(前 + ".json", "w", encoding="utf-8") as f:
                json.dump({"artifact": "规程×NEW 分层与首批待裁",
                           "rule": "见 distill.py 规程分；7 分制，≥6 高、5 中、≤4 低",
                           "counts": {"总数": 结["总数"], "域内": 结["域内"],
                                      "域外": 结["域外"], **结["分层"]},
                           "首批": [{k: x.get(k) for k in
                                     ("text", "fp", "locator", "筛分", "筛据")}
                                    for x in 结["首批"]]},
                          f, ensure_ascii=False, indent=2)
            行 = ["# 规程×NEW · 首批待裁（%d 条）" % len(结["首批"]), "",
                  "> 口径：先过「有没有命理术语」（域内 %d／域外 %d），再按 `规程分` 7 分制分层："
                  "高 ≥6：%d 条／中 5：%d 条／低 ≤4：%d 条。"
                  % (结["域内"], 结["域外"], 结["分层"]["高"],
                     结["分层"]["中"], 结["分层"]["低"]),
                  "> **分低不等于废**，只代表「这一轮先不看」。每条都要能回答「落到哪一册哪一条」。", ""]
            for i, x in enumerate(结["首批"], 1):
                行.append("- [ ] **%d**（%d 分）%s" % (i, x["筛分"], x["text"]))
                行.append("      `%s`" % x.get("locator", ""))
            open(前 + ".md", "w", encoding="utf-8").write("\n".join(行) + "\n")
            print("写出：%s.json ／ %s.md" % (前, 前))
        return 0
    if 命 == "摘要":
        d = json.load(open(参[1], encoding="utf-8"))
        print(json.dumps(d.get("counts", {}), ensure_ascii=False))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
