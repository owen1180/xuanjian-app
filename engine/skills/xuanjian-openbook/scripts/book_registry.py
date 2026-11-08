#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 TR108 · 全库册号命名空间登记与跨技能闸门（2026-11-04 查漏补缺）。

为什么有这个脚本（本轮实测到的硬伤）：
  skills/xuanjian-kb/references/95-四柱-格局专论-八格专旺两气成象与库四态.md
  skills/xuanjian-openbook/references/95-开源三阶段核验与许可防火墙.md
两个 95 撞号。既有的 kb_audit.py 只扫 xuanjian-kb/references，跨技能撞号
一律看不见；README 早就写过「撞号不是手滑，是流程缺一道闸」，本脚本就是那道闸。

定案规则（TR108）：
  - 册号 1–94 默认属 KB，可裸写；
  - 册号 95 及以上一律带命名空间前缀：KB / OB / TR / AR / EV / RI / SZ；
  - 撞号必须在 COLLISION_POLICY 显式登记裁决，未登记的撞号判 FAIL；
  - 已登记撞号的所有引用必须带前缀，裸号一律判 AMBIGUOUS；
  - 成员 agent 引用了某命名空间的册页，frontmatter skills 必须挂载对应技能。

用法：
  python3 book_registry.py                 # 打印全库报表
  python3 book_registry.py --strict       # 有硬错误时 exit 1（发出前闸门）
  python3 book_registry.py --out reg.json # 写 JSON 报表
  python3 book_registry.py --selftest
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN = HERE.parents[2]  # scripts -> xuanjian-openbook -> skills -> 专家包根

NS_DIRS = {
    "KB": "skills/xuanjian-kb/references",
    "OB": "skills/xuanjian-openbook/references",
    "TR": "skills/xuanjian-train/references",
    "AR": "skills/xuanjian-archive/references",
    "EV": "skills/xuanjian-evolve/references",
    "RI": "skills/xuanjian-ritual/references",
    "SZ": "skills/shizhan-pai/references",
}
NS_OF_SKILL = {
    "xuanjian-kb": "KB", "xuanjian-openbook": "OB", "xuanjian-train": "TR",
    "xuanjian-archive": "AR", "xuanjian-evolve": "EV",
    "xuanjian-ritual": "RI", "shizhan-pai": "SZ",
}
SKILL_OF_NS = {v: k for k, v in NS_OF_SKILL.items()}

# 参与「全库册号」编号体系的只有这三个命名空间。
# AR / RI / EV / SZ 的 01–06 是各自技能内部的章节自编号，从不以裸号被跨技能引用，
# 把它们算进撞号会把 KB 的 1–6 全部误判成歧义（本轮实测会造出 371 条噪声）。
GLOBAL_NS = ("KB", "OB", "TR")
LOCAL_NS = ("AR", "RI", "EV", "SZ")

BOOK_RE = re.compile(r"^(\d{1,3})-")
PREFIX_REF_RE = re.compile(r"`(KB|OB|TR|AR|EV|RI|SZ)(\d{1,3})`")
BARE_REF_RE = re.compile(r"`(\d{1,3})`")
FRONTMATTER_SKILLS = re.compile(r"^skills:\s*\[([^\]]*)\]", re.M)

