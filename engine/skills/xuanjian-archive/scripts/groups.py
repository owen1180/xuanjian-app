#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命盘存档分组 —— 给每一档打上「这是谁」，好按关系圈检索与对账。

为什么要有这件
--------------
档号是四柱连写，只说明「这造是什么盘」，不说明「这人和我什么关系」。
实际用起来最先问的恰恰是关系：

    「我给我同事看过的那盘，档号是多少？」
    「今年客户来了几个？」
    「名人那几档别和客户混在一张表里。」

`find_chart.py` 只能按四柱查，答不了这些。所以单独记一层「分组」。

七个分组（固定，不许自创）
--------------------------
家人／朋友／同学／同事／客户／名人／其他

- **名人**单列，是为了和「客户」分开：名人是公开盘，可引用、可写案例；
  客户是私人盘，进不了对外材料。这两类混在一起，迟早有人拿客户盘当案例讲。
- **其他**是兜底，但**兜底不等于不记**：迁移时读不出分组的档会落进「未分组」，
  必须一条条补，不许默认丢进「其他」——**默认值会掩盖没做的事**。

索引与卡片两处都写
------------------
- `命理档案/档案索引.json`：机器读（清单、统计、按组筛）
- 每档 `档案卡片.md` 的「基本信息」里 `- 分组：客户`：人读，跟着档走

**卡片是主，索引是缓存。** 卡片改过、索引对不上时，以卡片为准并重写索引
（`重建` 命令）。反过来用索引覆盖卡片，就等于用缓存冲掉原件。

用法
----
    python3 groups.py 登记 命理档案 丁酉己酉丙午辛卯 --分组 客户 --称呼 "张先生"
    python3 groups.py 清单 命理档案 --分组 客户
    python3 groups.py 统计 命理档案
    python3 groups.py 迁移 命理档案            # 扫全库，读卡片里的分组，缺的标「未分组」
    python3 groups.py 重建 命理档案            # 以卡片为准，重写索引
    python3 groups.py --selftest

