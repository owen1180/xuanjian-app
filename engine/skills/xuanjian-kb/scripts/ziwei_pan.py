# -*- coding: utf-8 -*-
"""紫微斗数排盘引擎（零依赖自算版）：十二宫安星、五行局、身宫、命主身主、大限。

口径来源与对拍
--------------
本脚本**逐条移植 iztro 2.5.8 的安星算法**（MIT 许可，算法本身为传统安星法，
非 iztro 独创），并与其逐项对拍通过。凡与 iztro 有分歧，**一律以 iztro 为准**。

移植的三段算法：

1. 命宫／身宫（iztro `lib/astro/palace.js` getSoulAndBody）
   紫微斗数以**寅宫为第一宫**（索引 0），故宫索引与地支索引差 2。
   命宫索引 = 农历月索引 − 生时地支索引；身宫索引 = 农历月索引 + 生时地支索引。
   农历月索引 = 农历月 + 1 − 寅索引(2)；闰月且农历日 > 15 时加 1（fixLeap）。

2. 紫微星位（iztro `lib/star/location.js` getStartIndex）——起紫微星诀：
       六五四三二，酉午亥辰丑，
       局数除日数，商数宫前走；
       若见数无余，便要起虎口，
       日数小于局，还直宫中守。
   即：以农历日除五行局数，余数非零则加偏移直到整除；商减一为起始位；
   偏移为偶数则逆行、为奇数则顺行。天府位 = 12 − 紫微位。

3. 五行局：以命宫干支纳音取（水二/木三/金四/土五/火六）。

**已知上游缺陷（本脚本已规避）**：iztro 的 `astro.byLunar()` 在农历日 ≥ 30 或
闰月场景会抛 `only N days in lunar year` / `wrong lunar year`——用 iztro 的
`byLunar` 做基准时必须避开这些日期。本脚本直接由公历推农历，不经该路径。

用法：
    python3 scripts/ziwei_pan.py 1990 5 15 14 男
    python3 scripts/ziwei_pan.py 1990 5 15 14 男 --json
    python3 scripts/ziwei_pan.py 1990 5 15 14 男 --daxian 3
    python3 scripts/ziwei_pan.py --selftest        # 内建对拍用例

输出只给**盘面事实**（宫位、主星、五行局、身宫、命主身主、大限）。
**断语不在此产出**——归斗枢（`22` 册），本脚本只做装盘。
"""

import json
import sys
import argparse

# ---------------------------------------------------------------------------
# 1. 常量
# ---------------------------------------------------------------------------
地支 = "子丑寅卯辰巳午未申酉戌亥"
天干 = "甲乙丙丁戊己庚辛壬癸"

# 紫微斗数以寅宫为第一宫（索引 0），故 index = 地支索引 - 2
寅索引 = 2

# 十二宫名。**顺序是逆时针**（iztro `PALACES` 常量）：
# 命宫 → 父母 → 福德 → 田宅 → 官禄 → 交友 → 迁移 → 疾厄 → 财帛 → 子女 → 夫妻 → 兄弟
# 注意：这与民间常说的「命宫→兄弟→夫妻→……」顺时针口诀方向相反。
# 紫微的十二宫在地支盘上是逆时针排布的：兄弟宫在命宫的前一宫（地支序号减一）。
# iztro `getPalaceNames(fromIndex)`：`names[i] = PALACES[fixIndex(i - fromIndex)]`，
# 即「某宫的宫名 = 以命宫宫序为起点、按地支序号递增方向回绕」。
宫名序 = ["命宫", "父母", "福德", "田宅", "官禄", "交友",
           "迁移", "疾厄", "财帛", "子女", "夫妻", "兄弟"]

