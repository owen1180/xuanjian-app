#!/usr/bin/env python3
"""进化编排器 —— 把「摄取 → 提炼 → 回测 → 同步 → 沉淀」五步串成一条可重复的流水线。

前三轮都是手工做的，每轮都要重新想一遍从哪开始、做完没有、有没有把旧结论改坏。
本脚本负责能自动的部分：报状态、排下一批、跑回测、跑两道同步闸、追写进化日志；
提炼仍然只能人来做——术数的内容判断不能交给脚本。

用法：
    python3 evolve.py            # 默认：出一份进化状态报告
    python3 evolve.py 下一批      # 列出该读的下十份，按优先级排
    python3 evolve.py 回测        # 校准集 + 在办档案两道回归
    python3 evolve.py 同步        # 知识库同步闸（kb:gate）+ 双向一致闸（sync:gate）
    python3 evolve.py 记录 <摘要>  # 把本轮追写进 命理档案/方法论/进化日志.md
    python3 evolve.py 沉淀        # 纯中文校验 + 两道闸 + 沉淀清单提示

优先级（数字小的先读）：
    1 主课笔记　2 实践课与作业　3 历年答疑　4 手面相　5 风水

**为什么同步要跑两道**（1.21.0 补）：
    kb:gate      单向——知识库改了，工具那边有没有漏做
    sync:gate    双向——工具版本、专家包版本、覆盖表、成员引用有没有分岔
只跑一道，工具加了一整层能力而专家团不知道的事就会重演（v1.3–v1.5 就是这么欠下的）。
"""
import os, subprocess, sys, datetime

此处 = os.path.dirname(os.path.abspath(__file__))
插件根 = os.path.join(此处, "..", "..", "..")
def _档案根():
    """与 ledger.py 同一处解析：环境变量 > 当前工作区 > 旧根 > 兜底。

    写死绝对路径的后果是「学习进度绑在一个工作区上」，换地方等于从头开始。
    """
    try:
        import study_state
        return study_state.状态根()
    except Exception:
        return os.environ.get("命理档案") or \
            "/Users/haoqing/WorkBuddy/2026-10-26-14-08-25/命理档案"


档案根 = _档案根()
校检 = os.path.join(此处, "..", "..", "xuanjian-archive", "scripts", "check_cn.py")
日志件 = os.path.join(档案根, "方法论", "进化日志.md")

# 排盘工具（另一侧的同一套知识）：知识库一改，它那边也要对拍，否则两边说法会分岔
工具目录 = os.environ.get("排盘工具") or \
    "/Users/haoqing/WorkBuddy/2026-10-30-13-17-15/xuanjian-paipan"


def 跑(命令, cwd=None):
    env = dict(os.environ)
    env["NODE_OPTIONS"] = ""      # 清空被注入的 --require shim，否则子进程会挂
    r = subprocess.run(命令, capture_output=True, text=True, cwd=cwd or 此处, env=env)
    return (r.stdout or "") + (r.stderr or ""), r.returncode


def 闸(名, 命令):
    """跑一道闸门。返回 (退出码, 报告文本)。工具不在返回 None。"""
    脚本 = os.path.join(工具目录, "scripts", 命令[1] if len(命令) > 1 else "")
    if not os.path.exists(脚本):
        return None, f"未找到排盘工具（{工具目录}），跳过"
    出, 码 = 跑(["npm", "run", 命令[0]], cwd=工具目录)
    return 码, 出


def 判闸(结果):
    """三态判定：全绿 / 有红 / 未跑。返回 (绿, 未跑)。

    **为什么不能写成 all(v == 0 for v in 结果.values() if v is not None)**（1.58.0 修）：
    空集合的 all() 恒为真——两条闸一条都没跑（排盘工具不在）时，它会报「全绿」，
    于是 `同步()` 退 0、`状态()` 打印「两道闸全绿」，而实际上什么都没验过。
    这与 1.56.0 那次台账 67→65 同型：**没跑被当成了通过**。
    纪律：绿必须由「跑过」证明，跑过 0 条不算证明。
    """
    跑过 = [v for v in 结果.values() if v is not None]
    绿 = bool(跑过) and all(v == 0 for v in 跑过)
    return 绿, len(跑过) == 0


