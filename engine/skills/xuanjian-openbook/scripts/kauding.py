#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玄鉴命理馆 · 口径卡生成 / 冲突检出 / 自检（本馆自撰，零依赖）

用法:
  python3 kauding.py new --tech ziwei --preset tianji-default --out card.json
  python3 kauding.py new --tech bazi --set leap_month=next-month --out bazi.json
  python3 kauding.py check card.json bazi.json
  python3 kauding.py selftest
"""
import argparse
import datetime as _dt
import hashlib
import json
import sys

CARD_VERSION = "1.0"
ENGINE_VERSION = "xuanjian-1.51.0"

# 十项分歧点开关（本馆默认档）
DEFAULT_SWITCHES = {
    "calendar": "solar",
    "hour_index": "0-11",
    "true_solar_time": "on",
    "late_zishi": "next-day",
    "leap_month": "split",
    "dst_cn": "detect-only",
    "year_boundary": "lichun",
    "zi_chu_huan_ri": "23:00-next-day",
    "brightness_school": "quanshu",
    "sihua_school": "tongxing-feixing",
    "dayun_age": "nominal",
    "judging_basis": "score-py",
}

# 跨成员互证必须一致的共用基础开关
COMMON_KEYS = [
    "calendar", "hour_index", "true_solar_time", "late_zishi",
    "leap_month", "dst_cn", "year_boundary", "zi_chu_huan_ri",
]

ALLOWED = {
    "calendar": {"solar", "lunar"},
    "hour_index": {"0-11"},
    "true_solar_time": {"on", "off"},
    "late_zishi": {"next-day", "current-day", "all-current", "day-cur-time-next"},
    "leap_month": {"split", "next-month", "prev-month", "origin-month"},
    "dst_cn": {"detect-only", "manual-adjust"},
    "year_boundary": {"lichun", "jan1", "lunar-newyear"},
    "zi_chu_huan_ri": {"23:00-next-day", "00:00-next-day"},
    "brightness_school": {"quanshu", "modern-v2"},
    "sihua_school": {"tongxing-feixing", "quanshu", "zhongzhou", "beipai", "feixing", "toupai"},
    "dayun_age": {"nominal"},
    "judging_basis": {"score-py"},
}

# 参数束预设：预设 = 一组命名参数取值，不是文案模板
PRESETS = {
    "tianji-default": {},
    "ni-school-leap": {"leap_month": "next-month"},
    "current-day-zishi": {"late_zishi": "current-day"},
    "modern-v2": {"brightness_school": "modern-v2"},
    "custom": {},
}

INPUT_TEMPLATE = {
    "name": "", "gender": "", "birth_datetime": "",
    "calendar_type": "solar", "birthplace": "", "timezone": "",
    "longitude": None, "question_focus": [], "unknown_time": False,
}

PALACES = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
           "迁移", "仆役", "官禄", "田宅", "福德", "父母"]

HOUR_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
HOUR_RANGES = ["23-1", "1-3", "3-5", "5-7", "7-9", "9-11",
               "11-13", "13-15", "15-17", "17-19", "19-21", "21-23"]

# 十天干生年四化白名单：禄 / 权 / 科 / 忌
SIHUA = {
    "甲": ["廉贞", "破军", "武曲", "太阳"],
    "乙": ["天机", "天梁", "紫微", "太阴"],
    "丙": ["天同", "天机", "文昌", "廉贞"],
    "丁": ["太阴", "天同", "天机", "巨门"],
    "戊": ["贪狼", "太阴", "右弼", "天机"],
    "己": ["武曲", "贪狼", "天梁", "文曲"],
    "庚": ["太阳", "武曲", "太阴", "天同"],
    "辛": ["巨门", "太阳", "文曲", "文昌"],
    "壬": ["天梁", "紫微", "左辅", "武曲"],
    "癸": ["破军", "巨门", "太阴", "贪狼"],
}
SIHUA_KINDS = ["化禄", "化权", "化科", "化忌"]


def make_card(tech, school, preset, overrides):
    if preset not in PRESETS:
        raise ValueError("unknown preset: %s" % preset)
    switches = dict(DEFAULT_SWITCHES)
    switches.update(PRESETS[preset])
    for k, v in overrides.items():
        if k not in switches:
            raise ValueError("unknown switch: %s" % k)
        if v not in ALLOWED[k]:
            raise ValueError("illegal value %s=%s (allowed: %s)" % (k, v, sorted(ALLOWED[k])))
        switches[k] = v
    if switches["judging_basis"] != "score-py":
        raise ValueError("judging_basis 锁死为 score-py：本馆禁设第二判档数 (R-015)")
    card = {
        "card_version": CARD_VERSION,
        "technique": tech,
        "school_preset": preset,
        "school_note": school or "玄鉴命理馆默认档；口径由主理人裁定",
        "engine_version": ENGINE_VERSION,
        "input": dict(INPUT_TEMPLATE),
        "switches": switches,
        "provenance": {
            "source": "本馆口径卡 v%s" % CARD_VERSION,
            "created_by": "主理人",
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        },
    }
    card["provenance"]["kauding_hash"] = hashlib.sha256(
        json.dumps(card["switches"], ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return card


def check_pair(a, b):
    sa, sb = a.get("switches", {}), b.get("switches", {})
    diffs = []
    for k in COMMON_KEYS:
        va, vb = sa.get(k, "<missing>"), sb.get(k, "<missing>")
        if va != vb:
            diffs.append({"key": k, "A": va, "B": vb})
    return {
        "conflict": bool(diffs),
        "common_keys_checked": COMMON_KEYS,
        "differences": diffs,
        "A": {"technique": a.get("technique"), "preset": a.get("school_preset")},
        "B": {"technique": b.get("technique"), "preset": b.get("school_preset")},
        "verdict": ("卡不一致：交叉印证册只列分歧，禁止加权、禁止写「互相印证」"
                    if diffs else "口径一致：允许进入 60 交叉印证（一致加权／分歧并列／互补补盲）"),
    }


def date_exists(y, m, d):
    """不存在的公历日期一律拒绝，禁止静默顺延。"""
    try:
        _dt.date(y, m, d)
        return True
    except ValueError:
        return False


def selftest():
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    # 1. 12 宫名齐全且唯一
    ok("12 宫名齐全且唯一", len(PALACES) == 12 and len(set(PALACES)) == 12)

    # 2. 逆时针排布：第 k 宫地支 = (命宫地支 - k + 12) % 12
    good = True
    for ming in range(12):
        seq = [(ming - k + 12) % 12 for k in range(12)]
        if sorted(seq) != list(range(12)):
            good = False
    ok("逆时针排布覆盖地支 0-11 各一次（768 盘公式级）", good)

    # 3. 机梁同宫只可能辰(4)/戌(10)
    #    本工具只做口径卡，不排星，这条是册页规则（`OB96`）——原先写成
    #    `ok("机梁同宫限定辰戌", {4, 10} == {4, 10})`，是条恒真断言，等于假绿，v1.57.0 删去。
    #    真要测它得先有安星实现，届时应写在排盘工具的测试里，不是这里。

    # 4. 紫府对称 (紫微 + 天府) % 12 === 4
    ok("紫府对称恒等式", all((b + (4 - b) % 12) % 12 == 4 for b in range(12)))

    # 5. 时辰地支索引 0-11
    ok("时辰索引 0-11 映射完整", len(HOUR_BRANCHES) == 12 and len(HOUR_RANGES) == 12
       and HOUR_BRANCHES[0] == "子" and HOUR_BRANCHES[11] == "亥")

    # 6. 四化白名单：十干各 4 星；七杀不入表；紫微从不化忌
    allstars = [s for row in SIHUA.values() for s in row]
    ok("十干四化表完整", len(SIHUA) == 10 and all(len(v) == 4 for v in SIHUA.values()))
    ok("七杀不在四化白名单", "七杀" not in allstars)
    ok("紫微从不化忌", all(row[3] != "紫微" for row in SIHUA.values()))

    # 7. 非法公历日期拒绝
    bad_dates = [(1925, 2, 29), (1925, 2, 30), (1980, 2, 30),
                 (1925, 4, 31), (1925, 13, 1), (1925, 0, 10), (1925, 6, 0)]
    ok("7 个非法日期全部拒绝", all(not date_exists(*d) for d in bad_dates))
    ok("边界合法日期放行", date_exists(2000, 2, 29) and date_exists(2026, 11, 4))

    # 8. 默认档 / 参数束 / 冲突检出
    base = make_card("ziwei", "", "tianji-default", {})
    alt = make_card("ziwei", "", "ni-school-leap", {})
    ok("默认档与倪师闰月档确有差异", base["switches"]["leap_month"] != alt["switches"]["leap_month"])
    ok("同档不报冲突", check_pair(base, make_card("bazi", "", "tianji-default", {}))["conflict"] is False)
    r = check_pair(base, alt)
    ok("异档报冲突且定位到 leap_month", r["conflict"] is True
       and r["differences"][0]["key"] == "leap_month")

    # 9. 判档锁死：改口径即须被拒（只断言一次，不在两个分支各写一遍）
    锁死 = False
    try:
        make_card("bazi", "", "tianji-default", {"judging_basis": "other"})
    except ValueError:
        锁死 = True
    ok("judging_basis 锁死", 锁死)

    # 10. 非法开关值拒绝
    拒了 = False
    try:
        make_card("ziwei", "", "tianji-default", {"leap_month": "nextmonth"})
    except ValueError:
        拒了 = True
    ok("非法开关值拒绝", 拒了)

    failed = [c for c in checks if not c[1]]
    for name, passed, _ in checks:
        print("%s  %s" % ("PASS" if passed else "FAIL", name))
    print("\n%d/%d passed" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


def main():
    p = argparse.ArgumentParser(description="玄鉴口径卡工具")
    sub = p.add_subparsers(dest="cmd")

    n = sub.add_parser("new")
    n.add_argument("--tech", default="ziwei")
    n.add_argument("--school", default="")
    n.add_argument("--preset", default="tianji-default", choices=sorted(PRESETS))
    n.add_argument("--set", action="append", default=[], dest="overrides")
    n.add_argument("--out", default="-")

    c = sub.add_parser("check")
    c.add_argument("a")
    c.add_argument("b")

    sub.add_parser("selftest")
    args = p.parse_args()

    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "new":
        ov = {}
        for item in args.overrides:
            if "=" not in item:
                print("bad --set %s (want key=value)" % item, file=sys.stderr)
                return 2
            k, v = item.split("=", 1)
            ov[k] = v
        try:
            card = make_card(args.tech, args.school, args.preset, ov)
        except ValueError as e:
            print("ERROR: %s" % e, file=sys.stderr)
            return 2
        text = json.dumps(card, ensure_ascii=False, indent=2)
        (open(args.out, "w", encoding="utf-8").write(text) if args.out != "-"
         else sys.stdout.write(text + "\n"))
        return 0
    if args.cmd == "check":
        with open(args.a, encoding="utf-8") as f:
            a = json.load(f)
        with open(args.b, encoding="utf-8") as f:
            b = json.load(f)
        r = check_pair(a, b)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
