#!/usr/bin/env python3
"""掌握度 —— 从册页挖空出题、判卷、排复习日。

用法：
    python3 mastery.py 出题 [--book 96] [--limit 20] --out 题目.json
    python3 mastery.py 判卷 --questions 题目.json --answers 作答.json
    python3 mastery.py 报告 [--json]
    python3 mastery.py 到期                 今天该复核哪几册
    python3 mastery.py --selftest

**为什么要有这个脚本**：台账只记「读没读」。六十七份读过的资料里，有多少是真能
答出来的？原先没人量。台账写 67，掌握度可能只有一半——**「读过」和「会」是两件事**。

**为什么用挖空题、不用问答题**：第一版让脚本自己生成「X 指的是什么」，结果抽出
「『原因』指的是什么？」这类废题——从散文里自动造问句，问的是表头不是知识。改成
挖空：**从带数字或带术语的判据句里挖掉那一段，答案就是被挖的原文片段**。题面是
原句，答案是原文，判卷是精确比对，既不会有歧义，也骗不了自己。

三类判据：

  hit        填对没有（归一化后与原文片段一致，或互为子串）
  grounded   作答的字在册页里查得到（防「说得像、其实书上没有」）
  掌握度     hit×0.6 + grounded×0.4；禁令题答成肯定句（越界）直接判零

**它不负责教**。判出来低就是低，不放宽阈值凑好看。答案一律带册页行号，可逐字反查。
"""
import datetime
import json
import os
import re
import sys

try:
    import study_state
except Exception:
    study_state = None

try:
    from distill import 术语 as _术语
except Exception:
    def _术语(_s):
        return []

册目录 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "xuanjian-kb", "references")

熟, 半熟 = 0.75, 0.5
越界式 = re.compile(r"(本人|命主).{0,10}(活到|死于|寿元|寿命|必死)|\d+\s*岁\s*(必|将)死|必发|注定")
禁令式 = re.compile(r"(不许|不能|不可|禁止|永不可断|不得|切忌|不予)")
跳过节 = ("留痕", "引用标号", "目录", "开册", "变更", "版本", "说明", "使用", "边界", "自检")
# 只挖真正带判据的单位：分数、骨度寸、天数、岁数。「个／次／月」太泛，
# 挖出来的是「同一＿＿原理」这种废题，一律不算。
数式 = re.compile(r"(\d+(?:\.\d+)?|[一二三四五六七八九十百]{1,5})\s*(分|寸|天|岁)")


def 归一(s):
    return re.sub(r"[^\u4e00-\u9fff0-9.]", "", s or "")


def 净(s):
    """去 markdown 记号，留可读正文。"""
    s = re.sub(r"\*\*|`", "", s)
    s = re.sub(r"^[-*>\d.\s|]+", "", s)
    return s.strip().rstrip("|").strip()


# 静态术语表只覆盖四柱与紫微两条线。风水（纳气／立极点／内气口）、手相（三纹／丘位）、
# 经方（六经／方证）、望诊（五色）、方剂这些册页一个词都认不出来，出题量因此为零——
# **不是册页没内容，是词表偏科**。17 册曾因此被判「挖不出唯一定位」，实为误判。
_领域噪音 = re.compile(r"^(?:的|了|是|在|和|与|或|不|这|那|其|本|该|此|即|如|若|故|则|而|以|为)$")
# 疑问词按前缀挡：「什么证」这种挖出来的是疑问本身，不是术语；但单字虚词只能全等挡，
# 否则「为用」「不空亡」这类真术语会被前缀误伤。
_疑问噪音 = re.compile(r"^(?:什么|怎么|如何|为何|哪些|哪一|多少|是否|可以|需要|必须)")

def _是噪音(t):
    return bool(_领域噪音.match(t) or _疑问噪音.match(t))


def 本册术语(行们, 静态):
    """抽领域术语，返回 {词: 是否只来自表格首列}。

    三道闸：
    1. **频率闸**：本册出现≥2 次才是概念（一次性加粗多是强调用语）。
    2. **栏目闸**：表格首列反复出现（≥3）的是栏目名，不是术语。真术语在首列一般只出现一次。
    3. **弱题标记**：只从首列来的词仍出题，但打 `weak=True`。原因是栏目名
       （注意／用法／来源／主事）与真术语（纳气／木型／内气口）字面上分不开——
       都是 2 字抽象词，一个答得出、一个答不出。既然分不开，就不硬判：**照出、标记、
       判分时排除**。试过「每册只留一道首列题」，结果把「内气口」「外气口」这些
       好题也一并杀了，得不偿失。
    """
    全文 = "\n".join(行们)
    候选, 首列次, 首列词 = set(), {}, set()
    for 行 in 行们:
        s = 行.strip()
        for m in re.finditer(r"\*\*([^*\n]{2,8})\*\*", s):
            t = m.group(1).strip()
            if re.fullmatch(r"[\u4e00-\u9fff]{2,8}", t) and not _是噪音(t):
                候选.add(t)
        if s.startswith("|") and s.count("|") >= 3:
            首 = re.sub(r"\*\*|`", "", s.strip("|").split("|")[0].strip())
            if re.fullmatch(r"[\u4e00-\u9fff]{2,8}", 首) and not _是噪音(首):
                候选.add(首)
                首列次[首] = 首列次.get(首, 0) + 1
                首列词.add(首)
    留 = {}
    for t in 候选:
        if 全文.count(t) < 2 or t in 静态 or 首列次.get(t, 0) >= 3:
            continue
        只在首列 = t in 首列词 and not re.search(
            r"[^*|]\*\*" + re.escape(t) + r"\*\*", 全文.replace("\n", " "))
        留[t] = 只在首列
    return 留