def 两道闸(详=True):
    """知识库同步闸 + 双向一致闸。返回 (是否全绿, 报告, 各闸退出码)。"""
    报 = []
    结果 = {}
    for 名, 令 in [("知识库同步闸（kb:gate）", ["kb:gate"]),
                 ("双向一致闸（sync:gate）", ["sync:gate"])]:
        码, 出 = 闸(名, 令)
        结果[名] = 码
        if 码 is None:
            报.append(f"  － {名}：{出}")
        elif 码 == 0:
            报.append(f"  ✓ {名}：通过")
        else:
            报.append(f"  ✗ {名}：未通过（退出码 {码}）")
            if 详:
                尾 = [l for l in 出.strip().split("\n") if l.strip()][-12:]
                报 += ["      " + l for l in 尾]
    绿, 未跑 = 判闸(结果)
    if 未跑:
        报.append("  ！ 两条闸都未跑：这不是绿，是没验")
    return 绿, "\n".join(报), 结果


优先级 = [
    ("53课笔记", 1, "主课笔记"),
    ("实践课与作业", 2, "实践课与作业"),
    ("历年答疑", 3, "历年答疑"),
    ("手面相", 4, "手面相"),
    ("居家办公风水", 5, "居家办公风水"),
]


def 批(数量=10):
    import ledger
    树 = ledger.全树()
    已 = ledger.读台账()
    未 = []
    for n in 树:
        态, _ = ledger.判状态(n["题"], 已)
        if 态 == "未摄取":
            权 = 9
            for k, w, _名 in 优先级:
                if k in n["径"]:
                    权 = w
                    break
            未.append((权, n["径"], n["号"]))
    未.sort(key=lambda x: (x[0], x[1]))
    print(f"下一批该读的 {min(数量, len(未))} 份（共 {len(未)} 份未读）：\n")
    当 = None
    for 权, 径, 号 in 未[:数量]:
        名 = next((m for k, w, m in 优先级 if w == 权), "其他")
        if 名 != 当:
            当 = 名
            print(f"\n【{名}】")
        print(f"  {号}  {径}")
    print("\n下载：`dl.sh <编号> <文件名>`　读完登记：`ledger.py 登记 <标题关键字> <册号>`")
    return 0


def 回测():
    print("=== 第一道闸：七十三题校准集 ===")
    出, _ = 跑(["python3", "verify.py"], cwd=os.path.join(此处, "..", "..", "xuanjian-kb", "scripts"))
    print(出.strip()[-800:] if len(出) > 800 else 出)
    print("\n=== 第二道闸：在办档案回归（两道引擎）===")
    出, 码 = 跑(["python3", "regress.py", "检查"])
    print(出)
    return 码


def 同步():
    print("=== 排盘工具两道同步闸 ===")
    绿, 报, 结果 = 两道闸()
    print(报)
    未跑 = all(v is None for v in 结果.values())
    if 未跑:
        print(f"\n处置：排盘工具不在（{工具目录}），两道闸一条都没跑——**这不是绿**。"
              "装回工具或设环境变量 `排盘工具=<路径>` 再到工具目录跑两道闸。")
        return 3
    if not 绿:
        print("\n处置：到工具目录跑 `npm run kb:check` 与 `npm run sync:check` 看报告，"
              "处置完再 `node scripts/kb-sync.mjs --accept` 推基线。")
    return 0 if 绿 else 3


def 补配置():
    """settings.json 会被外部清掉（已发生三次），校验前先补回来。"""
    p = os.path.join(插件根, "settings.json")
    if os.path.exists(p):
        return False
    with open(p, "w", encoding="utf-8") as f:
        f.write('{\n  "agent": "xuanjian-mingli-team-lead"\n}\n')
    return True


def 版本():
    p = os.path.join(插件根, ".codebuddy-plugin", "plugin.json")
    try:
        import json
        return json.load(open(p, encoding="utf-8")).get("version", "?")
    except Exception:
        return "?"


def 数字(文, 式):
    import re
    m = re.search(式, 文 or "")
    return m.group(1) if m else "?"


def 定行(文, 今, 版本号, 行, 摘):
    """决定这一轮该追加新行还是并进当天已有的行。返回 (新文, 动作)。

    **1.58.0 修**：原实现用 `文[:文.rfind("|") + 1] + f"＋{摘} |"` —— 按
    **文件里最后一个竖线**定位，根本不看那是不是今天那行。1.56.0／1.57.0 两版
    就是这样被并成一条的：当天已有 1.56.0 那行，第二轮跑完把摘要接到了它尾巴上，
    事后只能人工拆行。现在的规矩：
      · 文里没有今天 → 追加新行
      · 今天最后一行版本相同 → 只并入**那一行**
      · 今天已有记录但版本不同 → 另起一行（同一天多轮，各记各的版本）
    """
    if not 文.endswith("\n"):
        文 += "\n"
    行们 = 文.split("\n")
    今天 = [i for i, l in enumerate(行们) if l.startswith(f"| {今} |")]
    if not 今天:
        return 文 + 行 + "\n", "追加新行"
    末 = 今天[-1]
    旧 = 行们[末]
    列 = [c.strip() for c in 旧.split("|")]
    if len(列) > 2 and 列[2] == 版本号:
        新 = 旧.rstrip()
        if 新.endswith("|"):
            新 = 新[:-1].rstrip()
        行们[末] = 新 + f"＋{摘} |"
        return "\n".join(行们), "并入当天同版本那一行"
    return 文 + 行 + "\n", "同日新版本另起一行"


