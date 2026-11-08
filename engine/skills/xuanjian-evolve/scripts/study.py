#!/usr/bin/env python3
"""学习编排 —— 把「读 → 提炼 → 落册 → 出题 → 判卷 → 复查」串成一条可跑的链。

用法：
    python3 study.py 状态            学习到哪了：进度、掌握度、到期复习、待裁候选
    python3 study.py 下一批 [数量]    下一批该读什么（调 evolve.py 下一批）
    python3 study.py 提炼 <原文...>   抽候选断言（调 distill.py）
    python3 study.py 出题 <册号> [数量]
    python3 study.py 判卷 <题.json> <答.json>
    python3 study.py 复盘             到期复习 + 薄弱册 + 待裁候选，一屏看完
    python3 study.py 自检             全链路冒烟（不写状态根）

**为什么要有一个编排层**：摄取、提炼、出题、判卷、回归各自都是好脚本，但每轮
都要人记着「先跑哪个、跑完看哪、下一步做什么」。这一层只做两件事：**把顺序固定下来**，
**把该看的数摆在一屏里**。它不替人判断——候选要人裁，答案要人写，掌握度低就是低。
"""
import json
import os
import subprocess
import sys

此处 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, 此处)

import study_state          # noqa: E402
import mastery              # noqa: E402


def 跑(脚本, 参=None):
    return subprocess.run([sys.executable, os.path.join(此处, 脚本)] + (参 or []),
                          capture_output=True, text=True)


def 台账进度():
    r = 跑("ledger.py", ["统计"])
    行 = [l for l in r.stdout.splitlines() if l.strip()]
    合计 = ""
    for l in 行:
        if l.startswith("合计"):
            合计 = " ".join(l.split())
    return 合计 or (r.stdout.strip()[:120] or "台账读不到"), r.returncode


def 掌握概况():
    掌 = mastery.读掌握度()
    册们 = 掌.get("books", {})
    if not 册们:
        return "还没有掌握度记录（先 出题 → 作答 → 判卷）", 0.0, []
    平 = sum(v.get("掌握度", 0) for v in 册们.values()) / len(册们)
    薄 = sorted([(k, v) for k, v in 册们.items()], key=lambda kv: kv[1].get("掌握度", 0))[:5]
    return "平均掌握 %.2f（已测 %d 册）" % (平, len(册们)), 平, 薄


def 待裁():
    """最近一次提炼里，需要人看的候选条数。"""
    路 = os.path.join(os.getcwd(), ".workbuddy", "learning", "distill", "distill.json")
    if not os.path.exists(路):
        return None
    try:
        d = json.load(open(路, encoding="utf-8"))
        c = d.get("counts", {})
        return "NEW %d ／ REVIEW %d ／ CONFLICT %d（%s）" % (
            c.get("NEW", 0), c.get("REVIEW", 0), c.get("CONFLICT", 0),
            "、".join(d.get("sources", []))[:40])
    except Exception:
        return None


def 命令_状态(_参):
    根 = study_state.状态根()
    print("== 学习状态 ==")
    print("  状态根：%s" % 根)
    缺 = [k for k, v in study_state.四件现状().items() if not v["exists"]]
    print("  四件：%s" % ("齐全" if not 缺 else "缺 " + "、".join(缺)))
    进度, _ = 台账进度()
    print("  摄取：%s" % 进度)
    概, 平, 薄 = 掌握概况()
    print("  掌握：%s" % 概)
    if 薄:
        print("  最薄：%s" % "；".join("%s %.2f" % (k[:18], v.get("掌握度", 0)) for k, v in 薄[:3]))
    候 = 待裁()
    if 候:
        print("  待裁候选：%s" % 候)
    到 = [(k, v) for k, v in mastery.读掌握度().get("books", {}).items()
          if (v.get("下次复习") or "9999") <= __import__("datetime").date.today().isoformat()]
    print("  今日到期复习：%d 册" % len(到))
    旧 = study_state.四件现状(study_state.旧默认)
    新 = study_state.四件现状()
    if 根 != study_state.旧默认 and any(旧[k]["exists"] and not 新[k]["exists"] for k in study_state.四件):
        print("  注意：旧根还有进度没搬：`study_state.py 迁移 --到 %s`" % 根)
    return 0


