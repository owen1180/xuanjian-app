#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 102 · 起盘二十四铁律确定性校验器（照单全学 · 算法深度理解）。

来源机制：Renhuai123/ziwei-doushu 的 17 个回归测试与 CI 断言（源码研读报告
`11-ziwei-source.md` §3 共 24 条）。本文件为**本馆自撰**，只实现校验逻辑，
不复制任何外部源码；另补 4 条本馆定案级闸门（唯一判档、流派只读、事实分层、
本人寿元红线），合计 28 项。

纪律：
- 「校验用双源，输出用单源」；`judging_basis` 恒锁 `score-py`，不给双口径开后门。
- `reference_schools` 只读参考对照，绝不参与判档。
- 排盘事实与解读文本分层；模型/文案层不得回填确定性字段（册 `100` 第 6 条硬规矩）。

用法：
  cat card.json | python3 paipan_check.py check -
  python3 paipan_check.py from-row '<数据行 JSON>'
  python3 paipan_check.py --selftest
"""
import argparse
import datetime as dt
import json
import re
import sys

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
PALACES = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
           "迁移", "仆役", "官禄", "田宅", "福德", "父母"]
LEAP_POLICIES = {"split", "next-month", "prev-month", "origin-month"}
SIHUA_WHITELIST = {
    "甲": {"廉贞": "禄", "破军": "权", "武曲": "科", "太阳": "忌"},
    "乙": {"天机": "禄", "天梁": "权", "紫微": "科", "太阴": "忌"},
    "丙": {"天同": "禄", "天机": "权", "文昌": "科", "廉贞": "忌"},
    "丁": {"太阴": "禄", "天同": "权", "天机": "科", "巨门": "忌"},
    "戊": {"贪狼": "禄", "太阴": "权", "右弼": "科", "天机": "忌"},
    "己": {"武曲": "禄", "贪狼": "权", "天梁": "科", "文曲": "忌"},
    "庚": {"太阳": "禄", "武曲": "权", "太阴": "科", "天同": "忌"},
    "辛": {"巨门": "禄", "太阳": "权", "文曲": "科", "文昌": "忌"},
    "壬": {"天梁": "禄", "紫微": "权", "左辅": "科", "武曲": "忌"},
    "癸": {"破军": "禄", "巨门": "权", "太阴": "科", "贪狼": "忌"},
}
LEGAL_PAIRS = {(s, h) for row in SIHUA_WHITELIST.values() for s, h in row.items()}
FORBIDDEN = re.compile(r"(本人|命主).{0,12}(寿元|活到|死于|何时死|寿命)|必定大富|包生男")
RULE_NAMES = [
    "R01 时辰 0–11 整数", "R02 性别枚举", "R03 公历日期真实存在",
    "R04 晚子时归次日且时辰支 0", "R05 早子时不换日且时辰支 0",
    "R06 时辰不详不换日且时辰支 0", "R07 十二宫数量恰为 12",
    "R08 十二宫名齐全唯一", "R09 十二宫地支 0–11 各且仅一次",
    "R10 命宫唯一且标记一致", "R11 十二宫逆时针排布",
    "R12 机梁同宫只在辰(4)/戌(10)", "R13 紫府寅申轴对称",
    "R14 闰月 policy 四值白名单", "R15 红鸾天喜互为对宫",
    "R16 四化白名单（十干 40 组）", "R17 双四化同宫属正常",
    "R18 借宫须用结构化字段", "R19 闰月 policy 须回写盘面",
    "R20 夏令时只判定不自动扣时", "R21 立春边界年柱口径",
    "R22 空宫允许 ms=null", "R23 单一真值 judging_basis 锁死",
    "R24 流派只读不参与判档", "R25 事实／解读分层",
    "R26 禁止本人寿元与绝对化断言", "R27 键名与盘面一致",
    "R28 四柱／时辰同源",
]


def _ok(v, rule, note=""):
    return {"rule": rule, "pass": bool(v), "note": note}


def validate(card: dict) -> dict:
    """对一张盘面卡做 28 项确定性校验。字段缺省时按「未声明」跳过并注明。"""
    out = []

    def add(rule, cond, note=""):
        out.append(_ok(cond, rule, note))

    h = card.get("hour_index")
    add(RULE_NAMES[0], isinstance(h, int) and not isinstance(h, bool) and 0 <= h <= 11,
        f"hour_index={h!r}（禁止 0–23 钟点／禁止静默取模）")
    add(RULE_NAMES[1], card.get("gender") in ("male", "female"),
        "非 male 不得静默当女")

    solar = card.get("solar") or {}
    try:
        d = dt.date(int(solar["y"]), int(solar["m"]), int(solar["d"]))
        date_ok = True
    except Exception:
        d = None
        date_ok = False
    add(RULE_NAMES[2], date_ok, "2/30、非闰年 2/29、4/31 一律当场拒绝")

    clock = card.get("clock") or {}
    ch = clock.get("hour")
    late_zi = isinstance(ch, int) and ch == 23
    early_zi = isinstance(ch, int) and ch == 0
    if late_zi:
        add(RULE_NAMES[3], card.get("next_day_applied") is True and h == 0,
            "23:00–23:59 按真太阳时归次日，时辰支取 0")
    else:
        add(RULE_NAMES[3], True, "未声明钟表 23 点，跳过")
    if early_zi:
        add(RULE_NAMES[4], card.get("next_day_applied") is not True and h == 0)
    else:
        add(RULE_NAMES[4], True, "未声明早子时，跳过")
    if card.get("hour_unknown"):
        add(RULE_NAMES[5], card.get("next_day_applied") is not True and h == 0)
    else:
        add(RULE_NAMES[5], True, "时辰已知，跳过")

    palaces = card.get("palaces")
    if isinstance(palaces, list):
        add(RULE_NAMES[6], len(palaces) == 12)
        names = [p.get("name") for p in palaces]
        add(RULE_NAMES[7], set(names) == set(PALACES) and len(set(names)) == 12)
        bis = [p.get("branch_index") for p in palaces]
        add(RULE_NAMES[8], sorted(x for x in bis if isinstance(x, int)) == list(range(12)))
        ming_marks = [p for p in palaces if p.get("is_ming_gong")]
        ming_idx = card.get("ming_branch_index")
        add(RULE_NAMES[9], len(ming_marks) == 1 and
            (ming_idx is None or ming_marks[0].get("branch_index") == ming_idx))
        if isinstance(ming_idx, int) and len(palaces) == 12:
            expected = [(ming_idx - k + 12) % 12 for k in range(12)]
            add(RULE_NAMES[10], bis == expected,
                "第 k 宫地支 = (命宫地支 − k + 12) % 12")
        else:
            add(RULE_NAMES[10], True, "未声明命宫地支，跳过")
        jiliang = [p.get("branch_index") for p in palaces
                   if {"天机", "天梁"} <= set(p.get("stars") or [])]
        add(RULE_NAMES[11], all(x in (4, 10) for x in jiliang),
            f"机梁同宫落 {jiliang}")
        ziwei = [p.get("branch_index") for p in palaces if "紫微" in (p.get("stars") or [])]
        tianfu = [p.get("branch_index") for p in palaces if "天府" in (p.get("stars") or [])]
        if ziwei and tianfu:
            add(RULE_NAMES[12], (ziwei[0] + tianfu[0]) % 12 == 4)
        else:
            add(RULE_NAMES[12], True, "紫府未同时声明，跳过")
        dual = [p.get("branch_index") for p in palaces
                if len(p.get("sihua") or []) >= 2]
        add(RULE_NAMES[16], True, f"{len(dual)} 宫双四化，属正常结果不得去重")
        add(RULE_NAMES[17], all(isinstance(p.get("borrowed_stars"), (list, type(None)))
                                for p in palaces),
            "借宫必须走结构化 borrowed_stars，禁止从文案反查")
    else:
        for i in range(6, 13):
            add(RULE_NAMES[i], True, "未提供十二宫结构，跳过")
        add(RULE_NAMES[16], True, "跳过")
        add(RULE_NAMES[17], True, "跳过")

    lp = card.get("leap_month_policy")
    if lp is not None:
        add(RULE_NAMES[13], lp in LEAP_POLICIES,
            "拼错值须当场抛错，不得静默按归本月")
        add(RULE_NAMES[18], card.get("birth_info_leap_policy") == lp,
            "legal policy 须回写 birthInfo 供运限重建同口径盘")
    else:
        add(RULE_NAMES[13], True, "未声明闰月口径，跳过")
        add(RULE_NAMES[18], True, "跳过")

    yb = card.get("year_branch_index")
    hb = card.get("hongluan_branch_index")
    tb = card.get("tianxi_branch_index")
    if isinstance(yb, int) and isinstance(hb, int) and isinstance(tb, int):
        add(RULE_NAMES[14], hb == (3 - yb + 12) % 12 and tb == (hb + 6) % 12)
    else:
        add(RULE_NAMES[14], True, "未声明年支星，跳过")

    pairs = card.get("sihua") or []
    bad = [p for p in pairs if (p.get("star"), p.get("hua")) not in LEGAL_PAIRS]
    add(RULE_NAMES[15], not bad, f"非法 {len(bad)} 组：{[p for p in bad][:3]}")

    dst = card.get("dst")
    if isinstance(dst, dict):
        add(RULE_NAMES[19], dst.get("auto_adjust_minutes") in (None, 0),
            "夏令时只判定不自动扣时，钟表读数交用户确认")
    else:
        add(RULE_NAMES[19], True, "未声明夏令时，跳过")
    lichun = card.get("lichun")
    if isinstance(lichun, dict):
        add(RULE_NAMES[20], ("year_pillar_changed" in lichun and
                             "solar_term_basis" in lichun),
            "立春当天凌晨仍属上一年，须标明交节依据")
    else:
        add(RULE_NAMES[20], True, "未声明节气四柱，跳过")
    add(RULE_NAMES[21], "ms" not in card or card["ms"] is None or
        isinstance(card["ms"], str), "空宫 ms=null 合法")
    add(RULE_NAMES[22], card.get("judging_basis", "score-py") == "score-py",
        "旺衰唯一判档；任何第二口径入参一律拒绝")
    ref = card.get("reference_schools") or []
    add(RULE_NAMES[23], all(isinstance(x, str) and x.startswith("参考对照·") for x in ref),
        "流派只作只读参考对照，不得进 score.py 入参")
    interp = card.get("interpretation") or ""
    add(RULE_NAMES[24], not re.search(r"\b\d{1,3}分\b|运势分|评分[:：]\s*\d", interp),
        "解读层不得出现工具没给的分数")
    add(RULE_NAMES[25], not FORBIDDEN.search(interp),
        "本人终点永不可断；绝对化断言禁止")
    k = card.get("k")
    if k and date_ok and isinstance(h, int) and card.get("gender"):
        expect = f"{d.year:04d}-{d.month:02d}-{d.day:02d}-{h}-{card['gender']}"
        add(RULE_NAMES[26], k == expect, f"期望 {expect}")
    else:
        add(RULE_NAMES[26], True, "未声明键名，跳过")
    add(RULE_NAMES[27], card.get("hour_index") == card.get("four_pillars_hour_index")
        if "four_pillars_hour_index" in card else True,
        "四柱时支与盘面时辰索引须同源")

    passed = all(x["pass"] for x in out)
    return {"verdict": "PASS" if passed else "FAIL", "checks": out,
            "passed": sum(x["pass"] for x in out), "total": len(out),
            "scope_note": "只校验确定性与边界，不代表命理断语准确率"}


def from_row(row: dict) -> dict:
    """把 v4.0 数据集一行转成最小盘面卡（用于全量数据侧校验）。"""
    return {"k": row.get("k"), "solar": {"y": row.get("y"), "m": row.get("m"),
                                        "d": row.get("d")},
            "hour_index": row.get("h"), "gender": row.get("g"), "ms": row.get("ms")}


def selftest():
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    good = {"k": "1990-01-01-0-male", "solar": {"y": 1990, "m": 1, "d": 1},
            "hour_index": 0, "gender": "male", "ms": "天府",
            "leap_month_policy": "split", "birth_info_leap_policy": "split",
            "year_branch_index": 4, "hongluan_branch_index": 11,
            "tianxi_branch_index": 5,
            "sihua": [{"star": "廉贞", "hua": "禄"}, {"star": "破军", "hua": "权"}],
            "judging_basis": "score-py",
            "reference_schools": ["参考对照·中州派"], "interpretation": "倾向稳健，建议关注守成。"}
    palaces = []
    ming = 4
    names = PALACES
    # 第 i 宫地支 = (4 - i + 12) % 12：i=0→辰(4)、i=4→子(0)、i=6→戌(10)
    # 机梁须落辰戌，紫府须 (紫微支+天府支)%12==4 → 紫微在辰(4)、天府在子(0)
    stars = [[] for _ in range(12)]
    stars[0] = ["紫微", "天机", "天梁"]
    stars[4] = ["天府"]
    stars[6] = ["天机", "天梁"]
    for i in range(12):
        palaces.append({"name": names[i], "branch_index": (ming - i + 12) % 12,
                        "stars": stars[i], "is_ming_gong": i == 0,
                        "sihua": [{"star": "廉贞"}] if i == 0 else []})
    good["palaces"] = palaces
    good["ming_branch_index"] = ming
    r = validate(good)
    ck("合法盘全绿", r["verdict"] == "PASS")
    ck("28 项齐全", r["total"] == 28)
    ck("小时辰越界判失败", validate(dict(good, hour_index=12))["verdict"] == "FAIL")
    ck("0–23 钟点判失败", validate(dict(good, hour_index=23))["verdict"] == "FAIL")
    ck("不存在日期判失败", validate(dict(good, solar={"y": 1990, "m": 2, "d": 30}))["verdict"] == "FAIL")
    ck("闰月拼错判失败", validate(dict(good, leap_month_policy="nextmonth"))["verdict"] == "FAIL")
    ck("非法四化判失败", validate(dict(good, sihua=[{"star": "七杀", "hua": "权"}]))["verdict"] == "FAIL")
    ck("第二判档拒绝", validate(dict(good, judging_basis="other"))["verdict"] == "FAIL")
    ck("流派未标只读拒绝", validate(dict(good, reference_schools=["中州派"]))["verdict"] == "FAIL")
    ck("本人寿元红线拒绝", validate(dict(good, interpretation="本人寿元 73 岁"))["verdict"] == "FAIL")
    ck("解读层分数拒绝", validate(dict(good, interpretation="运势分 88 分"))["verdict"] == "FAIL")
    ck("机梁落错宫判失败",
       validate(dict(good, palaces=[dict(p, stars=["天机", "天梁"] if i == 2 else p["stars"])
                                    for i, p in enumerate(palaces)]))["verdict"] == "FAIL")
    ck("晚子时未换日判失败",
       validate(dict(good, clock={"hour": 23}, next_day_applied=False))["verdict"] == "FAIL")
    ck("时辰不详换日判失败",
       validate(dict(good, hour_unknown=True, next_day_applied=True))["verdict"] == "FAIL")
    ck("夏令时自动扣时判失败",
       validate(dict(good, dst={"auto_adjust_minutes": 60}))["verdict"] == "FAIL")
    ck("键名不一致判失败", validate(dict(good, k="1990-01-02-0-male"))["verdict"] == "FAIL")
    row = {"k": "1990-01-01-0-male", "y": 1990, "m": 1, "d": 1, "h": 0,
           "g": "male", "ms": "天府"}
    ck("数据行转卡可校验", validate(from_row(row))["verdict"] == "PASS")
    ok = sum(v for _, v in cases)
    for n, v in cases:
        if not v:
            print("FAIL", n)
    print(f"paipan_check selftest: {ok}/{len(cases)} passed")
    return 0 if ok == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="check")
    ap.add_argument("payload", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or a.cmd == "selftest":
        return selftest()
    text = sys.stdin.read() if a.payload in (None, "-") else a.payload
    data = json.loads(text)
    if a.cmd == "from-row":
        data = from_row(data)
    print(json.dumps(validate(data), ensure_ascii=False, indent=2))
    return 0 if validate(data)["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
