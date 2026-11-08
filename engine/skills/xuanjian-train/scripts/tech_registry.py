#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 103 · 技法挂载池注册表与口径显式化（照单全学 · 跨体系整合能力）。

借 Horosa 的「SCHOOL_PRESETS 八维字段束 + presetOf 实时反查 + 非流派键三分法」
机制（源码研读报告 `12-horosa-source.md` §3），借 yuan 的六法统一输入思路
（`13-rest-source.md` §2），但**只做只读参考对照**，不引入第二判档。

本馆定案级红线（不可被任何预设改写）：
- 旺衰唯一判档：`judging_basis` 恒为 `score-py`，任何 `custom` 档都不参与判档。
- 各安其位：成员只挂自己专长那条线，越线派单一律拒绝。
- 唯一互通时机＝主理人主持的交叉核对，且须先各自独立出完结论。
- 本人终点永不可断。

用法：
  python3 tech_registry.py summary
  python3 tech_registry.py card --tech ziwei --preset xuanjian --member 斗枢
  python3 tech_registry.py mount --tech bazi --member 斗枢
  python3 tech_registry.py --selftest
"""
import argparse
import json
import sys

# ── 十线专长注册表（各安其位的唯一真值） ──────────────────────────────
LINES = {
    "知微": {"techs": ["bazi", "sizhu", "dayun", "liunian"], "line": "子平八字"},
    "斗枢": {"techs": ["ziwei", "doushu", "feixing"], "line": "紫微斗数"},
    "明相": {"techs": ["xiangfa", "mianxiang", "shouxiang"], "line": "相法"},
    "青囊": {"techs": ["fengshui", "yangzhai", "yinzhai", "luopan"], "line": "堪舆"},
    "观象": {"techs": ["liuyao", "meihua", "xiaoliuren"], "line": "卦"},
    "司辰": {"techs": ["qimen", "zeri", "huangli"], "line": "奇门择日黄历"},
    "正名": {"techs": ["qiming", "kangxi"], "line": "取名"},
    "赤绳": {"techs": ["hehun"], "line": "合婚"},
    "南柯": {"techs": ["meng"], "line": "梦"},
    "南阳": {"techs": ["jingfang"], "line": "医"},
}
OWNER = {t: m for m, v in LINES.items() for t in v["techs"]}

# ── 清单里出现、但本馆不派单的技法（只读参考） ────────────────────────
REFERENCE_ONLY = [
    "western_astrology", "vedic", "numerology", "chenggu", "indian_astrology",
    "tarot", "ACG", "planetarium", "celebrity_db", "taiyi", "daliuren",
]

# ── 八维口径字段束（Horosa SCHOOL_PRESETS 机制的本馆自撰等价物） ────────
SCHOOL_FIELDS = ["calendar", "hour_index", "leap_policy", "sihua_school",
                 "dayun_start", "year_boundary", "brightness_table", "flying_star"]
SCHOOL_PRESETS = {
    # 零回归锚：全部维度 = 本馆当前默认值，选它必须逐字节等价
    "xuanjian": {"calendar": "solar", "hour_index": "0-11", "leap_policy": "split",
                 "sihua_school": "ni-school", "dayun_start": "minggong",
                 "year_boundary": "lichun", "brightness_table": "ni",
                 "flying_star": "off"},
    "zhongzhou": {"calendar": "solar", "hour_index": "0-11", "leap_policy": "split",
                  "sihua_school": "zhongzhou", "dayun_start": "minggong",
                  "year_boundary": "lichun", "brightness_table": "classic",
                  "flying_star": "on"},
    "beipai": {"calendar": "solar", "hour_index": "0-11", "leap_policy": "next-month",
               "sihua_school": "beipai", "dayun_start": "minggong",
               "year_boundary": "lunar_1_1", "brightness_table": "classic",
               "flying_star": "off"},
    "ni-school-leap": {"calendar": "solar", "hour_index": "0-11",
                       "leap_policy": "next-month", "sihua_school": "ni-school",
                       "dayun_start": "minggong", "year_boundary": "lichun",
                       "brightness_table": "ni", "flying_star": "off"},
}
PRESET_DEFAULT = "xuanjian"
# 三分法：输入键／显示键改动不得把口径打成 custom
NON_SCHOOL_KEYS = {
    "input": ["name", "gender", "birth_place", "longitude", "question", "hour_unknown"],
    "display": ["language", "export_format", "sections", "theme", "verbosity"],
}
JUDGING_BASIS = "score-py"


def normalize(fields: dict) -> dict:
    """补齐八维，未知档回落默认锚；非流派键原样保留、不参与反查。"""
    out = dict(SCHOOL_PRESETS[PRESET_DEFAULT])
    out.update({k: v for k, v in (fields or {}).items() if k in SCHOOL_FIELDS})
    return out


def preset_of(fields: dict) -> str:
    """实时字段反查档名，不依赖记忆值；单项被改 → custom。"""
    f = normalize(fields)
    for name, preset in SCHOOL_PRESETS.items():
        if all(f[k] == preset[k] for k in SCHOOL_FIELDS):
            return name
    return "custom"


def apply_preset(preset: str, current: dict) -> dict:
    """切档：口径键按预设写，输入/显示键保留当前值（Horosa 三分法）。"""
    if preset not in SCHOOL_PRESETS:
        raise ValueError(f"unknown preset: {preset}")
    out = dict(SCHOOL_PRESETS[preset])
    for group in NON_SCHOOL_KEYS.values():
        for k in group:
            if k in (current or {}):
                out[k] = current[k]
    return out


def validate_mount(tech: str, member: str) -> dict:
    """成员只能挂自己专长那条线；只读技法不派单。"""
    if tech in REFERENCE_ONLY:
        return {"ok": False, "reason": f"{tech} 属只读参考技法，不派单、不进判档"}
    if tech not in OWNER:
        return {"ok": False, "reason": f"未登记技法 {tech}，禁止越级抢答"}
    if member != OWNER[tech]:
        return {"ok": False,
                "reason": f"越线：{tech} 归 {OWNER[tech]}，{member} 不得替读"}
    return {"ok": True, "owner": member, "line": LINES[member]["line"]}


def reject_dual_basis(payload: dict) -> dict:
    """任何试图给 score.py 塞第二判档入参的请求一律拒绝。"""
    bad = []
    if payload.get("judging_basis", JUDGING_BASIS) != JUDGING_BASIS:
        bad.append("judging_basis 非 score-py")
    for key in ("school_for_scoring", "score_preset", "wangshuai_by", "strength_method"):
        if key in payload:
            bad.append(f"出现第二判档入参 {key}")
    ref = payload.get("reference_schools") or []
    if any(not str(x).startswith("参考对照·") for x in ref):
        bad.append("流派未标只读参考对照")
    return {"ok": not bad, "violations": bad, "judging_basis": JUDGING_BASIS}


def make_card(tech: str, fields: dict, member: str) -> dict:
    """生成口径卡：口径显式、判档唯一、流派只读、越线即拒。"""
    mount = validate_mount(tech, member)
    if not mount["ok"]:
        return {"status": "BLOCKED", **mount}
    f = normalize(fields)
    preset = preset_of(fields)
    dual = reject_dual_basis(fields)
    if not dual["ok"]:
        return {"status": "BLOCKED", "reason": "第二判档", **dual}
    return {
        "status": "OK", "tech": tech, "owner": member, "line": mount["line"],
        "preset": preset, "fields": f,
        "judging_basis": JUDGING_BASIS,
        "reference_schools": ["参考对照·" + p for p in SCHOOL_PRESETS if p != preset],
        "school_is_readonly": True,
        "note": "预设只影响口径元数据；判档恒由 score.py 单一真值给出，流派不参与判档。",
        "cross_check_allowed": False,
        "cross_check_note": "唯一互通时机＝主理人主持的交叉核对，且须先各自独立出完结论。",
    }


def summary() -> dict:
    return {
        "lines": len(LINES), "mountable_techs": len(OWNER),
        "reference_only_techs": len(REFERENCE_ONLY),
        "presets": list(SCHOOL_PRESETS), "school_fields": SCHOOL_FIELDS,
        "non_school_keys": NON_SCHOOL_KEYS,
        "judging_basis": JUDGING_BASIS,
        "red_lines": ["各安其位", "唯一判档", "本人终点永不可断", "交叉核对须先独立出结论"],
    }


def selftest():
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    ck("十线齐全", len(LINES) == 10)
    ck("技法唯一归属", len(OWNER) == sum(len(v["techs"]) for v in LINES.values()))
    ck("零回归默认锚", normalize({}) == SCHOOL_PRESETS[PRESET_DEFAULT])
    ck("默认反查命中", preset_of({}) == PRESET_DEFAULT)
    ck("完整档反查", preset_of(SCHOOL_PRESETS["zhongzhou"]) == "zhongzhou")
    ck("单项改判 custom", preset_of(dict(SCHOOL_PRESETS["zhongzhou"], flying_star="off")) == "custom")
    ck("未知档回落默认", preset_of({"leap_policy": "???", "sihua_school": "??"}) == "custom")
    cur = {"name": "张三", "language": "zh", "flying_star": "off"}
    ap = apply_preset("zhongzhou", cur)
    ck("切档保留输入键", ap["name"] == "张三" and ap["language"] == "zh")
    ck("切档覆盖口径键", ap["flying_star"] == "on")
    ck("非流派键不扰动反查", preset_of(ap) == "zhongzhou")
    ck("本线可挂", validate_mount("ziwei", "斗枢")["ok"])
    ck("越线拒绝", not validate_mount("ziwei", "知微")["ok"])
    ck("只读技法不派单", not validate_mount("vedic", "斗枢")["ok"])
    ck("未登记拒绝", not validate_mount("foo", "斗枢")["ok"])
    card = make_card("bazi", {}, "知微")
    ck("口径卡生成", card["status"] == "OK")
    ck("判档锁死", card["judging_basis"] == "score-py")
    ck("流派只读", card["school_is_readonly"] and not card["cross_check_allowed"])
    ck("参考对照标注", all(x.startswith("参考对照·") for x in card["reference_schools"]))
    ck("第二判档拒绝", make_card("bazi", {"judging_basis": "other"}, "知微")["status"] == "BLOCKED")
    ck("score.py 入参带流派拒绝",
       make_card("bazi", {"school_for_scoring": "beipai"}, "知微")["status"] == "BLOCKED")
    ck("未标只读流派拒绝",
       not reject_dual_basis({"reference_schools": ["中州派"]})["ok"])
    ck("越线出不了卡", make_card("ziwei", {}, "知微")["status"] == "BLOCKED")
    ok = sum(v for _, v in cases)
    for n, v in cases:
        if not v:
            print("FAIL", n)
    print(f"tech_registry selftest: {ok}/{len(cases)} passed")
    return 0 if ok == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="summary")
    ap.add_argument("--tech"); ap.add_argument("--preset")
    ap.add_argument("--member"); ap.add_argument("--fields")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or a.cmd == "selftest":
        return selftest()
    if a.cmd == "summary":
        out = summary()
    elif a.cmd == "card":
        base = SCHOOL_PRESETS.get(a.preset or PRESET_DEFAULT, {})
        if a.fields:
            base.update(json.loads(a.fields))
        out = make_card(a.tech or "bazi", base, a.member or "知微")
    elif a.cmd == "mount":
        out = validate_mount(a.tech or "", a.member or "")
    elif a.cmd == "presets":
        out = SCHOOL_PRESETS
    else:
        print("unknown cmd", file=sys.stderr)
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
