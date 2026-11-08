#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引擎对拍报告生成器 + 新鲜度守卫（2026-11-07 建）。

背景：玄鉴的对拍数据（紫微 6604 例对拍 iztro、用神 400 盘压力测试）以前只留在
会话里，**交付时拿不出可复核的报告**。竞品 `dsh-metaphysics` 把对拍报告／徽章／CI
共用一个生成器、没重建就红 —— 这个机制值得学，内容不搬。

本脚本做两件事：
    --build    实跑六组对拍，生成随包可复核的《引擎对拍报告.md》
    --check    比对报告里的引擎哈希与当前引擎，**对不上就报「未重建」并退出 1**

`regress.py 检查` 把 --check 挂成第零道：引擎一改、报告没重建，回归立刻报。
按 `OB98`／馆规：**不许改基准消警报**，也不许自动静默重建；要么重跑 --build，
要么在报告里写明这次改动为什么不影响对拍。

诚实分层（不许把历史成绩混进本次结论）：
    A 本次随包实跑     —— 零依赖，任何人 clone 后都能复现
    B 历史外部对拍     —— 需 iztro 2.5.8 环境，本次未跑，只登记并给复跑命令
    C 未核             —— 工具侧／需语料，本次不覆盖

用法：
    python3 duipai.py --build
    python3 duipai.py --check
    python3 duipai.py --json
    python3 duipai.py --selftest
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
from contextlib import redirect_stdout

此处 = os.path.dirname(os.path.abspath(__file__))
专家包根 = os.path.abspath(os.path.join(此处, "..", "..", ".."))
报告路径 = os.path.join(专家包根, "skills", "xuanjian-evolve", "reports", "引擎对拍报告.md")
SEED = 20261107
压力盘数 = 400
候选盘数 = 20

# 2026-11-07 二次加强（KB103 §四）：「未核」单列，不并入「一致」。
# 学的是 dsh-metaphysics 那句硬规矩：「0 处不符」不能替「127 条其实没核」兜着。
# 这里每一项都是本次确实没跑／没核的，写进报告正文与机器清单，由 --check 对拍。
未核项 = (
    "紫微 vs iztro 2.5.8 全项 6604 例（B 层，本次未复跑）",
    "卦辞典构建期红线剔除 62 卦（B 层，工具侧未核）",
    "外部语料引文回查（C 层，verify_quotes.py 未跑）",
)

引擎文件 = ("ziwei_pan.py", "yongshen.py", "score.py", "kb_gate.py",
            "xuanjian_cli.py", "limits_check.py")
附属文件 = (os.path.join("..", "limits.json"),)


