#!/usr/bin/env python3
"""八字查重：给定四柱，检索档案库里是否已有该八字档。

用法：
    python3 find_chart.py 命理档案 丁酉己酉丙午辛卯        # 精确查八柱
    python3 find_chart.py 命理档案 庚寅己卯戊午 --fuzzy    # 缺时柱，查同日前三柱
    python3 find_chart.py 命理档案 丁酉己酉丙午辛卯 --组 客户   # 只看某一关系圈

命中时同时报出**分组与称呼**（`档案索引.json`）。同组撞盘要特别小心：
同一片关系圈里出现同一个八字，多半是**同一个人被重复归档**，
不是「巧合同盘」——先比对性别、出生地、称呼再决定是追加还是新建。
"""

import argparse
import os
import pathlib
import re
import sys

天干地支字 = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")


def 归一化(字串):
    return re.sub(r"[\s·、,，]", "", 字串)


def 主程序():
    p = argparse.ArgumentParser(description="命理档案查重")
    p.add_argument("库", help="档案库根目录，例如 命理档案")
    p.add_argument("盘", help="四柱连写（八字）或前三柱（六字）")
    p.add_argument("--fuzzy", action="store_true", help="按前三柱模糊匹配")
    p.add_argument("--组", dest="组", default=None, help="只看某一分组（家人/朋友/同学/同事/客户/名人/其他）")
    a = p.parse_args()

    库 = pathlib.Path(a.库).expanduser()
    八字库 = 库 / "八字库"
    if not 八字库.is_dir():
        sys.exit("找不到八字库目录：%s（可用 init_library.py 建库）" % 八字库)

    盘 = 归一化(a.盘)
    杂字 = set(盘) - 天干地支字 - {"补", "时", "待"}
    if 杂字:
        print("提示：输入含非干支字符 %s，已忽略" % "".join(杂字))
        盘 = "".join(c for c in 盘 if c in 天干地支字)

    命中 = []
    for 档 in sorted(八字库.iterdir()):
        if not 档.is_dir():
            continue
        名 = 归一化(档.name)
        核心 = 名.replace("待补时", "")
        if not a.fuzzy:
            if 核心 == 盘 or 盘.startswith(核心) or 核心.startswith(盘):
                命中.append((档, "全同" if 核心 == 盘 else "部分（请核时辰）"))
        else:
            if 核心.startswith(盘[:6]) and len(盘) >= 6:
                命中.append((档, "同前三柱"))

    # 分组信息来自 档案索引.json；读不到就当没有，不影响查重本身
    组们 = {}
    try:
        import groups as _g
        for x in _g.清单(库):
            组们[x.get("档号", "")] = x
    except Exception:
        _g = None

    print("检索：%s（%s）%s" % (盘, "模糊" if a.fuzzy else "精确",
                             "　只看分组：%s" % a.组 if a.组 else ""))
    if a.组 and _g is not None and a.组 not in _g.分组们:
        print("提示：分组「%s」不在允许列表（%s）" % (a.组, "／".join(_g.分组们)))

    同组 = []
    if 命中:
        print("命中 %d 档，请打开《命主记录.md》比对性别与出生地：\n" % len(命中))
        for 档, 说明 in 命中:
            项 = 组们.get(归一化(档.name).replace("待补时", ""), {})
            g = 项.get("分组", "") or "未登记"
            c = 项.get("称呼", "")
            if a.组 and g != a.组:
                continue
            if a.组 and g == a.组:
                同组.append((档, c))
            print("  %s  →  %s　分组：%s%s" % (档, 说明, g, ("（%s）" % c) if c else ""))
            print("     卡片：%s" % (档 / "档案卡片.md"))
        if 同组:
            print("\n！同组撞盘 %d 档：同一片关系圈里出现同一个八字，**多半是同一个人被重复归档**。"
                  % len(同组))
            print("   先比对性别、出生地、称呼；确认同一人才追加，另一人才另立。")
        print("\n处置：命中即追加，不新建；只有全部核对不符时才另立新档。")
    else:
        print("无命中 → 可以按此四柱新建一档。")
        print("待补时辰时，目录名用前三柱加「待补时」后缀：%s待补时" % 盘[:6])
    return 0


def 自检():
    """查重本身 + 分组回显。库用临时目录，不碰真档案。"""
    import shutil
    import tempfile
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("归一化·去标点", 归一化("丁酉 己酉、丙午，辛卯") == "丁酉己酉丙午辛卯")
    查("干支字表齐", len(天干地支字) == 22)

    td = tempfile.mkdtemp()
    try:
        库 = os.path.join(td, "命理档案")
        os.makedirs(os.path.join(库, "八字库", "丁酉己酉丙午辛卯"))
        查("无索引·查重照样跑", os.path.isdir(os.path.join(库, "八字库")))
        import groups as g
        g.登记(库, "丁酉己酉丙午辛卯", "客户", "张先生", 建卡=True)
        项 = {x["档号"]: x for x in g.清单(库)}
        查("登记后索引有该档", 项["丁酉己酉丙午辛卯"]["分组"] == "客户")
        查("同档不同组可查出来", g.统计(库)[0]["客户"] == 1)
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(自检())
    sys.exit(主程序())
