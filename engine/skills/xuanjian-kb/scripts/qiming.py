#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取名体检：把五格算给你看，但不拿它断（玄鉴命理馆 · 见 references/84）

为什么要有这个脚本：客户常拿"某 APP 给我的名字打 92 分"来问。要答得干净，
必须**先能把它的数算出来**，再说明为什么本馆不用它断（84 §1、§5）。
算不出就辩不赢；算得出还得知道自己不靠它。

用法：
  python3 qiming.py 诸葛亮 --bi 15,10,9
  python3 qiming.py 王明 --bi 4,8
  python3 qiming.py 欧阳修 --bi 15,17,10 --fl 2 --tone 2,2,1
  python3 qiming.py 诸葛亮 --kangxi ~/kangxi-strokecount.csv   # 自动查康熙笔画并对照
  python3 qiming.py --selftest

口径（写死在代码里）：
  1. 五格用**康熙笔画（繁体）**，不是简体笔画；脚本不内置字典，笔画由使用者查定后输入，
     **不猜笔画**——猜出来的五格比不算更糟。
  2. 只出数、五格名、三才五行，**不出吉凶断语、不出评分**（84 §5）。
  3. 三才五行按数的个位：1–2 木、3–4 火、5–6 土、7–8 金、9–0 水。
  4. 声调检查只做"结构"（同调、全平、全仄），不判好坏。
  5. 若要自动查笔画，用 `--kangxi` 指向康熙字典笔划对照表（breezyreeds/kangxi-strokecount，
     MIT，覆盖康熙字典 63696 字）。**注意它按字形查**：简体字查到的是简体字形的笔数
     （华＝6、華＝14），而五格用繁体（正体）笔数——**简体名须先转正体再查**，否则五格全错。
     对照表与本脚本自带的两条口径都在 `88` §6。