退出码：0 正常／1 有未分组或参数不合规／2 用法错
"""

import json
import os
import re
import sys
from datetime import date

分组们 = ["家人", "朋友", "同学", "同事", "客户", "名人", "其他"]
未分组 = "未分组"
索引名 = "档案索引.json"

天干地支 = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")
分组行 = re.compile(r"^\s*[-*]?\s*分组\s*[:：]\s*(.+?)\s*$", re.M)
称呼行 = re.compile(r"^\s*[-*]?\s*称呼\s*[:：]\s*(.+?)\s*$", re.M)


def 归一档号(s):
    """只留干支；「待补时」去掉——与 find_chart 同一口径。"""
    s = re.sub(r"[\s·、,，]", "", s or "")
    s = s.replace("待补时", "")
    return "".join(c for c in s if c in 天干地支)


def 索引路(库):
    return os.path.join(os.path.abspath(库), 索引名)


def 空索引():
    return {"artifact": "命盘存档索引（按关系圈分组）",
            "groups": list(分组们),
            "items": []}


def 允许分组(库):
    """允许的分组：以索引里 `groups` 为准，缺省用七类。

    为什么留这个口子：馆主自己的盘（本造）不属于七类里的任何一类——
    归「家人」不对，归「其他」又等于没分。允许在 `档案索引.json` 的 `groups`
    里加一条（如「本人」），`登记` 才收得下；**改完跑一次 `迁移` 重建**。
    口子只开给「加一类」，不开放自创同义类（「亲戚」「亲友」这类仍判错）。
    """
    d = 读索引(库)
    g = [x for x in (d.get("groups") or []) if isinstance(x, str) and x.strip()]
    return g or list(分组们)


def 读索引(库):
    p = 索引路(库)
    if not os.path.isfile(p):
        return 空索引()
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return 空索引()
    d.setdefault("groups", list(分组们))
    d.setdefault("items", [])
    return d


def 写索引(库, d):
    p = 索引路(库)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    d["updated"] = date.today().isoformat()
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return p


def 卡片路(库, 档号):
    return os.path.join(os.path.abspath(库), "八字库", 档号, "档案卡片.md")


def 读卡片分组(库, 档号):
    """返回 (分组, 称呼)。卡片不在或没写分组 → ("", "")。"""
    p = 卡片路(库, 档号)
    if not os.path.isfile(p):
        return "", ""
    t = open(p, encoding="utf-8").read()
    m = 分组行.search(t)
    g = (m.group(1).strip() if m else "")
    m2 = 称呼行.search(t)
    c = (m2.group(1).strip() if m2 else "")
    return (g if g in 分组们 else ""), c


def 设卡片分组(库, 档号, 分组, 称呼=""):
    """把 `- 分组：X` 写进卡片基本信息；没有这一行就插在标题后的第一段引用下。

    返回 "已改" / "未改" / "无卡片"。
    """
    p = 卡片路(库, 档号)
    if not os.path.isfile(p):
        return "无卡片"
    t = open(p, encoding="utf-8").read()
    新行 = "- 分组：%s" % 分组
    if 分组行.search(t):
        新 = 分组行.sub(新行, t, count=1)
    else:
        # 插在「## 一、基本信息」标题后的第一行；没有该标题就插在首个空行前
        m = re.search(r"^(##\s*一、.*)$", t, re.M)
        if m:
            新 = t[:m.end()] + "\n\n" + 新行 + t[m.end():]
        else:
            新 = 新行 + "\n" + t
    if 称呼:
        if 称呼行.search(新):
            新 = 称呼行.sub("- 称呼：%s" % 称呼, 新, count=1)
        else:
            新 = 新.replace(新行, 新行 + "\n- 称呼：%s" % 称呼, 1)
    if 新 == t:
        return "未改"
    open(p, "w", encoding="utf-8").write(新)
    return "已改"


def 登记(库, 档号, 分组, 称呼="", 建卡=False):
    """登记/改分组。卡片在就改卡片，不在且 建卡=True 就建一张最小卡片。"""
    档号 = 归一档号(档号)
    许 = 允许分组(库)
    if 分组 not in 许:
        raise ValueError("分组「%s」不在允许列表：%s" % (分组, "／".join(许)))
    if not 档号:
        raise ValueError("档号为空")
    动作 = 设卡片分组(库, 档号, 分组, 称呼)
    if 动作 == "无卡片":
        if not 建卡:
            raise FileNotFoundError("没有这一档：%s（要新建骨架加 --建卡）" % 卡片路(库, 档号))
        d = os.path.dirname(卡片路(库, 档号))
        os.makedirs(d, exist_ok=True)
        open(卡片路(库, 档号), "w", encoding="utf-8").write(
            "# 档案卡片 · %s\n\n> 归档日期：%s ｜ 完整报告：待补\n\n"
            "## 一、基本信息与核盘\n\n- 分组：%s%s\n- 核盘方式：待补\n"
            % (档号, date.today().isoformat(), 分组,
               ("\n- 称呼：%s" % 称呼) if 称呼 else ""))
        动作 = "已建卡"

    d = 读索引(库)
    项 = next((x for x in d["items"] if x.get("档号") == 档号), None)
    if 项 is None:
        项 = {"档号": 档号}
        d["items"].append(项)
    项["分组"] = 分组
    if 称呼:
        项["称呼"] = 称呼
    项["更新"] = date.today().isoformat()
    # 排序只影响人读的顺序：先按分组表次序，再按档号
    d["items"].sort(key=lambda x: (分组们.index(x["分组"]) if x.get("分组") in 分组们
                                   else len(分组们), x.get("档号", "")))
    写索引(库, d)
    return 动作, 项


def 迁移(库):
    """扫八字库，把卡片里的分组读进索引；读不出的标「未分组」。

    **不默认归「其他」**：默认值会让人以为已经分过类，实际一条没分。
    """
    d = 读索引(库)
    有 = {x.get("档号"): x for x in d["items"]}
    新项, 未分, 已分 = [], [], 0
    根 = os.path.join(os.path.abspath(库), "八字库")
    for 名 in sorted(os.listdir(根)) if os.path.isdir(根) else []:
        if not os.path.isdir(os.path.join(根, 名)):
            continue
        档号 = 归一档号(名)
        g, c = 读卡片分组(库, 名)
        项 = dict(有.get(档号, {}))
        项["档号"] = 档号
        项["目录"] = 名
        if g:
            项["分组"] = g
            if c:
                项["称呼"] = c
            已分 += 1
        else:
            项["分组"] = 未分组
            未分.append(档号)
        新项.append(项)
    # 索引里有、盘上没有的（档被删或改名），保留但标出来
    盘上 = {x["档号"] for x in 新项}
    for 档号, 项 in 有.items():
        if 档号 not in 盘上:
            项 = dict(项)
            项["缺失"] = True
            新项.append(项)
    d["items"] = 新项
    写索引(库, d)
    return {"已分": 已分, "未分组": 未分, "总数": len(新项)}


def 清单(库, 分组=None):
    d = 读索引(库)
    们 = d["items"]
    if 分组:
        们 = [x for x in 们 if x.get("分组") == 分组]
    return 们


def 统计(库):
    d = 读索引(库)
    许 = 允许分组(库)
    计 = {g: 0 for g in 许}
    计[未分组] = 0
    for x in d["items"]:
        g = x.get("分组")
        计[g if g in 许 else 未分组] = 计.get(g if g in 许 else 未分组, 0) + 1
    return 计, len(d["items"])


def 齐(s, 宽):
    """按**显示宽度**补空格：中文算两列。`%-18s` 只数字符，中文列会歪。"""
    s = s or ""
    实 = sum(2 if ord(c) > 0x2E80 else 1 for c in s)
    return s + " " * max(0, 宽 - 实)


def 报表(库, 详=False):
    计, 总 = 统计(库)
    行 = ["== 命盘存档 · 按分组 ==", "共 %d 档" % 总, ""]
    for g in 允许分组(库) + [未分组]:
        n = 计.get(g, 0)
        行.append("  %-4s %3d" % (g, n))
    if 计.get(未分组):
        行.append("")
        行.append("！ %d 档未分组：跑 `groups.py 迁移` 后逐档补，**不许默认丢进「其他」**"
                  % 计[未分组])
    缺 = [x["档号"] for x in 读索引(库)["items"] if x.get("缺失")]
    if 缺:
        行.append("！ %d 档索引里有、盘上没有：%s" % (len(缺), "、".join(缺[:5])))
    return "\n".join(行)


# ---------------------------------------------------------------- 自检

def 自检():
    import shutil
    import tempfile
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("分组表七类", 分组们 == ["家人", "朋友", "同学", "同事", "客户", "名人", "其他"])
    查("归一档号·去标点", 归一档号("丁酉 己酉、丙午，辛卯") == "丁酉己酉丙午辛卯")
    查("归一档号·去待补时", 归一档号("庚寅己卯戊午待补时") == "庚寅己卯戊午")
    查("归一档号·剔杂字", 归一档号("丁酉己酉丙午辛卯X") == "丁酉己酉丙午辛卯")

    td = tempfile.mkdtemp()
    try:
        库 = os.path.join(td, "命理档案")
        os.makedirs(os.path.join(库, "八字库"))
        os.makedirs(os.path.join(库, "方法论"))

        查("空库·索引是空壳", 读索引(库)["items"] == [])

        动作, 项 = 登记(库, "丁酉己酉丙午辛卯", "客户", "张先生", 建卡=True)
        查("登记·建卡成功", 动作 == "已建卡" and 项["分组"] == "客户")
        查("登记·卡片已落分组", 读卡片分组(库, "丁酉己酉丙午辛卯")[0] == "客户")
        查("登记·卡片已落称呼", 读卡片分组(库, "丁酉己酉丙午辛卯")[1] == "张先生")
        查("登记·索引已写", os.path.isfile(索引路(库)))

        动作2, _ = 登记(库, "丁酉己酉丙午辛卯", "同事")
        查("改分组·动作是已改", 动作2 == "已改")
        查("改分组·卡片跟着改", 读卡片分组(库, "丁酉己酉丙午辛卯")[0] == "同事")
        查("改分组·称呼未丢", 读卡片分组(库, "丁酉己酉丙午辛卯")[1] == "张先生")

        # 负向：非法分组必须拒，且不许留下任何东西
        try:
            登记(库, "庚寅己卯戊午", "亲戚", 建卡=True)
            查("非法分组·应报错", False)
        except ValueError as e:
            查("非法分组·报错并列出允许值", "家人" in str(e) and "客户" in str(e))
        查("非法分组·没建出卡片", not os.path.isfile(卡片路(库, "庚寅己卯戊午")))

        # 负向：没卡片又不许建卡，必须报错
        try:
            登记(库, "甲子乙丑丙寅丁卯", "家人")
            查("无档·非建卡应报错", False)
        except FileNotFoundError as e:
            # 不用 `True` 当断言：except 里写 True 是恒真，等于没测（元闸会抓）
            查("无档·非建卡应报错", "没有这一档" in str(e))

        # 迁移：手写一张只带分组的老卡，与一张不带分组的卡
        os.makedirs(os.path.join(库, "八字库", "甲子乙丑丙寅丁卯"), exist_ok=True)
        open(卡片路(库, "甲子乙丑丙寅丁卯"), "w", encoding="utf-8").write(
            "# 档案卡片 · 甲子乙丑丙寅丁卯\n\n## 一、基本信息与核盘\n\n- 分组：名人\n")
        os.makedirs(os.path.join(库, "八字库", "戊辰己巳庚午辛未"), exist_ok=True)
        open(卡片路(库, "戊辰己巳庚午辛未"), "w", encoding="utf-8").write(
            "# 档案卡片 · 戊辰己巳庚午辛未\n\n## 一、基本信息与核盘\n\n- 核盘方式：待补\n")
        结 = 迁移(库)
        查("迁移·读出已有分组", any(x["档号"] == "甲子乙丑丙寅丁卯" and x["分组"] == "名人"
                                 for x in 读索引(库)["items"]))
        查("迁移·读不出的标未分组", 结["未分组"] == ["戊辰己巳庚午辛未"])
        查("迁移·未分组不混进其他",
           统计(库)[0]["其他"] == 0 and 统计(库)[0]["未分组"] == 1)

        查("清单·按组筛", [x["档号"] for x in 清单(库, "同事")] == ["丁酉己酉丙午辛卯"])
        查("清单·组内为空给空表", 清单(库, "朋友") == [])

        计, 总 = 统计(库)
        查("统计·总数对", 总 == 3)
        查("统计·各组相加等于总数", sum(计.values()) == 总)
        # 可扩展分组：索引里加了「本人」，登记才收得下；没加时该组必须判错
        d2 = 读索引(库)
        d2["groups"] = list(分组们) + ["本人"]
        写索引(库, d2)
        查("扩展分组·可登记", 登记(库, "丁酉己酉丙午辛卯", "本人")[1]["分组"] == "本人")
        查("扩展分组·统计里出现", "本人" in 统计(库)[0])
        d3 = 读索引(库)
        d3["groups"] = list(分组们)
        写索引(库, d3)
        try:
            登记(库, "丁酉己酉丙午辛卯", "本人")
            查("扩展分组·撤掉后应判错", False)
        except ValueError as e:
            # 断言异常内容，不写恒真的 `X in 同样的字符串`
            查("扩展分组·撤掉后应判错", "不在允许列表" in str(e) and "本人" in str(e))
        查("报表·提示未分组", "未分组" in 报表(库))
        查("对齐·中文按两列算", 齐("客户", 8) == "客户    " and 齐("abcd", 8) == "abcd    ")

        # 重建：以卡片为准
        d = 读索引(库)
        d["items"].append({"档号": "甲乙丙丁戊己庚辛", "分组": "客户"})   # 卡片不存在
        写索引(库, d)
        结2 = 迁移(库)
        查("重建·盘上没有的标缺失",
            any(x.get("缺失") for x in 读索引(库)["items"]))
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main(argv=None):
    参 = list(sys.argv[1:] if argv is None else argv)
    if not 参 or 参[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if 参[0] == "--selftest":
        return 自检()
    命 = 参[0]
    位 = [a for a in 参[1:] if not a.startswith("--")]
    选 = {}
    i = 1
    while i < len(参):
        if 参[i].startswith("--") and i + 1 < len(参):
            选[参[i]] = 参[i + 1]
            i += 2
        else:
            i += 1

    if 命 in ("登记",) and len(位) >= 2:
        try:
            动作, 项 = 登记(位[0], 位[1], 选.get("--分组", "其他"),
                           选.get("--称呼", ""), 建卡=("--建卡" in 参))
        except ValueError as e:
            print("错误：%s" % e)
            return 1
        except FileNotFoundError as e:
            print("错误：%s" % e)
            return 1
        print("%s → %s（%s）" % (项["档号"], 项["分组"], 动作))
        print("索引：%s" % 索引路(位[0]))
        return 0

    if 命 == "清单" and len(位) >= 1:
        们 = 清单(位[0], 选.get("--分组"))
        if not 们:
            print("（空）")
            return 0
        print("%s %s %s %s" % (齐("档号", 18), 齐("分组", 8), 齐("称呼", 12), "更新"))
        for x in 们:
            print("%s %s %s %s" % (齐(x.get("档号", ""), 18), 齐(x.get("分组", ""), 8),
                                   齐(x.get("称呼", "") or "—", 12), x.get("更新", "")))
        return 0

    if 命 == "统计" and len(位) >= 1:
        print(报表(位[0]))
        计, _ = 统计(位[0])
        return 1 if 计.get(未分组) else 0

    if 命 == "迁移" and len(位) >= 1:
        结 = 迁移(位[0])
        print("扫完：已分 %d ／ 未分组 %d ／ 索引共 %d 档"
              % (结["已分"], len(结["未分组"]), 结["总数"]))
        if 结["未分组"]:
            print("未分组：%s" % "、".join(结["未分组"][:10]))
            print("**逐档补 `--分组`，不许默认丢进「其他」。**")
        return 0

    if 命 == "重建" and len(位) >= 1:
        结 = 迁移(位[0])
        print("已按卡片重建索引：%d 档（未分组 %d）" % (结["总数"], len(结["未分组"])))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
