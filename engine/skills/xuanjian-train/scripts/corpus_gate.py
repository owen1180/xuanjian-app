#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玄鉴命理馆 · 训练语料合规闸门 corpus_gate.py (v1.0)

职责（只做闸门，不做断法、不做训练）：
  1. 逐行校验 v4.0 数据集的确定性字段（日期存在性 / 时辰索引 0-11 / 性别 / 档号一致性）。
  2. 检出解读文本里内嵌的倪师原话与古籍引文，**把原话正文全部剥离**，只保留
     结构指纹（引文类型、数量、出处元数据）与脱敏后的文本骨架。
  3. 抽出四化组合（术语，非引文），供「四化白名单」任务使用。
  4. 写可审计清单 audit.json：来源、SHA-256、许可、署名、拒绝计数、引文计数。

合规依据（一手，2026-11-04 核验）：
  DATASET-LICENSE 允许「模型微调（开源与闭源模型均可）」+ 商用，唯一要求署名；
  但「解读文本中引用的倪海厦《天纪》原话……不属于本数据集的授权范围……
  要把这些原话单独成批使用，按 docs/tianji-ziwei/LICENSE.md（CC BY-NC-SA 4.0）处理」。
  实测 300/300 盘均内嵌倪师原话，故整段解读入语料 = 成批使用非商用原话。
  本闸门一律剥离原话正文（古籍 PD 亦剥离，换取审计口径单一）。

用法：
  python3 corpus_gate.py --input year-1990.jsonl --out gated.jsonl \
      --audit audit.json --max-charts 1500
  python3 corpus_gate.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sys

SOURCE_URL = "https://github.com/Renhuai123/ziwei-doushu/releases/tag/v4.0-13d"
LICENSE = ("CC BY 4.0（DATASET-LICENSE，允许模型微调与商用，须署名）；"
           "内嵌倪师《天纪》原话不在授权范围（CC BY-NC-SA 4.0，非商用）")
ATTRIBUTION = ("本项目使用了 紫微斗数开源解读数据集 v4.0（674,976 张命盘 × 13 维）"
               "／来源：https://github.com/Renhuai123/ziwei-doushu ／作者：王多鱼AI")

TOPICS = ["overview", "personality", "love", "career", "wealth", "health",
          "family", "children", "move", "friends", "home", "spirit", "parents"]

# 十天干四化白名单（与 97 册、kauding.py 同一张表；只放术语，不放解读）
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
LEGAL_PAIRS = {(star, hua) for row in SIHUA_WHITELIST.values()
               for star, hua in row.items()}
# 已知星名全集：只有命中这里才算「星+四化」，否则是「财星化禄」「生年化忌」
# 「子女宫化忌」这类叙述文字，必须丢弃而不是记成非法四化。
KNOWN_STARS = {s for s, _ in LEGAL_PAIRS} | {
    "七杀", "破军", "天相", "巨门", "天机", "太阳", "太阴", "天同", "廉贞",
    "天府", "紫微", "贪狼", "天梁", "武曲", "文昌", "文曲", "左辅", "右弼",
    "禄存", "天马", "擎羊", "陀罗", "火星", "铃星", "地空", "地劫", "天空",
    "三台", "八座", "天魁", "天钺", "化气",
}

# 引文出处标记（保留元数据，不含正文）
RE_NI_CITE = re.compile(r"（(?:倪海厦)?《?天纪》?第\s*(\d+)\s*集\s*(\d{1,2}:\d{2}(?::\d{2})?)）")
RE_NI_SHORT = re.compile(r"（第\s*(\d+)\s*集\s*(\d{1,2}:\d{2}(?::\d{2})?)）")
RE_NI_PAGE = re.compile(r"《天纪》\s*p?(\d+)\s*(\d{1,2}:\d{2}:\d{2})")
RE_CLASSIC_BOOK = re.compile(r"《([^》]{2,20})》")
RE_QUOTE_CJK = re.compile(r"[「“]([^」”]{6,})[」”]")
RE_NI_LABEL = re.compile(r"倪(?:海厦)?(?:师|先生)?|〔倪师[^〕]*〕")
RE_SIHUA = re.compile(r"([\u4e00-\u9fff]{2,3})(化禄|化权|化科|化忌)")
STAR_NAMES = {s for row in SIHUA_WHITELIST.values() for s in row}

REDACT_NI = "「[倪师原话已剥离]」"
REDACT_CLASSIC = "「[引文已剥离]」"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def valid_chart(row: dict) -> tuple[bool, str]:
    """确定性字段校验：不靠模型，全靠 datetime 与枚举。"""
    try:
        y, m, d, h, g = int(row["y"]), int(row["m"]), int(row["d"]), int(row["h"]), row["g"]
        dt.date(y, m, d)                       # 不存在日期直接抛异常
        if not 0 <= h <= 11:
            return False, "hour_out_of_0_11"
        if g not in ("male", "female"):
            return False, "bad_gender"
        expect = f"{y:04d}-{m:02d}-{d:02d}-{h}-{g}"
        if row.get("k") != expect:
            return False, "key_mismatch"
        if set(row.get("c", {})) != set(TOPICS):
            return False, "topics_incomplete"
    except (KeyError, TypeError, ValueError):
        return False, "bad_date_or_field"
    return True, "ok"


