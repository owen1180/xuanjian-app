#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""黄历：一页黄历能算的九栏（玄鉴命理馆 · 见 references/85、90）

只用标准库 + sxtwl，建除与黄黑道复用 zeri.py。离线、不写盘、不联网。

用法：
  python3 huangli.py 2026-11-02                     # 一页黄历（事实栏）
  python3 huangli.py --range 2026-11-01 2026-11-10  # 区间速览
  python3 huangli.py 2026-11-02 --hour 10           # 加时柱
  python3 huangli.py 2026-11-02 --xiu               # 只印值宿宿名
  python3 huangli.py 2026-11-02 --xiu-luck          # 值宿宿名＋吉凶＋歌诀
  python3 huangli.py 2026-11-02 --taishen           # 胎神占方
  python3 huangli.py 2026-11-02 --yiji              # 全本宜忌
  python3 huangli.py 2026-11-02 --full              # 三栏全出
  python3 huangli.py --selftest

口径（写死在代码里）：
  1. 年干支按立春换年，月干支按节气换月（sxtwl），不用农历正月初一；
  2. 建除、黄黑道与 zeri.py 同一实现，不另写一套；
  3. 纳音、日冲、煞方、旬空、彭祖百忌是查表，不是推算，表在下面；
  4. **2026-11-03 主人开册**：值宿吉凶、胎神占方、全本宜忌三栏由"能算不出"改为"出"，
     数据在 huangli_data.py（源自 6tail/lunar-python，MIT），断法与分寸见册九十。
     开册松的是"能不能排"，**没松**"不承诺成败、不代退行程、医疗听医生的"。
  5. 三栏一律是**通书口径**，不是本馆判决；与建除冲突时按册八十三 §4 的优先级讲，
     硬忌不因软吉而抵消（"破日＋黄道＋吉宿"仍判慎）。