def 命令_复盘(_参):
    命 = 0
    print("== 复盘 ==")
    进度, _ = 台账进度()
    print("[1] %s" % 进度)
    概, 平, 薄 = 掌握概况()
    print("[2] %s" % 概)
    if 薄:
        print("    薄弱册：")
        for k, v in 薄:
            print("      %-40s %.2f %s 下次 %s" % (k[:40], v.get("掌握度", 0),
                                                v.get("档", ""), v.get("下次复习", "")))
    候 = 待裁()
    print("[3] 待裁候选：%s" % (候 or "无（本轮没跑提炼）"))
    r = 跑("mastery.py", ["到期"])
    print("[4] " + (r.stdout.strip().splitlines()[0] if r.stdout.strip() else "到期查询失败"))
    if r.stdout.strip().count("  ") > 1:
        for l in r.stdout.splitlines()[1:6]:
            print("    " + l.strip())
    return 命


def 命令_出题(参):
    if not 参:
        print("用法：python3 study.py 出题 <册号> [数量]")
        return 2
    册 = 参[0]
    数 = 参[1] if len(参) > 1 else "8"
    出 = os.path.join(os.getcwd(), ".workbuddy", "learning", "quiz", "q_%s.json" % 册[:2])
    os.makedirs(os.path.dirname(出), exist_ok=True)
    r = 跑("mastery.py", ["出题", "--book", 册, "--limit", 数, "--out", 出])
    print(r.stdout.strip() or r.stderr.strip())
    print("题目：%s" % 出)
    print("下一步：把作答写成 JSON（qid → 答案），再跑 `study.py 判卷`。")
    return r.returncode


def 命令_判卷(参):
    if len(参) < 2:
        print("用法：python3 study.py 判卷 <题.json> <答.json>")
        return 2
    r = 跑("mastery.py", ["判卷", "--questions", 参[0], "--answers", 参[1]])
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode


def 命令_提炼(参):
    if not 参:
        print("用法：python3 study.py 提炼 <原文.md ...>")
        return 2
    出 = os.path.join(os.getcwd(), ".workbuddy", "learning", "distill")
    r = 跑("distill.py", ["提炼"] + 参 + ["--out", 出])
    print(r.stdout.strip() or r.stderr.strip())
    print("裁决提醒：CONFLICT 一条都不许自动采用；NEW 要人核定后才落册。")
    return r.returncode


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("状态根可解析", bool(study_state.状态根()))
    概, 平, _ = 掌握概况()
    查("掌握概况可读", isinstance(概, str) and 0 <= 平 <= 1)
    查("台账进度可读", 台账进度()[0] != "台账读不到")
    查("提炼候选可读或为空", 待裁() is None or "NEW" in (待裁() or ""))
    q = os.path.join(此处, "..", "..", "xuanjian-kb", "references")
    查("册目录存在", os.path.isdir(os.path.normpath(q)))
    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    参 = sys.argv[1:]
    if not 参:
        参 = ["状态"]
    命 = 参[0]
    余 = 参[1:]
    if 命 == "自检":
        return 自检()
    if 命 == "状态":
        return 命令_状态(余)
    if 命 == "复盘":
        return 命令_复盘(余)
    if 命 == "下一批":
        r = 跑("evolve.py", ["下一批"])
        print(r.stdout.strip() or r.stderr.strip())
        return r.returncode
    if 命 == "提炼":
        return 命令_提炼(余)
    if 命 == "出题":
        return 命令_出题(余)
    if 命 == "判卷":
        return 命令_判卷(余)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
