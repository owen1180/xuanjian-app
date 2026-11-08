#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""边界↔实现联动闸（2026-11-07 吸收 DSH dsh-metaphysics `limits.js` 机制）。

它借的机制只有一句：**「声明不给什么」与「代码真的不给」必须自动对拍**，
改一侧另一侧没跟上就红。边界内容全部出自本馆册页，不搬它的。

为什么要有：`57` 管草稿出口、`kb_gate` 管措辞、`kb_audit` 管册页自洽，
三者之间有一道空档 —— **规矩写在册页上、实现却长出了别的东西**，没人管。
竞品把这件事做成了 `engine/limits.js` ↔ `test/limits.test.mjs` 联动，值得学。

四类检查：
    banned_present   出口禁词表必须含指定词（判「出口真拦」）
    banned_present_ts 工具侧 redline.ts 的 BANNED 段必须含指定词
    code_absent      实现文件里不得出现指定模式（判「代码真不给」）
    code_present     实现文件里必须出现指定守门代码（判「闸真接上」）
    doc_declared     册页里必须写有该声明（判「册页与实现同口径」）

用法：
    python3 limits_check.py --gate      # 真库逐条核，有不一致退出 1
    python3 limits_check.py --json      # 结构化结果
    python3 limits_check.py --selftest # 内建自检（含篡改检测）

诚实降级：工具侧工程不在本机时，相关条目标「未核」，**不算通过**；
`--gate` 不因此变红（那是另一个工程），但报告必须写「覆盖：不足」。
"""
import argparse
import importlib.util
import json
import os
import re
import sys

此处 = os.path.dirname(os.path.abspath(__file__))
专家包根 = os.path.abspath(os.path.join(此处, "..", "..", ".."))
知识库根 = os.path.abspath(os.path.join(此处, ".."))
表路径 = os.path.join(知识库根, "limits.json")
默认工具根 = "/Users/haoqing/WorkBuddy/2026-10-30-13-17-15/xuanjian-paipan"

# code_absent 的说明行豁免：册页或注释里写「不给综合分」不算越界
豁免词 = ("不给", "不许", "不出", "不折", "不用", "不说", "不等于", "禁止",
          "不得", "未", "禁", "不", "拒绝", "不是", "没有", "无")


def 读表(路=None):
    with open(路 or 表路径, encoding="utf-8") as f:
        return json.load(f)


def _禁词全表():
    """从运行时闸门实读，不复制一份词表（复制就会漂移）。"""
    p = os.path.join(此处, "kb_gate.py")
    spec = importlib.util.spec_from_file_location("_xj_kb_gate", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return set(w for words in m.BANNED.values() for w in words)


def _ts禁词段(文本):
    """只取 redline.ts 的 BANNED 定义段，避免注释里出现同词算命中。"""
    m = re.search(r"export const BANNED[^\{]*\{(.*?)\n\};", 文本, re.S)
    return m.group(1) if m else ""


def 查一条(实, 根们, 禁词=None):
    """返回 (状态, 说明)。状态 ∈ 通过／失败／未核。"""
    侧 = 实.get("侧", "专家包")
    根 = 根们.get(侧)
    if 根 is None:
        return "未核", "侧未配置：" + 侧
    路 = os.path.join(根, 实["路径"])
    if not os.path.isfile(路):
        return "未核", "文件不存在：" + 实["路径"]
    with open(路, encoding="utf-8") as f:
        文 = f.read()
    类 = 实["类型"]

    # 可选「只查实现段」：文档字符串与自检代码里拿禁用词当检测字面，
    # 那是**闸门自己**在用词，不是实现长出了禁用的东西。范围由表显式给出，
    # 不自动猜，免得把真正的实现区漏掉。
    起, 止 = 实.get("范围起"), 实.get("范围止")
    if 起 or 止:
        行们 = 文.splitlines()
        s = next((i for i, l in enumerate(行们) if 起 and re.search(起, l)), 0)
        e = next((i for i in range(s + 1, len(行们)) if 止 and re.search(止, 行们[i])), len(行们))
        文 = "\n".join(行们[s:e])

    if 类 == "banned_present":
        缺 = [w for w in 实["词"] if w not in (禁词 or set())]
        return ("失败", "出口禁词表缺：" + "、".join(缺)) if 缺 else ("通过", "禁词全在")

    if 类 == "banned_present_ts":
        段 = _ts禁词段(文)
        缺 = [w for w in 实["词"] if w not in 段]
        return ("失败", "redline.ts BANNED 段缺：" + "、".join(缺)) if 缺 else ("通过", "工具禁词全在")

    if 类 == "code_absent":
        豁免 = tuple(实.get("豁免", [])) or 豁免词
        否定前缀 = ("不", "禁", "未", "勿", "莫", "拒", "非", "无", "零")
        for n, 行 in enumerate(文.splitlines(), 1):
            行首 = 行.lstrip()
            是说明行 = 行首.startswith(("#", "//", "- ", "* ", ">", "/*", '"""', "'''"))
            # ① 说明行：明确在说「不给」的整行豁免（如 `- 不输出单盘综合分`）
            if 是说明行 and (any(x in 行 for x in 豁免) or any(x in 行 for x in 否定前缀)):
                continue
            # ② 数据字符串里的否定说明（如 `"不含综合分"`、`"不加权互证"`）：
            #    只看命中点前 4 字，含否定词才豁免。窗口取短是故意的——
            #    `const 不许 = 综合分` 的否定词落在窗口外，仍要报红。
            for p in 实["模式"]:
                for m in re.finditer(p, 行):
                    前 = 行[max(0, m.start() - 4):m.start()]
                    if any(x in 前 for x in 否定前缀):
                        continue
                    return "失败", "第 %d 行命中禁用模式 %s：%s" % (n, p, 行.strip()[:70])
        return "通过", "零命中"

    if 类 == "code_present":
        缺 = [p for p in 实["模式"] if not re.search(p, 文)]
        return ("失败", "守门代码缺：" + "、".join(缺)) if 缺 else ("通过", "守门代码在")

    if 类 == "doc_declared":
        缺 = [w for w in 实["词"] if w not in 文]
        return ("失败", "册页未写：" + "、".join(缺)) if 缺 else ("通过", "册页已声明")

    return "失败", "未知检查类型：" + 类


