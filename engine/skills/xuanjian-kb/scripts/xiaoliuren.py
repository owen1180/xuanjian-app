#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小六壬确定性起课（玄鉴命理馆 · 见 references/74 §5）

只用标准库 + sxtwl（仅公历转农历时需要）。全程离线，不联网，不写盘。

用法：
  # 掌上起课（公历，自动转农历与时辰）
  python3 xiaoliuren.py 2026-11-02 14:30
  # 掌上起课（直接给农历，免历法库）
  python3 xiaoliuren.py --lunar 6 5 辰
  # 活数起课（第一反应之数）
  python3 xiaoliuren.py --number 1436
  # 自检（复算 74 §5.3 的例一）
  python3 xiaoliuren.py --selftest

纪律（写死在代码里，不靠注释）：
  1. 事类不参与计算，只决定取哪一条断语；
  2. 输出默认走"安全转写"，原诀须 --raw 且仅供内部核对；
  3. 只答"起、过程、落点"，不答"为什么""该怎么办"。
"""

import argparse
import json
import sys
from datetime import date as _date, timedelta

PALACES = [
    {"i": 0, "name": "大安", "finger": "食指根", "wu": "木", "dir": "东", "god": "青龙",
     "xiang": "静、稳、旧处、不动之象"},
    {"i": 1, "name": "留连", "finger": "食指尖", "wu": "土", "dir": "四角", "god": "螣蛇",
     "xiang": "拖、缠、来回、久不决之象"},
    {"i": 2, "name": "速喜", "finger": "中指尖", "wu": "火", "dir": "南", "god": "朱雀",
     "xiang": "快、信至、口传、喜动之象"},
    {"i": 3, "name": "赤口", "finger": "无名指尖", "wu": "金", "dir": "西", "god": "白虎",
     "xiang": "争、伤、口舌、手续之象"},
    {"i": 4, "name": "小吉", "finger": "无名指根", "wu": "水", "dir": "东北", "god": "六合",
     "xiang": "合、和、有人帮、可商量之象"},
    {"i": 5, "name": "空亡", "finger": "中指根", "wu": "土", "dir": "中", "god": "勾陈",
     "xiang": "落空、无着、白费、待填实之象"},
]

SHICHEN = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 通行本六宫诀（仅内部核对与 --raw 用；原文含本馆禁语，见 SOFTEN）
YUANJUE = {
    "大安": "大安事事昌，求财在坤方，失物去不远，宅舍保安康，行人身未动，病者主无妨，将军回田野，仔细更推详。",
    "留连": "留连事难成，求谋日未明，官事凡宜缓，去者未回程，失物南方见，急讨方心称，更须防口舌，人口且平平。",
    "速喜": "速喜喜来临，求财向南行，失物申未午，逢人路上寻，官事有福德，病者无祸侵，田宅六畜吉，行人有信音。",
    "赤口": "赤口主口舌，官非切要防，失物急去寻，行人有惊慌，鸡犬多作怪，病者出西方，更须防咀咒，恐怕染瘟殃。",
    "小吉": "小吉最吉昌，路上好商量，阴人来报喜，失物在坤方，行人立便至，交易甚是强，凡事皆和合，病者叩穹苍。",
    "空亡": "空亡事不祥，阴人多乖张，求财无利益，行人有灾殃，失物寻不见，官事有刑伤，病人逢暗鬼，析解可安康。",
}

# 安全转写：原诀里触本馆红线（57 / 24 / 46）的字样，逐条换成风险语言
SOFTEN = [
    ("病者出西方", "身体方面宜先做检查，别拖"),
    ("恐怕染瘟殃", "换季时留意身体"),
    ("病人逢暗鬼", "身体上宜早睡、宜就医"),
    ("病者主无妨", "身体无大碍，仍宜规律作息"),
    ("病者叩穹苍", "身体上的事，求医比求神实在"),
    ("行人有灾殃", "出行或在外的人，宜多留一分余地"),
    ("行人有惊慌", "在外的人可能有点变动，宜先联系确认"),
    ("官事有刑伤", "手续或文书上容易卡，宜先备齐材料"),
    ("官非切要防", "涉及合同与手续的，宜先看清条款"),
    ("更须防咀咒", "也宜留意口舌与是非"),
    ("鸡犬多作怪", "家里琐事容易添乱"),
    ("求财无利益", "这一趟财上偏薄，宜守不宜进"),
    ("空亡事不祥", "这件事眼下不落地"),
    ("阴人多乖张", "中间的传话容易失真"),
    ("析解可安康", "把事说开、把结解开，人就松快"),
]

BANNED = ["必然", "必定", "必出", "必发", "必成", "必旺", "绝对", "灾殃", "刑伤",
          "暗鬼", "瘟", "夭折", "死别", "死亡", "寿尽", "必有"]


def palace(idx):
    return PALACES[idx % 6]


def cast_from_lunar(month, day, shichen_index):
    """掌上起课。month/day 为农历月日，shichen_index 子=0。"""
    m_pal = (month - 1) % 6
    d_pal = (m_pal + day - 1) % 6
    h_pal = (d_pal + shichen_index) % 6
    return m_pal, d_pal, h_pal


def cast_from_number(numbers):
    """活数起课：诸位相加，减（位数−1），除 6 取余（余 0 作 6）。"""
    digits = [int(c) for c in str(numbers) if c.isdigit()]
    if not digits:
        raise ValueError("活数至少要有一位数字")
    s = sum(digits) - (len(digits) - 1)
    if s <= 0:
        s += 6
    idx = (s - 1) % 6
    return idx, s, len(digits)


def hour_to_shichen(hour):
    return ((hour + 1) // 2) % 12


def solar_to_lunar(y, m, d):
    """公历 → 农历（月, 日, 是否闰月）。优先 sxtwl；离线走纯数据表。"""
    try:
        import sxtwl
        day = sxtwl.fromSolar(y, m, d)
        lm = day.getLunarMonth()
        leap = lm < 0
        return abs(lm), day.getLunarDay(), leap
    except Exception:
        pass
    # 离线兜底：纯数据表（不含 sxtwl）
    import _lunar_data
    ly, lm, ld, leap = _lunar_data.lunar_of(y, m, d)
    return lm, ld, leap


def soften(text):
    for bad, good in SOFTEN:
        text = text.replace(bad, good)
    return text


def guard(text):
    hits = [w for w in BANNED if w in text]
    if hits:
        raise ValueError("输出仍含红线字样：%s。改写后再出口。" % "、".join(hits))
    return text


EVENT_KEYS = {
    "求财": ["财"],
    "失物": ["失物"],
    "行人": ["行人", "去者", "在外"],
    "疾病": ["病"],
    "官事": ["官事", "官非", "咀咒"],
    "出行": ["行人", "去者", "出行"],
    "求谋": ["求谋", "事"],
    "交易": ["交易"],
    "婚姻": ["婚", "阴人"],
    "宅舍": ["宅舍", "田宅", "人口"],
}


def pick_clause(name, event):
    """按事类从原诀里挑出对应的一句（事类只挑句，不改课式）。"""
    keys = EVENT_KEYS.get(event or "", [])
    if not keys:
        return ""
    clauses = [c for c in YUANJUE[name].rstrip("。").split("，")]
    hit = [c for c in clauses if any(k in c for k in keys)]
    if not hit:
        return ""
    return "，".join(soften(c) for c in hit) + "。"


def render(m_pal, d_pal, h_pal, meta, raw=False, event=""):
    m, d, h = palace(m_pal), palace(d_pal), palace(h_pal)
    same = len({m_pal, d_pal, h_pal}) == 1
    lines = []
    lines.append("【小六壬课式】")
    lines.append("一、起课")
    for k, v in meta.items():
        lines.append("   %s：%s" % (k, v))
    lines.append("")
    lines.append("二、三宫")
    lines.append("   月宫（起因）：%s ｜ %s ｜ %s·%s ｜ %s" % (m["name"], m["wu"], m["dir"], m["god"], m["xiang"]))
    lines.append("   日宫（过程）：%s ｜ %s ｜ %s·%s ｜ %s" % (d["name"], d["wu"], d["dir"], d["god"], d["xiang"]))
    lines.append("   时宫（结局）：%s ｜ %s ｜ %s·%s ｜ %s" % (h["name"], h["wu"], h["dir"], h["god"], h["xiang"]))
    lines.append("")
    lines.append("三、结构")
    if same:
        lines.append("   三宫同宫（%s），事体单纯，起落在一处。" % m["name"])
    else:
        lines.append("   起 %s → 过程 %s → 落 %s。" % (m["name"], d["name"], h["name"]))
        if m_pal == h_pal:
            lines.append("   首尾同宫，绕一圈回到原处：多半是原地打转，非出新局。")
        if h_pal == 5:
            lines.append("   落空亡：眼下不落地，宜等填实（换个时点再说）。")
    lines.append("")
    lines.append("四、断语")
    if event:
        got = []
        for tag, p in (("起因", m), ("过程", d), ("结局", h)):
            c = pick_clause(p["name"], event)
            if c:
                got.append("   %s·%s：%s" % (tag, p["name"], c))
        if got:
            lines.append("   （按事类「%s」取句，已作安全转写）" % event)
            lines.extend(got)
        else:
            lines.append("   （「%s」在本宫诀中无对应句，只给宫象：%s）" % (event, m["xiang"]))
    else:
        lines.append("   未给事类，只给宫象，不代取断语：")
        for tag, p in (("起因", m), ("过程", d), ("结局", h)):
            lines.append("   %s·%s：%s" % (tag, p["name"], p["xiang"]))
        lines.append("   要取断语，加 --event（求财／失物／行人／疾病／官事／出行／求谋／交易／婚姻／宅舍）。")
    if raw:
        lines.append("")
        lines.append("五、原诀（内部核对，不得对客户原文输出）")
        for tag, p in (("起因", m), ("过程", d), ("结局", h)):
            lines.append("   %s·%s：%s" % (tag, p["name"], YUANJUE[p["name"]]))
        nxt = "六"
    else:
        nxt = "五"
    lines.append("")
    lines.append("%s、边界" % nxt)
    lines.append("   六宫五行／方位／六神为通行本配属，各本有异，只影响怎么讲，不影响怎么算。")
    lines.append("   只答起、过程、落点；不答为什么、该怎么办。要后者转奇门（16）或四柱（01–03）。")
    lines.append("   同一事当日重占取第一课；本课不构成医疗、投资、法律建议。")
    text = "\n".join(lines)
    # --raw 是内部核对通道：加警示但不拦（原诀本身就含禁语，这正是要拦的原因）
    if raw:
        return "⚠ 内部核对稿：下列原诀含本馆禁语，不得对客户原文输出。\n\n" + text
    return guard(text)


def selftest():
    """复算 74 §5.3 的两个例子。"""
    m, d, h = cast_from_lunar(6, 5, 4)  # 六月初五辰时
    got = (palace(m)["name"], palace(d)["name"], palace(h)["name"])
    assert got == ("空亡", "赤口", "留连"), got
    m2, d2, h2 = cast_from_lunar(1, 1, 0)
    assert (m2, d2, h2) == (0, 0, 0)
    idx, s, n = cast_from_number(1436)
    assert (idx, s, n) == (4, 11, 4), (idx, s, n)
    # 边界：所有组合都能算出且落在六宫
    for mo in range(1, 13):
        for da in range(1, 31):
            for sh in range(12):
                a, b, c = cast_from_lunar(mo, da, sh)
                assert 0 <= a < 6 and 0 <= b < 6 and 0 <= c < 6
    print("selftest OK：六月初五辰时＝空亡/赤口/留连；正月初一子时＝三安；活数 1436＝小吉")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="小六壬确定性起课（离线）")
    ap.add_argument("date", nargs="?", help="公历 YYYY-MM-DD")
    ap.add_argument("time", nargs="?", default="12:00", help="时刻 HH:MM，默认 12:00")
    ap.add_argument("--lunar", nargs=3, metavar=("MONTH", "DAY", "SHICHEN"),
                    help="直接给农历月 日 时辰（如 --lunar 6 5 辰），跳过历法换算")
    ap.add_argument("--number", help="活数起课，如 1436")
    ap.add_argument("--event", default="", help="事类，仅用于标注，不参与计算")
    ap.add_argument("--late-zi", choices=["same", "next"], default="same",
                    help="晚子时（23:00–23:59）口径：same=算当日（默认），next=算次日")
    ap.add_argument("--raw", action="store_true", help="附原诀（内部核对用）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    meta = {}
    if a.event:
        meta["事类"] = a.event + "（仅决定取哪条断语，不参与计算）"

    if a.number:
        idx, s, n = cast_from_number(a.number)
        meta["起课法"] = "活数起课"
        meta["活数"] = "%s → 诸位和 %d −（%d−1）＝ %d" % (a.number, s + n - 1, n, s)
        m_pal = d_pal = h_pal = idx
        meta["备注"] = "活数法只出一宫，无三宫分工"
    elif a.lunar:
        try:
            month, day, sc = int(a.lunar[0]), int(a.lunar[1]), a.lunar[2]
        except ValueError:
            ap.error("--lunar 需为：月 日 时辰（时辰用子丑寅…亥）")
        if sc not in SHICHEN:
            ap.error("时辰须为十二支之一：%s" % "".join(SHICHEN))
        if not (1 <= month <= 12 and 1 <= day <= 30):
            ap.error("农历月 1–12、日 1–30")
        m_pal, d_pal, h_pal = cast_from_lunar(month, day, SHICHEN.index(sc))
        meta["起课法"] = "掌上起课（农历直接给）"
        meta["农历"] = "%d 月 %d 日 %s 时" % (month, day, sc)
    else:
        if not a.date:
            ap.error("请给公历日期（YYYY-MM-DD）或 --lunar / --number")
        y, mo, dy = (int(x) for x in a.date.split("-"))
        try:
            hh, mi = (int(x) for x in a.time.split(":"))
        except ValueError:
            ap.error("时刻格式 HH:MM")
        lm, ld, leap = solar_to_lunar(y, mo, dy)
        sc_idx = hour_to_shichen(hh)
        meta["起课法"] = "掌上起课（公历换算）"
        meta["公历"] = "%04d-%02d-%02d %02d:%02d" % (y, mo, dy, hh, mi)
        if hh == 23 and a.late_zi == "next":
            nxt = _date(y, mo, dy) + timedelta(days=1)
            lm, ld, leap = solar_to_lunar(nxt.year, nxt.month, nxt.day)
            meta["晚子时"] = "按次日算（晚子时归次日派）"
        elif hh == 23:
            meta["晚子时"] = "按当日算（本馆默认）；另有归次日派，课式会移一位"
        meta["农历"] = "%s%d 月 %d 日 %s 时" % ("闰" if leap else "", lm, ld, SHICHEN[sc_idx])
        if leap:
            meta["闰月口径"] = "闰月按本月算；若按次月派，宫位会移一位（流派差异，不作对错）"
        m_pal, d_pal, h_pal = cast_from_lunar(lm, ld, sc_idx)

    if a.json:
        out = {
            "meta": meta,
            "palaces": [palace(m_pal), palace(d_pal), palace(h_pal)],
            "reading": {
                "cause": palace(m_pal)["name"],
                "process": palace(d_pal)["name"],
                "outcome": palace(h_pal)["name"],
            },
            "yuanjue_softened": {
                "cause": soften(YUANJUE[palace(m_pal)["name"]]),
                "process": soften(YUANJUE[palace(d_pal)["name"]]),
                "outcome": soften(YUANJUE[palace(h_pal)["name"]]),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(render(m_pal, d_pal, h_pal, meta, raw=a.raw, event=a.event))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as e:
        print("起课失败：%s" % e, file=sys.stderr)
        sys.exit(2)