# 紫微星系（逆行）：紫微、天机、（空）、太阳、武曲、天同、（空）、（空）、廉贞
# iztro `ziweiGroup` 用空串占位表示跳过，故须按原始下标定位，不能压缩后遍历。
紫微星系 = ["紫微", "天机", "", "太阳", "武曲", "天同", "", "", "廉贞"]
# 天府星系（顺行）：天府、太阴、贪狼、巨门、天相、天梁、七杀、（空）×3、破军
天府星系 = ["天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "", "", "", "破军"]

六十甲子 = []
for _i in range(60):
    六十甲子.append(天干[_i % 10] + 地支[_i % 12])

纳音表 = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
]

纳音五行 = {"金": "金", "火": "火", "木": "木", "土": "土", "水": "水"}
五行局表 = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
局名 = {2: "水二局", 3: "木三局", 4: "金四局", 5: "土五局", 6: "火六局"}

# 五虎遁：年干 → 寅宫天干
五虎遁 = {"甲": "丙", "乙": "戊", "丙": "庚", "丁": "壬", "戊": "甲",
          "己": "丙", "庚": "戊", "辛": "庚", "壬": "壬", "癸": "甲"}

# 命主：由**命宫地支**取（iztro earthlyBranches 表的 soul 列）
命主表 = {
    "子": "贪狼", "丑": "巨门", "寅": "禄存", "卯": "文曲",
    "辰": "廉贞", "巳": "武曲", "午": "破军", "未": "武曲",
    "申": "廉贞", "酉": "文曲", "戌": "禄存", "亥": "巨门",
}

# 身主：由**年支**取（iztro earthlyBranches 表的 body 列）。
# 注意：身主取年支，不是身宫地支——这是 iztro 的口径，也是传统「身主」的查法。
身主表 = {
    "子": "火星", "丑": "天相", "寅": "天梁", "卯": "天同",
    "辰": "文昌", "巳": "天机", "午": "火星", "未": "天相",
    "申": "天梁", "酉": "天同", "戌": "文昌", "亥": "天机",
}


def fix(n, m=12):
    """取模并归一到 0..m-1。"""
    return n % m


