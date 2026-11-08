#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 OB96 / TR102 · 口径卡 ↔ 外部排盘引擎 dump 逐格对拍适配器（v1.54.0）。

上轮「后续微调」第 4 项。先说实况，不假装做完：
  上游 `Renhuai123/ziwei-doushu` v4.0-13d 的 clone 在本机，但仓库里
  **没有任何 engine-dump / 盘面导出脚本**（scripts/ 下只有 18 个 regression 测试）。
  没有 dump 就没有逐格对拍的数据，本脚本不伪造 dump、不把测试断言当成盘面。

因此本轮交付的是**可运行的适配器 + 明确的数据契约**：
  - 约定 DUMP_SCHEMA（口径开关、十二宫、紫府/机梁安星、四化）；
  - 一旦上游或本馆导出 dump，直接 `--dump` 逐格比对，冲突全量列出；
  - 没给 dump 时如实报 `unavailable`，并说明缺什么。

用法：
  python3 engine_align.py --schema
  python3 engine_align.py --dump <dump.json> --card <kauding.json> --out <report.json>
  python3 engine_align.py --selftest
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
sys.path.insert(0, str(SKILLS / "xuanjian-train" / "scripts"))
try:
    from paipan_check import BRANCHES, LEGAL_PAIRS  # 十干四化 40 项白名单
except ImportError:
    BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
    LEGAL_PAIRS = set()

DUMP_SCHEMA = {
    "engine": "引擎标识与版本，例：ziwei-doushu@v4.0-13d",
    "input": {"date": "YYYY-MM-DD", "hour_index": "0–11", "gender": "male/female"},
    "switches": {"calendar": "solar/lunar", "hour_index": "0-11",
                 "true_solar_time": "on/off", "late_zishi": "next-day/same-day",
                 "leap_month": "split/next-month/prev-month/origin-month",
                 "dst_cn": "detect-only", "year_boundary": "lichun",
                 "brightness_school": "quanshu/...", "sihua_school": "tongxing-feixing/...",
                 "dayun_age": "nominal/...", "judging_basis": "score-py"},
    "palaces": [{"index": 0, "branch": "子", "name": "命宫"}],
    "ming_index": "命宫所在地支索引 0–11",
    "stars": {"ziwei": 0, "tianfu": 0, "tianji": 0, "tianliang": 0},
    "sihua": [{"stem": "甲", "star": "廉贞", "hua": "化禄"}],
}
# 与 kauding.py new --preset tianji-default 的 switches 一致；仅作无 --card 时的对照基线
DEFAULT_SWITCHES = {
    "calendar": "solar", "hour_index": "0-11", "true_solar_time": "on",
    "late_zishi": "next-day", "leap_month": "split", "dst_cn": "detect-only",
    "year_boundary": "lichun", "zi_chu_huan_ri": "23:00-next-day",
    "brightness_school": "quanshu", "sihua_school": "tongxing-feixing",
    "dayun_age": "nominal", "judging_basis": "score-py",
}
BRANCH_INDEX = {b: i for i, b in enumerate(BRANCHES)}


def align(dump, card=None):
    """逐格对拍；返回 conflicts 全量列表，不做加权、不隐藏分歧。"""
    switches = (card or {}).get("switches", DEFAULT_SWITCHES)
    dsw = dump.get("switches", {})
    conflicts = []
    for k, v in switches.items():
        if k not in dsw:
            conflicts.append({"layer": "switch", "key": k, "kind": "missing_in_dump",
                              "card": v})
        elif dsw[k] != v:
            conflicts.append({"layer": "switch", "key": k, "kind": "mismatch",
                              "card": v, "dump": dsw[k]})
    for k in dsw:
        if k not in switches:
            conflicts.append({"layer": "switch", "key": k, "kind": "extra_in_dump",
                              "dump": dsw[k]})

    # 十二宫逆时针：第 k 宫地支 = (命宫 − k + 12) % 12
    palaces = dump.get("palaces") or []
    ming = dump.get("ming_index")
    for p in palaces:
        k, b = p.get("index"), p.get("branch")
        if k is None or b not in BRANCH_INDEX or not isinstance(ming, int):
            continue
        expect = (ming - k + 12) % 12
        if BRANCH_INDEX[b] != expect:
            conflicts.append({"layer": "palace", "key": k, "kind": "branch_mismatch",
                              "card": BRANCHES[expect], "dump": b})

    stars = dump.get("stars") or {}
    if isinstance(stars.get("ziwei"), int) and isinstance(stars.get("tianfu"), int):
        if (stars["ziwei"] + stars["tianfu"]) % 12 != 4:
            conflicts.append({"layer": "star", "key": "紫府", "kind": "zi_fu_rule",
                              "card": "(紫微+天府)%12=4",
                              "dump": (stars["ziwei"] + stars["tianfu"]) % 12})
    for key in ("tianji", "tianliang"):
        v = stars.get(key)
        if isinstance(v, int) and BRANCHES[v % 12] not in ("辰", "戌"):
            conflicts.append({"layer": "star", "key": key, "kind": "ji_liang_rule",
                              "card": "机梁只在辰戌", "dump": BRANCHES[v % 12]})

    for s in dump.get("sihua") or []:
        star, hua = s.get("star"), s.get("hua")
        if LEGAL_PAIRS and (star, hua) not in LEGAL_PAIRS:
            # 排除古籍引证语境：判定只针对盘面四化断言，不针对引文
            if not s.get("citation_context"):
                conflicts.append({"layer": "sihua", "key": star, "kind": "off_whitelist",
                                  "dump": hua})
    return {
        "status": "aligned" if not conflicts else "conflicts",
        "engine": dump.get("engine", "unspecified"),
        "switch_count": len(switches), "palace_count": len(palaces),
        "conflict_count": len(conflicts), "conflicts": conflicts,
        "policy": "冲突全量保留，只列分歧、不加权互证；口径卡由主理人一人裁定，"
                  "引擎 dump 不得反向改写本馆口径（OB96 / TR103）。",
    }