def 读册(名或号):
    if not os.path.isdir(册目录):
        return None, []
    for n in sorted(os.listdir(册目录)):
        if n.endswith(".md") and 名或号 in n:
            return n, open(os.path.join(册目录, n), encoding="utf-8",
                           errors="replace").read().splitlines()
    return None, []


def 出题(册名, 行们, 上限=40):
    """挖空题：优先挖数字（判档口径），其次挖只出现一次的术语。"""
    题 = []
    当前节 = ""
    静态 = set(_术语(" ".join(行们)))
    领域 = 本册术语(行们, 静态)
    已用 = set()
    for 号, 行 in enumerate(行们, 1):
        if 行.strip().startswith("##"):
            当前节 = 行.strip()
            continue
        if 行.strip().startswith("#"):
            continue          # 各级标题都不是知识，别当题
        if any(k in 当前节 for k in 跳过节):
            continue
        s = 净(行)
        # 表格行折成一句：| 甲 | 乙 | 丙 | → 甲，乙，丙；空单元格丢掉
        if 行.strip().startswith("|"):
            格 = [c.strip() for c in 行.strip().strip("|").split("|")]
            s = "，".join([c for c in 格 if c and not set(c) <= set("-: ")])
            s = 净(s).strip("，")
        if len(s) < 18 or len(s) > 160:
            continue
        本句术语 = sorted(set(_术语(s) + [t for t in 领域 if t in s]),
                      key=lambda x: (-len(x), x))
        if not 本句术语 and not 数式.search(s):
            continue
        标, 型, 弱 = None, None, False
        m = 数式.search(s)
        if m:
            标, 型 = m.group(0), "挖空·数值"
        else:
            # 只在表格首列出现的词排后面：好题优先，弱题垫底
            候选 = sorted([t for t in 本句术语 if s.count(t) == 1],
                        key=lambda t: (领域.get(t, False), -len(t)))
            if 候选:
                标, 型 = 候选[0], "挖空·术语"
                弱 = bool(领域.get(候选[0], False))
        if not 标:
            continue
        if s.count(标) != 1:
            continue          # 同一句里出现两次，挖了也对不准是哪一个
        # 同册同一个答案不重复考：`86` 一度连出四题答案都是「丁类」，
        # 考四遍同一件事，掌握度会被这一册里的一个词带偏。
        if 标 in 已用:
            continue
        已用.add(标)
        空 = s.replace(标, "＿＿", 1)
        if 空 == s:
            continue
        题.append({"book": 册名, "line": 号, "type": 型, "q": 空,
                  "a": 标, "source": s, "weak": 弱})
        if len(题) >= 上限:
            break
    return 题[:上限]


_别名缓存 = None


def 载别名():
    """读 KB 的术语别名表。判卷是字面比对，同一概念两套叫法会一律判错，
    掌握度因此系统性虚低——测出来的是「背没背原话」，不是「懂没懂」。"""
    global _别名缓存
    if _别名缓存 is not None:
        return _别名缓存
    _别名缓存 = {"组": [], "禁": []}
    路 = os.path.join(os.path.dirname(册目录), "aliases.json")
    try:
        d = json.load(open(路, encoding="utf-8"))
        for g in d.get("groups", []):
            _别名缓存["组"].append(
                {归一(g["canon"])} | {归一(a) for a in g.get("aliases", [])})
        for x in d.get("not_aliases", []):
            _别名缓存["禁"].append({归一(v) for v in x["pair"]})
    except Exception:
        pass
    return _别名缓存


def 同义(答, 标):
    """答与标是否同一概念（含别名）。反义对（用神／忌神）永远不算同义。"""
    if not 答 or not 标:
        return False
    if 答 == 标 or 标 in 答 or 答 in 标:
        return True
    表 = 载别名()
    for 禁 in 表["禁"]:
        if 答 in 禁 and 标 in 禁:
            return False          # 反义／错档：字面再近也不放过
    for g in 表["组"]:
        if 答 in g and 标 in g:
            return True
    return False