def 记录():
    """把本轮追写进进化日志。

    凭什么要自动写：前几轮每轮做了什么，散在各处的工作区日志里，三个月后想查
    「打分基准是哪一轮改的」根本查不到。日志按轮次一行，脚本自动采集能采的
    （进度、精确率、漂移、两道闸、版本），只有「本轮做了什么」要人给一句摘要。
    """
    摘 = " ".join(sys.argv[2:]).strip() or "（未写摘要）"
    今 = str(datetime.date.today())

    import ledger
    树 = ledger.全树()
    已 = ledger.读台账()
    读 = sum(1 for n in 树 if ledger.判状态(n["题"], 已)[0] == "已摄取")

    校准, _ = 跑(["python3", "verify.py"], cwd=os.path.join(此处, "..", "..", "xuanjian-kb", "scripts"))
    精确 = 数字(校准, r"精确率（±0\.5 分）\s*([\d.]+)%")
    回归, 码 = 跑(["python3", "regress.py", "检查"])
    大 = 数字(回归, r"大漂移 (\d+) 处")
    中 = 数字(回归, r"中漂移 (\d+) 处")
    未归 = len([l for l in 回归.split("\n") if "[未回归]" in l])

    绿, 报, 结果 = 两道闸(详=False)
    闸记 = "／".join(f"{k.split('（')[0]}{'✓' if v == 0 else ('✗' if v is not None else '－')}"
                  for k, v in 结果.items()) or "（工具不在）"

    行 = (f"| {今} | {版本()} | {读}/{len(树)} | 精确 {精确}% | "
          f"大 {大}／中 {中}／未回归 {未归} | {闸记} | {摘} |")

    os.makedirs(os.path.dirname(日志件), exist_ok=True)
    if not os.path.exists(日志件):
        with open(日志件, "w", encoding="utf-8") as f:
            f.write("# 进化日志 —— 每一轮改了什么、当时底子如何\n\n"
                    "> 由 `python3 evolve.py 记录 <摘要>` 自动追写。前三轮是手工做的，"
                    "此后每轮留一行，供日后查「某个口径是哪一轮改的」。\n\n"
                    "| 日期 | 专家包版本 | 摄取 | 校准 | 回归（大／中／未回归） | 两道闸 | 本轮摘要 |\n"
                    "|---|---|---|---|---|---|---|\n")
    文 = open(日志件, encoding="utf-8").read()
    新文, 动作 = 定行(文, 今, 版本(), 行, 摘)
    with open(日志件, "w", encoding="utf-8") as f:
        f.write(新文)
    print(f"{动作} → {日志件}")
    print(f"\n{行}")
    return 0


def 沉淀():
    print("=== 配置文件自检 ===")
    print("  settings.json 缺失，已自动重建" if 补配置() else "  settings.json 在位")
    print("\n=== 纯中文校验 ===")
    出, 码 = 跑(["python3", 校检, os.path.join(插件根, "skills")])
    print(出.strip()[-1200:] if len(出) > 1200 else 出)
    print("\n=== 排盘工具两道同步闸 ===")
    绿, 报, _ = 两道闸()
    print(报)
    if not 绿:
        print("  处置：到工具目录跑 `npm run kb:check` 与 `npm run sync:check` 看报告，"
              "处置完再 `node scripts/kb-sync.mjs --accept` 推基线。")

    print("\n=== 运行时闸门两侧对拍（57 册）===")
    闸门 = os.path.join(插件根, "skills", "xuanjian-kb", "scripts", "kb_gate.py")
    出, 码 = 跑(["python3", 闸门, "对拍"])
    print(出.strip())
    if 码 != 0:
        绿 = False
        print("  处置：以 57 册 §3 禁词表与 §4 规则表为准，把差的那几条补进 kb_gate.py 再重跑。")

    print("\n=== 沉淀清单（人工逐项确认）===")
    for i, s in enumerate([
        "新规则是否编号并写入 命理档案/方法论/断法规则库.md",
        "本次用到的新读法是否写进对应册页并注明来源课次",
        "在办档案是否追写《分析记录.md》（日期、议题、结论增量、规则编号）",
        "档案卡片待验证表是否新增本次可验的项",
        "索引页的四项计数是否同步刷新",
        "专家包版本是否递增、settings.json 是否仍在",
        "新册页若在工具侧可编码，是否在 .kb-sync/coverage.json 登记（否则工具永远不跟）",
        "排盘工具是否同步（两道闸 + 测试全绿），版本与变更是否写进 MAC_BUILD.md",
        "是否跑 `python3 evolve.py 记录 <摘要>` 把本轮写进进化日志",
        "当日日志是否追加一行",
    ], 1):
        print(f"  {i}. {s}")
    return 0 if 绿 else 3


