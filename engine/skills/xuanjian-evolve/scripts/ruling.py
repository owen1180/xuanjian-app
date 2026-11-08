#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提炼裁决台 —— 把 `distill.py` 的提案逐条裁掉，别让它烂尾。

为什么要有它
------------
`distill.py` 只能提案，不能裁决——这是对的，脚本不该自己决定什么进知识库。
但问题出在另一半：226 条提案躺在 `distill.json` 里，**一条也没被裁过**。
提案没有消费端，等于没提案；攒得越多越像成绩，其实一行知识都没进库。

三条纪律
--------
1. **不许一键全采纳**。`裁` 只接受单条 id，不接受 `--all`。二百多条里大部分是
   课堂口语碎片（「食神七杀，食神正官交战」这种），全采纳等于把噪音灌进册页。
2. **每条必须写理由**。没理由的裁决不算裁决，只算点头。往后回看「当初为什么驳回」
   比「驳回了什么」更有用。
3. **已裁不许重裁**。同一条裁两次会让台账自相矛盾；真要改口用 `改判`，留痕。

用法
----
    python3 ruling.py 清单 [--verdict NEW] [--limit 20] [--offset 0]
    python3 ruling.py 裁 D001 采纳 --理由 "..." [--归 96]
    python3 ruling.py 裁 D002 驳回 --理由 "..."
    python3 ruling.py 改判 D001 驳回 --理由 "..."
    python3 ruling.py 台账
    python3 ruling.py 草稿 --out 目录
    python3 ruling.py 迁指纹 [--dry]        # 旧位置号 id → 内容指纹（按正文匹配）
    python3 ruling.py 核对                  # 每条裁决的 id 是否仍指回它当初裁的那句