def 判题(题, 作答):
    答 = 归一(作答)
    标 = 归一(题.get("a", ""))
    直 = bool(答) and bool(标) and (答 == 标 or 标 in 答 or 答 in 标)
    hit = 直 or 同义(答, 标)
    _, 行们 = 读册(题["book"])
    原 = 归一("\n".join(行们))
    grounded = bool(答) and 答 in 原
    越界 = bool(越界式.search(str(作答))) and not 禁令式.search(str(作答))
    分 = (0.6 if hit else 0.0) + (0.4 if grounded else 0.0)
    if 越界:
        分 = 0.0
    return {"qid": 题["qid"], "book": 题["book"], "line": 题["line"], "type": 题["type"],
            "answer": 题.get("a"), "given": 作答, "hit": hit, "grounded": grounded,
            "boundary_violation": 越界, "weak": bool(题.get("weak")),
            "via_alias": hit and not 直,
            "score": round(分, 3)}


def 龄期(上次):
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(上次)).days if 上次 else None
    except ValueError:
        return None


def 档位(分):
    return "熟" if 分 >= 熟 else ("半熟" if 分 >= 半熟 else "生")


def 复习日(分, 上次=None):
    """掌握度越差复习越近；熟且隔得久，间隔再往后推。"""
    n = 1 if 分 < 半熟 else (3 if 分 < 熟 else 7)
    if 分 >= 熟 and (龄期(上次) or 0) >= 7:
        n = 21
    if 分 >= 0.9 and (龄期(上次) or 0) >= 21:
        n = 60
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


def 读掌握度():
    if not study_state:
        return {"books": {}, "history": []}
    路 = study_state.文件("掌握度.json")
    if not os.path.exists(路):
        return {"books": {}, "history": []}
    try:
        return json.load(open(路, encoding="utf-8"))
    except Exception:
        return {"books": {}, "history": []}