def 状态():
    print("=" * 46)
    print("进化状态报告")
    print("=" * 46)
    print("\n【一、摄取进度】")
    出, _ = 跑(["python3", "ledger.py", "统计"])
    print(出)
    print("【二、引擎校准】")
    出, _ = 跑(["python3", "verify.py"], cwd=os.path.join(此处, "..", "..", "xuanjian-kb", "scripts"))
    行 = [l for l in 出.strip().split("\n") if l.strip()]
    要 = [l for l in 行 if any(k in l for k in ("题数", "精确率", "接近率", "档位一致率", "平均绝对误差", "未低于", "低于基准"))]
    print("\n".join(要) if 要 else "（无输出）")
    print("\n【三、在办档案回归（两道引擎）】")
    出, 码 = 跑(["python3", "regress.py", "检查"])
    print(出.strip())
    print("\n【四、两侧同步】")
    绿, 报, 结果 = 两道闸(详=False)
    print(报)
    未跑 = all(v is None for v in 结果.values())
    print("\n【五、下一步】")
    if 码 != 0:
        print("  先处理漂移：确认是订正还是引擎回归错误，处理完跑 `regress.py 建立` 刷新基准。")
    elif 未跑:
        print("  排盘工具不在，两道闸一条都没跑（未跑 ≠ 绿）。先确认工具路径，再判两侧是否分岔。")
    elif not 绿:
        print("  先补两侧同步：工具与专家团口径已分岔，处置完再继续摄取。")
    else:
        print("  两道回归无漂移、两道闸全绿。下一步跑 `python3 evolve.py 下一批` 取新资料，"
              "读完 `ledger.py 登记`，收尾 `python3 evolve.py 记录 <摘要>`。")
    return 0


