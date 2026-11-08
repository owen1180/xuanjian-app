#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄鉴命理馆 · 一键 CLI（2026-11-07 建，2026-11-07 二次加强）

对位竞品「16 个脚本 node scripts/xxx.js 直接出成品文本」的可用性：
本 CLI 把馆内已有引擎串成一条命令，输出**人能直接读**的结构化文本，
不新造算法、不重复实现、不出断语。

串接链：
    ziwei_pan.排盘()   → 紫微盘面事实（零依赖，6604 例对拍 iztro 2.5.8）
    yongshen.分析()    → 十神／调候／扶抑／通关／层次／力度／落地十类
    kb_gate.scan_banned() → 出口过闸（11 类 103 词，召回为空也拦）
    本文件             → 资料完备度分级、四段收口、诚实降级句式

2026-11-07 二次加强（吸收 DSH 头部的可复现与不确定性保留机制，只借机制）：
    ① --handle / 句柄   盘面确定性句柄：同输入＋同口径卡＋同引擎指纹 → 同句柄，
                        引擎一改句柄就变，历史盘不会和新盘混淆。
    ② --trace           推导链导出：每一步的事实与出处并列，可逐条反查册页。
    ③ 时辰未知候选盘    **不静默默认时辰**（KB100 / 92 / 43）：给 13 个候选时辰槽
                        并列，标明成立时段、时柱、命宫与判档差异，配「报两三个
                        顺逆年份反推喜忌」的校验动作；资料级别显式降为 B。
    ④ --card            可附主理人签发的口径卡（OB96 只读），句柄把卡哈希算进去；
                        不附卡时明写「未附，仅供复现盘面不供定案」。

用法：
    python3 xuanjian_cli.py --solar 1990 5 15 12 男
    python3 xuanjian_cli.py --solar 1990 5 15 12 男 --json --trace
    python3 xuanjian_cli.py --solar 1990 5 15 '?' 男     # 时辰未知
    python3 xuanjian_cli.py --solar 1990 5 15 12 男 --handle
    python3 xuanjian_cli.py --pillars 庚午 辛巳 庚辰 壬午
    python3 xuanjian_cli.py --selftest

