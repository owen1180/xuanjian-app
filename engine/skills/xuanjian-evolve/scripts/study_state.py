#!/usr/bin/env python3
"""学习状态根 —— 台账、回归基准、进化日志、掌握度四件的统一入口。

用法（既可直接跑，也可被 ledger.py／evolve.py 导入）：
    python3 study_state.py 状态            报当前根、四件是否齐全
    python3 study_state.py 校验            四件缺失即非零退出
    python3 study_state.py 初始化          缺什么补空壳，不动已有文件
    python3 study_state.py 迁移 [源根] [--到 目标根]   把旧根的四件搬到目标根（带备份）
    python3 study_state.py --selftest

**为什么要有这个模块**：台账、回归基准、进化日志原先各自写死一个绝对路径
（`/Users/haoqing/WorkBuddy/2026-10-26-14-08-25/命理档案`）。换一个工作区跑，
`ledger.py 统计` 还能跑（它回退到旧路径），但新工作区里既没有台账也没有掌握度——
**学习进度绑死在某一个工作区上，换地方就等于从头开始**。这是学习能力最底层的一处漏。

解析顺序（先命中先用）：
  1. 环境变量 `玄鉴学习`（显式指定，最高优先）
  2. 环境变量 `命理档案`（旧脚本沿用的名字，兼容）
  3. 当前工作区（向上找含 `命理档案/方法论` 的目录）
  4. **最近改过的工作区**（`~/WorkBuddy/*/命理档案`，取「方法论」目录最新的那个）
  5. 旧默认路径（回退，保证老库仍可读）
  6. 都没有 → 用 `~/玄鉴学习状态` 兜底，不让脚本直接崩

**第 4 步是 v1.67.0 补的，补的是一处会静默写错地方的口子**：中文环境变量
`命理档案=<路径>` 在本机 shell 里根本传不进去（实测 `os.environ.get('命理档案')`
为 `None`），而第 3 步只在「当前目录在某个工作区之内」时成立。于是在专家包目录里
跑 `evolve 记录`，前三步全落空，直接掉到旧默认 `2026-10-26-…/命理档案`——
**在 A 工作区里干活，进度写进 B 工作区**，只留一行 stderr 提示，脚本照退 0。
现在第 4 步会把「最近改过的工作区」挑出来，并把「用的哪个根、为什么」讲清楚；
真的要用别的根，`玄鉴学习=<路径>` 一句话钉死。

**不做静默迁移**。核到旧根有、新根没有时，只提示「跑 `迁移`」，不在读操作里偷偷写盘。
"""
import json
import os
import shutil
import sys
import time

四件 = {
    "摄取台账.md": "读到哪一份、落到哪一册",
    "回归基准.json": "既有结论的基准快照",
    "进化日志.md": "每一轮改了什么",
    "掌握度.json": "每册的实际掌握与下次复习日",
}

旧默认 = "/Users/haoqing/WorkBuddy/2026-10-26-14-08-25/命理档案"
兜底 = os.path.expanduser("~/玄鉴学习状态")


def _向上找(start=None):
    这里 = os.path.abspath(start or os.getcwd())
    for _ in range(6):
        if os.path.isdir(os.path.join(这里, "命理档案", "方法论")):
            return os.path.join(这里, "命理档案")
        上 = os.path.dirname(这里)
        if 上 == 这里:
            break
        这里 = 上
    return None


def _工作区候选():
    """列出 `~/WorkBuddy/*/命理档案`，按「方法论」目录的修改时间倒序。

    挑最近改的那个，等于挑「人此刻正在用的工作区」——比写死某一天靠谱。
    但**同一台机上有多个工作区时，猜就是猜**，所以每次回落都要把选中的根说出来。
    """
    import glob
    们 = glob.glob(os.path.expanduser(os.path.join("~", "WorkBuddy", "*", "命理档案")))
    们 = [p for p in 们 if os.path.isdir(os.path.join(p, "方法论"))]
    return sorted(们, key=lambda p: -os.path.getmtime(os.path.join(p, "方法论")))


def 根说明():
    """返回 (根, 来源说明)。**用哪个根必须能回答**，不只返回一个字符串。"""
    for 名 in ("玄鉴学习", "命理档案"):
        v = os.environ.get(名)
        if v:
            return os.path.abspath(v), "环境变量 %s" % 名
    当前 = _向上找()
    if 当前:
        return 当前, "当前目录向上找到"
    候选 = _工作区候选()
    if 候选:
        return 候选[0], "最近改过的工作区（共 %d 处）" % len(候选)
    if os.path.isdir(旧默认):
        return 旧默认, "旧默认路径（回退）"
    return 兜底, "兜底目录"


def 状态根(创建=False):
    根, 源 = 根说明()
    if 源.startswith("最近改过") or 源.startswith("旧默认") or 源.startswith("兜底"):
        _提示回落(根, 源)
    return 根