def 检查(表=None, 专家包=None, 工具根=None, 禁词=None):
    表 = 表 or 读表()
    根们 = {
        "专家包": 专家包 or 专家包根,
        "工具": 工具根 or os.environ.get("排盘工具") or 默认工具根,
    }
    禁词 = 禁词 if 禁词 is not None else _禁词全表()
    明细, 失败, 未核 = [], [], []
    for 条 in 表["条目"]:
        for 实 in 条["实现"]:
            态, 说 = 查一条(实, 根们, 禁词)
            项 = {"id": 条["id"], "声明": 条["声明"], "侧": 实.get("侧"),
                  "路径": 实["路径"], "类型": 实["类型"], "状态": 态, "说明": 说}
            明细.append(项)
            (失败 if 态 == "失败" else 未核 if 态 == "未核" else []).append(项) if 态 != "通过" else None
    return {
        "ok": not 失败,
        "表版本": 表.get("version"),
        "条目数": len(表["条目"]),
        "检查数": len(明细),
        "通过": sum(1 for x in 明细 if x["状态"] == "通过"),
        "失败": 失败,
        "未核": 未核,
        "覆盖": "充分" if not 未核 else "不足",
        "明细": 明细,
    }


def 打印(r, 简=False):
    print("== 边界↔实现联动闸 ==")
    print("表版本 %s｜%d 条声明／%d 项检查｜通过 %d｜失败 %d｜未核 %d｜覆盖：%s"
          % (r["表版本"], r["条目数"], r["检查数"], r["通过"],
             len(r["失败"]), len(r["未核"]), r["覆盖"]))
    if r["失败"]:
        print("\n[不一致] 改了一侧、另一侧没跟上：")
        last = None
        for x in r["失败"]:
            if x["id"] != last:
                print("  %s　%s" % (x["id"], x["声明"]))
                last = x["id"]
            print("     ✗ [%s] %s :: %s → %s" % (x["侧"], x["路径"], x["类型"], x["说明"]))
    if r["未核"] and not 简:
        print("\n[未核] 另一侧工程不在本机，相关检查本次没跑（不算通过）：")
        for x in r["未核"][:12]:
            print("     ? [%s] %s → %s" % (x["侧"], x["路径"], x["说明"]))
        if len(r["未核"]) > 12:
            print("     …另有 %d 项" % (len(r["未核"]) - 12))
    if not r["失败"] and not r["未核"]:
        print("\n结论：声明不给的，代码确实不给；册页也写了同一句。")
    elif not r["失败"]:
        print("\n结论：本侧全部一致；跨工程部分未核，覆盖记为「不足」。")
    else:
        print("\n结论：不一致 %d 项，按「改实现／改册页／改声明」三选一处置，不许改表消警报。"
              % len(r["失败"]))
    return r["ok"]