"""

import argparse
import datetime
import sys
from datetime import date, timedelta

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
SHENGXIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"

JQ = ["冬至", "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨", "立夏",
      "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑", "白露", "秋分", "寒露",
      "霜降", "立冬", "小雪", "大雪"]

# 六十甲子纳音：每两柱一名，共三十
NAYIN = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火", "涧下水", "城头土",
    "白蜡金", "杨柳木", "泉中水", "屋上土", "霹雳火", "松柏木", "长流水", "沙中金",
    "山下火", "平地木", "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]

# 彭祖百忌：天干十句（甲日…癸日）
PENGZU_GAN = {
    "甲": "甲不开仓，财物耗亡", "乙": "乙不栽植，千株不长", "丙": "丙不修灶，必见灾殃",
    "丁": "丁不剃头，头主生疮", "戊": "戊不受田，田主不祥", "己": "己不破券，二比并亡",
    "庚": "庚不经络，织机虚张", "辛": "辛不合酱，主人不尝", "壬": "壬不决水，更难提防",
    "癸": "癸不词讼，理弱敌强",
}
# 地支十二句（子日…亥日）
PENGZU_ZHI = {
    "子": "子不问卜，自惹祸殃", "丑": "丑不冠带，主不还乡", "寅": "寅不祭祀，神鬼不尝",
    "卯": "卯不穿井，水泉不香", "辰": "辰不哭泣，必主重丧", "巳": "巳不远行，财物伏藏",
    "午": "午不苫盖，屋主更张", "未": "未不服药，毒气入肠", "申": "申不安床，鬼祟入房",
    "酉": "酉不宴客，醉坐颠狂", "戌": "戌不吃犬，作怪上床", "亥": "亥不嫁娶，不利新郎",
}
# 建除十二句（与 zeri.py 的建除值日配合读；彭祖原文另有这十二句）
PENGZU_JIANCHU = {
    "建": "建宜出行，不可开仓", "除": "除可服药，针灸宜良", "满": "满可肆市，服药遭殃",
    "平": "平可涂泥，安机吉昌", "定": "定宜进畜，入学名扬", "执": "执可捕捉，盗贼难藏",
    "破": "破宜治病，主必安康", "危": "危可捕鱼，不利行船", "成": "成可入学，争讼不强",
    "收": "收宜纳财，却忌安葬", "开": "开可求仕，安葬不祥", "闭": "闭不竖造，只许安床",
}

# 三煞方按三合局（日煞与年煞同一张表）
SAN_SHA = {"申": "南", "子": "南", "辰": "南", "寅": "北", "午": "北", "戌": "北",
           "亥": "西", "卯": "西", "未": "西", "巳": "东", "酉": "东", "丑": "东"}

LUNA_MONTH = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
LUNA_DAY_1 = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十"]
LUNA_DAY_2 = ["十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
LUNA_DAY_3 = ["廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]

sys.path.insert(0, __file__.rsplit("/", 1)[0])
try:
    from zeri import day_info, jianchu_of, huanghei_of, liminal
except ImportError:  # 单独拷走脚本时退化为只读本文件能算的栏
    day_info = jianchu_of = huanghei_of = liminal = None

try:
    from huangli_data import XIU_LUCK, XIU_SONG
except ImportError:  # 缺数据表时值宿只报宿名
    XIU_LUCK, XIU_SONG = {}, {}

# 胎神与全本宜忌：随包内置 cnlunar（MIT，依《钦定协纪辨方书》，见册九十 §3、§5）
_VENDOR = __file__.rsplit("/", 1)[0] + "/vendor"
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
try:
    import cnlunar as _cn
except ImportError:  # 缺库时三栏自动降级为"不出"，不报错
    _cn = None


# 二十八宿（值宿：28 日一循环）
XU28 = "角亢氐房心尾箕斗牛女虚危室壁奎娄胃昴毕觜参井鬼柳星张翼轸"
XIU_ANCHOR = date(2026, 11, 2)   # 该日值宿＝毕（cnlunar／6tail 两方同值，见 88 §5）


def xiu(y, m, d):
    """值宿宿名。只给宿名，不给吉凶（85 §2）。"""
    return XU28[(XU28.index("毕") + (date(y, m, d) - XIU_ANCHOR).days) % 28]


def xiu_luck_of(name):
    """值宿吉凶与歌诀（册九十 §2）。2026-11-03 开册后出；
    吉凶只作通书参考，不作判决，也不与建除、黄黑道互相抵消。"""
    return XIU_LUCK.get(name, ""), XIU_SONG.get(name, "")


def split_taishen(text):
    """把「厨灶床外正西」拆成（屋内所佔，屋外方位）两段。"""
    for i, ch in enumerate(text or ""):
        if ch in "内外":
            return text[:i], text[i:]
    return (text or ""), ""


def yiji_of(y, m, d):
    """全本宜忌：依《钦定协纪辨方书》一路（册九十 §3）。

    条目是年、月、日三叠神煞的结果，**必须按整日算**，不能只按日干支查表：
    实测同（日干支、月支）在不同年份结果不同——七百二十个键里六百三十九个有冲突。
    这正是「全本」与「简本」的分野，也是本馆不用简化表的原因。

    条目出自集合，跨进程顺序会变，故按该库自带的通书次序表排定，保证同一页
    两次印出来一模一样；次序表未收的条目排在末尾并按字定序，不留随机。
    """
    if _cn is None:
        return [], []
    c = _cn.Lunar(datetime.datetime(y, m, d), godType="8char")
    try:
        from cnlunar.config import thingsSort
        order = {k: i for i, k in enumerate(thingsSort)}
    except Exception:
        order = {}

    def key(x):
        return (order.get(x, 1 << 20), x)

    return sorted(c.goodThing, key=key), sorted(c.badThing, key=key)


def taishen_of(y, m, d):
    """胎神占方（册九十 §4）。返回（屋内所佔，屋外方位），缺库则 None。"""
    if _cn is None:
        return None
    c = _cn.Lunar(datetime.datetime(y, m, d), godType="8char")
    return split_taishen(c.get_fetalGod())


def ganzhi_index(gan, zhi):
    """干支序号 0–59：甲子为 0。"""
    for i in range(60):
        if GAN[i % 10] == gan and ZHI[i % 12] == zhi:
            return i
    raise ValueError("非合法干支：%s%s" % (gan, zhi))


def nayin(gan, zhi):
    return NAYIN[ganzhi_index(gan, zhi) // 2]


def chong(zhi):
    """日冲：六冲之支与所冲生肖。"""
    t = ZHI[(ZHI.index(zhi) + 6) % 12]
    return t, SHENGXIAO[ZHI.index(t)]


def xunkong(gan, zhi):
    """旬空：本旬两个空亡地支。"""
    i = ganzhi_index(gan, zhi)
    head = i - i % 10          # 旬首序号（甲x）
    kong = [(head + 10) % 12, (head + 11) % 12]
    return ZHI[kong[0]] + ZHI[kong[1]]


def lunar_text(y, m, d):
    """返回 (农历文本, sxtwl日对象或None)。无 sxtwl 时第二项为 None。"""
    try:
        import sxtwl
        day = sxtwl.fromSolar(y, m, d)
        mo, dy = day.getLunarMonth(), day.getLunarDay()
        leap = "闰" if day.isLunarLeap() else ""
        ygz = GAN[day.getYearGZ().tg] + ZHI[day.getYearGZ().dz]
        return _lunar_text_build(ygz, mo, dy, leap), day
    except Exception:
        pass
    # 离线兜底：纯数据表（不含 sxtwl）
    import _lunar_data
    ly, lm, ld, leap = _lunar_data.lunar_of(y, m, d)
    ygz = GAN[(ly - 1984) % 10] + ZHI[(ly - 1984) % 12]
    return _lunar_text_build(ygz, lm, ld, "闰" if leap else ""), None


def _lunar_text_build(ygz, mo, dy, leap):
    mname = (leap + LUNA_MONTH[mo - 1] + "月") if 1 <= mo <= 12 else ("闰月" if leap else "月")
    if dy <= 10:
        dname = LUNA_DAY_1[dy - 1]
    elif dy <= 20:
        dname = LUNA_DAY_2[dy - 11]
    else:
        dname = LUNA_DAY_3[dy - 21] if dy <= 30 else str(dy)
    return "%s年%s%s" % (ygz, mname, dname)


def hour_gz(day_gan, hour):
    """时干支：五鼠遁（甲己还加甲，乙庚丙作初…）。"""
    start = (GAN.index(day_gan) % 5) * 2
    z = ((hour + 1) // 2) % 12
    return GAN[(start + z) % 10] + ZHI[z]


def page(y, m, d, hour=None):
    """一页黄历的可算栏。返回 dict，缺 sxtwl 的项为 None。"""
    out = {"date": date(y, m, d)}
    if day_info is None:
        return out
    info = day_info(y, m, d)
    g, z, mz = info["day_gan"], info["day_zhi"], info["month_zhi"]
    mg = info.get("month_gan", "")
    lt, _ = lunar_text(y, m, d)
    yi, ji = yiji_of(y, m, d)
    out.update({
        "lunar": lt,
        "ganzhi": "%s%s日" % (g, z),
        "month_gz": "月建" + mz,
        "jianchu": jianchu_of(z, mz)[0],
        "huanghei": huanghei_of(z, mz)[:2],
        "nayin": nayin(g, z),
        "chong": chong(z),
        "sha": SAN_SHA[z],
        "xunkong": xunkong(g, z),
        "pengzu": [PENGZU_GAN[g], PENGZU_ZHI[z], PENGZU_JIANCHU[jianchu_of(z, mz)[0]]],
        "jieqi": info["jieqi"],
        "liminal": liminal(y, m, d),
        "yi": yi,
        "ji": ji,
        "taishen": taishen_of(y, m, d),
    })
    if hour is not None:
        out["hour"] = hour_gz(g, hour)
    out["xiu"] = xiu(y, m, d)
    out["xiu_luck"], out["xiu_song"] = xiu_luck_of(out["xiu"])
    return out


def next_jieqi(y, m, d):
    """往后找最近一个节气（30 天内）。"""
    if day_info is None:
        return None
    for k in range(1, 31):
        x = date(y, m, d) + timedelta(days=k)
        info = day_info(x.year, x.month, x.day)
        if info["jieqi"]:
            return x, info["jieqi"][0]
    return None


def render_one(p):
    if "lunar" not in p:
        return "缺 sxtwl，只能给出公历日期：%s" % p["date"]
    L = []
    L.append("═" * 46)
    L.append("  %s   %s" % (p["date"].strftime("%Y年%m月%d日"), p["lunar"]))
    L.append("═" * 46)
    L.append("  日干支　%s（%s）" % (p["ganzhi"], p["nayin"]))
    L.append("  月建　　%s月（节气月，非农历月）" % p["month_gz"].replace("月建",""))
    L.append("  建除　　%s日" % p["jianchu"])
    L.append("  黄黑道　%s（%s）" % (p["huanghei"][0], "黄道" if p["huanghei"][1] else "黑道"))
    L.append("  日冲　　%s%s（煞%s）" % (p["chong"][0], p["chong"][1], p["sha"]))
    L.append("  旬空　　%s" % p["xunkong"])
    if p.get("hour"):
        L.append("  时柱　　%s" % p["hour"])
    if p.get("xiu"):
        if p.get("xiu_luck"):
            L.append("  值宿　　%s（%s宿）" % (p["xiu"], p["xiu_luck"]))
        else:
            L.append("  值宿　　%s（只报宿名，吉凶未请求；罗盘配宿见 17／20）" % p["xiu"])
    if p.get("xiu_song"):
        L.append("  宿诀　　%s" % p["xiu_song"])
    if p.get("taishen"):
        L.append("  胎神　　%s　%s" % (p["taishen"][0], p["taishen"][1]))
    if "yi" in p:
        if p["yi"] == ["诸事不宜"] and p.get("ji") == ["诸事不宜"]:
            L.append("  宜忌　　诸事不宜（宜守，不是凶日；见 85 §3）")
        else:
            L.append("  宜　　　%s" % ("、".join(p["yi"]) or "（通书无）"))
            L.append("  忌　　　%s" % ("、".join(p.get("ji", [])) or "（通书无）"))
    if p["jieqi"]:
        L.append("  节气　　今日%s" % p["jieqi"][0])
    else:
        nj = next_jieqi(p["date"].year, p["date"].month, p["date"].day)
        if nj:
            L.append("  节气　　下个节气 %s（%s，%d 天后）"
                     % (nj[1], nj[0].strftime("%m-%d"), (nj[0] - p["date"]).days))
    if p["liminal"]:
        L.append("  ⚠ %s：明日%s，今日为其前一日——第一级硬忌（83 §4）"
                 % (p["liminal"][0], p["liminal"][1]))
    L.append("─" * 46)
    L.append("  彭祖百忌")
    for s in p["pengzu"]:
        L.append("    ・%s" % s)
    L.append("─" * 46)
    opened = any(k in p for k in ("xiu_luck", "taishen", "yi"))
    if opened:
        L.append("  三栏系通书口径（册九十）：不作本馆判决、不承诺成败；")
        L.append("  与建除冲突按 83 §4 讲，硬忌不因软吉抵消；医疗听医生的。")
        L.append("  默认不出；加 --full 或 --xiu-luck／--taishen／--yiji 分项出。")
    else:
        L.append("  三栏默认未印：值宿吉凶、全本宜忌、胎神占方（册九十已开，加 --full 或分项参数即出）")
    L.append("  选日请用 zeri.py（83）；本页报事实与通书栏，不给成败断语。")
    return "\n".join(L)


def render_range(a, b):
    rows = []
    cur = a
    while cur <= b:
        p = page(cur.year, cur.month, cur.day)
        if "lunar" not in p:
            return "缺 sxtwl"
        mark = ""
        if p["liminal"]:
            mark = p["liminal"][0]
        rows.append((cur, p, mark))
        cur += timedelta(days=1)
    L = ["日期        农历            日干支  建除  黄黑道      冲    忌（彭祖干支二句）"]
    for cur, p, mark in rows:
        L.append("%s  %-14s %-6s  %s   %-8s %s%s  %s／%s %s"
                 % (cur.strftime("%m-%d"),
                    p["lunar"].split("年", 1)[-1][:12],
                    p["ganzhi"], p["jianchu"] + "日",
                    p["huanghei"][0] + ("·黄" if p["huanghei"][1] else "·黑"),
                    p["chong"][0], p["chong"][1],
                    p["pengzu"][0][:6], p["pengzu"][1][:6], mark))
    L.append("")
    L.append("注：黄黑道是底色，建除是当日性质，彭祖是当日忌事；三者不分吉凶总分（83 §4）。")
    return "\n".join(L)


def selftest():
    p = page(2026, 11, 2)
    assert p["lunar"] == "丙午年九月廿四", p["lunar"]
    assert p["ganzhi"] == "庚辰日", p["ganzhi"]
    assert p["nayin"] == "白蜡金", p["nayin"]           # 庚辰辛巳白蜡金
    assert p["jianchu"] == "破" and p["huanghei"][0] == "青龙", (p["jianchu"], p["huanghei"])
    assert p["chong"] == ("戌", "狗"), p["chong"]
    assert p["sha"] == "南" and p["xunkong"] == "申酉", (p["sha"], p["xunkong"])
    assert p["pengzu"][0].startswith("庚不经络"), p["pengzu"]
    # 纳音表锚点
    assert nayin("甲", "子") == "海中金"
    assert nayin("丙", "寅") == "炉中火"
    assert nayin("庚", "午") == "路旁土"
    assert nayin("壬", "戌") == "大海水"
    # 旬空：甲子旬空戌亥；甲戌旬空申酉
    assert xunkong("甲", "子") == "戌亥", xunkong("甲", "子")
    assert xunkong("甲", "戌") == "申酉", xunkong("甲", "戌")
    # 五鼠遁：甲日子时为甲子，丙日子时为戊子，庚日子时为丙子
    assert hour_gz("甲", 0) == "甲子" and hour_gz("丙", 0) == "戊子", (hour_gz("甲", 0), hour_gz("丙", 0))
    assert hour_gz("庚", 0) == "丙子", hour_gz("庚", 0)
    # 农历跨年：2026-01-01 尚在乙巳年十一月
    assert page(2026, 1, 1)["lunar"].startswith("乙巳年"), page(2026, 1, 1)["lunar"]
    # 值宿：2026-11-02＝毕（cnlunar 毕月乌／6tail 毕）；28 日一循环；次日觜、前一日昴
    assert xiu(2026, 11, 2) == "毕", xiu(2026, 11, 2)
    assert xiu(2026, 11, 3) == "觜", xiu(2026, 11, 3)
    assert xiu(2026, 11, 30) == "毕", xiu(2026, 11, 30)
    assert xiu(2026, 11, 1) == "昴", xiu(2026, 11, 1)
    assert xiu(2026, 10, 31) == "胃", xiu(2026, 10, 31)
    # 三栏（册九十）：2026-11-03 觜·凶·胎神厨灶床外正西；2026-11-02 毕·吉·碓磨栖外正西
    p = page(2026, 11, 3)
    assert p["xiu"] == "觜" and p["xiu_luck"] == "凶", (p["xiu"], p["xiu_luck"])
    assert p["taishen"] == ("厨灶床", "外正西"), p["taishen"]
    assert "祭祀" in p["yi"] and "出行" in p["ji"], (p["yi"][:3], p["ji"][:3])
    assert len(p["yi"]) >= 15 and len(p["ji"]) >= 10, (len(p["yi"]), len(p["ji"]))
    q = page(2026, 11, 2)
    assert q["xiu"] == "毕" and q["xiu_luck"] == "吉", (q["xiu"], q["xiu_luck"])
    assert q["taishen"] == ("碓磨栖", "外正西"), q["taishen"]
    # 破日仍列"宜祭祀"——通书宜忌与建除本就分属两层，合看规则见册九十 §6
    assert q["jianchu"] == "破" and "安葬" in q["ji"], (q["jianchu"], q["ji"][:3])
    # 表自洽
    assert len(XIU_LUCK) == 28 and len(XIU_SONG) == 28, (len(XIU_LUCK), len(XIU_SONG))
    # 六十甲子纳音表长度自洽
    assert len(NAYIN) == 30
    print("selftest OK：农历、干支、纳音、日冲、煞方、旬空、五鼠遁、值宿、值宿吉凶、胎神、宜忌十一项锚点皆对")


def parse_date(s):
    y, m, d = (int(x) for x in s.replace("/", "-").split("-"))
    return date(y, m, d)


def main(argv=None):
    ap = argparse.ArgumentParser(description="一页黄历（只报事实栏，不给吉凶）")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD")
    ap.add_argument("--range", nargs=2, metavar=("起", "止"))
    ap.add_argument("--hour", type=int, help="0–23，给出时柱")
    ap.add_argument("--xiu", action="store_true", help="印值宿宿名")
    ap.add_argument("--xiu-luck", dest="xiu_luck", action="store_true", help="值宿宿名＋吉凶＋歌诀")
    ap.add_argument("--taishen", action="store_true", help="胎神占方")
    ap.add_argument("--yiji", action="store_true", help="全本宜忌")
    ap.add_argument("--full", action="store_true", help="三栏全出")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
        return 0
    if a.range:
        print(render_range(parse_date(a.range[0]), parse_date(a.range[1])))
        return 0
    if not a.date:
        ap.print_help()
        return 2
    d = parse_date(a.date)
    p = page(d.year, d.month, d.day, a.hour)
    if a.full:
        a.xiu = a.xiu_luck = a.taishen = a.yiji = True
    if a.xiu_luck:
        a.xiu = True
    if not a.xiu:
        p.pop("xiu", None)
    if not a.xiu_luck:
        p.pop("xiu_luck", None)
        p.pop("xiu_song", None)
    if not a.taishen:
        p.pop("taishen", None)
    if not a.yiji:
        p.pop("yi", None)
        p.pop("ji", None)
    print(render_one(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