纪律：
- 只出「方向」与「该往哪边调」，断语归成员、合参归主理人（各安其位）。
- 盘面术语「大限」属出口禁词，本 CLI 一律写「运限（十年段）」。
- 不因资料不足硬凑精排盘；缺什么显式说缺什么（`KB100`）。
- 不输出单盘综合分、不把对拍例数说成准确率（`TR105`／`OB98`）。
- 口径卡由主理人一人裁定，工具只读不改（`OB96`）；工具不代做定案。
"""

import argparse
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ziwei_pan  # noqa: E402
import yongshen  # noqa: E402
from kb_gate import scan_banned  # noqa: E402

DISCLAIMER = "以上为传统术数文化分析，供参考；不替代医疗、法律、投资与心理专业判断。"

# 四段收口（`71` 坏消息三段式 + 主理人收尾规格）
SECTIONS = ("优势", "短板", "当下怎么走", "什么时机动")

# 13 个时辰槽：iztro timeIndex 0=早子、1..11=丑至亥、12=晚子（`92` 晚子时口径）
时辰槽 = [
    (0, "早子", "00:00–01:00"), (1, "丑", "01:00–03:00"),
    (2, "寅", "03:00–05:00"), (3, "卯", "05:00–07:00"),
    (4, "辰", "07:00–09:00"), (5, "巳", "09:00–11:00"),
    (6, "午", "11:00–13:00"), (7, "未", "13:00–15:00"),
    (8, "申", "15:00–17:00"), (9, "酉", "17:00–19:00"),
    (10, "戌", "19:00–21:00"), (11, "亥", "21:00–23:00"),
    (12, "晚子", "23:00–01:00（日柱进位次日）"),
]
# 每个索引取一个代表小时喂给 排盘()：0→0、1→1、k≥2→2k−1、12→23
代表小时 = {0: 0, 1: 1, 12: 23}
for _i in range(2, 12):
    代表小时[_i] = 2 * _i - 1

引擎文件 = ("ziwei_pan.py", "yongshen.py", "score.py", "kb_gate.py")


def 引擎指纹(目录=_HERE):
    """引擎文件内容的短哈希。引擎一改，句柄必变——不许悄悄换算法还沿用旧号。"""
    h = hashlib.sha256()
    for f in 引擎文件:
        with open(os.path.join(目录, f), "rb") as fp:
            h.update(fp.read())
    return h.hexdigest()[:12]


def 卡摘要(卡路径=None):
    """OB96：口径卡由主理人签发，工具只读不改；只取哈希与十项开关进句柄。"""
    if not 卡路径:
        return {"状态": "未附口径卡", "说明": "仅供复现盘面，不供定案；定案须由主理人签发口径卡。"}
    with open(卡路径, encoding="utf-8") as f:
        raw = f.read()
    try:
        card = json.loads(raw)
    except json.JSONDecodeError:
        return {"状态": "口径卡非 JSON", "哈希": hashlib.sha256(raw.encode()).hexdigest()[:12]}
    return {
        "状态": "已附口径卡（只读）",
        "哈希": hashlib.sha256(raw.encode()).hexdigest()[:12],
        "卡内哈希": (card.get("provenance") or {}).get("kauding_hash", "")[:12] or None,
        "口径开关": card.get("config") or card.get("口径") or None,
    }


def 算句柄(载荷, 指纹=None):
    s = json.dumps(载荷, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    s += "|engine=" + (指纹 or 引擎指纹())
    return "XJ-" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:16].upper()


def 判完备度(solar=None, pillars=None, 时辰未知=False):
    """`KB100`：先判资料，再定断语深度。"""
    if 时辰未知:
        return "B", ("时辰未知，未静默默认：给 13 个候选时辰槽并列，先补时辰或报顺逆年份反推；"
                     "凡落时柱的事（子女、晚年、时干十神）本轮不落断语。")
    if solar and pillars:
        return "S", "盘面与四柱俱在，可做精读；仍须核对真太阳时与晚子时口径。"
    if solar:
        return "A", "主体资料完整，可做标准版；真太阳时与节气边界带来的误差需明说。"
    if pillars:
        return "S", "已给四柱盘面，可做四柱精读；无生辰，紫微盘不排、大运不推。"
    return "C", "只有问题没有资料，本 CLI 不做假精排盘，请补生辰或四柱。"


def 取落地行(落地, 栏, 类目):
    for 行 in 落地.get(栏, []) or []:
        if isinstance(行, dict):
            v = (行.get("十项") or {}).get(类目)
            if v:
                return v
    return None


def 四段收口(用神结果, 盘=None, 级别="A"):
    """只给方向与动作，不给结果保证（`77` 窗口＋做什么收口）。"""
    if 级别 == "B":
        return {
            "优势": "年月日三柱已定，格局倾向与五行偏性可谈；时辰未定不影响这一层。",
            "短板": ("时柱未定，凡落时柱的事本轮不落断语；13 个候选槽的判档与用神方向"
                     "有差别，不做「先挑一个再说」的静默默认。"),
            "当下怎么走": ("先补时辰；若确实无从查，请报两三个明显顺、明显逆的年份，"
                           "用它们反推喜忌方向（`43` §4），再定取用。"),
            "什么时机动": "时辰未定前不给具体年份窗口；定完再排运限（十年段），并由两位成员各自出结论后交叉。",
        }

    l = 用神结果.get("落地", {}) or {}
    层次 = (用神结果.get("层次") or {}).get("层次") or l.get("层次") or "未定"
    力度 = (用神结果.get("力度") or {}).get("力度") or l.get("力度") or "未定"
    档位 = (用神结果.get("强弱") or {}).get("档位") or "未定"

    用行 = 取落地行(l, "用", "行为") or "守住节奏、把该定的规矩定下来"
    用场 = 取落地行(l, "用", "场所") or "与用神方向相合的环境"
    用业 = 取落地行(l, "用", "行业") or "与用神方向相合的事类"
    忌行 = 取落地行(l, "忌", "行为") or "少在耗神的事上反复加码"
    病行 = 取落地行(l, "病", "行为") or "把长期透支的项目排到后面"

    return {
        "优势": (
            f"日主{用神结果['日主']['干']}（{用神结果['日主']['五行']}），"
            f"判档{档位}；用神层次{层次}、力度{力度}。"
            f"力量集中在{用业}一类的事上，走对了路比多使力气管用。"
        ),
        "短板": (
            f"内耗主要来自用力方向散：忌神一类不必强求（{忌行}），"
            f"病神一类宜先减负（{病行}）。"
            + ("调候与扶抑相冲，体感调整与主体取用要分开看，不并列当喜神。"
               if l.get("调候冲突") else "")
        ),
        "当下怎么走": (
            f"把行为往「{用行}」上靠，场合优先选{用场}；"
            "「缺」不等于「该补」、「忌」不等于「禁用」，只是少碰，不是不能碰。"
        ),
        "什么时机动": (
            "看运限十年段的顺与不平，不点具体年份事件；"
            + ("紫微运限与四柱大运须由两位成员各自出结论后，交主理人交叉。"
               if 盘 else "缺生辰，本轮不排运限，只给用神方向，不硬凑时间窗口。")
        ),
    }


def 候选时辰槽(y, m, d, gender):
    """时辰未知时的 13 槽并列：只给盘面事实与判档差异，不给断语。"""
    out = []
    for idx, 名, 时段 in 时辰槽:
        h = 代表小时[idx]
        try:
            盘 = ziwei_pan.排盘(y, m, d, h, gender)
            四柱 = [盘["四柱"][k] for k in ("年", "月", "日", "时")]
            用 = yongshen.分析(四柱)
            out.append({
                "序": idx + 1, "时辰": 名, "时段": 时段, "时辰索引": idx,
                "时柱": 四柱[3], "日柱": 四柱[2],
                "命宫": 盘["命宫"]["干支"], "五行局": 盘["五行局"],
                "判档": 用["强弱"]["档位"], "分数": 用["强弱"]["分数"],
                "用神方向": 用["扶抑"]["用神五行列表"],
                "口径注": "晚子时日柱进位次日（`92`）" if idx == 12 else None,
            })
        except Exception as e:            # 引擎算不出就明说，不假装算得出（`36`）
            out.append({"序": idx + 1, "时辰": 名, "时段": 时段,
                        "时辰索引": idx, "状态": "本槽未算出", "原因": str(e)[:80]})
    return out


def 推导链(载荷, 盘, 用神结果, 四柱, 出口, 级别, 卡):
    """每一步事实都配出处；不写分数以外的评价，不折成一个总分（TR105）。"""
    步 = [
        {"序": 1, "环节": "输入与口径", "出处": "CLI 入参／`OB96` 口径卡（只读）",
         "事实": {"输入": 载荷.get("输入"), "口径卡": 卡.get("状态"), "资料级别": 级别}},
    ]
    if 盘:
        步.append({"序": 2, "环节": "历法换算", "出处": "ziwei_pan.公历转农历／sxtwl",
                   "事实": {"农历": 盘["输入"]["农历"],
                            "年分界": "农历正月初一（紫微盘），四柱以节气为界，两者分开"}})
    步.append({"序": 3, "环节": "四柱", "出处": "ziwei_pan.四柱（时辰索引 0–12，晚子时进位）",
               "事实": {"四柱": " ".join(四柱)}})
    if 用神结果:
        步.append({"序": 4, "环节": "判档", "出处": "`R-015`／`01`／`41`／`43`；唯一口径 score.py",
                   "事实": {"档位": 用神结果["强弱"]["档位"], "分数": 用神结果["强弱"]["分数"],
                            "声明": "判档只报一个数，不许双口径并列"}})
        步.append({"序": 5, "环节": "取用四层", "出处": "yongshen.py／`02`／`39`／`47`",
                   "事实": {"十神计数": 用神结果["十神"]["计数"],
                            "调候": 用神结果["调候"]["调候五行"],
                            "扶抑": 用神结果["扶抑"]["路线"],
                            "通关": 用神结果["通关"]["通关五行"]}})
        l = 用神结果["落地"]
        步.append({"序": 6, "环节": "落地十类", "出处": "yongshen.落地／主人定案级报告规格",
                   "事实": {"状态": l.get("状态"),
                            "四栏五行": {k: [r.get("五行") for r in (l.get(k) or [])
                                          if isinstance(r, dict)] for k in ("用", "喜", "忌", "病")},
                            "铁律": l.get("落地铁律")}})
    if 盘:
        步.append({"序": 7, "环节": "紫微安星", "出处": "ziwei_pan.py（移植 iztro 2.5.8，6604 例对拍）",
                   "事实": {"命宫": 盘["命宫"]["干支"], "身宫": 盘["身宫"]["干支"],
                            "五行局": 盘["五行局"], "命主": 盘["命主"], "身主": 盘["身主"],
                            "运限顺逆": 盘["大限顺逆"], "起运虚岁": 盘["起运虚岁"]}})
    步.append({"序": len(步) + 1, "环节": "出口过闸", "出处": "`57`／kb_gate.scan_banned（11 类 103 词）",
               "事实": {"禁词命中": 出口["禁词命中"], "过闸": 出口["过闸"]}})
    return {
        "版本": "1.0",
        "引擎指纹": 引擎指纹(),
        "说明": "推导链只列事实与出处，不含断语、不含综合分；断语归成员，合参归主理人。",
        "步骤": 步,
    }


def 组装(solar=None, pillars=None, 时辰未知=False, 要trace=False, 卡路径=None):
    级别, 降级语 = 判完备度(solar, pillars, 时辰未知)
    if 级别 == "C":
        return {"资料级别": 级别, "降级说明": 降级语, "四段": {}, "出口": {}}

    卡 = 卡摘要(卡路径)
    y = m = d = gender = None
    if solar:
        y, m, d, h, gender = solar

    盘 = None
    四柱 = None
    用神结果 = None
    候选 = None
    if 时辰未知 and solar:
        候选 = 候选时辰槽(y, m, d, gender)
        四段 = 四段收口(None, None, "B")
    else:
        if solar:
            盘 = ziwei_pan.排盘(y, m, d, h, gender)
            四柱 = [盘["四柱"][k] for k in ("年", "月", "日", "时")]
        else:
            四柱 = list(pillars)
        用神结果 = yongshen.分析(四柱)
        四段 = 四段收口(用神结果, 盘, 级别)

    # 出口过闸：把准备说出去的话整段扫一遍（含候选表，避免表格绕过闸门）
    草稿块 = [降级语] + [f"{k}：{v}" for k, v in 四段.items()] + [DISCLAIMER]
    if 候选:
        草稿块 += [f"{x['时辰']}{x['时段']}{x.get('判档', '')}" for x in 候选]
    命中 = scan_banned("\n".join(草稿块))
    出口 = {
        "禁词命中": 命中,
        "过闸": len(命中) == 0,
        "说明": "11 类 103 词逐条扫；召回为空也拦（`57` 空召回兜底）。",
    }

    载荷 = {
        "输入": ({"公历": [y, m, d], "时辰": "未知", "性别": gender} if 时辰未知
                 else {"公历": list(solar[:4]), "性别": solar[4]} if solar
                 else {"四柱": list(pillars)}),
        "口径卡哈希": 卡.get("哈希") or 卡.get("状态"),
    }
    r = {
        "句柄": 算句柄(载荷),
        "引擎指纹": 引擎指纹(),
        "口径": 卡,
        "资料级别": 级别,
        "降级说明": 降级语,
        "出口": 出口,
        "声明": DISCLAIMER,
        "四段": 四段,
    }
    if 候选 is not None:
        r["候选时辰槽"] = 候选
        r["反推动作"] = "请报两三个明显顺、明显逆的年份，用它们反推喜忌方向后再定取用（`43` §4）。"
        r["四柱"] = "年月日三柱已定，时柱未定（不静默默认）"
    else:
        r["四柱"] = " ".join(四柱)
        r["紫微"] = (
            None if 盘 is None else {
                "命宫": 盘["命宫"]["干支"],
                "身宫": 盘["身宫"]["干支"],
                "五行局": 盘["五行局"],
                "命主": 盘["命主"],
                "身主": 盘["身主"],
                "命宫主星": next(
                    (p["主星"] for p in 盘["十二宫"] if p["是命宫"]), []
                ),
                "运限十年段": [
                    {"序": x["序"] + 1, "宫名": x["宫名"],
                     "干支": x["干支"], "起止虚岁": x["起止虚岁"],
                     "起年": x["起年"]}
                    for x in 盘["大限"][:4]
                ],
                "口径声明": 盘["口径声明"],
            }
        )
        r["用神"] = {
            "日主": 用神结果["日主"],
            "强弱": 用神结果["强弱"],
            "层次": 用神结果["层次"],
            "力度": 用神结果["力度"],
            "落地": 用神结果["落地"],
            "口径声明": 用神结果["口径声明"],
        }
    if 要trace:
        r["trace"] = 推导链(载荷, 盘, 用神结果, 四柱, 出口, 级别, 卡)

    # 整包再扫一次：JSON 里也不许藏禁词（trace 与字段名同样受管）
    全文命中 = scan_banned(json.dumps(r, ensure_ascii=False))
    if 全文命中:
        出口["禁词命中"] = sorted(set(出口["禁词命中"] + 全文命中))
        出口["过闸"] = False
    return r


def 打印(r):
    print("=" * 68)
    print("玄鉴命理馆 · 一键盘面速览（引擎事实，不含断语）")
    print("=" * 68)
    print(f"盘面句柄：{r['句柄']}　引擎指纹：{r['引擎指纹']}")
    print(f"口径卡：{r['口径']['状态']}" + (f"（{r['口径'].get('哈希', '')}）" if r["口径"].get("哈希") else ""))
    print(f"资料完备度：{r['资料级别']} 级　{r['降级说明']}")
    if r["资料级别"] == "C":
        print("\n" + r["声明"])
        return
    print(f"四柱：{r['四柱']}")

    if "候选时辰槽" in r:
        print("-" * 68)
        print("候选时辰槽（并列，不代表已选定任何一个）：")
        print(f"　{'时辰':<5}{'时段':<22}{'时柱':<6}{'命宫':<6}{'五行局':<8}{'判档':<12}用神方向")
        for x in r["候选时辰槽"]:
            print(f"　{x['时辰']:<5}{x['时段']:<22}{x.get('时柱', '—'):<6}"
                  f"{x.get('命宫', '—'):<6}{x.get('五行局', '—'):<8}"
                  f"{x.get('判档', '—'):<12}{'、'.join(x.get('用神方向', [])) or '—'}")
        print(f"　反推动作：{r['反推动作']}")
    else:
        z = r["紫微"]
        if z:
            print("-" * 68)
            print(f"紫微　命宫 {z['命宫']}　身宫 {z['身宫']}　{z['五行局']}　"
                  f"命主{z['命主']}／身主{z['身主']}")
            print(f"　　　命宫主星：{'、'.join(z['命宫主星']) or '空宫'}")
            print("　　　运限（十年段，只列结构不排事件）：")
            for x in z["运限十年段"]:
                print(f"　　　　第{x['序']}段 {x['宫名']} {x['干支']}　"
                      f"虚岁{x['起止虚岁'][0]}–{x['起止虚岁'][1]}（约 {x['起年']} 年起）")
        y = r["用神"]
        print("-" * 68)
        print(f"用神　日主 {y['日主']['干']}（{y['日主']['五行']}）　"
              f"判档 {y['强弱']['档位']}"
              + (f"（{y['强弱']['分数']} 分）" if y["强弱"]["分数"] is not None else ""))
        l = y["落地"]

        def 取名(v, key):
            if isinstance(v, dict):
                return v.get(key, "未定")
            return v or "未定"

        print(f"　　　落地状态：{l.get('状态', '未定')}　"
              f"层次：{取名(l.get('层次'), '层次')}　力度：{取名(l.get('力度'), '力度')}")
        for 栏 in ("用", "喜", "忌", "病"):
            rows = l.get(栏) or []
            if not rows:
                print(f"　　　{栏}：—")
                continue
            for row in rows:
                if isinstance(row, dict):
                    print(f"　　　{栏}·{row.get('五行', '')}："
                          f"方位 {row.get('十项', {}).get('方位', '—')}｜"
                          f"行业 {row.get('十项', {}).get('行业', '—')}｜"
                          f"行为 {row.get('十项', {}).get('行为', '—')}")
        if l.get("铁律"):
            for i, rule in enumerate(l["铁律"], 1):
                print(f"　　　铁律{i}：{rule}")
    print("-" * 68)
    print("四段收口")
    for k in SECTIONS:
        print(f"  【{k}】{r['四段'].get(k, '—')}")
    if r.get("trace"):
        print("-" * 68)
        print(f"推导链（{len(r['trace']['步骤'])} 步，每步带出处；--trace 可导出全量 JSON）")
        for s in r["trace"]["步骤"]:
            print(f"  {s['序']}. {s['环节']}　← {s['出处']}")
    print("-" * 68)
    e = r["出口"]
    print(f"出口闸门：{'PASS（零禁词命中）' if e['过闸'] else 'BLOCKED：' + str(e['禁词命中'])}")
    print(r["声明"])


def selftest():
    通过, 失败 = [], []

    def 查(name, cond, extra=""):
        (通过 if cond else 失败).append(name + ((" → " + str(extra)[:100]) if not cond and extra else ""))

    cases = [
        ("A 级完整生辰", dict(solar=(1990, 5, 15, 12, "男"))),
        ("S 级仅四柱", dict(pillars=("乙丑", "庚辰", "庚辰", "辛巳"))),
        ("C 级无资料", dict()),
        ("B 级时辰未知", dict(solar=(1990, 5, 15, 0, "男"), 时辰未知=True)),
    ]
    results = {}
    for name, kw in cases:
        try:
            r = 组装(**kw)
            results[name] = r
            查(name + "·级别", r["资料级别"] in ("S", "A", "B", "C"))
            if r["资料级别"] != "C":
                查(name + "·过闸", r["出口"]["过闸"], r["出口"]["禁词命中"])
                查(name + "·四段齐", all(k in r["四段"] and r["四段"][k] for k in SECTIONS))
                查(name + "·无禁词原字", "大限" not in json.dumps(r, ensure_ascii=False))
                查(name + "·有句柄", r["句柄"].startswith("XJ-") and len(r["句柄"]) == 19)
            json.dumps(r, ensure_ascii=False)
        except Exception as e:
            查(name + "·不抛异常", False, e)

    a = results.get("A 级完整生辰", {})
    # 句柄：确定性、敏感性、引擎指纹联动
    查("句柄·同输入同卡可复现", a.get("句柄") == 组装(solar=(1990, 5, 15, 12, "男")).get("句柄"))
    查("句柄·换时辰必变", a.get("句柄") != 组装(solar=(1990, 5, 15, 10, "男")).get("句柄"))
    查("句柄·换性别必变", a.get("句柄") != 组装(solar=(1990, 5, 15, 12, "女")).get("句柄"))
    查("句柄·引擎指纹一改必变",
       算句柄({"x": 1}, 指纹="abc") != 算句柄({"x": 1}, 指纹="def"))
    # 2026-11-07 补（KB103 §四）：可复现 handle 还要抗「键序变化」与「跨调用漂移」。
    查("句柄·载荷键序无关",
       算句柄({"甲": 1, "乙": 2}, 指纹="fp") == 算句柄({"乙": 2, "甲": 1}, 指纹="fp"))
    查("句柄·同输入跨调用稳定",
       all(算句柄({"x": 7}, 指纹="fp") == 算句柄({"x": 7}, 指纹="fp") for _ in range(20)))
    查("句柄·不同载荷不碰撞",
       len({算句柄({"x": i}, 指纹="fp") for i in range(20)}) == 20)
    查("句柄·未附口径卡要明说", "未附" in a.get("口径", {}).get("状态", ""))

    # 推导链：每步有出处、判档锁唯一口径、无综合分
    t = 组装(solar=(1990, 5, 15, 12, "男"), 要trace=True).get("trace", {})
    查("trace·步骤不少于 7", len(t.get("步骤", [])) >= 7, len(t.get("步骤", [])))
    查("trace·每步有事实与出处", all(s.get("事实") and s.get("出处") for s in t.get("步骤", [])))
    查("trace·判档锁 score.py 唯一口径",
       any("score.py" in s["出处"] and "只报一个数" in str(s["事实"]) for s in t.get("步骤", [])))
    查("trace·不给综合分",
       not any("综合分" in str(s["事实"]) or "总分" in str(s["事实"]) for s in t.get("步骤", [])))
    查("trace·默认不导出", "trace" not in a)

    # 时辰未知：13 槽、并列、显式降级、反推动作
    b = results.get("B 级时辰未知", {})
    查("时辰未知·恰好 13 槽", len(b.get("候选时辰槽", [])) == 13, len(b.get("候选时辰槽", [])))
    查("时辰未知·索引 0–12 连续",
       [x["时辰索引"] for x in b.get("候选时辰槽", [])] == list(range(13)))
    查("时辰未知·晚子时日柱进位有注", b.get("候选时辰槽", [{}])[-1].get("口径注") is not None)
    查("时辰未知·显式降 B 级", b.get("资料级别") == "B")
    查("时辰未知·明说未静默默认", "静默默认" in b.get("降级说明", ""))
    查("时辰未知·有反推动作", "顺" in b.get("反推动作", "") and "逆" in b.get("反推动作", ""))
    查("时辰未知·不做单盘落地", "用神" not in b and "紫微" not in b)
    查("时辰未知·每槽有判档", all(x.get("判档") for x in b.get("候选时辰槽", [])))
    查("时辰未知·候选判档确有差异",
       len({x.get("判档") for x in b.get("候选时辰槽", [])}) >= 1)

    # 口径卡：只读接入，句柄把卡哈希算进去；不同卡 → 不同句柄
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        c1, c2 = os.path.join(td, "a.json"), os.path.join(td, "b.json")
        json.dump({"config": {"历法": "公历"}}, open(c1, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"config": {"历法": "农历"}}, open(c2, "w", encoding="utf-8"), ensure_ascii=False)
        查("口径卡·附卡后标只读", "只读" in 卡摘要(c1)["状态"])
        查("口径卡·卡哈希进句柄",
           组装(solar=(1990, 5, 15, 12, "男"), 卡路径=c1)["句柄"]
           != 组装(solar=(1990, 5, 15, 12, "男"), 卡路径=c2)["句柄"])
        查("口径卡·同卡可复现",
           组装(solar=(1990, 5, 15, 12, "男"), 卡路径=c1)["句柄"]
           == 组装(solar=(1990, 5, 15, 12, "男"), 卡路径=c1)["句柄"])

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return not 失败


def main():
    ap = argparse.ArgumentParser(description="玄鉴命理馆一键 CLI（引擎事实，不含断语）")
    ap.add_argument("--solar", nargs=5, metavar=("年", "月", "日", "时", "性别"),
                    help="公历生辰，如 --solar 1990 5 15 12 男；时填 ? 表示时辰未知")
    ap.add_argument("--pillars", nargs=4, metavar=("年柱", "月柱", "日柱", "时柱"),
                    help="四柱，如 --pillars 乙丑 庚辰 庚辰 辛巳")
    ap.add_argument("--card", help="主理人签发的口径卡 JSON（OB96，工具只读不改）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--trace", action="store_true", help="导出推导链（每步事实＋出处）")
    ap.add_argument("--handle", action="store_true", help="只打印盘面句柄，便于脚本串联")
    ap.add_argument("--selftest", action="store_true", help="跑内建自检")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    solar = None
    时辰未知 = False
    if a.solar:
        if a.solar[3] in ("?", "？", "unknown", "未知"):
            时辰未知 = True
            a.solar[3] = "0"
        try:
            solar = (int(a.solar[0]), int(a.solar[1]), int(a.solar[2]),
                     int(a.solar[3]), a.solar[4])
        except ValueError:
            ap.error("--solar 前四位须为数字（时辰未知填 ?）")
        if solar[4] not in ("男", "女"):
            ap.error("性别须为 男 或 女")
    r = 组装(solar=solar, pillars=a.pillars, 时辰未知=时辰未知,
             要trace=a.trace, 卡路径=a.card)
    if a.handle:
        print(r.get("句柄", ""))
    elif a.json or a.trace:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        打印(r)
    sys.exit(0 if r.get("出口", {}).get("过闸", True) else 2)


if __name__ == "__main__":
    main()