def selftest():
    import tempfile
    通过, 失败 = [], []

    def 查(name, cond):
        (通过 if cond else 失败).append(name)

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "s"), exist_ok=True)
        根们 = {"专家包": d, "工具": d}
        禁 = {"血光之灾", "必定"}

        f = os.path.join(d, "s", "x.ts")
        open(f, "w", encoding="utf-8").write("const a = 1;\n// 不许给综合分\nlet x = 综合分 + 1;\n")
        查("code_absent·命中实现行判失败",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不许"]}, 根们, 禁)[0] == "失败")
        查("code_absent·说明行豁免",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不许", "综合分不"]}, 根们, 禁)[0] == "失败")  # 实现行仍命中
        open(f, "w", encoding="utf-8").write("const a = 1;\n// 不给综合分，也不折成一个数\n")
        查("code_absent·纯说明行不算越界",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不给"]}, 根们, 禁)[0] == "通过")
        # 「不输出」不含连续的「不出」：说明行只靠否定语义识别，不靠字面词表
        open(f, "w", encoding="utf-8").write("- 不输出单盘综合分、不把对拍例数说成准确率\n")
        查("code_absent·否定说明行不因字面漏豁免",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分", "准确率"], "豁免": ["不给"]}, 根们, 禁)[0] == "通过")
        open(f, "w", encoding="utf-8").write("// 这里展示综合分\n")
        查("code_absent·注释行没写否定仍报红（豁免不许过宽）",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不给"]}, 根们, 禁)[0] == "失败")
        open(f, "w", encoding="utf-8").write("const 不许 = 综合分 + 1;\n")
        查("code_absent·实现行含否定词也不豁免",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不给"]}, 根们, 禁)[0] == "失败")
        open(f, "w", encoding="utf-8").write('"说明": "推导链不含综合分；"\n')
        查("code_absent·数据字符串里的否定说明豁免",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不给"]}, 根们, 禁)[0] == "通过")
        open(f, "w", encoding="utf-8").write('"divergence_policy": "不加权互证、不隐藏"\n')
        查("code_absent·不加权互证这类政策字符串豁免",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["加权互证"], "豁免": ["不给"]}, 根们, 禁)[0] == "通过")
        open(f, "w", encoding="utf-8").write('"total": 综合分\n')
        查("code_absent·真把综合分当字段仍报红",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_absent",
                   "模式": ["综合分"], "豁免": ["不给"]}, 根们, 禁)[0] == "失败")
        open(f, "w", encoding="utf-8").write("const a = 1;\n")
        查("code_present·有守门代码判通过",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_present",
                   "模式": ["const a"]}, 根们, 禁)[0] == "通过")
        查("code_present·缺守门代码判失败",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "code_present",
                   "模式": ["scan_banned"]}, 根们, 禁)[0] == "失败")
        查("doc_declared·册页没写判失败",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "doc_declared",
                   "词": ["本人终点永不可断"]}, 根们, 禁)[0] == "失败")
        查("banned_present·禁词表实读命中",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "banned_present",
                   "词": ["血光之灾"]}, 根们, 禁)[0] == "通过")
        查("banned_present·删掉禁词即红（不许改基准消警报）",
           查一条({"侧": "专家包", "路径": "s/x.ts", "类型": "banned_present",
                   "词": ["血光之灾"]}, 根们, set())[0] == "失败")
        t = os.path.join(d, "s", "r.ts")
        open(t, "w", encoding="utf-8").write(
            "// 注释里写 血光之灾 不算\nexport const BANNED = {\n  生死禁词: ['血光之灾'],\n};\n")
        查("banned_present_ts·只认 BANNED 段",
           查一条({"侧": "专家包", "路径": "s/r.ts", "类型": "banned_present_ts",
                   "词": ["血光之灾"]}, 根们, 禁)[0] == "通过")
        查("banned_present_ts·BANNED 段里没有就红",
           查一条({"侧": "专家包", "路径": "s/r.ts", "类型": "banned_present_ts",
                   "词": ["不存在的词"]}, 根们, 禁)[0] == "失败")
        查("文件不存在标未核不冒称通过",
           查一条({"侧": "专家包", "路径": "s/nope.ts", "类型": "code_present",
                   "模式": ["x"]}, 根们, 禁)[0] == "未核")

        # 整表联动：把一条声明改成「代码里明明有」的模式，应当整体变红
        假表 = {"version": "t", "条目": [
            {"id": "T1", "声明": "测试", "实现": [
                {"侧": "专家包", "路径": "s/x.ts", "类型": "code_present", "模式": ["const a"]}]}]}
        查("整表·一致时 ok=True", 检查(假表, d, d, 禁)["ok"] is True)
        假表["条目"][0]["实现"][0]["模式"] = ["绝不存在的守门"]
        查("整表·实现没跟上时 ok=False", 检查(假表, d, d, 禁)["ok"] is False)

    # 真库：本侧不许有不一致
    真 = 检查()
    查("真库·本侧零不一致（工具侧未核不计）",
       all(x["侧"] != "专家包" for x in 真["失败"]))
    查("真库·检查数不少于声明数", 真["检查数"] >= 真["条目数"])
    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    if 真["失败"]:
        for x in 真["失败"][:8]:
            print("  真库不一致：%s [%s] %s → %s" % (x["id"], x["侧"], x["路径"], x["说明"]))
    return not 失败


def main():
    ap = argparse.ArgumentParser(description="边界↔实现联动闸")
    ap.add_argument("--gate", action="store_true", help="有不一致退出 1")
    ap.add_argument("--json", action="store_true", help="输出结构化结果")
    ap.add_argument("--selftest", action="store_true", help="跑内建自检")
    a = ap.parse_args()
    if a.selftest:
        return 0 if selftest() else 1
    r = 检查()
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        打印(r)
    if a.gate and not r["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
