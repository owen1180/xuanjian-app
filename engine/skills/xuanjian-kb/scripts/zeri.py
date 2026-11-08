#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""择日：建除十二神与黄黑道（玄鉴命理馆 · 见 references/83）

只用标准库 + sxtwl。离线、不写盘、不联网。

用法：
  python3 zeri.py 2026-11-02                      # 单日：建除、黄黑道、离决、冲煞
  python3 zeri.py 2026-11-02 --zhi 卯 --dir 北     # 加：冲命主、三煞方
  python3 zeri.py --range 2026-11-01 2026-11-10 --use 入宅
  python3 zeri.py --selftest

口径（写死在代码里）：
  1. 月建按节气月（立春/惊蛰…为界），不按农历月；
  2. 建除以月建为「建」，日支顺行；
  3. 黄黑道以月支起青龙，顺行十二神；
  4. 只出「宜／慎／避」三档参考，不判吉凶、不承诺成败。
"""

import argparse
import json
import sys
from datetime import date, timedelta

JQ = ["冬至", "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨", "立夏",
      "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑", "白露", "秋分", "寒露",
      "霜降", "立冬", "小雪", "大雪"]

ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 建除十二神（以月建为建，顺行）
JIANCHU = ["建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭"]

# 建除宜忌（通行本摘要；各家通书有出入，只取大方向）
JIANCHU_YI = {
    "建": ("出行、上任、见贵、祈福", "动土、开仓、掘井、乘船"),
    "除": ("扫舍、除服、疗病、解除", "出行、赴任、求财"),
    "满": ("祭祀、祈福、开市、结亲", "赴任、求医、服药"),
    "平": ("修饰垣墙、平治道涂、嫁娶", "开渠、栽种、求医"),
    "定": ("嫁娶、订盟、开市、入宅、安床", "诉讼、出行"),
    "执": ("捕捉、纳畜、修造", "开市、出行、搬迁"),
    "破": ("破屋坏垣、求医治病", "嫁娶、开市、动土、入宅、安葬"),
    "危": ("安床、祭祀、祈福", "登高、出行、乘船"),
    "成": ("嫁娶、开市、入宅、动土、安葬", "诉讼、争斗"),
    "收": ("纳财、进人口、捕捉", "开仓、出行、安葬"),
    "开": ("开市、交易、出行、求医、入学", "安葬、动土"),
    "闭": ("筑堤、埋穴、填补、修坟", "开市、出行、求医、开仓"),
}

# 黄黑道十二神（顺行）
HUANGHEI = [("青龙", True), ("明堂", True), ("天刑", False), ("朱雀", False),
            ("金匮", True), ("天德", True), ("白虎", False), ("玉堂", True),
            ("天牢", False), ("玄武", False), ("司命", True), ("勾陈", False)]

# 离日：二分二至前一日；决日：四立前一日
LI_IDX = {6: "春分", 12: "夏至", 18: "秋分", 0: "冬至"}
JUE_IDX = {3: "立春", 9: "立夏", 15: "立秋", 21: "立冬"}

# 三煞方（按年支三合局）
SAN_SHA = {"寅": "北", "午": "北", "戌": "北",
           "申": "南", "子": "南", "辰": "南",
           "亥": "西", "卯": "西", "未": "西",
           "巳": "东", "酉": "东", "丑": "东"}
SHA_FANG = {"北": ["亥", "子", "丑"], "南": ["巳", "午", "未"],
            "西": ["申", "酉", "戌"], "东": ["寅", "卯", "辰"]}

# 用事类别 → 关心的建除神（宜）与忌讳神
USE_KEYS = ["入宅", "开业", "动土", "嫁娶", "安葬", "出行", "求医", "签约"]


def _jdn_day_gz(y, m, d):
    """日干支序号 0–59（甲子=0）：儒略日公式，纯算，与 sxtwl.getDayGZ 一致。"""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    return (jdn - 2433191) % 60


def day_info(y, m, d):
    try:
        import sxtwl
        day = sxtwl.fromSolar(y, m, d)
        dgz = day.getDayGZ()
        mgz = day.getMonthGZ()
        return {
            "date": date(y, m, d),
            "day_gan": GAN[dgz.tg], "day_zhi": ZHI[dgz.dz],
            "month_gan": GAN[mgz.tg], "month_zhi": ZHI[mgz.dz],
            "jieqi": (JQ[day.getJieQi()], day.getJieQi()) if day.hasJieQi() else None,
        }
    except Exception:
        pass
    # 离线兜底：纯数据表（不含 sxtwl）
    import _lunar_data
    dg = _jdn_day_gz(y, m, d)
    mgz = _lunar_data.month_gz_of(y, m, d)
    return {
        "date": date(y, m, d),
        "day_gan": GAN[dg % 10], "day_zhi": ZHI[dg % 12],
        "month_gan": mgz[0], "month_zhi": mgz[1],
        "jieqi": _lunar_data.jieqi_on(y, m, d),
    }


def jianchu_of(day_zhi, month_zhi):
    i = (ZHI.index(day_zhi) - ZHI.index(month_zhi)) % 12
    return JIANCHU[i], i


def huanghei_of(day_zhi, month_zhi):
    start = ((ZHI.index(month_zhi) - 2) * 2) % 12
    i = (ZHI.index(day_zhi) - start) % 12
    name, yellow = HUANGHEI[i]
    return name, yellow, i, ZHI[start]


def liminal(y, m, d):
    """返回（是否离日/决日, 依据节气名, 明日或今日）。判的是"某节气的前一日"。"""
    nxt = date(y, m, d) + timedelta(days=1)
    try:
        import sxtwl
        day = sxtwl.fromSolar(nxt.year, nxt.month, nxt.day)
        if not day.hasJieQi():
            return None
        idx = day.getJieQi()
        if idx in LI_IDX:
            return ("离日", LI_IDX[idx], nxt)
        if idx in JUE_IDX:
            return ("决日", JUE_IDX[idx], nxt)
        return None
    except Exception:
        pass
    # 离线兜底：纯数据表（不含 sxtwl）
    import _lunar_data
    return _lunar_data.next_liminal(y, m, d)


def assess(info, zhi=None, direction=None):
    zc, _ = jianchu_of(info["day_zhi"], info["month_zhi"])
    hh, yellow, _, start = huanghei_of(info["day_zhi"], info["month_zhi"])
    lim = liminal(info["date"].year, info["date"].month, info["date"].day)

    flags = []
    level = "宜"
    reasons = []

    if lim:
        level = "避"
        flags.append(lim[0])
        reasons.append("%s前一日（%s），人气最弱，不宜办大事" % (lim[0], lim[1]))

    if zhi:
        chong = ZHI[(ZHI.index(zhi) + 6) % 12]
        if info["day_zhi"] == chong:
            level = "避"
            flags.append("冲命主")
            reasons.append("日支%s冲命主%s" % (info["day_zhi"], zhi))

    # 岁破／月破
    year_zhi = info.get("year_zhi")
    if year_zhi and (ZHI.index(info["day_zhi"]) - ZHI.index(year_zhi)) % 12 == 6:
        flags.append("岁破")
        reasons.append("日支冲太岁（%s）" % year_zhi)
        if level == "宜":
            level = "慎"
    if (ZHI.index(info["day_zhi"]) - ZHI.index(info["month_zhi"])) % 12 == 6:
        flags.append("月破")
        reasons.append("日支冲月建（%s）" % info["month_zhi"])
        if level == "宜":
            level = "慎"

    if zc == "破":
        flags.append("破日")
        reasons.append("建除值破，宜破旧不宜立新")
        if level == "宜":
            level = "慎"
    if zc in ("危", "闭"):
        reasons.append("建除值%s，宜收不宜开" % zc)
        if level == "宜":
            level = "慎"

    if not yellow:
        flags.append("黑道")
        reasons.append("黄黑道值%s（黑道）" % hh)
        if level == "宜":
            level = "慎"
    else:
        reasons.append("黄黑道值%s（黄道）" % hh)

    if direction:
        fang = SAN_SHA.get(year_zhi) if year_zhi else None
        if fang and direction == fang:
            flags.append("三煞方")
            reasons.append("年支%s，三煞在%s，此方不宜动土" % (year_zhi, fang))
            if level == "宜":
                level = "慎"

    yi, ji = JIANCHU_YI[zc]
    return {
        "jianchu": zc, "huanghei": hh, "yellow": yellow, "start": start,
        "liminal": lim, "flags": flags, "level": level,
        "reasons": reasons, "yi": yi, "ji": ji,
    }


def render(rows, use=None):
    L = []
    head = "【择日 · 建除与黄黑道】"
    L.append(head)
    for r in rows:
        i = r["info"]
        a = r["assess"]
        L.append("")
        L.append("%s　%s%s日　月建%s" % (i["date"].isoformat(), i["day_gan"], i["day_zhi"], i["month_zhi"]))
        if i["jieqi"]:
            L.append("   节气：今日%s" % i["jieqi"][0])
        L.append("   建除：%s日　｜　黄黑道：%s（%s，起%s）" % (
            a["jianchu"], a["huanghei"], "黄道" if a["yellow"] else "黑道", a["start"]))
        L.append("   宜：%s" % a["yi"])
        L.append("   忌：%s" % a["ji"])
        if a["liminal"]:
            L.append("   ⚠ %s：明日%s" % (a["liminal"][0], a["liminal"][1]))
        if a["flags"]:
            L.append("   标记：%s" % "、".join(a["flags"]))
        L.append("   参考等级：%s" % a["level"])
        for why in a["reasons"]:
            L.append("     · %s" % why)
        if use:
            if use in a["ji"]:
                note = "在忌栏（不宜）"
            elif use in a["yi"]:
                note = "在宜栏（合）"
            else:
                note = "两栏均未列（自行斟酌）"
            L.append("   用事对照：%s → %s" % (use, note))
    L.append("")
    L.append("【边界】")
    L.append("   三档只表示「合不合通书」，不表示事情成不成；日子是条件之一，不是开关。")
    L.append("   遇避档另择；遇慎档可办小事，大事另选；黄道不等于万事吉，破日不等于必定凶。")
    L.append("   紫白日课、董公 144 条、正体五行造命：本馆未开（83 §8）。")
    return "\n".join(L)


def selftest():
    a = day_info(2026, 11, 2)
    zc, _ = jianchu_of(a["day_zhi"], a["month_zhi"])
    hh, yellow, _, start = huanghei_of(a["day_zhi"], a["month_zhi"])
    assert (a["month_zhi"], a["day_zhi"]) == ("戌", "辰"), (a["month_zhi"], a["day_zhi"])
    assert zc == "破", zc
    assert (hh, yellow, start) == ("青龙", True, "辰"), (hh, yellow, start)
    # 决日：2026-11-06 为立冬（11-07）前一日
    assert liminal(2026, 11, 6)[0] == "决日", liminal(2026, 11, 6)
    # 离日：2026-03-19 为春分（03-20）前一日
    assert liminal(2026, 3, 19)[0] == "离日", liminal(2026, 3, 19)
    # 建除十二神：同一个节气月内连续 12 日应遍历十二神
    # （2026-11-08 立冬后、11-22 小雪前，全在亥月）
    seen = set()
    for k in range(12):
        x = day_info(2026, 11, 8 + k)
        assert x["month_zhi"] == "亥", (x["date"], x["month_zhi"])
        seen.add(jianchu_of(x["day_zhi"], x["month_zhi"])[0])
    assert len(seen) == 12, seen
    # 黄黑道：每月起神符合 寅申子／卯酉寅／辰戌辰／巳亥午／子午申／丑未戌
    for mz, want in [("寅", "子"), ("申", "子"), ("卯", "寅"), ("酉", "寅"),
                     ("辰", "辰"), ("戌", "辰"), ("巳", "午"), ("亥", "午"),
                     ("子", "申"), ("午", "申"), ("丑", "戌"), ("未", "戌")]:
        assert huanghei_of("子", mz)[3] == want, (mz, want, huanghei_of("子", mz))
    print("selftest OK：戌月辰日＝破日／黄道青龙；离决判定与十二神轮值皆对")


def parse_zhi(s):
    if s in ZHI:
        return s
    raise ValueError("地支须为：%s" % "".join(ZHI))


def main(argv=None):
    ap = argparse.ArgumentParser(description="择日：建除十二神与黄黑道（离线）")
    ap.add_argument("date", nargs="?", help="公历 YYYY-MM-DD")
    ap.add_argument("--range", nargs=2, metavar=("START", "END"), help="区间，如 2026-11-01 2026-11-10")
    ap.add_argument("--zhi", help="命主生年支（子丑…亥），用于判冲")
    ap.add_argument("--dir", help="动土方位（东南西北），用于判三煞")
    ap.add_argument("--use", choices=USE_KEYS, help="用事类别")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    zhi = parse_zhi(a.zhi) if a.zhi else None

    if a.range:
        y1, m1, d1 = (int(x) for x in a.range[0].split("-"))
        y2, m2, d2 = (int(x) for x in a.range[1].split("-"))
        cur, end = date(y1, m1, d1), date(y2, m2, d2)
        if end < cur:
            ap.error("区间终点早于起点")
        if (end - cur).days > 60:
            ap.error("区间最多 60 天")
        days = []
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)
    else:
        if not a.date:
            ap.error("请给日期，或用 --range / --selftest")
        y, m, d = (int(x) for x in a.date.split("-"))
        days = [date(y, m, d)]

    rows = []
    for dd in days:
        info = day_info(dd.year, dd.month, dd.day)
        # 年支：以立春为界的年干支（黄历岁破/三煞用）
        try:
            import sxtwl
            ygz = sxtwl.fromSolar(dd.year, dd.month, dd.day).getYearGZ()
            info["year_zhi"] = ZHI[ygz.dz]
        except Exception:
            import _lunar_data
            info["year_zhi"] = _lunar_data.year_zhi_of(dd.year, dd.month, dd.day)
        rows.append({"info": info, "assess": assess(info, zhi, a.dir)})

    if a.json:
        out = []
        for r in rows:
            i, s = r["info"], r["assess"]
            out.append({
                "date": i["date"].isoformat(), "ganzhi": i["day_gan"] + i["day_zhi"],
                "month_zhi": i["month_zhi"], "year_zhi": i["year_zhi"],
                "jianchu": s["jianchu"], "huanghei": s["huanghei"],
                "yellow": s["yellow"], "flags": s["flags"], "level": s["level"],
                "yi": s["yi"], "ji": s["ji"], "reasons": s["reasons"],
            })
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(render(rows, a.use))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as e:
        print("择日失败：%s" % e, file=sys.stderr)
        sys.exit(2)