def redact(text: str) -> tuple[str, dict]:
    """剥掉原话正文，只留出处元数据与结构骨架。"""
    ni_full = RE_NI_CITE.findall(text)
    ni_short = RE_NI_SHORT.findall(text)
    ni_page = RE_NI_PAGE.findall(text)
    books = sorted(set(RE_CLASSIC_BOOK.findall(text)))
    ni_labels = len(RE_NI_LABEL.findall(text))

    out = text
    # 0) 无引号的倪师引语（实测漏网：「倪师说天府是文官星」这类转述句）
    out = re.sub(r"(?:倪师|倪海厦)(?:说|提醒|讲|云|曰|直接说|指出)[：:]?[^。\n]{4,200}[。]?",
                 "倪师说[原话已剥离]。", out)
    out = re.sub(r"^.*〔倪师.*$", "〔倪师断法标注：原话已剥离〕", out, flags=re.M)
    # 1) 先剥引号内成段原话（中文引号、弯引号）
    n_quotes = len(RE_QUOTE_CJK.findall(out))
    out = RE_QUOTE_CJK.sub(REDACT_NI, out)
    # 2) 再剥「（……）」里不含集数时间码、但明显是原话的长括号内容
    def _paren(m: re.Match) -> str:
        inner = m.group(0)
        if RE_NI_CITE.search(inner) or RE_NI_SHORT.search(inner):
            return inner                      # 纯出处，保留
        if len(inner) >= 30 and ni_labels:
            return "（[原话已剥离]）"
        return inner
    out = re.sub(r"（[^（）]{1,400}）", _paren, out)
    # 3) 星号/校勘说明里若残留长引文，按行剥离
    lines = []
    for ln in out.split("\n"):
        if "「" in ln and "已剥离" not in ln and len(ln) > 60:
            ln = re.sub(r"[「“]([^」”]{6,})[」”]", REDACT_CLASSIC, ln)
        lines.append(ln)
    out = "\n".join(lines)

    inv = {
        "ni_quote_episodes": [{"ep": a, "ts": b} for a, b in ni_full + ni_short],
        "ni_quote_pages": [{"p": a, "ts": b} for a, b in ni_page],
        "classic_books": books,
        "ni_label_hits": ni_labels,
        "quoted_spans_redacted": n_quotes,
    }
    return out, inv


def extract_sihua(text: str) -> list[dict]:
    """抽四化组合并标白名单合法性。只读术语，不读断语。"""
    seen, out = set(), []
    for star, hua in RE_SIHUA.findall(text):
        # 星名可能被截成 3 字（如「壬干紫微化权」），做一次最长匹配修正；
        # 匹配不到已知星名的一律是叙述文字，丢弃，绝不记成非法四化。
        matched = None
        for cand in sorted(KNOWN_STARS, key=len, reverse=True):
            if star == cand or star.endswith(cand):
                matched = cand
                break
        if not matched:
            continue
        star = matched
        pair = (star, hua.replace("化", ""))
        if pair in seen:
            continue
        seen.add(pair)
        # 白名单外的星（如七杀化权、紫微化忌）必须保留并标非法，
        # 不能静默跳过——静默跳过等于放过了「不会发生的四化」。
        out.append({"star": star, "hua": hua, "legal": pair in LEGAL_PAIRS})
    return out