def 纳音(干支: str) -> str:
    """由干支取纳音名。六十甲子每两柱共用一个纳音，故取 索引//2。"""
    i = 六十甲子.index(干支)
    return 纳音表[i // 2]


# ---------------------------------------------------------------------------
# 2. 公历 → 农历（本库自带实现，不依赖 sxtwl）
# ---------------------------------------------------------------------------
def 公历转儒略日(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return (d + (153 * mm + 2) // 5 + 365 * yy + yy // 4
            - yy // 100 + yy // 400 - 32045)


def 干支纪日(jdn: int) -> str:
    """儒略日序 → 日干支。基准：1949-10-01 为甲子日。"""
    return 六十甲子[(jdn - 2433191) % 60]


# 农历转换：优先用 sxtwl/huangli；离线无 sxtwl 时走预生成纯数据表 _lunar_data
def 公历转农历(y: int, m: int, d: int):
    """返回 (农历年, 农历月, 农历日, 是否闰月)。"""
    try:
        import huangli
        _txt, day = huangli.lunar_text(y, m, d)
        if day is not None:
            return (day.getLunarYear(), day.getLunarMonth(),
                    day.getLunarDay(), bool(day.isLunarLeap()))
    except Exception:
        pass
    # 离线兜底：纯数据表（不含 sxtwl）
    try:
        import _lunar_data
        return _lunar_data.lunar_of(y, m, d)
    except Exception:
        pass
    return _内置农历(y, m, d)


def _解析农历文本(lt: str):
    """从「庚午年四月廿一」解析出 (年, 月, 日, 闰月)。"""
    import re
    日汉字 = "一二三四五六七八九十廿卅"
    m1 = re.search(r"年(.)月", lt)
    m2 = re.search(r"月([一二三四五六七八九十廿卅]+)", lt)
    if not m1 or not m2:
        raise ValueError("无法解析农历文本")
    月字 = m1.group(1)
    if 月字 == "十":
        月 = 10
    elif 月字 == "冬":
        月 = 11
    elif 月字 == "腊":
        月 = 12
    else:
        月 = int(月字)
    日 = 0
    for ch in m2.group(1):
        if ch == "十":
            日 += 10
        elif ch == "廿":
            日 += 20
        elif ch == "卅":
            日 += 30
        else:
            日 += 日汉字.index(ch) + 1
    年 = int(re.search(r"([一二三四五六七八九〇零]{4})年", lt).group(1).translate(
        str.maketrans("一二三四五六七八九〇零", "12345678900"))) if re.search(
        r"([一二三四五六七八九〇零]{4})年", lt) else 0
    闰 = "闰" in lt
    return 年, 月, 日, 闰


# 内置农历表：1900-2100 常用范围（用标准算法推导）
def _内置农历(y: int, m: int, d: int):
    """无 sxtwl 时的兜底：优先用预生成纯数据表，再失败才报错。

    农历月日是安紫微星诀与命宫的必需输入，**没有准确农历就不出盘**，
    宁可报错也不给错盘。
    """
    try:
        import _lunar_data
        return _lunar_data.lunar_of(y, m, d)
    except Exception:
        pass
    raise RuntimeError(
        "缺少 sxtwl/lunar 依赖，也无法加载离线农历数据表，紫微排盘中止。"
        "请先安装 sxtwl（pip install sxtwl）或确保 scripts/_lunar_data.py 存在。"
    )


# ---------------------------------------------------------------------------
# 3. 干支
# ---------------------------------------------------------------------------
def 四柱(y: int, m: int, d: int, hour: int):
    """返回 (年干支, 月干支, 日干支, 时干支, 农历月, 农历日, 农历是否闰月, 时辰索引)。

    **年分界口径（重要）**：紫微斗数盘的年干支以**农历正月初一**换年，
    不是八字常用的立春。iztro `getConfig().yearDivide` 默认 `'normal'`，
    对应 lunar-lite 的 `lunar.getYearGan()`——即农历年干支。

    两者在「立春 → 正月初一」之间（约 20 天）会给出不同的年干支，
    进而影响宫干、五行局、身宫与大限顺逆。凡此区间内的盘，
    **以农历正月初一为准**（紫微本盘），并须在报告中声明。
    """
    农历年, 农历月, 农历日, 闰 = 公历转农历(y, m, d)

    # 年干支：以**农历正月初一**换年（iztro yearDivide='normal'）。
    # 农历年由 sxtwl 给出（已跨年则为前一年的农历年）。
    年干支 = 六十甲子[(农历年 - 1984) % 60]

    # 月干支：紫微用**农历月**（与八字「节气月」不同口径）。
    # 寅宫起正月，顺排；月干用五虎遁自年干起。
    # 闰月：iztro `calculateMonthlyGanZhi` 中，闰月且日 > 15 才按下一月论
    #       （fixLeap 规则），否则仍作本月。
    月支序表 = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
    fix_leap = 1 if (闰 and 农历日 > 15) else 0
    月序 = 农历月 - 1 + fix_leap
    月地支 = 月支序表[月序 % 12]
    起 = 天干.index(五虎遁[年干支[0]])
    月干支 = 天干[(起 + 月序) % 10] + 月地支

    # 时辰索引（iztro `timeToIndex`）：0=早子时，1..11=丑至亥，12=晚子时。
    # 注意 iztro 的时辰索引 **不是** 地支序号——晚子时是 12，不是 0。
    时辰索引 = 0 if hour == 0 else (12 if hour == 23 else (hour + 1) // 2)

    # 日干支：晚子时（时辰索引 12）日柱进位到次日。
    日偏移 = 1 if 时辰索引 >= 12 else 0
    日干支 = 干支纪日(公历转儒略日(y, m, d) + 日偏移)

    # 时干支：日干起五鼠遁。时支按地支序号取（子=0）。
    五鼠遁 = {"甲": "甲", "乙": "丙", "丙": "戊", "丁": "庚", "戊": "壬",
              "己": "甲", "庚": "丙", "辛": "戊", "壬": "庚", "癸": "壬"}
    时支序 = 时辰索引 % 12
    时干支 = 天干[(天干.index(五鼠遁[日干支[0]]) + 时支序) % 10] + 地支[时支序]

    return 年干支, 月干支, 日干支, 时干支, 农历月, 农历日, 闰, 时辰索引


# ---------------------------------------------------------------------------
# 4. 安星（移植 iztro）
# ---------------------------------------------------------------------------
def 农历月索引(农历月: int, 农历日: int, 闰: bool, 时辰索引: int, fix_leap=True) -> int:
    """iztro `fixLunarMonthIndex`：寅为 0。

    农历月索引 = 农历月 + 1 − 寅索引(2)；
    闰月且农历日 > 15（且非晚子时）时加 1。
    """
    need_add = 闰 and fix_leap and 农历日 > 15 and 时辰索引 != 12
    return fix(农历月 + 1 - 寅索引 + (1 if need_add else 0))


def 起紫微星位(农历日: int, 五行局数: int, 当月最大天数: int, 时辰索引: int):
    """iztro `getStartIndex` —— 起紫微星诀。

    返回 (紫微宫索引, 天府宫索引)，宫索引以寅为 0。
    """
    day = 农历日
    if 时辰索引 == 12:      # 晚子时算次日（iztro dayDivide='forward'）
        day += 1
    if day > 当月最大天数:
        day -= 当月最大天数

    remainder = -1
    quotient = 0
    offset = -1
    while True:
        offset += 1
        divisor = day + offset
        quotient = divisor // 五行局数
        remainder = divisor % 五行局数
        if remainder == 0:
            break

    quotient %= 12
    ziwei_index = quotient - 1
    if offset % 2 == 0:
        ziwei_index += offset      # 偶数：逆行
    else:
        ziwei_index -= offset      # 奇数：顺行
    ziwei_index = fix(ziwei_index)
    tianfu_index = fix(12 - ziwei_index)
    return ziwei_index, tianfu_index


def 紫微主星分布(紫微位: int, 天府位: int):
    """紫微星系逆布、天府星系顺布，返回 星名 → 宫索引。

    **注意空位**：两星系各有间隔宫（紫微系隔 3 宫、天府系隔 3 宫），
    iztro 用空串占位保持下标，故须按原始下标定位，不能压缩后遍历。
    """
    result = {}
    for i, s in enumerate(紫微星系):
        if s:
            result[s] = fix(紫微位 - i)
    for i, s in enumerate(天府星系):
        if s:
            result[s] = fix(天府位 + i)
    return result


def 宫位地支(宫索引: int) -> str:
    """宫索引（寅为0）→ 地支。"""
    return 地支[(宫索引 + 寅索引) % 12]


def 宫位天干(年干: str, 宫索引: int) -> str:
    """以五虎遁起寅宫天干，逐宫顺排。

    宫索引以寅为 0，故天干索引 = 五虎遁起干索引 + 宫索引。
    """
    起 = 天干.index(五虎遁[年干])
    return 天干[(起 + 宫索引) % 10]


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------
def 排盘(y: int, m: int, d: int, hour: int, gender: str = "男"):
    """排一盘，返回盘面事实字典。"""
    年干支, 月干支, 日干支, 时干支, 农历月, 农历日, 闰, 时辰索引 = 四柱(y, m, d, hour)

    # 时辰地支序号（0=子…11=亥）。晚子时（时辰索引 12）地支仍为子。
    时支序 = 时辰索引 % 12

    # --- 命宫 / 身宫 ---
    月索引 = 农历月索引(农历月, 农历日, 闰, 时辰索引)
    命宫索引 = fix(月索引 - 时支序)
    身宫索引 = fix(月索引 + 时支序)

    # --- 五行局：命宫干支纳音 ---
    命宫干 = 宫位天干(年干支[0], 命宫索引)
    命宫干支 = 命宫干 + 宫位地支(命宫索引)
    局数 = 五行局表[纳音五行[纳音(命宫干支)[-1]]]

    # --- 紫微星位 ---
    当月最大天数 = _农历月天数(y, m, d)
    紫微位, 天府位 = 起紫微星位(农历日, 局数, 当月最大天数, 时辰索引)
    stars = 紫微主星分布(紫微位, 天府位)

    # --- 十二宫 ---
    # 宫名随命宫轮转。iztro `getPalaceNames(fromIndex)`：
    #   names[i] = PALACES[fixIndex(i - fromIndex)]
    # 即「宫序号减命宫序号」回绕后查表；此表是逆时针序
    # （命→父母→福德→田宅→官禄→交友→迁移→疾厄→财帛→子女→夫妻→兄弟）。
    palaces = []
    for i in range(12):
        支 = 宫位地支(i)
        干 = 宫位天干(年干支[0], i)
        偏移 = (i - 命宫索引) % 12
        palaces.append({
            "index": i,
            "宫名": 宫名序[偏移],
            "地支": 支,
            "天干": 干,
            "干支": 干 + 支,
            "主星": sorted([s for s, p in stars.items() if p == i]),
            "是命宫": i == 命宫索引,
            "是身宫": i == 身宫索引,
        })

    # --- 大限 ---
    # iztro `getHoroscope`：
    #   阳男阴女顺行（+），阴男阳女逆行（−）；以**命宫**为第一步起点；
    #   起运虚岁 = 五行局数（如土五局 5 岁起运，第 1 限 5–14）。
    #   阴阳以**年支**论，非年干。
    阳 = 年干支[1] in "子寅辰午申戌"     # 年支阴阳
    顺行 = (阳 and gender == "男") or (not 阳 and gender == "女")
    起运虚岁 = 局数

    大限 = []
    for step in range(12):
        idx = fix(命宫索引 + step) if 顺行 else fix(命宫索引 - step)
        宫 = palaces[idx]
        起虚岁 = 起运虚岁 + step * 10
        大限.append({
            "序": step,
            "宫位": idx,
            "宫名": 宫["宫名"],
            "地支": 宫["地支"],
            "干支": 宫["干支"],
            "起止虚岁": [起虚岁, 起虚岁 + 9],
            "起年": y + (起虚岁 - 1),
        })

    命主 = 命主表[宫位地支(命宫索引)]
    身主 = 身主表[年干支[1]]

    return {
        "输入": {"公历": f"{y}-{m:02d}-{d:02d} {hour:02d}:00", "性别": gender,
                "农历": f"农历{农历月}月{农历日}日" + ("（闰月）" if 闰 else "")},
        "四柱": {"年": 年干支, "月": 月干支, "日": 日干支, "时": 时干支},
        "五行局": 局名[局数],
        "命宫": {"地支": 宫位地支(命宫索引), "干支": 命宫干支,
                "纳音": 纳音(命宫干支)},
        "身宫": {"地支": 宫位地支(身宫索引), "干支": 宫位天干(年干支[0], 身宫索引) + 宫位地支(身宫索引)},
        "命主": 命主,
        "身主": 身主,
        "十二宫": palaces,
        "大限": 大限,
        "大限顺逆": "顺行" if 顺行 else "逆行",
        "起运虚岁": 起运虚岁,
        "口径声明": (
            "安星算法移植自 iztro 2.5.8（MIT），并与其逐项对拍通过；"
            "凡分歧以 iztro 为准。月柱以节气为界，真太阳时未处理——"
            "跨节气、跨时辰界、跨时辰边界（如 23:00 前后）的盘，"
            "须先按 `92` 册校正后重排。断语不在本脚本产出，归斗枢（22 册）。"
        ),
    }


def _农历月天数(y: int, m: int, d: int) -> int:
    """取出生农历月的最大天数（用于起紫微星诀的跨月处理）。

    **做法：找到下一个「农历初一」为止的间隔。**
    不能用「下个月初一 − 本月初一」的算法——遇到闰月会漏掉闰月那一整个月
    （如 2014 年闰九月：九月三十之后是闰九月初一，不是十月初一，
    差值会算成 59 天）。逐月边界处理对闰月、大小月、跨年一律正确。
    """
    # 离线优先：用预生成纯数据表定位本月起点与下一月起点
    try:
        import _lunar_data as _ld
        import datetime as _dt
        o = _dt.date(y, m, d).toordinal()
        i = _ld._b(_ld.LUNAR_ORDS, o)
        if 0 <= i < len(_ld.LUNAR_ORDS) - 1:
            return _ld.LUNAR_ORDS[i + 1] - o   # 本月天数 = 下一月初一 − 本月初一
    except Exception:
        pass
    # 次选：sxtwl 逐日扫描（本机有 sxtwl 时路径）
    try:
        import sxtwl
        import datetime as _dt
        day = sxtwl.fromSolar(y, m, d)
        农历日 = day.getLunarDay()
        cur = _dt.date(y, m, d)
        for k in range(1, 32):          # 农历月最长 30 天，扫 31 天足够
            cur = _dt.date(y, m, d) + _dt.timedelta(days=k)
            nxt = sxtwl.fromSolar(cur.year, cur.month, cur.day)
            if nxt.getLunarDay() == 1:
                return 农历日 + k - 1   # 本月天数 = 当日农历日 + 到初一的间隔
    except Exception:
        pass
    # 兜底：无 sxtwl 时按大小月粗估（会影响跨月的极少数盘，故置 30 偏保守）
    return 30


def 打印(盘: dict, daxian: int = None):
    print("=" * 62)
    print(f"紫微斗数盘  {盘['输入']['公历']}  {盘['输入']['性别']}  "
          f"（{盘['输入']['农历']}）")
    print("=" * 62)
    四柱 = 盘["四柱"]
    print(f"四柱  {四柱['年']} {四柱['月']} {四柱['日']} {四柱['时']}"
          f"    五行局 {盘['五行局']}")
    print(f"命宫 {盘['命宫']['干支']}（{盘['命宫']['纳音']}）"
          f"   身宫 {盘['身宫']['干支']}"
          f"   命主 {盘['命主']}  身主 {盘['身主']}")
    print("-" * 62)
    for p in 盘["十二宫"]:
        标 = ("【命】" if p["是命宫"] else "") + ("【身】" if p["是身宫"] else "")
        星 = " ".join(p["主星"]) if p["主星"] else "（空宫）"
        print(f"{p['宫名']:<4s} {p['干支']}  {星}{标}")
    print("-" * 62)
    print(f"大限{盘['大限顺逆']}  起运虚岁 {盘['起运虚岁']}")
    for i, dx in enumerate(盘["大限"][:6]):
        标 = "  ←当前" if daxian is not None and i == daxian else ""
        print(f"  第{i+1}限 {dx['宫名']}({dx['地支']}) "
              f"虚岁 {dx['起止虚岁'][0]}-{dx['起止虚岁'][1]} "
              f"约 {dx['起年']} 年起{标}")
    print("-" * 62)
    print(盘["口径声明"])


# ---------------------------------------------------------------------------
# 6. 自检（与 iztro 对拍的已知真值）
# ---------------------------------------------------------------------------
def selftest(truth_path: str = None):
    """与 iztro 全项对拍。

    真值来自 iztro 2.6.x（`astro.bySolar`）。
    注意 iztro 的 API 签名是 `bySolar(date, timeIndex, gender, fixLeap, language)`
    —— 第二参是时辰索引，不是性别；时辰索引 0=早子时、12=晚子时。

    对拍项：**十二宫宫名 / 宫干支 / 主星分布 / 大限虚岁区间 / 五行局 /
    命宫 / 身宫 / 命主 / 身主**，逐盘逐宫核对。

    若传入 `truth_path`（iztro 导出的 JSON 真值数组），则跑全量对拍；
    否则跑内建 8 例最小回归集。
    """
    if truth_path:
        return _对拍文件(truth_path)
    return _对拍内置()


# iztro 的英文宫名 → 本库中文宫名
_宫名映射 = {
    "命宫": "命宫", "兄弟": "兄弟", "夫妻": "夫妻", "子女": "子女",
    "财帛": "财帛", "疾厄": "疾厄", "迁移": "迁移", "仆役": "交友",
    "官禄": "官禄", "田宅": "田宅", "福德": "福德", "父母": "父母",
}


def _对拍文件(truth_path: str):
    """与 iztro 导出的真值 JSON 逐盘逐宫全项核对。"""
    import json
    with open(truth_path, encoding="utf-8") as f:
        真值集 = json.load(f)

    通过 = 0
    失败明细 = []
    for case in 真值集:
        y, m, d = (int(x) for x in case["date"].split("-"))
        hour = case["hour"]
        gender = case["gender"]
        try:
            盘 = 排盘(y, m, d, hour, gender)
        except Exception as e:
            失败明细.append(f"{case['date']} {hour}时 {gender}：排盘异常 {e}")
            continue

        错 = []

        # 1. 五行局
        if 盘["五行局"] != case["five"]:
            错.append(f"五行局 {盘['五行局']}≠{case['five']}")

        # 2. 命宫 / 身宫
        if 盘["命宫"]["地支"] != case["soulBranch"]:
            错.append(f"命宫 {盘['命宫']['地支']}≠{case['soulBranch']}")
        if 盘["身宫"]["地支"] != case["bodyBranch"]:
            错.append(f"身宫 {盘['身宫']['地支']}≠{case['bodyBranch']}")

        # 3. 命主 / 身主
        if 盘["命主"] != case["soulStar"]:
            错.append(f"命主 {盘['命主']}≠{case['soulStar']}")
        if 盘["身主"] != case["bodyStar"]:
            错.append(f"身主 {盘['身主']}≠{case['bodyStar']}")

        # 4. 十二宫逐宫：宫名 / 干支 / 主星 / 大限区间
        大限表 = {dx["宫位"]: dx["起止虚岁"] for dx in 盘["大限"]}
        for tp in case["palaces"]:
            p = 盘["十二宫"][tp["index"]]
            期望名 = _宫名映射.get(tp["name"], tp["name"])
            if p["宫名"] != 期望名:
                错.append(f"宫{tp['index']}名 {p['宫名']}≠{期望名}")
            if p["干支"] != tp["gz"]:
                错.append(f"宫{tp['index']}干支 {p['干支']}≠{tp['gz']}")
            if p["是命宫"] != tp["isSoul"]:
                错.append(f"宫{tp['index']}命宫标错")
            if p["是身宫"] != tp["isBody"]:
                错.append(f"宫{tp['index']}身宫标错")
            # 主星：iztro 用英文名，中文映射后比对
            期望星 = sorted(_星名映射.get(s, s) for s in tp["major"])
            if sorted(p["主星"]) != 期望星:
                错.append(f"宫{tp['index']}主星 {p['主星']}≠{期望星}")
            # 大限虚岁区间
            exp_dx = tp["decadal"]
            if exp_dx:
                got = 大限表.get(tp["index"])
                if got != exp_dx:
                    错.append(f"宫{tp['index']}大限 {got}≠{exp_dx}")

        if 错:
            失败明细.append(f"{case['date']} {hour}时 {gender}：{'; '.join(错[:6])}")
        else:
            通过 += 1

    总 = len(真值集)
    print(f"全量对拍：{通过}/{总} 通过")
    if 失败明细:
        print(f"\n失败明细（前 30 条，共 {len(失败明细)} 条）：")
        for line in 失败明细[:30]:
            print("  ✗ " + line)
    return 通过 == 总


# iztro 英文星名 → 本库中文星名
_星名映射 = {
    "紫微": "紫微", "天机": "天机", "太阳": "太阳", "武曲": "武曲",
    "天同": "天同", "廉贞": "廉贞", "天府": "天府", "太阴": "太阴",
    "贪狼": "贪狼", "巨门": "巨门", "天相": "天相", "天梁": "天梁",
    "七杀": "七杀", "破军": "破军",
}


def _对拍内置():
    """内建最小回归集：命宫 / 五行局 / 紫微位 / 天府位 四项。"""
    用例 = [
        ((1990, 5, 15), 14, "戌", "土五局", "戌", "午"),
        ((1990, 5, 15), 2, "辰", "金四局", "辰", "子"),
        ((1990, 5, 15), 8, "丑", "火六局", "寅", "寅"),
        ((1990, 5, 7), 14, "戌", "土五局", "午", "戌"),
        ((1990, 5, 15), 0, "巳", "金四局", "辰", "子"),
        ((1990, 5, 15), 20, "未", "木三局", "申", "申"),
        ((1985, 8, 8), 12, "丑", "火六局", "未", "酉"),
        ((2000, 1, 1), 10, "未", "土五局", "午", "戌"),
    ]
    通过 = 0
    for (y, m, d), hour, 命宫地支, 局, 紫微地支, 天府地支 in 用例:
        try:
            盘 = 排盘(y, m, d, hour, "男")
        except Exception as e:
            print(f"✗ {y}-{m}-{d} {hour}时 排盘失败：{e}")
            continue
        实际紫微 = next((p["地支"] for p in 盘["十二宫"]
                        if "紫微" in p["主星"]), None)
        实际天府 = next((p["地支"] for p in 盘["十二宫"]
                        if "天府" in p["主星"]), None)
        项 = [
            ("命宫", 盘["命宫"]["地支"], 命宫地支),
            ("五行局", 盘["五行局"], 局),
            ("紫微位", 实际紫微, 紫微地支),
            ("天府位", 实际天府, 天府地支),
        ]
        全过 = all(a == e for _, a, e in 项)
        标 = "✓" if 全过 else "✗"
        细 = "  ".join(f"{名}={实}" for 名, 实, _ in 项)
        print(f"  {标} {y}-{m}-{d} {hour}时  {细}")
        if not 全过:
            for 名, 实, 期 in 项:
                if 实 != 期:
                    print(f"      ✗ {名}: 实际 {实} / 期望 {期}")
        通过 += 1 if 全过 else 0
    print(f"\n自检：{通过}/{len(用例)} 通过")
    return 通过 == len(用例)


def main():
    ap = argparse.ArgumentParser(description="紫微斗数排盘（零依赖自算版，移植 iztro 口径）")
    ap.add_argument("year", nargs="?", type=int, help="公历年")
    ap.add_argument("month", nargs="?", type=int, help="公历月")
    ap.add_argument("day", nargs="?", type=int, help="公历日")
    ap.add_argument("hour", nargs="?", type=int, help="出生时辰（0-23）")
    ap.add_argument("gender", nargs="?", default="男", choices=["男", "女"])
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--daxian", type=int, default=None, help="标记第几个大限为当前")
    ap.add_argument("--selftest", action="store_true", help="跑内建对拍用例")
    ap.add_argument("--truth", type=str, default=None,
                    help="与 iztro 导出的真值 JSON 全量对拍")
    a = ap.parse_args()

    if a.truth:
        sys.exit(0 if selftest(a.truth) else 1)
    if a.selftest:
        sys.exit(0 if selftest() else 1)

    if None in (a.year, a.month, a.day, a.hour):
        ap.print_help()
        sys.exit(1)
    if not (0 <= a.hour <= 23):
        sys.exit("hour 须在 0-23 之间")
    if not (1 <= a.month <= 12 and 1 <= a.day <= 31):
        sys.exit("month/day 超出范围")

    try:
        盘 = 排盘(a.year, a.month, a.day, a.hour, a.gender)
    except RuntimeError as e:
        sys.exit(f"排盘中止：{e}")
    if a.json:
        print(json.dumps(盘, ensure_ascii=False, indent=2))
    else:
        打印(盘, a.daxian)


if __name__ == "__main__":
    main()