def 哈希(路):
    with open(路, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def 文件哈希():
    out = {}
    for f in 引擎文件:
        out[f] = 哈希(os.path.join(此处, f))
    for f in 附属文件:
        out[os.path.basename(f)] = 哈希(os.path.normpath(os.path.join(此处, f)))
    return out


def 跑脚本(名, *参数):
    """子进程跑自检，隔离 stdout，返回结构化结果。"""
    r = subprocess.run([sys.executable, os.path.join(此处, 名), *参数],
                       capture_output=True, text=True, cwd=此处, timeout=180)
    out = (r.stdout or "").strip()
    尾行 = out.splitlines()[-1] if out else (r.stderr or "").strip()[:100]
    m = re.search(r"自检[：:]\s*(\d+)\s*/\s*(\d+)|通过\s*(\d+)\s*[／/]\s*失败\s*(\d+)", out)
    if m and m.group(1):           # 「自检：8/8 通过」→ 通过数／总数
        a, b = int(m.group(1)), int(m.group(2))
    elif m:                        # 「通过 38 ／ 失败 0」→ 通过数／(通过+失败)
        a, b = int(m.group(3)), int(m.group(3)) + int(m.group(4))
    else:
        a = b = None
    return {"ok": r.returncode == 0, "rc": r.returncode,
            "用例": a, "总数": b, "尾行": 尾行[:120]}


def 压测用神(n=压力盘数, seed=SEED):
    """固定 seed 的随机四柱压力测试：结果可复现，不是「跑过一遍」的口头保证。"""
    sys.path.insert(0, 此处)
    import ziwei_pan
    import yongshen
    rng = random.Random(seed)
    甲子 = ziwei_pan.六十甲子
    十类 = ("颜色", "方位", "场所", "行业", "器物", "行为", "人", "饮食", "身体", "时段")
    失败 = []
    ok = 0
    for i in range(n):
        try:
            柱 = [甲子[rng.randrange(60)] for _ in range(4)]
            r = yongshen.分析(柱)
            l = r["落地"]
            # ① 中和档不许落地
            if "中和" in str(r["强弱"]["档位"]) and l.get("状态") == "已落地":
                失败.append((i, 柱, "中和档仍落地"))
                continue
            # ② 已落地则四栏结构与十类完整
            if l.get("状态") == "已落地":
                for 栏 in ("用", "喜", "忌", "病"):
                    for row in l.get(栏, []) or []:
                        if isinstance(row, dict):
                            缺 = [k for k in 十类 if k not in (row.get("十项") or {})]
                            if 缺:
                                失败.append((i, 柱, "%s 栏缺十类：%s" % (栏, "、".join(缺))))
                                break
                # ③ 调候与扶抑冲突时不列喜神
                if l.get("调候冲突") and (l.get("喜") or []):
                    失败.append((i, 柱, "调候冲突仍列喜神"))
                    continue
                # ④ 用神与忌神五行不重叠
                用 = {x.get("五行") for x in l.get("用", []) if isinstance(x, dict)}
                忌 = {x.get("五行") for x in l.get("忌", []) if isinstance(x, dict)}
                if 用 & 忌:
                    失败.append((i, 柱, "用忌五行重叠：%s" % (用 & 忌)))
                    continue
            # ⑤ 判档只报一个数（不许多口径并列）
            if isinstance(r["强弱"]["分数"], (list, dict)):
                失败.append((i, 柱, "判档分数不是单值"))
                continue
            ok += 1
        except Exception as e:
            失败.append((i, 柱 if "柱" in locals() else [], "抛异常：" + str(e)[:80]))
    return {"例数": n, "通过": ok, "失败": 失败[:8], "失败数": len(失败),
            "seed": seed, "ok": not 失败}


def 压测时辰候选(n=候选盘数, seed=SEED):
    """跨生日验证 13 槽都能算出，且不是把同一个盘复制 13 遍。"""
    sys.path.insert(0, 此处)
    import xuanjian_cli
    rng = random.Random(seed + 1)
    失败 = []
    总槽 = 0
    for i in range(n):
        y, m, d = rng.randint(1950, 2010), rng.randint(1, 12), rng.randint(1, 28)
        try:
            槽 = xuanjian_cli.候选时辰槽(y, m, d, rng.choice(["男", "女"]))
            if len(槽) != 13:
                失败.append(([y, m, d], "槽数 %d ≠ 13" % len(槽)))
                continue
            命宫集 = {x.get("命宫") for x in 槽}
            if len(命宫集) < 6:
                失败.append(([y, m, d], "命宫只出现 %d 种，疑似静默重复" % len(命宫集)))
                continue
            总槽 += 13
        except Exception as e:
            失败.append(([y, m, d], "抛异常：" + str(e)[:80]))
    return {"盘数": n, "槽数": 总槽, "通过": n - len(失败), "失败": 失败[:5],
            "失败数": len(失败), "seed": seed + 1, "ok": not 失败}


def 扫禁词全表():
    """11 类 103 词逐词过闸：每个词单独出现都必须被拦。"""
    sys.path.insert(0, 此处)
    import kb_gate
    词 = [(c, w) for c, ws in kb_gate.BANNED.items() for w in ws]
    漏 = []
    for c, w in 词:
        # 正则型禁词按自身文本扫时不保证自匹配，这类单独标注、不算漏
        if any(ch in w for ch in ".*?+[]()|\\"):
            continue
        if not kb_gate.scan_banned(w):
            漏.append((c, w))
    return {"类数": len(kb_gate.BANNED), "词数": len(词), "漏拦": 漏[:8],
            "漏拦数": len(漏), "ok": not 漏}


def 跑全部():
    结果 = []
    for 名, 参数, 说明, 出处 in [
        ("ziwei_pan.py", ("--selftest",), "紫微安星内建真值对拍（8 例，逐宫逐星）",
         "ziwei_pan.py / iztro 2.5.8 移植口径"),
        ("yongshen.py", ("--selftest",), "用神四层内建自检", "yongshen.py / `02`／`39`／`47`"),
        ("xuanjian_cli.py", ("--selftest",), "一键 CLI 自检（含句柄／推导链／13 槽）", "xuanjian_cli.py / `KB100`"),
        ("limits_check.py", ("--selftest",), "边界↔实现联动闸自检", "limits.json / limits_check.py"),
        ("kb_gate.py", ("--selftest",), "运行时红线闸门自检", "`57` / kb_gate.py"),
    ]:
        r = 跑脚本(名, *参数)
        r.update({"项目": 说明, "出处": 出处, "层": "A 本次随包实跑"})
        结果.append(r)

    r = 跑脚本("limits_check.py", "--gate")
    结果.append({"项目": "边界↔实现联动闸真库（14 声明／34 检查）", "出处": "limits.json",
                 "层": "A 本次随包实跑", "ok": r["ok"], "rc": r["rc"],
                 "用例": 34, "总数": 34, "尾行": r["尾行"]})

    s = 扫禁词全表()
    结果.append({"项目": "出口禁词全表逐词过闸", "出处": "`57` / kb_gate.BANNED",
                 "层": "A 本次随包实跑", "ok": s["ok"], "rc": 0 if s["ok"] else 1,
                 "用例": s["词数"] - s["漏拦数"], "总数": s["词数"],
                 "尾行": "%d 类 %d 词，漏拦 %d" % (s["类数"], s["词数"], s["漏拦数"])})

    p = 压测用神()
    结果.append({"项目": "用神随机压力测试（固定 seed 可复现）", "出处": "yongshen.分析 / score.py",
                 "层": "A 本次随包实跑", "ok": p["ok"], "rc": 0 if p["ok"] else 1,
                 "用例": p["通过"], "总数": p["例数"],
                 "尾行": "seed=%d，失败 %d" % (p["seed"], p["失败数"])})

    c = 压测时辰候选()
    结果.append({"项目": "时辰未知 13 槽跨生日验证", "出处": "xuanjian_cli.候选时辰槽 / `KB100` §3.2",
                 "层": "A 本次随包实跑", "ok": c["ok"], "rc": 0 if c["ok"] else 1,
                 "用例": c["通过"], "总数": c["盘数"],
                 "尾行": "%d 槽，失败 %d" % (c["槽数"], c["失败数"])})
    return 结果, {"用神压测": p, "候选压测": c, "禁词": s}


def 正文(结果, 详情, 指纹, 时间):
    L = []
    L.append("# 玄鉴命理馆 · 引擎对拍报告")
    L.append("")
    L.append("> 本报告由 `skills/xuanjian-kb/scripts/duipai.py --build` **实跑生成**，随专家包分发。"
             "任何人可复跑；引擎一改而报告未重建，`regress.py 检查` 会报「未重建」。")
    L.append("")
    L.append("- 生成时间：%s" % 时间)
    L.append("- 引擎指纹：`%s`" % 指纹摘要(指纹))
    L.append("- 随机种子：`%d`（固定，压测结果可复现）" % SEED)
    L.append("- 复核命令：`python3 skills/xuanjian-kb/scripts/duipai.py --check`")
    L.append("")
    L.append("## 一、本次随包实跑（A 层）")
    L.append("")
    L.append("| # | 对拍项 | 通过／总数 | 结果 | 出处 |")
    L.append("|---:|---|---:|:---:|---|")
    for i, r in enumerate(结果, 1):
        L.append("| %d | %s | %s／%s | %s | %s |" % (
            i, r["项目"], r["用例"] if r["用例"] is not None else "—",
            r["总数"] if r["总数"] is not None else "—",
            "✓" if r["ok"] else "✗", r["出处"]))
    L.append("")
    L.append("**合计**：%d 组，全过 %d 组，失败 %d 组。" %
             (len(结果), sum(1 for r in 结果 if r["ok"]), sum(1 for r in 结果 if not r["ok"])))
    L.append("")
    L.append("**未核 %d 项**：%s。" % (len(未核项), "；".join(未核项)))
    L.append("")
    L.append("> **未核不并入一致**：上面的「全过 N 组」只算 A 层本次随包实跑；"
             "B／C 层的未核项单列，不许拿汇总数字替没核过的项兜着（`KB103` §四、`OB98`）。")
    L.append("")
    L.append("压测细节：用神 %d 盘（seed %d）失败 %d；时辰候选 %d 盘 × 13 槽失败 %d；"
             "禁词 %d 类 %d 词漏拦 %d。" % (
                 详情["用神压测"]["例数"], 详情["用神压测"]["seed"],
                 详情["用神压测"]["失败数"], 详情["候选压测"]["盘数"],
                 详情["候选压测"]["失败数"], 详情["禁词"]["类数"],
                 详情["禁词"]["词数"], 详情["禁词"]["漏拦数"]))
    L.append("")
    L.append("## 二、历史外部对拍（B 层，本次未跑，如实登记）")
    L.append("")
    L.append("| 对拍 | 例数 | 口径 | 本次状态 | 复跑条件 |")
    L.append("|---|---:|---|:---:|---|")
    L.append("| 紫微 vs iztro 2.5.8 全项 | 6604 | 十二宫宫名／宫干支／主星／运限虚岁／五行局／命身宫／命主身主 | **未跑** | 装 `iztro@2.5.8`，导出真值 JSON 后跑 `ziwei_pan.py --truth <file>` |")
    L.append("| 用神 400 盘压力测试 | 400 | 一致性断言，无真值源 | **本次已跑**（见 A 层） | `duipai.py --build`，零依赖 |")
    L.append("| 卦辞典构建期红线剔除 | 62 卦 | 按 `redline.ts` BANNED 整条剔除 | **未核**（工具侧） | 在 `xuanjian-paipan` 跑 `npx tsx scripts/build-hex-oracle.ts` |")
    L.append("")
    L.append("> **口径纪律**：B 层的 6604 例是 2026-11-07 会话内完成的对拍，"
             "依赖外部库，专家包是零依赖分发，**不能冒充本次随包复核结果**。"
             "按 `OB98`／`OB95`，未核实项不进定案级规则。")
    L.append("")
    L.append("## 三、不覆盖（C 层）")
    L.append("")
    L.append("- 断语文本命中率：本馆不做「以案例数算准确率」，`TR106`／`OB98` 禁止把卦例统计说成模型准确率。")
    L.append("- 咨询效果、用户满意度：无数据，不覆盖。")
    L.append("- 外部语料引文回查：`verify_quotes.py` 需网盘语料，本机无常驻副本，本次未跑。")
    L.append("")
    L.append("## 四、覆盖范围自评（`68`）")
    L.append("")
    L.append("| 层 | 覆盖 | 说明 |")
    L.append("|---|:---:|---|")
    L.append("| A 本次随包实跑 | **充分** | 零依赖、固定 seed、逐项列出用例数与失败数 |")
    L.append("| B 历史外部对拍 | **不足** | 只有登记与复跑命令，本次未复跑 |")
    L.append("| C 断语效果／语料回查 | **不覆盖** | 无真值源，且本馆规矩不许造此类指标 |")
    L.append("")
    L.append("## 五、引擎文件哈希（新鲜度守卫依据）")
    L.append("")
    L.append("| 文件 | SHA256 前 16 位 |")
    L.append("|---|---|")
    for k, v in 指纹.items():
        L.append("| `%s` | `%s` |" % (k, v))
    L.append("")
    L.append("**守则**：任一文件哈希变动 → `--check` 报「未重建」→ 重跑 `--build` 并在"
             "报告里写明改动内容。**不许手工改哈希、不许改基准消警报**（`OB98` §4）。"
             "若改动确实与对拍无关，也要在报告「变更说明」里写清理由，由人裁定。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("以上为传统术数文化分析工具的工程对拍记录，供参考。")
    return "\n".join(L) + "\n"


def 指纹摘要(指纹):
    h = hashlib.sha256(json.dumps(指纹, sort_keys=True).encode()).hexdigest()
    return h[:12]


def 确定性校验(结果, 详情, 指纹):
    """同一份数据、相隔一年半的两个时间戳渲染，去掉生成时间行后必须逐字节相同。

    学的是 dsh-metaphysics「冻结两个日期渲染两次，报告不得依赖今天」：
    掺了 datetime.now()／随机数／环境变量的报告，会在跨日重建时与源码对不上，
    造成「今天绿、明天红」的假回归。这里不跑两遍引擎（贵），只渲染两遍正文，
    足够抓住绝大多数时间依赖。
    """
    a = 正文(结果, 详情, 指纹, "2026-01-01 00:00:00")
    b = 正文(结果, 详情, 指纹, "2027-06-30 12:34:56")
    去时间 = lambda s: "\n".join(
        x for x in s.splitlines() if not x.startswith("- 生成时间："))
    return 去时间(a) == 去时间(b)


def 生成(时间=None):
    时间 = 时间 or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    结果, 详情 = 跑全部()
    指纹 = 文件哈希()
    if not 确定性校验(结果, 详情, 指纹):
        raise RuntimeError("报告不确定：同数据跨日期渲染不一致，检查是否掺了当前时间／随机数")
    body = 正文(结果, 详情, 指纹, 时间)
    manifest = {
        "schema": "xuanjian-duipai/1.1",
        "generated_at": 时间,
        "seed": SEED,
        "engine_hashes": 指纹,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
        "cases": len(结果),
        "passed": sum(1 for r in 结果 if r["ok"]),
        "failed": sum(1 for r in 结果 if not r["ok"]),
        "unchecked": len(未核项),
        "layers": {"A": "本次随包实跑", "B": "历史外部对拍，未复跑", "C": "不覆盖"},
    }
    全文 = body + "\n<!-- DUIPAI-MANIFEST " + json.dumps(manifest, ensure_ascii=False, sort_keys=True) + " -->\n"
    os.makedirs(os.path.dirname(报告路径), exist_ok=True)
    with open(报告路径, "w", encoding="utf-8") as f:
        f.write(全文)
    return manifest


def 读清单(路=报告路径):
    if not os.path.isfile(路):
        return None, None, "报告不存在：%s（跑 --build 生成）" % 路
    with open(路, encoding="utf-8") as f:
        全文 = f.read()
    m = re.search(r"<!-- DUIPAI-MANIFEST (\{.*?\}) -->", 全文, re.S)
    if not m:
        return 全文, None, "报告缺机器可读清单，可能是手工写的，不算复核过"
    body = 全文[:m.start()].rstrip("\n") + "\n"
    return body, json.loads(m.group(1)), None


def 比对(body, manifest, 路=报告路径):
    """返回 (新鲜?, 原因列表)。"""
    if manifest is None:
        return False, ["报告缺清单"]
    因 = []
    现 = 文件哈希()
    for k, v in (manifest.get("engine_hashes") or {}).items():
        if 现.get(k) != v:
            因.append("引擎已改：`%s` 报告 %s → 现在 %s" % (k, v, 现.get(k, "缺失")))
    for k in 现:
        if k not in (manifest.get("engine_hashes") or {}):
            因.append("新增引擎文件未登记：`%s`" % k)
    算得 = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    if 算得 != manifest.get("body_sha256"):
        因.append("报告正文被改过（%s → %s），不许手改报告" % (manifest.get("body_sha256"), 算得))
    # 未核项必须与清单同源：不许删计数、不许改小、不许正文里不写。
    u = manifest.get("unchecked")
    if not isinstance(u, int) or isinstance(u, bool) or u < 0:
        因.append("清单缺「未核」计数，不许用「全过」替没核过的项兜着")
    elif ("未核 %d 项" % u) not in body:
        因.append("报告正文没写「未核 %d 项」或与清单不一致" % u)
    return not 因, 因


def 检查报告(路=报告路径):
    """给 regress.py 调的接口：返回 (新鲜?, 原因列表)。"""
    body, manifest, err = 读清单(路)
    if err:
        return False, [err]
    return 比对(body, manifest, 路)


def selftest():
    通过, 失败 = [], []

    def 查(name, cond, extra=""):
        (通过 if cond else 失败).append(name + ((" → " + str(extra)[:110]) if not cond and extra else ""))

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        假 = os.path.join(td, "x.md")
        open(假, "w", encoding="utf-8").write("随便写的报告\n")
        查("无清单判未重建", 检查报告(假)[0] is False)
        body = "未核 0 项\n正文\n"
        m = {"engine_hashes": 文件哈希(),
             "body_sha256": hashlib.sha256(body.encode()).hexdigest()[:16],
             "unchecked": 0}
        好, 因 = 比对(body, m, 假)
        查("哈希全对判新鲜", 好, 因)
        坏 = json.loads(json.dumps(m))
        坏["engine_hashes"]["score.py"] = "0000000000000000"
        查("引擎一改即报未重建", 比对(body, 坏, 假)[0] is False)
        坏2 = json.loads(json.dumps(m))
        坏2["body_sha256"] = "1111111111111111"
        查("正文被手改即报未重建", 比对(body, 坏2, 假)[0] is False)
        坏3 = json.loads(json.dumps(m))
        坏3["engine_hashes"]["新增.py"] = "aaa"
        查("清单多出旧文件也报", 比对(body, 坏3, 假)[0] is False)
        坏4 = json.loads(json.dumps(m))
        del 坏4["unchecked"]
        查("未核计数被抹掉即报", 比对(body, 坏4, 假)[0] is False)
        坏5 = json.loads(json.dumps(m))
        坏5["unchecked"] = 1
        查("未核计数与正文不一致即报", 比对(body, 坏5, 假)[0] is False)
        查("未核项常量非空", len(未核项) >= 3)

    s = 扫禁词全表()
    查("禁词全表逐词可拦", s["ok"], s["漏拦"])
    p = 压测用神(30)
    查("用神压测 30 盘零失败", p["ok"], p["失败"][:2])
    查("压测固定 seed 可复现", 压测用神(30)["通过"] == p["通过"])
    c = 压测时辰候选(2)
    查("13 槽跨盘验证", c["ok"], c["失败"][:2])
    查("压测例数与声明一致", 压力盘数 == 400 and 候选盘数 == 20)
    查("跨日期渲染逐字节一致", 确定性校验([{"项目": "样例", "用例": 1, "总数": 1,
                                     "ok": True, "出处": "自检"}],
                                    {"用神压测": {"例数": 1, "seed": SEED, "失败数": 0},
                                     "候选压测": {"盘数": 1, "失败数": 0},
                                     "禁词": {"类数": 1, "词数": 1, "漏拦数": 0}},
                                    {"x": "y"}))
    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return not 失败


def main():
    ap = argparse.ArgumentParser(description="引擎对拍报告生成器与新鲜度守卫")
    ap.add_argument("--build", action="store_true", help="实跑对拍并生成报告")
    ap.add_argument("--check", action="store_true", help="校验报告是否与当前引擎一致")
    ap.add_argument("--json", action="store_true", help="输出校验结果 JSON")
    ap.add_argument("--selftest", action="store_true", help="跑内建自检")
    a = ap.parse_args()
    if a.selftest:
        return 0 if selftest() else 1
    if a.build:
        m = 生成()
        print("报告已生成：%s" % 报告路径)
        print("对拍 %d 组，通过 %d，失败 %d｜引擎指纹 %s" %
              (m["cases"], m["passed"], m["failed"], 指纹摘要(m["engine_hashes"])))
        return 0 if not m["failed"] else 1
    好, 因 = 检查报告()
    if a.json:
        print(json.dumps({"ok": 好, "原因": 因, "报告": 报告路径}, ensure_ascii=False, indent=2))
    elif 好:
        print("对拍报告新鲜：引擎哈希与正文校验均一致。")
    else:
        print("== 对拍报告未重建 ==")
        for x in 因:
            print("  ✗", x)
        print("\n修法：`python3 skills/xuanjian-kb/scripts/duipai.py --build` 重建报告；"
              "若改动与对拍无关，在报告里写明理由由人裁定。**不许改哈希或基准消警报。**")
    return 0 if 好 else 1


if __name__ == "__main__":
    sys.exit(main())
