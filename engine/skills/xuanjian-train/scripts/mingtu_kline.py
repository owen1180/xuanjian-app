#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 105 · 命途轨迹图生成器（照单全学 · 可视化表达能力）。

借 life-kline 的「按年时间轴 + 大运分区 + 极值/事件标注 + 预测验证状态」
编码思路（源码研读报告 `13-rest-source.md` §3），**剔除**它把命运量化成
1–100 分、OHLC 四价、吉/凶、暴富流年、健康部位等与本馆冲突的部分。

本馆改造（定案级）：
- 纵轴不是「运势分」，而是 **用／喜／忌／病／平 五类运段**（用忌神落地）；
- 不打分、不判吉凶、不画 K 线与均线；只表达「阶段倾向与转折」；
- 每一点带 `reason` 与 `source_ref`，数值可复算、文本可引证；
- 事件带 `verificationStatus`，天然支持修正案例库回写；
- 无本人寿元、无死亡、无具体应期、无财富数额、无疾病诊断。

用法：
  python3 mingtu_kline.py render --input <json> --out <svg>
  python3 mingtu_kline.py demo --out <svg>
  python3 mingtu_kline.py --selftest
"""
import argparse
import html
import json
import pathlib
import re
import sys

BANDS = ["用神运", "喜神运", "忌神运", "病神运", "平运"]
BAND_COLOR = {"用神运": "#1f6f6b", "喜神运": "#6aa9a3", "忌神运": "#c87941",
              "病神运": "#8f6a94", "平运": "#9aa3ab"}
BAND_ROW = {"用神运": 4, "喜神运": 3, "忌神运": 2, "病神运": 1, "平运": 0}
VERIFY = {"pending": "○", "verified": "●", "unverified": "×"}
FORBIDDEN_WORDS = re.compile(
    r"(本人|命主).{0,10}(寿元|活到|死于|何时死|寿命)|暴富|必定大富|"
    r"运势分|评分[:：]\s*\d|\b\d{1,3}\s*分\b")
FORBIDDEN_FIELDS = {"score", "open", "close", "high", "low", "overall_score",
                    "healthBodyParts", "cryptoYear"}
TENDENCY_WORDS = ["倾向", "常见", "容易", "建议关注", "宜", "需留意"]


def validate(data: dict) -> dict:
    """输入闸门：不许数值化、不许断语越界、不许未经引证的理由。"""
    errors = []
    years = data.get("years") or []
    if not years:
        errors.append("years 为空")
    for i, y in enumerate(years):
        where = f"years[{i}]"
        for f in FORBIDDEN_FIELDS:
            if f in y:
                errors.append(f"{where} 出现禁字段 {f}（本馆不把命运量化）")
        if y.get("band") not in BANDS:
            errors.append(f"{where} band 不在五类运段内")
        if FORBIDDEN_WORDS.search(str(y.get("reason", "")) + str(y.get("tendency", ""))):
            errors.append(f"{where} 出现寿元/绝对化/分数量化措辞")
        if not y.get("source_ref"):
            errors.append(f"{where} 缺 source_ref（理由须可引证）")
        if not any(w in str(y.get("tendency", "")) for w in TENDENCY_WORDS):
            errors.append(f"{where} tendency 未用倾向措辞")
        for ev in y.get("events") or []:
            if ev.get("verificationStatus", "pending") not in VERIFY:
                errors.append(f"{where} 事件验证状态非法")
    blob = json.dumps(data, ensure_ascii=False)
    if FORBIDDEN_WORDS.search(blob):
        errors.append("整体输入含禁词")
    return {"ok": not errors, "errors": errors, "points": len(years),
            "note": "只表达阶段倾向与转折，不代表吉凶、不代表咨询效果"}


def render(data: dict) -> str:
    """生成自包含 SVG（无外部依赖、无脚本、纯静态可归档）。"""
    v = validate(data)
    if not v["ok"]:
        raise ValueError("input rejected: " + "; ".join(v["errors"][:5]))
    years = data["years"]
    W, H = 980, 430
    left, right, top, bottom = 70, 30, 74, 74
    plot_w = W - left - right
    n = len(years)
    step = plot_w / max(1, n)
    bw = min(step * 0.66, 22)
    row_h = 44
    base_y = top + 5 * row_h + 16
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="{left}" y="30" font-family="sans-serif" font-size="17" '
        f'font-weight="600" fill="#24313a">{html.escape(data.get("title", "命途轨迹 · 用忌神运段"))}</text>',
        f'<text x="{left}" y="50" font-family="sans-serif" font-size="11" '
        f'fill="#6b7780">纵轴＝用／喜／忌／病／平运段（非分数、非吉凶）　·　'
        f'每段须有出处　·　仅供文化研究与阶段回顾</text>',
    ]
    # 行_label + 网格
    for band, row in BAND_ROW.items():
        y = top + (4 - row) * row_h
        parts.append(f'<rect x="{left}" y="{y}" width="{plot_w}" height="{row_h - 4}" '
                     f'fill="{BAND_COLOR[band]}" fill-opacity="0.055" rx="3"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 20}" text-anchor="end" '
                     f'font-family="sans-serif" font-size="12" fill="#4a565e">'
                     f'{html.escape(band)}</text>')
    # 大运分区
    zones, prev, start = [], None, 0
    for i, y in enumerate(years):
        dy = y.get("dayun", "")
        if dy != prev:
            if prev is not None:
                zones.append((start, i, prev))
            prev, start = dy, i
    zones.append((start, n, prev))
    for zi, (a, b, label) in enumerate(zones):
        x = left + a * step
        w = (b - a) * step
        parts.append(f'<rect x="{x:.1f}" y="{top - 8}" width="{w:.1f}" '
                     f'height="{5 * row_h + 14}" fill="{["#eef3f2", "#f5f0ea"][zi % 2]}" '
                     f'fill-opacity="0.75"/>')
        if a != b:
            parts.append(f'<text x="{x + 5:.1f}" y="{top + 5}" font-family="sans-serif" '
                         f'font-size="10" fill="#88939b">{html.escape(str(label))}</text>')
        if a > 0:
            parts.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" '
                         f'y2="{base_y + 8}" stroke="#c9d2d6" stroke-dasharray="3 3"/>')
    # 每年色块 + 转折 + 事件
    prev_band = None
    for i, y in enumerate(years):
        band = y["band"]
        x = left + i * step + (step - bw) / 2
        yy = top + (4 - BAND_ROW[band]) * row_h + 6
        parts.append(f'<rect x="{x:.1f}" y="{yy:.1f}" width="{bw:.1f}" '
                     f'height="{row_h - 16}" rx="2" fill="{BAND_COLOR[band]}" '
                     f'fill-opacity="0.88"><title>{html.escape(str(y.get("year", "")))}'
                     f' {html.escape(str(y.get("ganzhi", "")))}｜{html.escape(band)}｜'
                     f'{html.escape(str(y.get("tendency", "")))}｜'
                     f'{html.escape(str(y.get("source_ref", "")))}</title></rect>')
        if band != prev_band and i > 0:
            cx = left + i * step
            parts.append(f'<line x1="{cx:.1f}" y1="{top}" x2="{cx:.1f}" '
                         f'y2="{base_y + 8}" stroke="#b06a3b" stroke-width="1.1" '
                         f'stroke-opacity="0.55"/>')
            parts.append(f'<text x="{cx + 3:.1f}" y="{base_y + 22}" '
                         f'font-family="sans-serif" font-size="9" fill="#b06a3b">转折</text>')
        prev_band = band
        for ev in y.get("events") or []:
            st = ev.get("verificationStatus", "pending")
            parts.append(f'<circle cx="{x + bw/2:.1f}" cy="{base_y - 10:.1f}" r="4.5" '
                         f'fill="{"#24313a" if st == "verified" else "none"}" '
                         f'stroke="#24313a" stroke-width="1.2"><title>'
                         f'{html.escape(str(ev.get("title", "")))}（{st}）</title></circle>')
        if i % max(1, n // 12) == 0:
            parts.append(f'<text x="{x + bw/2:.1f}" y="{base_y + 38:.1f}" '
                         f'text-anchor="middle" font-family="sans-serif" font-size="10" '
                         f'fill="#6b7780">{html.escape(str(y.get("year", "")))}</text>')
    parts.append(f'<text x="{left}" y="{H - 38}" font-family="sans-serif" '
                 f'font-size="10" fill="#6b7780">事件标记：● 已核验　○ 待核验　× 未证实'
                 f'　｜　转折＝运段切换，不判吉凶</text>')
    # 图例
    lx = W - right - 320
    for i, band in enumerate(BANDS):
        parts.append(f'<rect x="{lx + i * 62}" y="{H - 26}" width="10" height="10" '
                     f'rx="2" fill="{BAND_COLOR[band]}"/>')
        parts.append(f'<text x="{lx + i * 62 + 14}" y="{H - 17}" '
                     f'font-family="sans-serif" font-size="9" fill="#6b7780">'
                     f'{html.escape(band)}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def demo() -> dict:
    """确定性示例：只用结构事实与用忌神运段，不含任何断语正文。"""
    bands = ["平运", "喜神运", "用神运", "用神运", "忌神运", "忌神运",
             "平运", "喜神运", "用神运", "用神运", "病神运", "平运"]
    out = []
    for i, b in enumerate(bands):
        y = {"age": 30 + i, "year": 1990 + i, "ganzhi": "示例干支",
             "dayun": "丙子大运" if i < 6 else "丁丑大运", "band": b,
             "tendency": "倾向守成，建议关注节奏", "reason": "结构事实示例",
             "source_ref": "册 100 §用忌神落地 / 册 102 §R23",
             "events": []}
        if i in (2, 5, 9):
            y["events"] = [{"title": "阶段回顾", "verificationStatus":
                            ["verified", "pending", "unverified"][i % 3]}]
        out.append(y)
    return {"title": "玄鉴命理馆 · 命途轨迹（示例·结构性示意）",
            "start_age": 30, "years": out}


def selftest():
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    d = demo()
    v = validate(d)
    ck("示例输入合法", v["ok"])
    svg = render(d)
    ck("SVG 根标签", svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
    ck("大运分区存在", "丙子大运" in svg and "丁丑大运" in svg)
    ck("转折标注存在", "转折" in svg)
    ck("事件三态图例", all(s in svg for s in ("●", "○", "×")))
    ck("无 K 线四价", not any(x in svg for x in ("open", "close", "high", "low")))
    ck("无运势分", "运势分" not in svg)
    ck("无本人寿元", "寿元" not in svg)
    ck("五类运段齐全", all(b in svg for b in BANDS))
    ck("禁分数字段拒绝", not validate({"years": [dict(d["years"][0], score=88)]})["ok"])
    ck("禁 OHLC 字段拒绝", not validate({"years": [dict(d["years"][0], open=1)]})["ok"])
    ck("非法运段拒绝", not validate({"years": [dict(d["years"][0], band="大吉")]})["ok"])
    ck("绝对化措辞拒绝",
       not validate({"years": [dict(d["years"][0], tendency="必定大富")]})["ok"])
    ck("缺引证拒绝",
       not validate({"years": [{k: val for k, val in d["years"][0].items()
                               if k != "source_ref"}]})["ok"])
    ck("无倾向措辞拒绝",
       not validate({"years": [dict(d["years"][0], tendency="大发")]})["ok"])
    ck("非法验证状态拒绝",
       not validate({"years": [dict(d["years"][0], events=[
           {"title": "x", "verificationStatus": "maybe"}])]})["ok"])
    ck("空 years 拒绝", not validate({"years": []})["ok"])
    ck("整体禁词拒绝", not validate(dict(d, title="本人寿元 73 岁"))["ok"])
    ck("渲染非法输入抛错", (lambda: _raises(d))())
    ok = sum(v2 for _, v2 in cases)
    for n, v2 in cases:
        if not v2:
            print("FAIL", n)
    print(f"mingtu_kline selftest: {ok}/{len(cases)} passed")
    return 0 if ok == len(cases) else 1


def _raises(d):
    bad = dict(d, years=[dict(d["years"][0], score=1)])
    try:
        render(bad)
        return False
    except ValueError:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="demo")
    ap.add_argument("--input"); ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or a.cmd == "selftest":
        return selftest()
    data = demo() if a.cmd == "demo" else json.loads(
        pathlib.Path(a.input).read_text(encoding="utf-8"))
    v = validate(data)
    if not v["ok"]:
        print(json.dumps(v, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    svg = render(data)
    if a.out:
        pathlib.Path(a.out).write_text(svg, encoding="utf-8")
        print(f"written {a.out} ({len(svg)} bytes, {v['points']} points)")
    else:
        print(svg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