"""

import argparse
import sys

WUXING_BY_DIGIT = {1: "木", 2: "木", 3: "火", 4: "火", 5: "土",
                   6: "土", 7: "金", 8: "金", 9: "水", 0: "水"}

# 人工检查清单：脚本只打印，不代判
CHECKLIST = [
    ("读音", "连姓带名读三遍，快读慢读都不拗口；普通话与家乡话各读一遍"),
    ("谐音", "有无不雅谐音、绰号联想（含网络流行语与方言）"),
    ("字义", "逐字查本义与常用义；不取夸大、不取贬义、不取生造"),
    ("字形", "笔画不繁（书写负担）、结构不挤（左右/上下失衡）、不用生僻字"),
    ("录入", "能否上户口、买机票、办银行卡（生僻字与异体字常打不出）"),
    ("重名", "近十年高频字尽量避开（涵/梓/轩/萱/沐/辰一类），同名太多生活添麻烦"),
    ("避讳", "不与直系长辈同名同音；有字辈的按字辈"),
    ("性别", "气质与性别相符即可，不必强分；但要想到上学被取笑的可能"),
    ("时代", "不用一时流行语，也不用过于古奥到无人识读的字"),
    ("中道", "名字不要把话说满——太满则无退路（84 §2，诸葛亮字孔明之例）"),
]


def load_kangxi(path):
    """读康熙字典笔划对照表：列格式 U+XXXX,十进制,字,笔画（breezyreeds/kangxi-strokecount，MIT）。"""
    import csv, os
    if not os.path.exists(path):
        raise SystemExit("找不到康熙笔画表：%s" % path)
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) == 4 and row[0].startswith("U+") and len(row[2]) == 1:
                try:
                    out[row[2]] = int(row[3])
                except ValueError:
                    pass
    return out


def wuxing(n):
    return WUXING_BY_DIGIT[n % 10]


def wuge(bi, fl=1):
    """bi：按字序的康熙笔画列表；fl：姓的字数（1 单姓 / 2 复姓）。"""
    n = len(bi)
    if fl not in (1, 2) or n <= fl:
        raise ValueError("姓 %d 字、全名 %d 字，不成立" % (fl, n))
    xing, ming = bi[:fl], bi[fl:]
    tian = xing[0] + 1 if fl == 1 else xing[0] + xing[1]
    ren = xing[-1] + ming[0]
    di = sum(ming) if len(ming) >= 2 else ming[0] + 1
    zong = sum(bi)
    wai = 2 if (fl == 1 and len(ming) == 1) else zong - ren + 1
    return {"天格": tian, "人格": ren, "地格": di, "外格": wai, "总格": zong}


def santai(g):
    return wuxing(g["天格"]) + wuxing(g["人格"]) + wuxing(g["地格"])


def tone_report(tone):
    """tone: 每字声调 1–4（轻声记 0）。只报结构。"""
    names = {1: "阴平", 2: "阳平", 3: "上声", 4: "去声", 0: "轻声"}
    ping = [t in (1, 2) for t in tone]
    out = ["声调　　" + "／".join(names.get(t, str(t)) for t in tone)]
    out.append("平仄　　" + "".join("平" if p else "仄" for p in ping))
    flags = []
    if len(set(tone)) == 1:
        flags.append("全名同调，读起来平板")
    if all(ping):
        flags.append("全平，缺顿挫")
    if not any(ping):
        flags.append("全仄，读音偏硬")
    if len(tone) >= 2 and tone[0] == tone[-1]:
        flags.append("首尾同调，收尾弱")
    out.append("提示　　" + ("；".join(flags) if flags else "无明显结构问题"))
    return out


def render(name, bi, fl=1, tone=None):
    g = wuge(bi, fl)
    L = []
    L.append("═" * 44)
    L.append("  %s　（%d 字，%s，笔画 %s）"
             % (name, len(name), "复姓" if fl == 2 else "单姓", ",".join(map(str, bi))))
    L.append("═" * 44)
    L.append("  五格（康熙笔画）")
    for k in ("天格", "人格", "地格", "外格", "总格"):
        L.append("    %s　%2d　→ %s" % (k, g[k], wuxing(g[k])))
    L.append("  三才　　%s（天／人／地）" % santai(g))
    if tone:
        L.append("─" * 44)
        for line in tone_report(tone):
            L.append("  " + line)
    L.append("─" * 44)
    L.append("  这张表能做什么：把五格算准，好在客户拿「APP 打分」来问时，算给他看。")
    L.append("  这张表不做什么：不给吉凶、不给评分、不给「该不该改名」。")
    L.append("    理由见 84 §1——同划数的人成千上万，命运各异；")
    L.append("    「有例外就不是理论」（天纪 08-yili，00:10:16）。")
    L.append("─" * 44)
    L.append("  取名的正办（84 §3）：取神不取形——音、形、义、用四条 + 中道一条。")
    L.append("  人工检查清单：")
    for i, (k, v) in enumerate(CHECKLIST, 1):
        L.append("    %2d. %s：%s" % (i, k, v))
    return "\n".join(L)


def selftest():
    g = wuge([16, 15, 9], 1)          # 诸葛亮（康熙笔划表实测：諸16 葛15 亮9）
    assert (g["天格"], g["人格"], g["地格"], g["总格"], g["外格"]) == (17, 31, 24, 40, 10), g
    assert santai(g) == "金木火", santai(g)
    g2 = wuge([4, 8], 1)              # 王明：单姓单名，外格恒 2
    assert (g2["天格"], g2["人格"], g2["地格"], g2["总格"], g2["外格"]) == (5, 12, 9, 12, 2), g2
    assert santai(g2) == "土木水", santai(g2)
    g3 = wuge([15, 17, 10], 2)        # 欧阳修（歐15 陽17 修10）
    assert (g3["天格"], g3["人格"], g3["地格"], g3["外格"]) == (32, 27, 11, 16), g3
    g4 = wuge([7, 5], 1)              # 李白：单名地格 = 名笔画 + 1
    assert g4["地格"] == 6, g4
    assert wuxing(10) == "水" and wuxing(19) == "水" and wuxing(16) == "土"
    assert wuxing(1) == "木" and wuxing(8) == "金"
    r = tone_report([3, 1, 4])
    assert "平仄　　仄平仄" in r[1], r
    print("selftest OK：五格五格名、单姓单名外格恒二、三才、个位五行、平仄五项皆对")


def main(argv=None):
    ap = argparse.ArgumentParser(description="取名体检：算五格，不断吉凶")
    ap.add_argument("name", nargs="?", help="全名（含姓）")
    ap.add_argument("--bi", help="按字序的康熙笔画，逗号分隔，如 16,15,9")
    ap.add_argument("--kangxi", help="康熙笔划对照表 CSV（breezyreeds/kangxi-strokecount，MIT）")
    ap.add_argument("--fl", type=int, default=1, help="姓的字数：1 单姓（默认）／2 复姓")
    ap.add_argument("--tone", help="按字序的声调 1–4，逗号分隔，如 3,1,4")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
        return 0
    if not a.name:
        ap.print_help()
        return 2

    bi = [int(x) for x in a.bi.replace("，", ",").split(",") if x.strip()] if a.bi else None
    if a.kangxi:
        tab = load_kangxi(a.kangxi)
        auto = [tab.get(c) for c in a.name]
        miss = [c for c in a.name if c not in tab]
        print("康熙笔划表：" + "  ".join("%s=%s" % (c, n if n else "缺") for c, n in zip(a.name, auto)))
        if miss:
            print("  表里没有：%s（不猜，请另行查定）" % "".join(miss))
        print("  提醒：表按字形给笔画，简体字须先转正体（华＝6、華＝14）；五格用繁体笔数。")
        if bi is None:
            if miss:
                print("  缺字未补，无法计算五格。")
                return 2
            bi = auto
        else:
            diff = [(c, x, y) for c, x, y in zip(a.name, bi, auto) if y and x != y]
            if diff:
                print("  与手输不一致：" + "；".join("%s 手输%d／表%d" % d for d in diff))
                print("  → 以核对过的口径为准，别两个数混着用。")
            else:
                print("  与手输一致。")
    if not bi:
        ap.print_help()
        return 2
    if len(bi) != len(a.name):
        print("笔画数 %d 与名字字数 %d 不符" % (len(bi), len(a.name)))
        return 2
    tone = [int(x) for x in a.tone.replace("，", ",").split(",")] if a.tone else None
    print(render(a.name, bi, a.fl, tone))
    return 0


if __name__ == "__main__":
    sys.exit(main())
