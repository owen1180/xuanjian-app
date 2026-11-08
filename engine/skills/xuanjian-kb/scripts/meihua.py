#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""梅花易数确定性起卦（玄鉴命理馆 · 见 references/82 §5）

只用标准库 + sxtwl（仅公历转农历时需要）。离线、不写盘、不联网。

用法：
  python3 meihua.py 2026-11-02 14:30          # 时间起卦（公历自动转农历）
  python3 meihua.py --lunar 9 24 未           # 直接给农历月日时辰
  python3 meihua.py --number 37 58            # 报数起卦（两数）
  python3 meihua.py --selftest                # 自检：64 卦表 + 互变校验

纪律：
  1. 起卦用先天数，判方位用后天数——两套不许混（82 §4）；
  2. 脚本只出卦象、体用与生克关系，**不出断语**；断语归人（82 §5.5）；
  3. 一卦只断一象，不许拿它断六亲、断一生。
"""

import argparse
import sys

# 先天数 → 卦（1 乾 2 兑 3 离 4 震 5 巽 6 坎 7 艮 8 坤）
TRIGRAMS = {
    1: {"name": "乾", "sym": "☰", "wu": "金", "lines": [1, 1, 1], "nature": "天", "dir": "西北", "fam": "父"},
    2: {"name": "兑", "sym": "☱", "wu": "金", "lines": [1, 1, 0], "nature": "泽", "dir": "西", "fam": "少女"},
    3: {"name": "离", "sym": "☲", "wu": "火", "lines": [1, 0, 1], "nature": "火", "dir": "南", "fam": "中女"},
    4: {"name": "震", "sym": "☳", "wu": "木", "lines": [1, 0, 0], "nature": "雷", "dir": "东", "fam": "长男"},
    5: {"name": "巽", "sym": "☴", "wu": "木", "lines": [0, 1, 1], "nature": "风", "dir": "东南", "fam": "长女"},
    6: {"name": "坎", "sym": "☵", "wu": "水", "lines": [0, 1, 0], "nature": "水", "dir": "北", "fam": "中男"},
    7: {"name": "艮", "sym": "☶", "wu": "土", "lines": [0, 0, 1], "nature": "山", "dir": "东北", "fam": "少男"},
    8: {"name": "坤", "sym": "☷", "wu": "土", "lines": [0, 0, 0], "nature": "地", "dir": "西南", "fam": "母"},
}

# 六十四卦名（上卦数, 下卦数）
HEX = {
    (1, 1): "乾为天", (1, 2): "天泽履", (1, 3): "天火同人", (1, 4): "天雷无妄",
    (1, 5): "天风姤", (1, 6): "天水讼", (1, 7): "天山遁", (1, 8): "天地否",
    (2, 1): "泽天夬", (2, 2): "兑为泽", (2, 3): "泽火革", (2, 4): "泽雷随",
    (2, 5): "泽风大过", (2, 6): "泽水困", (2, 7): "泽山咸", (2, 8): "泽地萃",
    (3, 1): "火天大有", (3, 2): "火泽睽", (3, 3): "离为火", (3, 4): "火雷噬嗑",
    (3, 5): "火风鼎", (3, 6): "火水未济", (3, 7): "火山旅", (3, 8): "火地晋",
    (4, 1): "雷天大壮", (4, 2): "雷泽归妹", (4, 3): "雷火丰", (4, 4): "震为雷",
    (4, 5): "雷风恒", (4, 6): "雷水解", (4, 7): "雷山小过", (4, 8): "雷地豫",
    (5, 1): "风天小畜", (5, 2): "风泽中孚", (5, 3): "风火家人", (5, 4): "风雷益",
    (5, 5): "巽为风", (5, 6): "风水涣", (5, 7): "风山渐", (5, 8): "风地观",
    (6, 1): "水天需", (6, 2): "水泽节", (6, 3): "水火既济", (6, 4): "水雷屯",
    (6, 5): "水风井", (6, 6): "坎为水", (6, 7): "水山蹇", (6, 8): "水地比",
    (7, 1): "山天大畜", (7, 2): "山泽损", (7, 3): "山火贲", (7, 4): "山雷颐",
    (7, 5): "山风蛊", (7, 6): "山水蒙", (7, 7): "艮为山", (7, 8): "山地剥",
    (8, 1): "地天泰", (8, 2): "地泽临", (8, 3): "地火明夷", (8, 4): "地雷复",
    (8, 5): "地风升", (8, 6): "地水师", (8, 7): "地山谦", (8, 8): "坤为地",
}

SHICHEN = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ZHI_NUM = {z: i + 1 for i, z in enumerate(SHICHEN)}       # 子1…亥12
WU_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WU_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

SEASON_WANG = {  # 时令旺衰（简法）
    "春": "木", "夏": "火", "秋": "金", "冬": "水", "四季": "土",
}


def tri_by_lines(lines):
    for k, v in TRIGRAMS.items():
        if v["lines"] == list(lines):
            return k
    raise ValueError("非法三爻：%s" % lines)


def build(upper, lower):
    """返回六爻，自初爻至上爻：下卦三爻在前，上卦三爻在后。"""
    return TRIGRAMS[lower]["lines"] + TRIGRAMS[upper]["lines"]


def mutual(lines):
    lower_i = tri_by_lines(lines[1:4])
    upper_i = tri_by_lines(lines[2:5])
    return upper_i, lower_i


def change(lines, moving):
    out = list(lines)
    out[moving - 1] = 1 - out[moving - 1]
    return out


def relation(body_wu, use_wu):
    if body_wu == use_wu:
        return "比和", "吉：同类相合，平稳"
    if WU_SHENG[use_wu] == body_wu:
        return "用生体", "吉：有外力相助，事顺"
    if WU_SHENG[body_wu] == use_wu:
        return "体生用", "耗：自己出力，付出多"
    if WU_KE[body_wu] == use_wu:
        return "体克用", "吉但费力：能成，要使力"
    if WU_KE[use_wu] == body_wu:
        return "用克体", "凶：受制受阻，重则事难成"
    return "未知", ""


def cast_time(y, m, d, hh, mi):
    try:
        import sxtwl
        day = sxtwl.fromSolar(y, m, d)
        lm = abs(day.getLunarMonth())
        ld = day.getLunarDay()
        ygz = day.getYearGZ()
        year_zhi = SHICHEN[ygz.dz]           # sxtwl 地支 0-based，子=0
    except Exception:
        # 离线兜底：纯数据表（不含 sxtwl）
        import _lunar_data
        ly, lm, ld, leap = _lunar_data.lunar_of(y, m, d)
        year_zhi = _lunar_data.year_zhi_of(y, m, d)   # 立春界年支
    sc_idx = ((hh + 1) // 2) % 12
    shichen = SHICHEN[sc_idx]
    return dict(lunar_month=lm, lunar_day=ld, year_zhi=year_zhi, shichen=shichen,
                year_zhi_num=ZHI_NUM[year_zhi], shichen_num=ZHI_NUM[shichen],
                note="%04d-%02d-%02d %02d:%02d" % (y, m, d, hh, mi))


def compute(upper, lower, moving, meta):
    lines = build(upper, lower)
    mu_up, mu_low = mutual(lines)
    ch = change(lines, moving)
    ch_up, ch_low = tri_by_lines(ch[3:6]), tri_by_lines(ch[0:3])

    # 体用：动爻所在之卦为用，另一为体（1–3 爻在下卦，4–6 爻在上卦）
    if moving <= 3:
        body, use = upper, lower
        body_pos, use_pos = "上卦", "下卦"
    else:
        body, use = lower, upper
        body_pos, use_pos = "下卦", "上卦"

    bw, uw = TRIGRAMS[body]["wu"], TRIGRAMS[use]["wu"]
    rel, judge = relation(bw, uw)
    mu_wu = TRIGRAMS[mu_up]["wu"] if TRIGRAMS[mu_up]["wu"] != bw else TRIGRAMS[mu_low]["wu"]
    ch_wu = TRIGRAMS[ch_up]["wu"]

    return {
        "meta": meta,
        "ben": {"name": HEX[(upper, lower)], "upper": TRIGRAMS[upper]["name"],
                "lower": TRIGRAMS[lower]["name"],
                "symbol": TRIGRAMS[upper]["sym"] + TRIGRAMS[lower]["sym"]},
        "moving": moving,
        "ti_yong": {"body": TRIGRAMS[body]["name"], "body_pos": body_pos, "body_wu": bw,
                    "use": TRIGRAMS[use]["name"], "use_pos": use_pos, "use_wu": uw,
                    "relation": rel, "judge": judge},
        "hu": {"name": HEX[(mu_up, mu_low)], "upper": TRIGRAMS[mu_up]["name"],
               "lower": TRIGRAMS[mu_low]["name"]},
        "bian": {"name": HEX[(ch_up, ch_low)], "upper": TRIGRAMS[ch_up]["name"],
                 "lower": TRIGRAMS[ch_low]["name"]},
        "lines_bottom_up": lines,
    }


def render(r):
    m = r["meta"]
    L = []
    L.append("【梅花易数 · 卦象】")
    L.append("一、起卦")
    for k in ("起卦法", "公历", "农历", "年支", "时辰", "数"):
        if m.get(k):
            L.append("   %s：%s" % (k, m[k]))
    L.append("")
    L.append("二、卦")
    L.append("   本卦：%s（上%s 下%s）%s" % (r["ben"]["name"], r["ben"]["upper"], r["ben"]["lower"], r["ben"]["symbol"]))
    L.append("   动爻：第 %d 爻" % r["moving"])
    L.append("   互卦：%s（上%s 下%s）—— 看过程" % (r["hu"]["name"], r["hu"]["upper"], r["hu"]["lower"]))
    L.append("   变卦：%s（上%s 下%s）—— 看结果" % (r["bian"]["name"], r["bian"]["upper"], r["bian"]["lower"]))
    L.append("")
    L.append("三、体用")
    ty = r["ti_yong"]
    L.append("   体：%s（%s，%s）" % (ty["body"], ty["body_pos"], ty["body_wu"]))
    L.append("   用：%s（%s，%s）" % (ty["use"], ty["use_pos"], ty["use_wu"]))
    L.append("   关系：%s —— %s" % (ty["relation"], ty["judge"]))
    L.append("")
    L.append("四、边界")
    L.append("   本脚本只出卦象、体用与生克，不出断语；断语归人（82 §5.5）。")
    L.append("   一卦只断一象：不许拿它断六亲、断一生、断金额。")
    L.append("   起卦用先天数、判方位用后天数；两套不许混（82 §4）。")
    return "\n".join(L)


def selftest():
    assert len(HEX) == 64, len(HEX)
    assert len(set(HEX.values())) == 64, "卦名有重复"
    # 乾为天：互卦仍是乾为天；初爻动 → 天风姤
    up, lo = 1, 1
    lines = build(up, lo)
    mu = mutual(lines)
    assert HEX[mu] == "乾为天", HEX[mu]
    ch = change(lines, 1)
    assert HEX[(tri_by_lines(ch[3:6]), tri_by_lines(ch[0:3]))] == "天风姤"
    # 水雷屯：互卦为山地剥（经典校验）
    lines = build(6, 4)
    assert HEX[mutual(lines)] == "山地剥", HEX[mutual(lines)]
    # 六十四卦全覆盖：每个上/下卦组合都取得到
    for u in range(1, 9):
        for l in range(1, 9):
            assert (u, l) in HEX
    # 体用：动爻在下卦 → 体为上卦
    r = compute(1, 6, 2, {})
    assert r["ti_yong"]["body_pos"] == "上卦"
    r = compute(1, 6, 5, {})
    assert r["ti_yong"]["body_pos"] == "下卦"
    print("selftest OK：64 卦表完整；乾之姤、屯互剥、体用定位皆对")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="梅花易数确定性起卦（离线）")
    ap.add_argument("date", nargs="?", help="公历 YYYY-MM-DD")
    ap.add_argument("time", nargs="?", default="12:00", help="时刻 HH:MM")
    ap.add_argument("--lunar", nargs=3, metavar=("MONTH", "DAY", "SHICHEN"))
    ap.add_argument("--number", nargs=2, metavar=("A", "B"), help="报数起卦（两个正整数）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    if a.number:
        try:
            n1, n2 = int(a.number[0]), int(a.number[1])
        except ValueError:
            ap.error("报数须为两个正整数")
        if n1 <= 0 or n2 <= 0:
            ap.error("报数须为正整数")
        upper = n1 % 8 or 8
        lower = n2 % 8 or 8
        moving = (n1 + n2) % 6 or 6
        meta = {"起卦法": "报数", "数": "%d、%d" % (n1, n2)}
    elif a.lunar:
        try:
            month, day, sc = int(a.lunar[0]), int(a.lunar[1]), a.lunar[2]
        except ValueError:
            ap.error("--lunar 需为：月 日 时辰")
        if sc not in SHICHEN:
            ap.error("时辰须为十二支之一：%s" % "".join(SHICHEN))
        yz = 1  # 未知年支时按子起，须显式声明
        total = yz + month + day
        upper = total % 8 or 8
        total2 = total + ZHI_NUM[sc]
        lower = total2 % 8 or 8
        moving = total2 % 6 or 6
        meta = {"起卦法": "时间（农历直接给）", "农历": "%d 月 %d 日 %s 时" % (month, day, sc),
                "年支": "未给（按子1计），若知年支请改用公历起卦"}
    else:
        if not a.date:
            ap.error("请给公历日期（YYYY-MM-DD）或 --lunar / --number")
        y, mo, dy = (int(x) for x in a.date.split("-"))
        hh, mi = (int(x) for x in a.time.split(":"))
        t = cast_time(y, mo, dy, hh, mi)
        total = t["year_zhi_num"] + t["lunar_month"] + t["lunar_day"]
        upper = total % 8 or 8
        total2 = total + t["shichen_num"]
        lower = total2 % 8 or 8
        moving = total2 % 6 or 6
        meta = {"起卦法": "时间（先天数）", "公历": t["note"],
                "农历": "%d 月 %d 日 %s 时" % (t["lunar_month"], t["lunar_day"], t["shichen"]),
                "年支": t["year_zhi"], "时辰": t["shichen"]}

    r = compute(upper, lower, moving, meta)
    if a.json:
        import json
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(render(r))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as e:
        print("起卦失败：%s" % e, file=sys.stderr)
        sys.exit(2)