_已提示 = [False]


def _提示回落(根, 源="回退"):
    """回落到「猜」出来的根时出一次声，并说清是怎么猜的。

    为什么要提示：v1.57.0 实测踩过——在专家包目录里跑 `evolve.py 记录`，
    向上找不到工作区，于是**静默写进了旧根**的进化日志，而人以为写的是当前工作区。
    「回落」本身不算错（旧库也是库），但**不许静默**。
    v1.67.0 补：提示里要带「依据」（最近改过的工作区／旧默认／兜底），
    因为「回落到 X」不带依据时，人没法判断该不该改成别处。
    """
    if _已提示[0]:
        return
    _已提示[0] = True
    import sys as _sys
    print("！ 未指定状态根，按「%s」取：%s\n"
          "  要钉死：set 玄鉴学习=<工作区>/命理档案（或旧名 命理档案=<...>）" % (源, 根),
          file=_sys.stderr)


def 文件(名):
    return os.path.join(状态根(), "方法论", 名)


def 四件现状(根=None):
    根 = 根 or 状态根()
    d = os.path.join(根, "方法论")
    出 = {}
    for 名 in 四件:
        p = os.path.join(d, 名)
        出[名] = {"path": p, "exists": os.path.isfile(p),
                  "bytes": os.path.getsize(p) if os.path.isfile(p) else 0}
    return 出


def 初始化(根=None, 静默=False):
    根 = 根 or 状态根()
    d = os.path.join(根, "方法论")
    os.makedirs(d, exist_ok=True)
    建 = []
    p = os.path.join(d, "摄取台账.md")
    if not os.path.exists(p):
        open(p, "w", encoding="utf-8").write(
            "# 摄取台账 —— 资料库读了多少、还差多少\n\n"
            "> 一行代表一份资料。**已摄取**＝读完并落到册页；**未摄取**＝下一轮要做的。\n"
            "> 登记：`python3 ledger.py 登记 <标题关键字> <落到哪一册>`\n\n"
            "| 资料标题 | 落到哪册 | 状态 | 日期 |\n|---|---|---|---|\n")
        建.append(p)
    p = os.path.join(d, "回归基准.json")
    if not os.path.exists(p):
        open(p, "w", encoding="utf-8").write(json.dumps(
            {"生成于": "", "档": [], "待补": [], "工具引擎": {}, "未回归": []},
            ensure_ascii=False, indent=2))
        建.append(p)
    p = os.path.join(d, "进化日志.md")
    if not os.path.exists(p):
        open(p, "w", encoding="utf-8").write(
            "# 进化日志 —— 每一轮改了什么、当时底子如何\n\n"
            "| 日期 | 专家包版本 | 摄取 | 校准 | 回归 | 两道闸 | 本轮摘要 |\n"
            "|---|---|---|---|---|---|---|\n")
        建.append(p)
    p = os.path.join(d, "掌握度.json")
    if not os.path.exists(p):
        open(p, "w", encoding="utf-8").write(json.dumps(
            {"artifact": "掌握度 —— 每册出题、判卷与下次复习日",
             "generated": "", "books": {}, "history": []},
            ensure_ascii=False, indent=2))
        建.append(p)
    if not 静默:
        print("状态根：%s" % 根)
        print("新建 %d 件：%s" % (len(建), "、".join(os.path.basename(x) for x in 建) or "无"))
    return 建