"""

import datetime
import json
import os
import sys

try:
    import study_state
except Exception:
    study_state = None

判决们 = ("采纳", "驳回", "延后")
台账名 = "提炼裁决.json"


def 载提案(路):
    """给每条提案定 id。**有指纹用指纹，没有才退回位置号**。

    位置号（`D001` 起）看着好念，但它是「第几条」，不是「哪一条」：
    distill 少提一条问句，或某条对撞结果从 NEW 变 KNOWN，后面全体前移一位，
    已裁的裁决就会静默指向别的提案。2026-11-05 实测：加了一句问句过滤，
    提案 226→223，若还用位置号，51 条裁决里有 3 条起会错位。
    指纹（`D-<md5前8>`）跟内容绑定，内容在，编号就在。
    """
    d = json.load(open(路, encoding="utf-8"))
    条 = d.get("assertions", [])
    for i, x in enumerate(条, 1):
        fp = (x.get("fp") or "").strip()
        x["id"] = ("D-%s" % fp) if fp else ("D%03d" % i)
        x["id_legacy"] = "D%03d" % i
    return d, 条


def 迁指纹(台, 条, 写=False):
    """把台账里按位置号的旧 id 换成指纹 id。**按正文匹配，不按序号推**。

    为什么按正文：台账每条裁决都存了 `text`（当初裁的那句原文）。拿它对提案表
    做匹配，与「现在是第几条」无关，distill 重跑多少次都不影响。
    匹配梯度：完全相等 → 提案以裁决文本开头（台账只存前 200 字）→ 都失败则记 unmatched。
    """
    索 = {}
    for x in 条:
        索.setdefault((x.get("text") or "").strip(), []).append(x)
    换 = 未匹配 = 已是指纹 = 0
    for r in 台.get("rulings", []):
        if str(r.get("id", "")).startswith("D-"):
            已是指纹 += 1
            continue
        正文 = (r.get("text") or "").strip()
        命中 = 索.get(正文)
        if not 命中 and 正文:
            命中 = [x for x in 条 if (x.get("text") or "").strip().startswith(正文)]
        if not 命中:
            r["fp_missing"] = True
            未匹配 += 1
            continue
        r.setdefault("id_legacy", r["id"])
        r["id"] = 命中[0]["id"]
        r.pop("fp_missing", None)
        换 += 1
    if 写 and 换:
        存台账(台)
    return {"换": 换, "未匹配": 未匹配, "已是指纹": 已是指纹, "共": len(台.get("rulings", []))}


def 台账路():
    if study_state:
        return study_state.文件(台账名)
    return os.path.join(os.getcwd(), 台账名)


def 读台账():
    p = 台账路()
    if not os.path.exists(p):
        return {"artifact": "提炼裁决台账", "rulings": []}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {"artifact": "提炼裁决台账", "rulings": []}


def 存台账(d):
    p = 台账路()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    return p


def 查已裁(台, id):
    return [r for r in 台["rulings"] if r["id"] == id]


def 裁决(台, id, 判决, 理由, 归, 提案=None):
    if 判决 not in 判决们:
        return {"ok": False, "err": "判决只能是 %s" % "／".join(判决们)}
    if not (理由 or "").strip():
        return {"ok": False, "err": "必须写理由：没有理由的裁决只是点头"}
    旧 = 查已裁(台, id)
    return {"ok": True, "旧": 旧[0] if 旧 else None}


def 记(台, id, 判决, 理由, 归, 提案=None, 覆盖=False):
    """写一条裁决。旧裁决保留在 superseded 里，不删——留痕。"""
    旧 = 查已裁(台, id)
    if 旧 and not 覆盖:
        return False
    if 旧 and 覆盖:
        旧[0]["superseded"] = True
    条 = {"id": id, "verdict": 判决, "reason": 理由.strip(),
          "on": datetime.date.today().isoformat()}
    if 归:
        条["merged_into"] = 归
    if 提案:
        条["text"] = 提案.get("text", "")[:200]
        条["locator"] = 提案.get("locator", "")
        条["proposed"] = 提案.get("verdict", "")
    台["rulings"].append(条)
    return True


def 核对(台, 条):
    """每条裁决的 id 必须指回它当初裁的那句话。这是防错位的最后一道。

    为什么需要：指纹只保证「同一个内容同一个号」，但若台账被手工改过、或提案表
    被另一台机器重写过，id 仍可能挂到别的条目上。判据取「提案正文以裁决正文开头」
    （台账只存前 200 字），对不上就算错位，逐条报出来。
    """
    按id = {x["id"]: x for x in 条}
    坏 = []
    for r in 台.get("rulings", []):
        x = 按id.get(r.get("id"))
        正文 = (r.get("text") or "").strip()
        if x is None:
            坏.append((r.get("id"), "提案表里没有这个 id", 正文[:50]))
        elif 正文 and not (x.get("text") or "").strip().startswith(正文):
            坏.append((r.get("id"), "id 指向的是另一句", 正文[:50]))
    return 坏


def 待裁(条, 台, 只看=None):
    裁过 = {r["id"] for r in 台["rulings"] if not r.get("superseded")}
    out = [x for x in 条 if x["id"] not in 裁过]
    if 只看:
        out = [x for x in out if x.get("verdict") == 只看]
    return out


def 排序键(x):
    """先看边界类（讲红线，错了要出事），再看数值（可核对），最后判断类。
    同类里相似度高的排前面——那是最可能「其实讲过、只是换了说法」的。"""
    权 = {"边界": 0, "数值": 1, "判断": 2}
    return (权.get(x.get("type"), 3), -x.get("similarity", 0))


def 统计(条, 台):
    裁过 = [r for r in 台["rulings"] if not r.get("superseded")]
    计 = {"采纳": 0, "驳回": 0, "延后": 0}
    for r in 裁过:
        计[r["verdict"]] = 计.get(r["verdict"], 0) + 1
    return {"提案": len(条), "已裁": len(裁过), "待裁": len(条) - len(裁过),
            "分项": 计, "覆盖": round(len(裁过) / len(条), 4) if 条 else 0.0}


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    条 = [{"id": "D001", "verdict": "NEW", "type": "边界", "similarity": 0.2,
           "text": "甲", "locator": "x#L1"},
          {"id": "D002", "verdict": "NEW", "type": "判断", "similarity": 0.5,
           "text": "乙", "locator": "x#L2"},
          {"id": "D003", "verdict": "REVIEW", "type": "数值", "similarity": 0.3,
           "text": "丙", "locator": "x#L3"}]
    台 = {"artifact": "t", "rulings": []}
    查("排序边界优先", [x["id"] for x in sorted(条, key=排序键)] == ["D001", "D003", "D002"])
    查("待裁初始三条", len(待裁(条, 台)) == 3)

    chk = 裁决(台, "D001", "采纳", "", None)
    查("空理由被拒", not chk["ok"])
    chk = 裁决(台, "D001", "同意", "理由", None)
    查("非法判决被拒", not chk["ok"])
    chk = 裁决(台, "D001", "采纳", "与 96 册重复，归并", "96")
    查("合法裁决通过", chk["ok"])

    查("记入台账", 记(台, "D001", "采纳", "与 96 册重复，归并", "96", 条[0]))
    查("已裁不许重裁", not 记(台, "D001", "驳回", "改口", None, 条[0]))
    查("改判走覆盖并留痕", 记(台, "D001", "驳回", "想清楚了", None, 条[0], 覆盖=True))
    查("旧裁决标 superseded", 台["rulings"][0].get("superseded") is True)
    查("有效裁决只剩新的一条",
       len([r for r in 台["rulings"] if not r.get("superseded")]) == 1)

    查("待裁减一", len(待裁(条, 台)) == 2)
    查("按判定过滤", len(待裁(条, 台, 只看="REVIEW")) == 1)

    # 指纹：id 跟内容走，不跟位置走
    带指纹 = [{"text": "甲乙", "fp": "aaaa1111"}, {"text": "丙丁", "fp": "bbbb2222"}]
    import tempfile
    临 = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"assertions": 带指纹}, 临, ensure_ascii=False)
    临.close()
    try:
        _, 载入 = 载提案(临.name)
        查("指纹·有 fp 用指纹", 载入[0].get("id") == "D-aaaa1111")
        查("指纹·位置号留作 legacy", 载入[1].get("id_legacy") == "D002")
        查("指纹·两条内容不同则 id 不同", 载入[0]["id"] != 载入[1]["id"])
        # 换序不该换 id
        倒序 = {"assertions": list(reversed(带指纹))}
        open(临.name, "w", encoding="utf-8").write(json.dumps(倒序, ensure_ascii=False))
        _, 载入2 = 载提案(临.name)
        查("指纹·提案换序 id 不变",
           {x["id"] for x in 载入2} == {x["id"] for x in 载入})
    finally:
        os.unlink(临.name)

    # 迁移：按正文匹配
    台2 = {"rulings": [
        {"id": "D001", "verdict": "采纳", "reason": "r", "on": "d", "text": "甲乙"},
        {"id": "D002", "verdict": "驳回", "reason": "r", "on": "d", "text": "这句已经不在提案表里"},
        {"id": "D003", "verdict": "驳回", "reason": "r", "on": "d", "text": "丙"},
    ]}
    条2 = [{"text": "甲乙", "fp": "aaaa1111", "id": "D-aaaa1111"},
           {"text": "丙丁戊", "fp": "bbbb2222", "id": "D-bbbb2222"}]
    结 = 迁指纹(台2, 条2)
    查("迁移·按正文换到指纹", 台2["rulings"][0].get("id") == "D-aaaa1111")
    查("迁移·保留旧号备查", 台2["rulings"][0].get("id_legacy") == "D001")
    查("迁移·正文前缀也能匹配", 台2["rulings"][2].get("id") == "D-bbbb2222")
    查("迁移·找不到的标 fp_missing", 台2["rulings"][1].get("fp_missing") is True)
    查("迁移·计数对", (结["换"], 结["未匹配"]) == (2, 1))

    # 核对：错位必须报出来
    条3 = [{"id": "D-x", "text": "甲"}, {"id": "D-y", "text": "乙"}]
    台3 = {"rulings": [{"id": "D-x", "text": "甲"}, {"id": "D-y", "text": "丙"}]}
    查("核对·对的上不报", 核对({"rulings": [{"id": "D-x", "text": "甲"}]}, 条3) == [])
    坏 = 核对(台3, 条3)
    查("核对·指错句要报", len(坏) == 1 and 坏[0][0] == "D-y")
    查("核对·id 不存在要报", len(核对({"rulings": [{"id": "D-zzz", "text": "甲"}]}, 条3)) == 1)
    s = 统计(条, 台)
    查("统计已裁一", s["已裁"] == 1 and s["待裁"] == 2)
    查("采纳计数", s["分项"]["驳回"] == 1)
    print("自检：通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    if 失败:
        for f in 失败:
            print("  ✗", f)
        return 1
    return 0


def main():
    参 = sys.argv[1:]
    if not 参:
        print(__doc__)
        return 0
    if 参[0] == "--selftest":
        return 自检()

    命 = 参[0]
    选 = {"--src": None, "--verdict": None, "--limit": "20", "--offset": "0",
          "--理由": None, "--归": None, "--out": None}
    i = 1
    while i < len(参):
        if 参[i] in 选 and i + 1 < len(参):
            选[参[i]] = 参[i + 1]
            i += 2
        else:
            i += 1
    源 = 选["--src"] or os.path.join(
        os.environ.get("玄鉴学习", os.getcwd()), "distill", "distill.json")

    if 命 == "迁指纹":
        if not os.path.exists(源):
            print("找不到提炼产物：%s\n用 --src 指定 distill.json" % 源)
            return 2
        _, 条 = 载提案(源)
        台 = 读台账()
        干跑 = "--dry" in 参
        结 = 迁指纹(台, 条, 写=not 干跑)
        print("== 迁移台账 id → 内容指纹 ==")
        print("  共 %d 条裁决：换 %d ／ 已是指纹 %d ／ 未匹配 %d" % (
            结["共"], 结["换"], 结["已是指纹"], 结["未匹配"]))
        if 结["未匹配"]:
            print("  ✗ 未匹配的保持原 id 并标 fp_missing（该提案内容已不在提案表里，须人工看）")
            for r in 台.get("rulings", []):
                if r.get("fp_missing"):
                    print("    %s  %s" % (r.get("id_legacy") or r["id"], (r.get("text") or "")[:60]))
        print("  %s" % ("（干跑，未写盘；去掉 --dry 才写）" if 干跑 else "已写台账：%s" % 台账路()))
        return 0

    if 命 == "核对":
        if not os.path.exists(源):
            print("找不到提炼产物：%s\n用 --src 指定 distill.json" % 源)
            return 2
        _, 条 = 载提案(源)
        台 = 读台账()
        坏 = 核对(台, 条)
        print("== 裁决挂靠核对 ==")
        print("  裁决 %d 条，错位 %d 条" % (len(台.get("rulings", [])), len(坏)))
        for i, 因, 文 in 坏[:20]:
            print("  ✗ %s：%s\n     %s" % (i, 因, 文))
        if 坏:
            return 1
        print("  结论：每条裁决都指回它当初裁的那一句 ✓")
        return 0

    if 命 in ("清单", "台账", "草稿", "裁", "改判"):
        if not os.path.exists(源):
            print("找不到提炼产物：%s\n用 --src 指定 distill.json" % 源)
            return 2
        _, 条 = 载提案(源)
        台 = 读台账()
    else:
        print(__doc__)
        return 2

    if 命 == "清单":
        组 = 待裁(条, 台, 选["--verdict"])
        组.sort(key=排序键)
        限, 偏 = int(选["--limit"] or 20), int(选["--offset"] or 0)
        s = 统计(条, 台)
        print("== 待裁清单（已裁 %d／%d，覆盖 %.1f%%）==" % (
            s["已裁"], s["提案"], s["覆盖"] * 100))
        print("   筛选：%s；本页 %d 条，从第 %d 条起\n" % (
            选["--verdict"] or "全部", min(限, max(0, len(组) - 偏)), 偏 + 1))
        for x in 组[偏:偏 + 限]:
            print("[%s] %s（相似 %.2f）" % (x["id"], x.get("verdict"), x.get("similarity", 0)))
            print("   %s" % x["text"][:150])
            print("   %s" % x.get("locator", ""))
            m = x.get("match")
            if m:
                print("   ↔ %s L%d：%s" % (m["book"][:30], m["line"], m["text"][:80]))
            print()
        if len(组) > 偏 + 限:
            print("（还有 %d 条，用 --offset %d 翻页）" % (len(组) - 偏 - 限, 偏 + 限))
        return 0

    if 命 in ("裁", "改判"):
        if len(参) < 3:
            print("用法：python3 ruling.py 裁 D001 采纳 --理由 \"...\" [--归 96]")
            return 2
        id, 判决 = 参[1], 参[2]
        提 = next((x for x in 条 if x["id"] == id), None)
        if not 提:
            print("没有这个 id：%s" % id)
            return 2
        chk = 裁决(台, id, 判决, 选["--理由"], 选["--归"])
        if not chk["ok"]:
            print("拒绝：%s" % chk["err"])
            return 1
        覆 = 命 == "改判"
        if chk["旧"] and not 覆:
            print("拒绝：%s 已裁为「%s」。要改口用「改判」，会留痕。" % (
                id, chk["旧"]["verdict"]))
            return 1
        记(台, id, 判决, 选["--理由"], 选["--归"], 提, 覆盖=覆)
        存台账(台)
        print("已记：%s → %s%s" % (id, 判决, "（归 %s）" % 选["--归"] if 选["--归"] else ""))
        print("  原文：%s" % 提["text"][:100])
        s = 统计(条, 台)
        print("  进度：已裁 %d／%d（%.1f%%），待裁 %d" % (
            s["已裁"], s["提案"], s["覆盖"] * 100, s["待裁"]))
        return 0

    if 命 == "台账":
        s = 统计(条, 台)
        print("== 提炼裁决台账 ==")
        print("  提案 %d，已裁 %d（%.1f%%），待裁 %d" % (
            s["提案"], s["已裁"], s["覆盖"] * 100, s["待裁"]))
        print("  采纳 %d／驳回 %d／延后 %d" % (
            s["分项"]["采纳"], s["分项"]["驳回"], s["分项"]["延后"]))
        有效 = [r for r in 台["rulings"] if not r.get("superseded")]
        if 有效:
            print()
            for r in 有效[-12:]:
                print("  %s %s %s%s" % (r["on"], r["id"], r["verdict"],
                                        "（归 %s）" % r["merged_into"] if r.get("merged_into") else ""))
                print("     理由：%s" % r["reason"][:90])
        return 0

    if 命 == "草稿":
        有效 = [r for r in 台["rulings"]
                if not r.get("superseded") and r["verdict"] == "采纳"]
        if not 有效:
            print("没有已采纳的裁决，无可导出")
            return 0
        byid = {x["id"]: x for x in 条}
        出 = 选["--out"] or os.getcwd()
        os.makedirs(出, exist_ok=True)
        组 = {}
        for r in 有效:
            组.setdefault(r.get("merged_into") or "待定", []).append(
                dict(byid.get(r["id"], {}), reason=r["reason"]))
        for 册, 项 in 组.items():
            路 = os.path.join(出, "草稿-%s.md" % 册)
            with open(路, "w", encoding="utf-8") as f:
                f.write("# 提炼提案落册草稿 · 归 %s\n\n" % 册)
                f.write("> 本文件由 `ruling.py 草稿` 生成。**是草稿，不是册页**——\n")
                f.write("> 每条须人再核一遍原文行号，确认没歪，才准并入册页。\n\n")
                for x in 项:
                    f.write("- **%s**　%s\n" % (x["id"], x.get("text", "")[:300]))
                    f.write("  - 出处：%s\n" % x.get("locator", ""))
                    f.write("  - 采纳理由：%s\n\n" % x["reason"])
            print("写出 %s（%d 条）" % (路, len(项)))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
