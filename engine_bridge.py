# 玄鉴命理馆 · 离线引擎桥接层
# 由 Pyodide 加载；所有函数返回 JSON 字符串（ensure_ascii=False），前端 JSON.parse 后使用。
import sys, io, contextlib, json, os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "skills", "xuanjian-kb", "scripts"))

import score as _score
import ziwei_pan as _ziwei_pan
import huangli as _huangli
import xiaoliuren as _xiaoliuren
import qiming as _qiming
import meihua as _meihua  # noqa


def _j(obj):
    return json.dumps(obj, ensure_ascii=False)


def ready():
    return _j({"ok": True,
               "modules": ["score", "ziwei_pan", "huangli",
                           "xiaoliuren", "qiming", "meihua"],
               "engine": "xuanjian-offline", "version": "XJ-1.78"})


def bazi(y, m, d, hour):
    """八字打分：公历 + 时辰(0-23) -> 四柱/总分/档位/过程/释读。"""
    y, m, d, hour = int(y), int(m), int(d), int(hour)
    四柱 = _ziwei_pan.四柱(y, m, d, hour)
    s = _score.打分(四柱[:4])
    释 = _score.释读(s["档位"])
    return _j({
        "四柱": list(四柱[:4]),
        "天干分": s["天干分"], "地支分": s["地支分"],
        "总分": s["总分"], "档位": s["档位"],
        "过程": s["过程"], "释读": 释,
    })


def ziwei(y, m, d, hour, gender):
    """紫微排盘：公历 + 时辰 + 性别(男/女) -> 完整盘。"""
    y, m, d, hour = int(y), int(m), int(d), int(hour)
    gender = "女" if str(gender) in ("女", "F", "f") else "男"
    盘 = _ziwei_pan.排盘(y, m, d, hour, gender)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _ziwei_pan.打印(盘)
    text = buf.getvalue()
    palaces = [{
        "宫名": p["宫名"], "干支": p["干支"], "主星": p["主星"],
        "是命宫": p.get("是命宫", False), "是身宫": p.get("是身宫", False),
    } for p in 盘["十二宫"]]
    return _j({
        "text": text,
        "命宫": 盘["命宫"], "身宫": 盘["身宫"],
        "命主": 盘["命主"], "身主": 盘["身主"],
        "五行局": 盘["五行局"], "大限顺逆": 盘["大限顺逆"],
        "起运虚岁": 盘["起运虚岁"], "十二宫": palaces,
        "口径声明": 盘.get("口径声明", ""),
    })


def huangli(y, m, d, hour=None):
    """黄历：公历 -> 当日宜忌/建除/黄黑道/值宿等。"""
    y, m, d = int(y), int(m), int(d)
    if hour is None or str(hour) == "":
        p = _huangli.page(y, m, d)
    else:
        p = _huangli.page(y, m, d, int(hour))
    return _j({"text": _huangli.render_one(p)})


def xiaoliuren_number(num, event=""):
    """小六壬·活数起课：输入一串数字 -> 落点宫。"""
    idx, s, n = _xiaoliuren.cast_from_number(str(num))
    meta = {"起课方式": "活数", "数字": str(num), "求和减位": s, "位数": n}
    text = _xiaoliuren.render(idx, idx, idx, meta, raw=False, event=event or "")
    return _j({"text": text})


def xiaoliuren_lunar(month, day, shichen, event=""):
    """小六壬·农历起课：农历月/日 + 时辰序(子=0) -> 三宫。"""
    month, day, shichen = int(month), int(day), int(shichen)
    m_pal, d_pal, h_pal = _xiaoliuren.cast_from_lunar(month, day, shichen)
    meta = {"起课方式": "农历月日时", "农历月": month,
            "农历日": day, "时辰序": shichen}
    text = _xiaoliuren.render(m_pal, d_pal, h_pal, meta, raw=False, event=event or "")
    return _j({"text": text})


def qiming(name, strokes, fl=1, tones=""):
    """五格取名：姓名 + 每字康熙笔画(csv) + 姓字数(1/2) + 声调(csv,可选)。"""
    bi = [int(x) for x in str(strokes).replace("，", ",").split(",") if x.strip()]
    fl = int(fl)
    tone = None
    if tones:
        tone = [int(x) for x in str(tones).replace("，", ",").split(",") if x.strip()]
    text = _qiming.render(name, bi, fl, tone if tone else None)
    return _j({"text": text})