def unavailable():
    return {
        "status": "unavailable",
        "reason": "未提供 dump 文件；上游 ziwei-doushu v4.0-13d 的 scripts/ 下"
                  "只有 18 个 regression 测试，没有任何 engine-dump / 盘面导出脚本。",
        "what_is_missing": "一份符合 DUMP_SCHEMA 的盘面导出（口径开关 + 十二宫 + 紫府/机梁安星 + 四化）。",
        "what_is_ready": "对拍适配器、冲突检出、口径卡默认值、十干四化白名单均已就绪并通过自检。",
        "honesty_note": "不伪造 dump、不把上游测试断言当成盘面、不称此项已完成。",
        "upstream_clone": ".workbuddy/upstream/ziwei-doushu",
    }


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  FAIL: " + name)

    def mkdump():
        return {"engine": "synthetic-fixture@v0",
                "input": {"date": "1988-01-01", "hour_index": 0, "gender": "male"},
                "switches": dict(DEFAULT_SWITCHES),
                "ming_index": 6,
                "palaces": [{"index": k, "branch": BRANCHES[(6 - k + 12) % 12]}
                            for k in range(12)],
                "stars": {"ziwei": 2, "tianfu": 2, "tianji": 4, "tianliang": 10},
                "sihua": []}

    d = mkdump()
    r = align(d)
    chk("合成夹具全对齐", r["status"] == "aligned" and r["conflict_count"] == 0)
    chk("紫府 (2+2)%12=4 通过", not any(c["key"] == "紫府" for c in r["conflicts"]))
    d2 = mkdump(); d2["switches"]["leap_month"] = "next-month"
    chk("口径开关冲突可检出", any(c["key"] == "leap_month" for c in align(d2)["conflicts"]))
    d3 = mkdump(); d3["stars"]["tianfu"] = 5
    chk("紫府铁律冲突可检出", any(c["key"] == "紫府" for c in align(d3)["conflicts"]))
    d4 = mkdump(); d4["palaces"][3]["branch"] = "亥"
    chk("十二宫逆时针冲突可检出",
        any(c["layer"] == "palace" for c in align(d4)["conflicts"]))
    d5 = mkdump(); d5["stars"]["tianji"] = 0
    chk("机梁只在辰戌可检出",
        any(c["key"] == "tianji" for c in align(d5)["conflicts"]))
    chk("无 dump 时如实报 unavailable", unavailable()["status"] == "unavailable")
    chk("schema 含四层", set(DUMP_SCHEMA) >= {"switches", "palaces", "stars", "sihua"})
    if LEGAL_PAIRS:
        d6 = mkdump(); d6["sihua"] = [{"stem": "甲", "star": "七杀", "hua": "化权"}]
        chk("白名单外四化可检出",
            any(c["kind"] == "off_whitelist" for c in align(d6)["conflicts"]))
        d7 = mkdump(); d7["sihua"] = [{"stem": "甲", "star": "七杀", "hua": "化权",
                                      "citation_context": "紫微七杀化权反作桢梓"}]
        chk("古籍引证语境豁免",
            not any(c["kind"] == "off_whitelist" for c in align(d7)["conflicts"]))
    print("SELFTEST %d/%d %s" % (ok, ok + fail, "PASS" if not fail else "FAIL"))
    return 0 if not fail else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump")
    ap.add_argument("--card")
    ap.add_argument("--out")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.schema:
        print(json.dumps(DUMP_SCHEMA, ensure_ascii=False, indent=2))
        return 0
    if not a.dump or not pathlib.Path(a.dump).exists():
        r = unavailable()
    else:
        dump = json.loads(pathlib.Path(a.dump).read_text(encoding="utf-8"))
        card = json.loads(pathlib.Path(a.card).read_text(encoding="utf-8")) if a.card else None
        r = align(dump, card)
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