# ---------------------------------------------------------------- 自检
def 自检():
    """进化编排器自己的体检。

    为什么必须测它：它是「本轮做完了没有」的总开关，`状态` 与 `同步` 的结论
    直接决定下一轮从哪开始。它坏的方式都不响：报一句「全绿」就带过去了。
    1.58.0 实测就抓出两处——
      · 两道闸()：`all()` 对空序列恒真，工具不在时两条闸都没跑却报「全绿」；
      · 记录()：同一天追加摘要按 `rfind("|")` 定位，不看是不是今天那行，
        1.56.0／1.57.0 两版账被并成一条。
    这两条现在都成了用例，**改坏就该红**。
    """
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    # 一、判闸三态：绿必须由「跑过」证明
    查("判闸·两闸都 0 才算绿", 判闸({"a": 0, "b": 0}) == (True, False))
    查("判闸·有一道红即不绿", 判闸({"a": 0, "b": 1}) == (False, False))
    查("判闸·一红一未跑仍不绿", 判闸({"a": None, "b": 1}) == (False, False))
    查("判闸·一跑一未跑、跑的那道绿也算绿（不是全绿）",
       判闸({"a": None, "b": 0}) == (True, False))
    查("判闸·两闸都未跑：不绿且标未跑（原实现此处误报全绿）",
       判闸({"a": None, "b": None}) == (False, True))
    查("判闸·空表不绿", 判闸({}) == (False, True))
    查("判闸·退出码 2 这种非零也算红", 判闸({"a": 2}) == (False, False))

    # 二、取数字：取不到给「?」，不许静默变 0
    查("数字·取到", 数字("精确率（±0.5 分） 95.9%", r"精确率（±0\.5 分）\s*([\d.]+)%") == "95.9")
    查("数字·取不到给问号而不是 0",
       数字("没有这一行", r"大漂移 (\d+) 处") == "?")
    查("数字·空文不炸", 数字("", r"x") == "?" and 数字(None, r"x") == "?")

    # 三、定行：同一天两轮各记各的版本（1.56.0 事故的回归用例）
    头 = ("| 日期 | 专家包版本 | 摄取 | 校准 | 回归 | 两道闸 | 摘要 |\n"
          "|---|---|---|---|---|---|---|\n")
    甲 = "| 2026-11-05 | 1.56.0 | 67/172 | 精确 95.9% | 大 0／中 0／未回归 1 | 两闸✓ | 甲 |"

    文, 动作 = 定行(头, "2026-11-05", "1.56.0", 甲, "乙")
    查("定行·无今天则追加", 动作 == "追加新行")
    查("定行·追加后行数 +1", 文.count("| 2026-11-05 |") == 1 and 文.endswith(甲 + "\n"))

    文, 动作 = 定行(文, "2026-11-05", "1.56.0", 甲, "乙")
    查("定行·同日同版本并进那一行", 动作.startswith("并入"))
    查("定行·并入后不新增行", 文.count("| 2026-11-05 |") == 1)
    查("定行·并入写成＋摘要", "甲＋乙 |" in 文)

    甲57 = 甲.replace("1.56.0", "1.57.0")   # 用例必须给「新版本那一行」，不能拿旧版模板来记新版
    文, 动作 = 定行(文, "2026-11-05", "1.57.0", 甲57, "丙")
    查("定行·同日不同版本另起一行", 动作.startswith("同日新版本"))
    查("定行·两版各占一行", 文.count("| 2026-11-05 |") == 2)
    查("定行·旧版那行没被追写", "甲＋乙 |" in 文 and "甲＋丙" not in 文)
    查("定行·新版本按原行照录（摘要列由调用方给，不由 摘 覆盖）",
       文.endswith(甲57 + "\n"))
    查("定行·旧版只出现一次（新行没被写成旧版本号）", 文.count("| 1.56.0 |") == 1)

    # 核心回归：今天那行**不是最后一行**时，不许把摘要接到别人尾巴上
    多日 = (头 + 甲 + "\n"
           "| 2026-11-06 | 1.58.0 | 67/172 | 精确 96% | 大 0／中 0／未回归 0 | 两闸✓ | 明日 |\n")
    新, 动作 = 定行(多日, "2026-11-05", "1.56.0", 甲, "补记")
    查("定行·今天不在末行也并到今天那行", "甲＋补记 |" in 新)
    查("定行·明天那行一字未动", "| 明日 |" in 新 and "明日＋" not in 新)
    查("定行·只并一处（不改别的行）", 新.count("＋") == 1)

    查("定行·文末无换行也能追加",
       (定行(头 + 甲, "2026-11-07", "1.58.0", "| 2026-11-07 | x |", "丁")[0]).endswith("| 2026-11-07 | x |\n"))

    # 四、版本与配置
    查("版本·读得到真版本号（非问号）", 版本() not in ("?", None, ""))
    查("版本·形如 x.y.z", len(版本().split(".")) == 3)
    查("补配置·settings.json 在位时不重建", 补配置() is False)

    # 五、闸：工具不在返回 None，不许当 0
    原工具 = 工具目录
    try:
        globals()["工具目录"] = "/nonexistent/xuanjian-paipan"
        码, 出 = 闸("假闸", ["kb:gate"])
        查("闸·工具不在返回 None（不是 0）", 码 is None)
        查("闸·给出跳过原因", "未找到排盘工具" in 出)
    finally:
        globals()["工具目录"] = 原工具

    # 六、优先级表：五档、权重唯一、表头与批()的默认名一致
    查("优先级·五档", len(优先级) == 5)
    查("优先级·权重唯一", len({w for _, w, _ in 优先级}) == 5)
    查("优先级·权重恰是 1..5", sorted(w for _, w, _ in 优先级) == [1, 2, 3, 4, 5])
    查("优先级·主课笔记排第一", 优先级[0][1] == 1 and "笔记" in 优先级[0][0])

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    令 = sys.argv[1] if len(sys.argv) > 1 else "状态"
    if 令 == "--selftest":
        sys.exit(自检())
    表 = {"状态": 状态, "下一批": 批, "回测": 回测, "同步": 同步, "记录": 记录, "沉淀": 沉淀}
    if 令 not in 表:
        print("可用：状态（默认）｜下一批｜回测｜同步｜记录 <摘要>｜沉淀")
        sys.exit(1)
    sys.exit(表[令]() or 0)