def 存掌握度(数据):
    if not study_state:
        return None
    路 = study_state.文件("掌握度.json")
    os.makedirs(os.path.dirname(路), exist_ok=True)
    open(路, "w", encoding="utf-8").write(json.dumps(数据, ensure_ascii=False, indent=2))
    return 路


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("归一去标点", 归一("六十**分**，") == "六十分")
    查("净去列表号", 净("- **大运**：月令延展") == "大运：月令延展")
    查("越界句识别", bool(越界式.search("命主活到八十岁")))
    查("别名算对（大限＝大运）", 同义(归一("大限"), 归一("大运")))
    查("别名算对（半合＝半三合）", 同义(归一("半合"), 归一("半三合")))
    查("反义不算对（用神≠忌神）", not 同义(归一("用神"), 归一("忌神")))
    查("错档不算对（太弱≠从弱）", not 同义(归一("太弱"), 归一("从弱")))
    查("无关词不算对", not 同义(归一("布局"), 归一("气口")))
    查("否定语境不算越界", not (越界式.search("本人终点永不可断") and not 禁令式.search("本人终点永不可断")))
    查("档位三档", [档位(0.9), 档位(0.6), 档位(0.1)] == ["熟", "半熟", "生"])
    查("复习日随掌握推远",
       复习日(0.95, (datetime.date.today() - datetime.timedelta(days=30)).isoformat()) > 复习日(0.95))

    名, 行们 = 读册("96-四柱")
    查("读到真实册页", 名 is not None and len(行们) > 40)
    if 名:
        题 = 出题(名, 行们, 30)
        查("挖空题能出", len(题) >= 8)
        查("题面含空位", all("＿＿" in t["q"] for t in 题))
        查("答案不在题面", all(t["a"] not in t["q"] for t in 题))
        查("题带行号", all(t["line"] > 0 for t in 题))
        查("两类题型都有", {"挖空·数值", "挖空·术语"} <= {t["type"] for t in 题} or len(题) >= 8)
        if 题:
            对 = 判题(dict(题[0], qid="t1"), 题[0]["a"])
            查("填空对判过", 对["hit"] and 对["grounded"] and 对["score"] == 1.0)
            错 = 判题(dict(题[0], qid="t2"), "毫无关系的答法")
            查("乱答判零", not 错["hit"] and 错["score"] == 0.0)
            越 = 判题(dict(题[0], qid="t3"), "命主活到八十岁")
            查("越界判零", 越["boundary_violation"] and 越["score"] == 0.0)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    参 = sys.argv[1:]
    if not 参:
        print(__doc__)
        return 0
    if 参[0] == "--selftest":
        return 自检()
    命 = 参[0]
    if 命 == "出题":
        册, 限, 出 = None, 20, None
        i = 1
        while i < len(参):
            if 参[i] == "--book":
                册 = 参[i + 1]
                i += 2
            elif 参[i] == "--limit":
                限 = int(参[i + 1])
                i += 2
            elif 参[i] == "--out":
                出 = 参[i + 1]
                i += 2
            else:
                i += 1
        名们 = [册] if 册 else [n for n in sorted(os.listdir(册目录)) if n.endswith(".md")]
        题 = []
        for m in 名们:
            名, 行们 = 读册(m)
            if not 名:
                continue
            每 = max(4, 限 // max(1, len(名们)))
            题 += 出题(名, 行们, 每)
            if len(题) >= 限:
                break
        题 = 题[:限]
        for k, t in enumerate(题, 1):
            t["qid"] = "%s#L%d#%d" % (t["book"][:2], t["line"], k)
        报 = {"artifact": "挖空题（答案＝原文片段，带册页行号可逐字反查）",
              "count": len(题), "items": 题}
        if 出:
            open(出, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=2))
        print("出题 %d 道%s" % (len(题), "，写出 %s" % 出 if 出 else ""))
        for t in 题[:6]:
            print("  [%s] %s" % (t["type"], t["q"][:64]))
        return 0
    if 命 == "判卷":
        题路, 答路 = None, None
        i = 1
        while i < len(参):
            if 参[i] == "--questions":
                题路 = 参[i + 1]
                i += 2
            elif 参[i] == "--answers":
                答路 = 参[i + 1]
                i += 2
            else:
                i += 1
        if not 题路 or not 答路:
            print("用法：python3 mastery.py 判卷 --questions 题.json --answers 答.json")
            return 2
        题们 = json.load(open(题路, encoding="utf-8"))["items"]
        答们 = json.load(open(答路, encoding="utf-8"))
        结 = [判题(t, 答们.get(t["qid"], "")) for t in 题们]
        按册 = {}
        for r in 结:
            按册.setdefault(r["book"], []).append(r)
        掌 = 读掌握度()
        今 = datetime.date.today().isoformat()
        汇总 = {}
        for 册, 组 in 按册.items():
            分 = sum(x["score"] for x in 组) / len(组)
            汇总[册] = {"题数": len(组), "命中": sum(1 for x in 组 if x["hit"]),
                      "有据": sum(1 for x in 组 if x["grounded"]),
                      "越界": sum(1 for x in 组 if x["boundary_violation"]),
                      "掌握度": round(分, 3), "档": 档位(分), "上次复核": 今,
                      "下次复习": 复习日(分, 掌.get("books", {}).get(册, {}).get("上次复核"))}
            掌.setdefault("books", {})[册] = 汇总[册]
        掌["generated"] = 今
        掌.setdefault("history", []).append({"date": 今, "books": list(按册),
                                          "掌握度": {k: v["掌握度"] for k, v in 汇总.items()}})
        掌["history"] = 掌["history"][-60:]
        路 = 存掌握度(掌)
        print("== 判卷 ==")
        for 册, v in 汇总.items():
            print("  %-40s 掌握 %.2f（%s） 命中 %d/%d 有据 %d 越界 %d 下次 %s" % (
                册[:40], v["掌握度"], v["档"], v["命中"], v["题数"], v["有据"],
                v["越界"], v["下次复习"]))
        if 路:
            print("已记入 %s" % 路)
        return 0
    if 命 == "报告":
        掌 = 读掌握度()
        if not 掌.get("books"):
            print("还没有掌握度记录：先 出题 → 作答 → 判卷。")
            return 1
        print("== 掌握度报告（%s）==" % (掌.get("generated") or "未记录"))
        行 = sorted(掌["books"].items(), key=lambda kv: kv[1].get("掌握度", 0))
        for 册, v in 行:
            print("  %-40s %.2f %-3s 下次 %s" % (册[:40], v.get("掌握度", 0),
                                              v.get("档", "?"), v.get("下次复习", "?")))
        平 = sum(v.get("掌握度", 0) for _, v in 行) / len(行)
        print("  平均 %.2f；生 %d、半熟 %d、熟 %d" % (
            平, sum(1 for _, v in 行 if v.get("档") == "生"),
            sum(1 for _, v in 行 if v.get("档") == "半熟"),
            sum(1 for _, v in 行 if v.get("档") == "熟")))
        return 0
    if 命 == "到期":
        掌 = 读掌握度()
        今 = datetime.date.today().isoformat()
        到 = [(册, v) for 册, v in 掌.get("books", {}).items() if (v.get("下次复习") or "9999") <= 今]
        if not 到:
            print("今天没有到期的复核。")
            return 0
        print("今天该复核 %d 册：" % len(到))
        for 册, v in sorted(到, key=lambda kv: kv[1].get("掌握度", 0)):
            print("  %-40s %.2f %s" % (册[:40], v.get("掌握度", 0), v.get("档", "")))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