# 撞号裁决台账：登记过的撞号不判死，但强制带前缀；未登记的一律 FAIL。
COLLISION_POLICY = {
    95: {
        "namespaces": ["KB", "OB"],
        "decided": "2026-11-04",
        "policy": "KB95=四柱格局专论（八格/专旺/两气成象/库四态）；"
                  "OB95=开源三阶段核验与许可防火墙。两者不合并、不改号，"
                  "全部引用强制带命名空间前缀。",
    },
    96: {
        "namespaces": ["KB", "OB"],
        "decided": "2026-11-05",
        "policy": "KB96=四柱·相同八字差异与断语边界（第45课实证）；"
                  "OB96=起盘口径卡 schema。两者不合并、不改号，引用强制带前缀。",
    },
    97: {
        "namespaces": ["KB", "OB"],
        "decided": "2026-11-05",
        "policy": "KB97=四柱·寿元星引动与暗合级别（第52课实证）；"
                  "OB97=引证可追溯与确定性分层。两者不合并、不改号，引用强制带前缀。",
    },
    98: {
        "namespaces": ["KB", "OB"],
        "decided": "2026-11-05",
        "policy": "KB98=古籍版本核验与合法取书（书在哪、哪个版本、能引不能引）；"
                  "OB98=语料分层与取用。两者不合并、不改号，引用强制带前缀。",
    },
    99: {
        "namespaces": ["KB", "OB"],
        "decided": "2026-11-07",
        "policy": "KB99=伦理边界与措辞规范（七类绝对禁止／措辞替换表／诚实降级，吸收命理大师长处）；"
                  "OB99=合参边界与结构化输出契约。两者不合并、不改号，引用强制带前缀。",
    },
    100: {
        "namespaces": ["KB", "OB", "TR"],
        "decided": "2026-11-05",
        "policy": "KB100=资料完备度分级路由（S/A/B/C 四级、双重降档）；"
                  "OB100=病名级健康提示（四线统一的写法与红线）；"
                  "TR100=数据训练治理与守门模型。2026-11-07 由两方扩为三方撞号（KB 新建 100 册）。"
                  "三者不合并、不改号，引用强制带前缀。",
    },
    101: {
        "namespaces": ["KB", "TR"],
        "decided": "2026-11-07",
        "policy": "KB101=隐私与用户资料留存治理（数据四级／最小化三问／零外呼）；"
                  "TR101=全量数据核验与统计。两者不合并、不改号，引用强制带前缀。",
    },
    102: {
        "namespaces": ["KB", "TR"],
        "decided": "2026-11-07",
        "policy": "KB102=技能卡规范与触发词一致性纪律（八项必填、description⊆keywords⊆description）；"
                  "TR102=起盘二十八项确定性校验。两者不合并、不改号，引用强制带前缀。",
    },
    103: {
        "namespaces": ["KB", "TR"],
        "decided": "2026-11-07",
        "policy": "KB103=外部对拍数据核验与原理原文入库（dsh-metaphysics 四组数据的实测台账、"
                  "两处数字订正、A/B/C 三档原文）；TR103=技法挂载池与口径显式化。"
                  "两者不合并、不改号，引用强制带前缀。",
    },
    104: {
        "namespaces": ["KB", "TR"],
        "decided": "2026-11-07",
        "policy": "KB104=三平台生态复查与计数口径台账（GitHub/WorkBuddy/OpenClaw 对象核实、"
                  "四层数字口径、同一包两套计数、十仓库一手核实）；TR104=AI-Agent 工具层与统一输入包。"
                  "两者不合并、不改号，引用强制带前缀。",
    },
    105: {
        "namespaces": ["KB", "TR"],
        "decided": "2026-11-07",
        "policy": "KB105=单项价目与收费标准（全平台人工测算价带调研、AI 折扣锚定、上架 singleItems 价目表）；"
                  "TR105=命途轨迹可视化边界（图不量化、案例双门禁）。"
                  "两者不合并、不改号，引用强制带前缀。"
    },
}


def scan_books(root, namespaces=GLOBAL_NS):
    """{ns: {num: filename}}，只认「数字-标题.md」命名的册页。

    默认只返回参与全库编号的 KB/OB/TR；传 NS_DIRS 可取全部（含技能内部自编号）。
    """
    books = {}
    for ns in namespaces:
        rel = NS_DIRS.get(ns)
        if not rel:
            continue
        d = pathlib.Path(root) / rel
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            m = BOOK_RE.match(p.name)
            if m:
                books.setdefault(ns, {})[int(m.group(1))] = p.name
    return books


def find_collisions(books):
    owners = {}
    for ns, vols in books.items():
        for num in vols:
            owners.setdefault(num, []).append(ns)
    return {n: sorted(v) for n, v in owners.items() if len(v) > 1}


def unregistered_collisions(coll, policy=None):
    policy = COLLISION_POLICY if policy is None else policy
    return {n: v for n, v in coll.items() if n not in policy}


def namespace_of(path, root):
    """文件所属命名空间；agents/ 与根目录文档返回 None。"""
    try:
        rel = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "skills":
        return NS_OF_SKILL.get(parts[1])
    return None


def extract_refs(text):
    """返回 (带前缀引用列表, 裸号引用列表)，两类不重复计数。"""
    prefixed = [(m.group(1), int(m.group(2))) for m in PREFIX_REF_RE.finditer(text)]
    stripped = PREFIX_REF_RE.sub("", text)
    bare = [int(m.group(1)) for m in BARE_REF_RE.finditer(stripped)]
    return prefixed, bare


