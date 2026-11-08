#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库自洽性检查（玄鉴命理馆 · 对应 69 的口径与 74 的登记纪律）

检查五类问题，只报不改：
  1. 册号重复、文件名号与正文标题号不一致
  2. 交叉引用指向不存在的册（`NN` 形式）
  3. Markdown 表格列数不一致
  4. 禁编词共现：写了大六壬／建除／紫白日课等，却没标注"只作工具／不扩展／候选未决"
  5. 版本口径：plugin.json 版本与 README／36 号册声明是否一致

用法：
  python3 kb_audit.py            # 检查并打印报告
  python3 kb_audit.py --strict   # 有问题即非零退出（可挂进 CI）
"""

import argparse
import glob
import json
import os
import re
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(KB, "references")
PLUGIN = os.path.dirname(os.path.dirname(KB))  # .../xuanjian-mingli

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cn_to_int(s):
    """把「八十一」这类中文序数转成 81。"""
    if not s:
        return None
    # 「一百零八」这类带零的，原实现把零后的数字丢了（算成 100）。当前册号还没过百，
    # 属潜伏错；百号之后必有此写法，先修（v1.58.0 自检抓到）。
    if "零" in s:
        a, _, b = s.partition("零")
        return (cn_to_int(a) or 0) + (cn_to_int(b) or 0)
    total = 0
    if "百" in s:
        a, _, b = s.partition("百")
        total += (CN_NUM.get(a, 1) if a else 1) * 100
        s = b
    if "十" in s:
        a, _, b = s.partition("十")
        total += (CN_NUM.get(a, 1) if a else 1) * 10
        total += CN_NUM.get(b, 0) if b else 0
    elif s:
        total += CN_NUM.get(s, 0)
    return total


def load_volumes():
    vols = {}
    dups = []
    for p in sorted(glob.glob(os.path.join(REF, "*.md"))):
        base = os.path.basename(p)
        m = re.match(r"^(\d+)-(.*)\.md$", base)
        if not m:
            continue
        num = int(m.group(1))
        if num in vols:
            dups.append((num, vols[num][0], base))
        vols[num] = (base, p)
    return vols, dups


def check_dir_completeness():
    """references/ 里有没有「检查器看不见」的文件。

    load_volumes 只认 `数字-标题.md`，认不出的直接 skip。这意味着一个叫
    `98-新册.md.bak`、`草稿.md`、`99-待定.MD` 的文件可以整篇消失于所有检查——
    六道检查全绿，而那份册页根本没被看过。v1.58.0 补此闸。
    """
    stray = []
    for p in sorted(glob.glob(os.path.join(REF, "*"))):
        b = os.path.basename(p)
        if b.startswith(".") or os.path.isdir(p):
            continue
        if not re.match(r"^\d+-.+\.md$", b):
            stray.append(b)
    return stray


def check_gaps(vols):
    """册号断号。断号意味着有册页消失，而引用它的地方会变成悬空引用。"""
    if not vols:
        return []
    return [i for i in range(1, max(vols) + 1) if i not in vols]


def check_titles(vols):
    bad = []
    for num, (base, p) in vols.items():
        first = open(p, encoding="utf-8").readline().strip()
        # 2026-11-07：册号过百后「一百零一／一百零二」进不了字符类（漏「零」），
        # 标题明明写了中文序号却判「无中文序号」。cn_to_int 早就能算对，坏的是这道正则。
        m = re.match(r"^#\s*([一二三四五六七八九十百零]+)、", first)
        if not m:
            bad.append((base, "标题无中文序号"))
            continue
        if cn_to_int(m.group(1)) != num:
            bad.append((base, "标题号「%s」≠ 文件号 %d" % (m.group(1), num)))
    return bad


def check_refs(vols):
    missing = {}
    for num, (base, p) in vols.items():
        t = open(p, encoding="utf-8").read()
        for ref in set(re.findall(r"`(\d{1,3})`", t)):
            r = int(ref)
            # 原判据是 `r not in vols and r > max(vols)`，只报「指向未来的号」。
            # 册号一旦出现断号（某册被删或改名），指向那个断号的引用一条都不会报。
            if r not in vols:
                missing.setdefault(base, set()).add(ref)
    return missing


def check_tables(vols):
    bad = []
    for num, (base, p) in vols.items():
        lines = open(p, encoding="utf-8").read().split("\n")
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("|"):
                j = i
                widths = []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    widths.append(lines[j].count("|"))
                    j += 1
                if len(set(widths)) > 1:
                    bad.append((base, i + 1, sorted(set(widths))))
                i = j
            else:
                i += 1
    return bad


# 禁编词 → 必须同时出现的限定语（任一即可）
FENCE = {
    # 词：必须同时出现的限定语（任一即可）
    "大六壬": ["只作工具", "只作装盘", "不作断语", "断不展开", "只装盘"],
    # 2026-11-02 起择日下半层已开（83），故"已开／本册／83"也算合规限定
    "建除": ["已开", "本册", "`83`", "不扩展", "不自排", "只翻通书", "参考"],
    "黄黑道": ["已开", "本册", "`83`", "不扩展", "不自排", "只翻通书", "参考"],
    "紫白日课": ["候选未决", "未开", "不扩展", "不展开", "不构成开册", "若将来", "待议"],
    # 2026-11-02 七轮：五格"能算不能断"，胎神"本馆不出"——两词一出场就必须带限定
    "五格": ["不拿它断", "不用它断", "不能断", "不作断语", "能算不断"],
    "胎神": ["不出", "不替客户解"],
    # 第八轮：值宿"能算不出"，出场必须带这层限定
    "值宿": ["不出", "只印宿名", "吉凶不出", "选择不出"],
}


# 2026-11-04 订正（TR108 §4，分辨「订正」而非「回归」之后）：
# KB95 的「一气专旺五格／特殊五格」是八字格局术语（出自第二十八课「五格与库」），
# 与取名三才五格毫无关系。原检测器把两个「五格」当一个禁编词，报了假警。
# 处理方式是给检测器加语境白名单，不删词、不改册页、不放宽取名侧的限定。
WUGE_BAZI_CONTEXT = ("一气专旺", "特殊五格", "五格与库", "专旺")
WUGE_NAMING_CONTEXT = ("取名", "姓名学", "三才", "康熙")


def check_fences(vols):
    hits = []
    for num, (base, p) in vols.items():
        t = open(p, encoding="utf-8").read()
        for kw, oks in FENCE.items():
            if kw == "五格" and any(c in t for c in WUGE_BAZI_CONTEXT) \
                    and not any(c in t for c in WUGE_NAMING_CONTEXT):
                continue
            if kw in t and not any(o in t for o in oks):
                hits.append((base, kw, oks[0]))
    return hits


def check_version():
    out = []
    pj = os.path.join(PLUGIN, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(pj):
        return [("plugin.json", "找不到")]
    ver = json.load(open(pj, encoding="utf-8")).get("version")
    rd = os.path.join(PLUGIN, "README.md")
    if os.path.exists(rd):
        t = open(rd, encoding="utf-8").read()
        nums = re.findall(r"下 (\d+) 份 references", t)
        actual = len(glob.glob(os.path.join(REF, "*.md")))
        if not nums:
            # 原来这里静默跳过：README 换了说法，闸门就再也没读过册数。
            out.append(("README.md", "找不到「下 N 份 references」这句，册数无从校对"))
        elif int(nums[0]) != actual:
            out.append(("README.md", "册数声明 %s ≠ 实际 %d" % (nums[0], actual)))
    return out, ver


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--next", action="store_true", help="只报下一个可用册号（新增册页前先跑它）")
    a = ap.parse_args(argv)

    vols, dups = load_volumes()
    if a.next:
        # 撞过两次号的教训：编号前先问它，别凭记忆
        print("册数 %d，最大号 %d → 下一个可用号：%d" % (len(vols), max(vols), max(vols) + 1))
        if dups:
            print("⚠ 当前已有重号，先修重号再编号：")
            for num, a1, b1 in dups:
                print("   %d：%s ／ %s" % (num, a1, b1))
        return 0
    problems = 0
    print("== 知识库自洽检查 ==")
    print("册数：%d（最大号 %d）" % (len(vols), max(vols)))

    if dups:
        problems += len(dups)
        print("\n[1] 册号重复：")
        for num, a1, b1 in dups:
            print("   %d：%s ／ %s" % (num, a1, b1))
    else:
        print("\n[1] 册号重复：无")

    bad_titles = check_titles(vols)
    if bad_titles:
        problems += len(bad_titles)
        print("\n[2] 标题号与文件号不一致：")
        for b, why in bad_titles:
            print("   %s：%s" % (b, why))
    else:
        print("[2] 标题号：一致")

    missing = check_refs(vols)
    if missing:
        problems += len(missing)
        print("\n[3] 引用了不存在的册：")
        for b, refs in missing.items():
            print("   %s → %s" % (b, "、".join(sorted(refs))))
    else:
        print("[3] 交叉引用：无悬空")

    bad_tables = check_tables(vols)
    if bad_tables:
        problems += len(bad_tables)
        print("\n[4] 表格列数不一致：")
        for b, ln, w in bad_tables:
            print("   %s:%d 列宽 %s" % (b, ln, w))
    else:
        print("[4] 表格：列数一致")

    fences = check_fences(vols)
    if fences:
        problems += len(fences)
        print("\n[5] 禁编词缺少限定语（需人工确认）：")
        for b, kw, need in fences:
            print("   %s：出现「%s」，未见「%s」一类限定" % (b, kw, need))
    else:
        print("[5] 禁编词限定：齐备")

    ver = check_version()
    if isinstance(ver, tuple):
        rows, v = ver
        if rows:
            problems += len(rows)
            print("\n[6] 版本口径：")
            for b, why in rows:
                print("   %s：%s" % (b, why))
        else:
            print("[6] 版本与册数：一致（plugin %s）" % v)
    else:
        print("\n[6] 版本：读取失败 %s" % ver)
        problems += 1

    stray = check_dir_completeness()
    if stray:
        problems += len(stray)
        print("\n[7] 目录里有检查器看不见的文件（未按「数字-标题.md」命名）：")
        for b in stray:
            print("   %s" % b)
    else:
        print("[7] 目录完整性：无游离文件")

    gaps = check_gaps(vols)
    if gaps:
        problems += len(gaps)
        print("\n[8] 册号断号（有册页消失，引用它的地方会悬空）：")
        print("   %s" % "、".join(str(g) for g in gaps))
    else:
        print("[8] 册号连续性：1–%d 无断号" % max(vols))

    print("\n结论：%s" % ("发现问题 %d 处" % problems if problems else "全部通过"))
    if a.strict and problems:
        return 1
    return 0


# ---------------------------------------------------------------- 自检
def 自检():
    """册页自洽闸自己的体检。

    这台闸是「册页有没有坏」的唯一报警器，它有三种安静的死法：
      ① **算错**——中文序数转错，标题号对不上也判一致；
      ② **看不见**——只认 `数字-标题.md`，别的命名直接 skip，那些册页等于没检查；
      ③ **判据太窄**——交叉引用只盯「比最大号还大的号」，册号一旦断号，
         指向断号的那些引用一条都不会报。
    本节按这三种死法逐条测，全部在临时目录里造样本，不碰真册页。
    """
    import tempfile
    import shutil
    import contextlib
    import io

    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    def 造(文件们):
        根 = tempfile.mkdtemp(prefix="kbaudit-")
        for 名, 文 in 文件们.items():
            路 = os.path.join(根, 名)
            父 = os.path.dirname(路)
            if 父 and not os.path.isdir(父):
                os.makedirs(父, exist_ok=True)
            with open(路, "w", encoding="utf-8") as f:
                f.write(文)
        return 根

    原REF, 原PLUGIN = globals()["REF"], globals()["PLUGIN"]
    临时 = []
    try:
        # ── 一、中文序数 ────────────────────────────────────────────────
        查("序数·一 = 1", cn_to_int("一") == 1)
        查("序数·十 = 10", cn_to_int("十") == 10)
        查("序数·二十三 = 23", cn_to_int("二十三") == 23)
        查("序数·八十一 = 81", cn_to_int("八十一") == 81)
        查("序数·九十七 = 97", cn_to_int("九十七") == 97)
        查("序数·一百 = 100", cn_to_int("一百") == 100)
        查("序数·一百零八 = 108（原实现算成 100）", cn_to_int("一百零八") == 108)
        查("序数·空给 None", cn_to_int("") is None and cn_to_int(None) is None)

        # ── 二、册号装载：重号必须抓到 ──────────────────────────────────
        根 = 造({"1-甲.md": "# 一、甲\n", "2-乙.md": "# 二、乙\n", "3-丙.md": "# 三、丙\n"})
        临时.append(根)
        globals()["REF"] = 根
        vols, dups = load_volumes()
        查("装载·三册都进来", len(vols) == 3 and not dups)
        查("装载·文件名留着", os.path.basename(vols.get(2, ("", ""))[1]) == "2-乙.md")

        根 = 造({"1-甲.md": "# 一、甲\n", "1-重.md": "# 一、重\n"})
        临时.append(根)
        globals()["REF"] = 根
        _, dups = load_volumes()
        查("装载·重号抓到一条", len(dups) == 1 and dups[0][0] == 1)

        # ── 三、目录完整性：检查器看不见的文件必须报出来 ────────────────
        根 = 造({"1-甲.md": "# 一、甲\n", "备注.md": "随手记\n",
                 "2-乙.md.bak": "备份\n", ".隐藏.md": "隐藏\n"})
        临时.append(根)
        globals()["REF"] = 根
        游离 = check_dir_completeness()
        查("游离·抓到「备注.md」", "备注.md" in 游离)
        查("游离·抓到不合规的 .bak", "2-乙.md.bak" in 游离)
        查("游离·正常册页不误报", "1-甲.md" not in 游离)
        查("游离·点开头的不算", ".隐藏.md" not in 游离)

        # ── 四、断号 ────────────────────────────────────────────────────
        查("断号·缺 2 就报 2", check_gaps({1: ("a", "a"), 3: ("c", "c")}) == [2])
        查("断号·连号不报", check_gaps({1: ("a", "a"), 2: ("b", "b")}) == [])
        查("断号·空表不炸", check_gaps({}) == [])

        # ── 五、标题号 ──────────────────────────────────────────────────
        根 = 造({"1-甲.md": "# 一、甲\n", "2-乙.md": "# 三、乙\n",
                 "3-丙.md": "# 没有序号的标题\n",
                 "101-丁.md": "# 一百零一、丁\n", "102-戊.md": "# 一百零二、戊\n"})
        临时.append(根)
        globals()["REF"] = 根
        vols, _ = load_volumes()
        坏 = dict((b, why) for b, why in check_titles(vols))
        查("标题·对的放行", "1-甲.md" not in 坏)
        查("标题·号对不上要报", "2-乙.md" in 坏 and "≠" in 坏["2-乙.md"])
        查("标题·没有中文序号要报", "3-丙.md" in 坏)
        # 2026-11-07：带「零」的百号标题曾被正则判成「无中文序号」，故单列两条
        查("标题·一百零一 = 101 放行", "101-丁.md" not in 坏)
        查("标题·一百零二 = 102 放行", "102-戊.md" not in 坏)

        # ── 六、交叉引用：指向断号也算悬空（本轮修的洞）──────────────────
        根 = 造({"1-甲.md": "# 一、甲\n\n见 `2` 与 `9` 与 `1`。\n",
                 "3-丙.md": "# 三、丙\n"})
        临时.append(根)
        globals()["REF"] = 根
        vols, _ = load_volumes()
        缺 = check_refs(vols)
        查("引用·指向未来号要报", "9" in 缺.get("1-甲.md", set()))
        查("引用·指向断号也报（原判据会漏）", "2" in 缺.get("1-甲.md", set()))
        查("引用·指向已有册不报", "1" not in 缺.get("1-甲.md", set()))

        # ── 七、表格列宽 ────────────────────────────────────────────────
        根 = 造({"1-甲.md": "# 一、甲\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                 "2-乙.md": "# 二、乙\n\n| a | b |\n|---|---|\n| 1 |\n"})
        临时.append(根)
        globals()["REF"] = 根
        vols, _ = load_volumes()
        坏表 = check_tables(vols)
        查("表格·同宽不报", all(b != "1-甲.md" for b, _, _ in 坏表))
        查("表格·异宽要报", any(b == "2-乙.md" for b, _, _ in 坏表))
        查("表格·报出行号", any(isinstance(ln, int) and ln > 0 for _, ln, _ in 坏表))

        # ── 八、禁编词限定 ──────────────────────────────────────────────
        根 = 造({"1-甲.md": "# 一、甲\n\n大六壬只作装盘。\n",
                 "2-乙.md": "# 二、乙\n\n大六壬很准。\n",
                 "3-丙.md": "# 三、丙\n\n一气专旺五格讲的是从格。\n",
                 "4-丁.md": "# 四、丁\n\n取名要看三才五格。\n"})
        临时.append(根)
        globals()["REF"] = 根
        vols, _ = load_volumes()
        条 = check_fences(vols)
        查("限定·带限定不报", all(b != "1-甲.md" for b, _, _ in 条))
        查("限定·裸词要报", any(b == "2-乙.md" for b, _, _ in 条))
        查("限定·八字语境的「五格」是假警，不报", all(b != "3-丙.md" for b, _, _ in 条))
        查("限定·取名语境的「五格」照报", any(b == "4-丁.md" for b, _, _ in 条))

        # ── 九、版本闸：读不到册数不再静默通过 ──────────────────────────
        根 = 造({".codebuddy-plugin/plugin.json": '{"version": "9.9.9"}',
                 "README.md": "共 97 份参考资料。\n",
                 "references/1-甲.md": "# 一、甲\n"})
        临时.append(根)
        globals()["PLUGIN"] = 根
        globals()["REF"] = os.path.join(根, "references")
        行, 版 = check_version()
        查("版本·读取插件版本号", 版 == "9.9.9")
        查("版本·README 说法变了要报（原实现静默跳过）",
           any("册数无从校对" in why for _, why in 行))

        根 = 造({".codebuddy-plugin/plugin.json": '{"version": "9.9.9"}',
                 "README.md": "下 99 份 references。\n",
                 "references/1-甲.md": "# 一、甲\n"})
        临时.append(根)
        globals()["PLUGIN"] = 根
        globals()["REF"] = os.path.join(根, "references")
        行, _ = check_version()
        查("版本·册数对不上要报", any("≠ 实际" in why for _, why in 行))

        # ── 十、main 的退出码：--strict 必须真的影响返回码 ──────────────
        根 = 造({"1-甲.md": "# 一、甲\n\n| a | b |\n|---|---|\n| 1 |\n"})
        临时.append(根)
        globals()["REF"] = 根
        globals()["PLUGIN"] = 根
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            r = main(["--strict"])
        查("退出码·--strict 有问题给 1", r == 1)
        查("退出码·报告里说找到了问题", "发现问题" in buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            非严 = main([])
        查("退出码·不加 --strict 时只报不拦", 非严 == 0)

        # ── 十一、真库跑一遍：八项检查一项都不能有 ──────────────────────
        globals()["REF"] = 原REF
        globals()["PLUGIN"] = 原PLUGIN
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            真 = main([])
        出 = buf.getvalue()
        查("真库·结论全部通过", "全部通过" in 出)
        查("真库·八道闸都打印了", all(("[%d]" % i) in 出 for i in range(1, 9)))
        查("真库·册号无断号", check_gaps(load_volumes()[0]) == [])
        查("真库·目录无游离文件", check_dir_completeness() == [])
        查("真库·退出码 0", 真 == 0)

    finally:
        globals()["REF"] = 原REF
        globals()["PLUGIN"] = 原PLUGIN
        for d in 临时:
            shutil.rmtree(d, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(自检())
    sys.exit(main())