def 迁移(源=None, 目标=None, 覆盖=False):
    源 = os.path.abspath(源 or 旧默认)
    目标 = os.path.abspath(目标 or 状态根())
    if 源 == 目标:
        return {"ok": False, "reason": "源与目标是同一处：%s" % 源, "copied": []}
    源方法 = os.path.join(源, "方法论")
    if not os.path.isdir(源方法):
        return {"ok": False, "reason": "源根下没有 方法论 目录：%s" % 源, "copied": []}
    # 先搬后补空壳：若先初始化，目标里就有了空壳，搬家会误判「已存在」而全部保留，
    # 结果迁移「成功」但一个字也没搬过去（首轮就踩了这个）。
    os.makedirs(os.path.join(目标, "方法论"), exist_ok=True)
    目标方法 = os.path.join(目标, "方法论")
    搬, 保留, 拒绝 = [], [], []
    for 名 in 四件:
        s = os.path.join(源方法, 名)
        if not os.path.isfile(s):
            continue
        d = os.path.join(目标方法, 名)
        if os.path.exists(d) and not 覆盖:
            保留.append(名)
            continue
        # 这道闸是 2026-11-05 踩出来的：迁移时带了 --覆盖，把当前工作区里
        # 刚写进去的进度原样盖回旧库的版本——摄取台账 67 退回 65、
        # 进化日志丢了一整行。备份有，但「有备份」不等于「该覆盖」。
        # 目标文件比源**更新**，就说明它装着源里没有的新进展，一律拒覆盖。
        if 覆盖 and os.path.exists(d) and os.path.getmtime(d) > os.path.getmtime(s) + 1:
            拒绝.append(名)
            continue
        if os.path.exists(d):
            bak = "%s.bak-%s" % (d, time.strftime("%Y%m%d%H%M%S"))
            shutil.copy2(d, bak)
        shutil.copy2(s, d)
        搬.append(名)
    初始化(目标, 静默=True)   # 源里没有的那几件，补空壳
    return {"ok": True, "source": 源, "target": 目标, "copied": 搬, "kept": 保留,
            "refused_newer": 拒绝}


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    # **每次用唯一临时根**：原来写死 `/tmp/study-src` 这一类固定路径，
    # 上一次跑崩留下的残留、或两个进程同时跑，都会让断言时红时绿。
    # 「偶发红」比稳定红更坏——人会开始忽略这道自检（本轮实测撞到一次 1155/1156）。
    import tempfile
    基 = tempfile.mkdtemp(prefix="study-selftest-")

    def P(*a):
        return os.path.join(基, *a)

    旧 = os.environ.get("玄鉴学习")
    try:
        查("默认根非空", bool(状态根()))

        # ── 根解析：四层各测一遍，重点是「不许静默掉到旧默认」──
        os.makedirs(P("ws-x", "命理档案", "方法论"), exist_ok=True)
        查("向上找·深层子目录能找到", _向上找(P("ws-x", "某", "层", "子目录")) == P("ws-x", "命理档案"))
        查("向上找·找不到给 None", _向上找(P("study-nothing-here")) is None)

        候 = _工作区候选()
        查("候选·都是含方法论的根",
           all(os.path.isdir(os.path.join(x, "方法论")) for x in 候))
        if len(候) >= 2:
            查("候选·按方法论修改时间倒序",
               all(os.path.getmtime(os.path.join(a, "方法论"))
                   >= os.path.getmtime(os.path.join(b, "方法论"))
                   for a, b in zip(候, 候[1:])))
        # 这一条是本轮修的那个 bug：有工作区候选时要用候选，不许掉到写死的旧默认。
        # **不能拿真机上的候选来断言**——真机的候选里正好包含旧默认，条件会被跳过，
        # 测试看着绿其实一条没跑（本馆栽过的「测试是空的」）。所以把候选与向上找
        # 临时换成假的，四层优先级逐层钉死。
        原候, 原旧 = globals()["_工作区候选"], globals()["旧默认"]
        原上 = globals()["_向上找"]
        try:
            globals()["_向上找"] = lambda *a, **k: None
            globals()["_工作区候选"] = lambda: [P("ws-a", "命理档案"), P("ws-b", "命理档案")]
            globals()["旧默认"] = P("ws-old", "命理档案")
            根, 源 = 根说明()
            查("候选·有候选就用候选第一个", 根 == P("ws-a", "命理档案"))
            查("候选·来源标清楚", 源.startswith("最近改过的工作区"))
            查("候选·不走旧默认", 根 != P("ws-old", "命理档案"))

            globals()["_工作区候选"] = lambda: []
            os.makedirs(P("ws-old", "命理档案", "方法论"), exist_ok=True)
            根2, 源2 = 根说明()
            查("无候选·才回落到旧默认", 根2 == P("ws-old", "命理档案"))
            查("无候选·来源标成回退", 源2.startswith("旧默认路径"))

            globals()["旧默认"] = P("ws-none", "命理档案")
            根3, 源3 = 根说明()
            查("连旧默认都没有·走兜底", 根3 == 兜底)
            查("兜底·来源标清楚", 源3.startswith("兜底"))
        finally:
            globals()["_工作区候选"] = 原候
            globals()["_向上找"] = 原上
            globals()["旧默认"] = 原旧

        os.environ["玄鉴学习"] = P("study-self-check")
        查("环境变量优先", 状态根() == P("study-self-check"))
        查("根说明·标出环境变量", 根说明() == (P("study-self-check"), "环境变量 玄鉴学习"))
        shutil.rmtree(P("study-self-check"), ignore_errors=True)
        建 = 初始化(P("study-self-check"), 静默=True)
        查("初始化一次建四件", len(建) == 4)
        查("四件全部落地", all(v["exists"] for v in 四件现状().values()))
        再 = 初始化(P("study-self-check"), 静默=True)
        查("重复初始化不重建", 再 == [])
        # 迁移：造一个源根，目标已有台账时应保留不覆盖
        os.makedirs(P("study-src", "方法论"), exist_ok=True)
        open(P("study-src", "方法论", "摄取台账.md"), "w", encoding="utf-8").write(
            "| 资料 | 册 | 状态 | 日期 |\n|---|---|---|---|\n| 甲 | 96 | 已摄取 | 2026-11-05 |\n")
        os.makedirs(P("study-dst", "方法论"), exist_ok=True)
        open(P("study-dst", "方法论", "摄取台账.md"), "w", encoding="utf-8").write("# 已有\n")
        结 = 迁移(P("study-src"), P("study-dst"))
        查("迁移不覆盖已有", "摄取台账.md" in 结["kept"])
        结2 = 迁移(P("study-src"), P("study-dst"), 覆盖=True)
        查("覆盖时留备份", "摄取台账.md" in 结2["copied"])
        查("迁移后内容正确", "甲" in open(P("study-dst", "方法论", "摄取台账.md"), encoding="utf-8").read())
        # 防覆盖闸：目标比源新，说明它装着源里没有的新进展，一律拒。
        # 2026-11-05 真踩过：带 --覆盖 迁移，把当前工作区的 67 份进度盖回旧库 65 份，
        # 还丢了一整行进化日志。备份有，但「有备份」不等于「该覆盖」。
        os.makedirs(P("study-src2", "方法论"), exist_ok=True)
        os.makedirs(P("study-dst2", "方法论"), exist_ok=True)
        open(P("study-src2", "方法论", "摄取台账.md"), "w", encoding="utf-8").write("旧内容\n")
        open(P("study-dst2", "方法论", "摄取台账.md"), "w", encoding="utf-8").write("新内容\n")
        os.utime(P("study-src2", "方法论", "摄取台账.md"), (1_600_000_000, 1_600_000_000))
        结3 = 迁移(P("study-src2"), P("study-dst2"), 覆盖=True)
        查("目标更新时拒覆盖", 结3.get("refused_newer") == ["摄取台账.md"])
        查("拒覆盖后内容未变",
          open(P("study-dst2", "方法论", "摄取台账.md"), encoding="utf-8").read().strip() == "新内容")
        os.utime(P("study-src2", "方法论", "摄取台账.md"), (1_900_000_000, 1_900_000_000))
        结4 = 迁移(P("study-src2"), P("study-dst2"), 覆盖=True)
        查("源更新时允许覆盖", 结4.get("copied") == ["摄取台账.md"])
        查("同源同目标拒绝", 迁移(P("study-dst"), P("study-dst"))["ok"] is False)
        查("源缺方法论报错", 迁移(P("study-nope"), P("study-dst"))["ok"] is False)
    finally:
        if 旧 is None:
            os.environ.pop("玄鉴学习", None)
        else:
            os.environ["玄鉴学习"] = 旧
        shutil.rmtree(基, ignore_errors=True)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    参 = sys.argv[1:]
    if not 参:
        参 = ["状态"]
    if 参[0] == "--selftest":
        return 自检()
    if 参[0] == "状态":
        根 = 状态根()
        print("状态根：%s" % 根)
        现 = 四件现状()
        缺 = [k for k, v in 现.items() if not v["exists"]]
        for k, v in 现.items():
            print("  %-14s %s %s" % (k, "✓" if v["exists"] else "✗",
                                     "%d 字节" % v["bytes"] if v["exists"] else "（%s）" % 四件[k]))
        if 缺:
            print("缺 %d 件。补空壳：`python3 study_state.py 初始化`；"
                  "旧库有进度：`python3 study_state.py 迁移`" % len(缺))
        # 旧根有新根没有的，只提示不写盘
        旧 = 四件现状(旧默认)
        if 根 != 旧默认 and any(旧[k]["exists"] and not 现[k]["exists"] for k in 四件):
            print("提示：旧根 %s 仍有进度未搬过来，跑 `迁移` 可搬（带备份）。" % 旧默认)
        return 0
    if 参[0] == "校验":
        缺 = [k for k, v in 四件现状().items() if not v["exists"]]
        if 缺:
            print("学习状态不全：%s" % "、".join(缺))
            return 1
        print("学习状态四件齐全：%s" % 状态根())
        return 0
    if 参[0] == "初始化":
        初始化()
        return 0
    if 参[0] == "迁移":
        源, 到, 覆 = None, None, False
        i = 1
        while i < len(参):
            if 参[i] == "--到":
                到 = 参[i + 1]
                i += 2
            elif 参[i] == "--覆盖":
                覆 = True
                i += 1
            else:
                源 = 参[i]
                i += 1
        结 = 迁移(源, 到, 覆)
        if not 结["ok"]:
            print("✗ 迁移未执行：%s" % 结["reason"])
            return 1
        print("迁移：%s → %s" % (结["source"], 结["target"]))
        print("  搬过来：%s" % ("、".join(结["copied"]) or "无"))
        if 结["kept"]:
            print("  目标已存在、未覆盖：%s（要覆盖加 --覆盖 会先备份）" % "、".join(结["kept"]))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