def classify_refs(books, coll, owners_ns, policy=None):
    """把裸号分成 ambiguous / ok / unknown。owner_ns 为引用所在文件的命名空间。"""
    policy = COLLISION_POLICY if policy is None else policy
    flat = {}
    for ns, vols in books.items():
        for num in vols:
            flat.setdefault(num, []).append(ns)
    out = {"ambiguous": [], "ok": [], "unknown": []}
    for num in owners_ns:  # 实际传入裸号列表
        if num in coll:
            # 撞号：即使本文件属于其中一个命名空间，也必须带前缀
            out["ambiguous"].append(num)
        elif num in flat:
            out["ok"].append(num)
        else:
            out["unknown"].append(num)
    return out


def scan_documents(root):
    """扫描全包 md，返回引用级问题清单。"""
    root = pathlib.Path(root)
    issues = {"ambiguous": [], "dangling": [], "needs_prefix": [], "unknown": []}
    books = scan_books(root)
    coll = find_collisions(books)
    flat = {}
    for ns, vols in books.items():
        for num in vols:
            flat.setdefault(num, []).append(ns)
    for p in sorted(root.rglob("*.md")):
        if ".bak" in p.name or "__pycache__" in p.parts:
            continue
        rel = str(p.relative_to(root))
        ns_here = namespace_of(p, root)
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            prefixed, bare = extract_refs(line)
            for ns, num in prefixed:
                if num not in books.get(ns, {}):
                    issues["dangling"].append({"file": rel, "line": i,
                                              "ref": f"{ns}{num}"})
            for num in bare:
                loc = {"file": rel, "line": i, "ref": f"`{num}`"}
                if num in coll:
                    issues["ambiguous"].append(loc)
                elif num >= 95 and num in flat:
                    # 95+ 一律带前缀（TR108 定案）
                    issues["ambiguous"].append({**loc, "reason": "95+未带命名空间前缀"})
                elif num not in flat:
                    issues["unknown"].append(loc)
    return issues, books, coll


def scan_mounts(root):
    """成员引用了某命名空间的册页，skills 必须挂载对应技能。"""
    root = pathlib.Path(root)
    books = scan_books(root)
    flat = {}
    for ns, vols in books.items():
        for num in vols:
            flat.setdefault(num, []).append(ns)
    gaps, mounts = [], {}
    for p in sorted((root / "agents").glob("*.md")):
        if ".bak" in p.name:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_SKILLS.search(text)
        declared = [s.strip() for s in m.group(1).split(",")] if m else []
        have = {NS_OF_SKILL[s] for s in declared if s in NS_OF_SKILL}
        mounts[p.name] = sorted(have)
        need = set()
        for ns, num in PREFIX_REF_RE.findall(text):
            need.add(ns)
        _, bare = extract_refs(text)
        for num in bare:
            if num >= 95:
                for ns in flat.get(num, []):
                    need.add(ns)
            else:
                # 1–94 默认属 KB；不得把 KB 的 `1`–`6` 误算成 AR/RI 的自编号
                need.add("KB")
        for ns in sorted(need - have):
            gaps.append({"agent": p.name, "missing_ns": ns,
                         "skill": SKILL_OF_NS[ns]})
    return gaps, mounts