def process(path: str, out_path: str, audit_path: str, max_charts: int) -> dict:
    src_hash = sha256_file(path)
    stats = collections.Counter()
    quotes = collections.Counter()
    books = collections.Counter()
    stars = collections.Counter()
    sihua_legal = collections.Counter()
    written = 0
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    with open(path, encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            stats["lines"] += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                stats["reject_json"] += 1
                continue
            ok, why = valid_chart(row)
            if not ok:
                stats["reject_" + why] += 1
                continue
            stats["valid"] += 1
            if written >= max_charts:
                stats["skipped_after_cap"] += 1
                continue

            c = row["c"]
            redacted, inv = {}, {}
            all_sihua = []
            for topic in TOPICS:
                r, i = redact(c[topic])
                redacted[topic] = r
                inv[topic] = i
                for q in i["ni_quote_episodes"] + i["ni_quote_pages"]:
                    quotes[f"ni_{topic}"] += 1
                for b in i["classic_books"]:
                    books[b] += 1
                quotes["quoted_spans_redacted"] += i["quoted_spans_redacted"]
                all_sihua.extend(extract_sihua(r))
            for s in all_sihua:
                sihua_legal["legal" if s["legal"] else "illegal"] += 1
            stars[row["ms"]] += 1

            rec = {
                "k": row["k"], "y": row["y"], "m": row["m"], "d": row["d"],
                "h": row["h"], "g": row["g"], "ms": row["ms"],
                "topic_lengths": row["t"],
                "redacted": redacted,
                "quote_inventory": inv,
                "sihua": all_sihua,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    audit = {
        "gate_version": "1.0",
        "input_file": os.path.abspath(path),
        "input_sha256": src_hash,
        "source_url": SOURCE_URL,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "quote_policy": "所有倪师原话与古籍引文正文一律剥离，仅保留出处元数据与结构骨架；语料内不含原话正文",
        "source_scope": "仅 GitHub Releases v4.0-13d；未从 ouranic.cn 抓取任何内容",
        "charts_written": written,
        "stats": dict(stats),
        "quote_hits_by_topic": dict(quotes),
        "classic_books": dict(books.most_common(20)),
        "ming_stars": dict(stars.most_common(20)),
        "sihua_pairs": dict(sihua_legal),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    return audit


def selftest() -> int:
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    ck("日期 1990-02-30 拒绝",
       not valid_chart({"y": 1990, "m": 2, "d": 30, "h": 0, "g": "male",
                        "k": "1990-02-30-0-male", "c": {t: "" for t in TOPICS}})[0])
    ck("闰年 1992-02-29 通过",
       valid_chart({"y": 1992, "m": 2, "d": 29, "h": 11, "g": "female",
                    "k": "1992-02-29-11-female", "c": {t: "" for t in TOPICS}})[0])
    ck("非闰年 1991-02-29 拒绝",
       not valid_chart({"y": 1991, "m": 2, "d": 29, "h": 0, "g": "male",
                        "k": "1991-02-29-0-male", "c": {t: "" for t in TOPICS}})[0])
    ck("时辰 12 拒绝",
       not valid_chart({"y": 1990, "m": 1, "d": 1, "h": 12, "g": "male",
                        "k": "1990-01-01-12-male", "c": {t: "" for t in TOPICS}})[0])
    ck("档号与字段不符拒绝",
       not valid_chart({"y": 1990, "m": 1, "d": 1, "h": 0, "g": "male",
                        "k": "1990-01-02-0-male", "c": {t: "" for t in TOPICS}})[0])
    ck("13 维不全拒绝",
       not valid_chart({"y": 1990, "m": 1, "d": 1, "h": 0, "g": "male",
                        "k": "1990-01-01-0-male", "c": {"overview": ""}})[0])

    sample = ("倪师说天府是文官星。「那如果你看到煞星跟天府星在一起的时候，"
              "书上说天府星可以解厄制化，实际上是一点用都没有。」"
              "（倪海厦《天纪》第5集53:06）《紫微斗数全书》卷二说天府「能解一切灾厄」。"
              "武曲化禄、贪狼化权、七杀化权、紫微化忌。")
    red, inv = redact(sample)
    ck("原话正文不出现在脱敏文本", "一点用都没有" not in red and "能解一切灾厄" not in red)
    ck("倪师原话占位符存在", "[倪师原话已剥离]" in red or "[引文已剥离]" in red)
    ck("集数时间码元数据保留", any(q["ep"] == "5" for q in inv["ni_quote_episodes"]))
    ck("古籍书名元数据保留", any("紫微斗数全书" in b for b in inv["classic_books"]))
    ck("脱敏文本不含裸长引文", "实际上是一点用都没有" not in red)

    sh = extract_sihua(sample)
    pairs = {(x["star"], x["hua"], x["legal"]) for x in sh}
    ck("武曲化禄判为合法", ("武曲", "化禄", True) in pairs)
    ck("贪狼化权判为合法", ("贪狼", "化权", True) in pairs)
    ck("七杀化权判为非法", ("七杀", "化权", False) in pairs)
    ck("紫微化忌判为非法", ("紫微", "化忌", False) in pairs)
    ck("白名单十干齐全", len(SIHUA_WHITELIST) == 10)
    noise = extract_sihua("财星化禄、生年化忌、问何星化忌、子女宫化忌、"
                          "禄存或化禄、天梁宜化科、宫又见化权")
    ck("叙述文字不误记为四化", noise == [])

    bad = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"\ncorpus_gate selftest: {len(cases) - len(bad)}/{len(cases)} passed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="玄鉴命理馆训练语料合规闸门")
    ap.add_argument("--input", help="原始 year-YYYY.jsonl")
    ap.add_argument("--out", help="脱敏后的 gated.jsonl")
    ap.add_argument("--audit", help="审计清单 audit.json")
    ap.add_argument("--max-charts", type=int, default=1500)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.input and a.out and a.audit):
        ap.error("需要 --input / --out / --audit，或用 --selftest")
    audit = process(a.input, a.out, a.audit, a.max_charts)
    print(json.dumps({k: audit[k] for k in
                      ("charts_written", "input_sha256", "stats", "sihua_pairs")},
                     ensure_ascii=False, indent=2))
    print("\n[许可] " + LICENSE)
    print("[署名] " + ATTRIBUTION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