def report(root, strict=False):
    issues, books, coll = scan_documents(root)
    gaps, mounts = scan_mounts(root)
    unreg = unregistered_collisions(coll)
    local = scan_books(root, namespaces=LOCAL_NS)
    hard = len(issues["ambiguous"]) + len(issues["dangling"]) + len(gaps) + len(unreg)
    lines = [
        "== 全库册号命名空间闸门（TR108） ==",
        "册页：%s，合计 %d 份" % (
            " / ".join("%s:%d" % (n, len(v)) for n, v in sorted(books.items())),
            sum(len(v) for v in books.values())),
        "技能内部自编号（不参与全库撞号）：%s" % (
            " / ".join("%s:%d" % (n, len(v)) for n, v in sorted(local.items())) or "无"),
        "撞号：%s" % (", ".join("%d→%s" % (n, "+".join(v))
                              for n, v in sorted(coll.items())) or "无"),
        "  已裁决：%s" % (", ".join(map(str, sorted(COLLISION_POLICY))) or "无"),
        "  未登记（硬错误）：%s" % (", ".join(map(str, sorted(unreg))) or "无"),
        "歧义/缺前缀引用：%d" % len(issues["ambiguous"]),
        "悬空带前缀引用：%d" % len(issues["dangling"]),
        "成员技能挂载缺漏：%d" % len(gaps),
        "非册号数字（忽略）：%d" % len(issues["unknown"]),
    ]
    for key in ("ambiguous", "dangling"):
        for x in issues[key][:12]:
            lines.append("  [%s] %s:%d %s %s" % (
                key, x["file"], x["line"], x["ref"], x.get("reason", "")))
        if len(issues[key]) > 12:
            lines.append("  ... 另有 %d 处" % (len(issues[key]) - 12))
    for g in gaps[:12]:
        lines.append("  [mount] %s 缺 %s（%s）" % (
            g["agent"], g["missing_ns"], g["skill"]))
    lines.append("结论：%s（硬错误 %d）" % ("FAIL" if hard else "PASS", hard))
    print("\n".join(lines))
    data = {"books": {n: {str(k): v for k, v in d.items()}
                      for n, d in books.items()},
            "collisions": {str(k): v for k, v in coll.items()},
            "collision_policy": {str(k): v for k, v in COLLISION_POLICY.items()},
            "issues": issues, "mounts": mounts, "mount_gaps": gaps,
            "hard_errors": hard, "verdict": "FAIL" if hard else "PASS"}
    return data


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  FAIL: " + name)

    books = {"KB": {94: "94-a.md", 95: "95-格局.md"},
             "OB": {95: "95-核验.md", 96: "96-口径.md"},
             "TR": {100: "100-训练.md", 108: "108-命名空间.md"}}
    chk("扫描识别命名空间", set(books) == {"KB", "OB", "TR"})
    coll = find_collisions(books)
    chk("检出 KB95/OB95 撞号", coll == {95: ["KB", "OB"]})
    chk("未登记撞号判硬错误", unregistered_collisions(coll, {}) == coll)
    chk("已登记撞号豁免", unregistered_collisions(coll, {95: {}}) == {})

    pf, bare = extract_refs("见 `OB95` §5 与 `TR108`、`96`、`100`、`999`")
    chk("带前缀引用解析", ("OB", 95) in pf and ("TR", 108) in pf)
    chk("带前缀不重复计为裸号", 95 not in bare and 108 not in bare)
    chk("裸号保留", 96 in bare and 100 in bare and 999 in bare)

    r = classify_refs(books, coll, [95, 96, 100, 999])
    chk("撞号裸号判歧义", r["ambiguous"] == [95])
    chk("唯一归属裸号可解析", r["ok"] == [96, 100])
    chk("非册号数字归入 unknown", r["unknown"] == [999])

    # 真实专家包：撞号须已登记，且不得存在未裁决的新撞号
    real_books = scan_books(PLUGIN)
    real_coll = find_collisions(real_books)
    chk("真实包识别到 KB/OB/TR 三个全局命名空间", set(real_books) == set(GLOBAL_NS))
    chk("技能内部自编号不参与撞号", "AR" in scan_books(PLUGIN, namespaces=LOCAL_NS))
    # 这里原来写死 {95,96,97,98}：**每登记一个新撞号，测试就红一次**，
    # 逼人去改测试——改着改着就把它改成「当前实况」，于是这条断言什么也没守住。
    # 现在改成与裁决表对齐：实况撞号必须恰好等于已登记的那几个，
    # 多一个（未登记）判红，少一个（登记了却没撞）也判红。
    chk("真实包撞号全部已裁决", set(real_coll) == set(COLLISION_POLICY)
        and not unregistered_collisions(real_coll))
    chk("裁决表里没有空悬挂（登记了却不存在该撞号）",
        set(COLLISION_POLICY) <= set(real_coll))
    chk("TR108 已登记", 108 in real_books.get("TR", {}))
    chk("KB95 与 OB95 并存", 95 in real_books.get("KB", {})
        and 95 in real_books.get("OB", {}))

    print("SELFTEST %d/%d %s" % (ok, ok + fail, "PASS" if not fail else "FAIL"))
    return 0 if not fail else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(PLUGIN))
    ap.add_argument("--out")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    data = report(a.root, a.strict)
    if a.out:
        pathlib.Path(a.out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if (a.strict and data["hard_errors"]) else 0


if __name__ == "__main__":
    sys.exit(main())
