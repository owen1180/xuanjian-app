#!/usr/bin/env python3
"""摄取台账 —— 查资料库有什么、比对已读了什么、输出还差什么。

用法：
    python3 ledger.py 列表                 列全部节点与状态
    python3 ledger.py 未读                 只列尚未摄取的
    python3 ledger.py 登记 <标题关键字> <落到哪一册>   把一份资料标为已摄取
    python3 ledger.py 统计                 各板块读了多少、还剩多少
    python3 ledger.py 待编码                已摄取的册页在排盘工具侧跟到哪了

**待编码是 1.21.0 补的**：台账原先只管「读没读」，读完落到哪一册就断了。
工具侧靠 .kb-sync/coverage.json 决定跟不跟——册号没登记，工具永远不会知道。
`待编码` 把这两头对起来：哪些册已登记、哪些还挂着、哪些根本没登记。

台账本体在工作区 命理档案/方法论/摄取台账.md，本脚本只做比对与登记。
"""
import json, os, re, subprocess, sys

# 排盘工具：同一套知识的另一半，册页落库后要靠它的覆盖表决定是否编码
工具目录 = os.environ.get("排盘工具") or \
    "/Users/haoqing/WorkBuddy/2026-10-30-13-17-15/xuanjian-paipan"

空间编号 = "AtPweohLDGk35AOhX5JNGR"
根编号 = "Gz3Azws8Lvo5gTQ6hpqoO9"

def 技能目录():
    """找到资料库接口脚本所在目录。"""
    基 = "/Users/haoqing/.workbuddy/plugins/cache/workbuddy-builtin/skill-library"
    if not os.path.isdir(基):
        return None
    命中 = []
    for d in os.listdir(基):
        p = os.path.join(基, d, "space_api.py")
        if os.path.exists(p):
            命中.append(p)
    if not 命中:
        return None
    return os.path.dirname(sorted(命中)[-1])

def 拉节点(父编号):
    sk = 技能目录()
    if not sk:
        return []
    r = subprocess.run(["python3", os.path.join(sk, "space_api.py"),
                        "space.workspace.list-nodes", "--space-id", 空间编号,
                        "--parent-node-id", 父编号, "--limit", "200"],
                       capture_output=True, text=True, cwd=sk)
    try:
        return json.loads(r.stdout)["data"]["nodes"]
    except Exception:
        return []

def 全树(编号=根编号, 路径="", 层=0, 出=None):
    if 出 is None:
        出 = []
    for n in 拉节点(编号):
        题 = n.get("title", "").strip()
        p = 路径 + "/" + 题
        if n.get("kind") == "folder":
            if 层 < 3:
                全树(n["id"], p, 层 + 1, 出)
        else:
            出.append({"号": n["id"], "题": 题, "径": p})
    return 出

def 台账路径():
    """台账位置统一由 study_state 解析（环境变量 > 当前工作区 > 旧根 > 兜底）。

    原先这里写死一个绝对路径：换工作区跑就只认旧库，新工作区里永远没有台账。
    """
    try:
        import study_state
        return study_state.文件("摄取台账.md")
    except Exception:
        环 = os.environ.get("命理档案")
        if 环:
            return os.path.join(环, "方法论", "摄取台账.md")
        return "/Users/haoqing/WorkBuddy/2026-10-26-14-08-25/命理档案/方法论/摄取台账.md"

def 读台账():
    """从台账正文里抽出已登记的标题关键字。"""
    p = 台账路径()
    if not os.path.exists(p):
        return set()
    s = open(p, encoding="utf-8").read()
    已 = set()
    for 行 in s.split("\n"):
        if 行.startswith("|") and "已摄取" in 行:
            格 = [c.strip() for c in 行.strip("|").split("|")]
            if len(格) >= 1 and 格[0] and not 格[0].startswith("---"):
                已.add(格[0])
    return 已

def 判状态(题, 已):
    """判定一份资料读没读。

    匹配分三级，从严到宽：完全相同 → 登记项包含在标题里（登记写的是完整路径、
    标题只是文件名，这是最常见的情况）→ 反向包含。反向包含只对长标题开——
    短标题（如「第一课」）去反查长登记项，会把同名的另一份也误判成已读。
    """
    if 题 in 已:
        return "已摄取", 题
    for k in 已:
        if k and k in 题:
            return "已摄取", k
    if len(题) >= 6:
        for k in 已:
            if k and 题 in k:
                return "已摄取", k
    return "未摄取", ""


def 册号(册文本):
    """从「48 天干五合与合化」「01 打分法（身弱细则）」里抽出册号。"""
    m = re.match(r"\s*(\d{1,2})\b", 册文本 or "")
    return m.group(1) if m else ""


def 覆盖表():
    p = os.path.join(工具目录, ".kb-sync", "coverage.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8")).get("entries", {})
    except Exception:
        return None


def 提示跟进(册文本):
    """登记完立刻回显：这一册在排盘工具侧跟到哪了。

    读完登记就算完了？不算。册页写进知识库，工具那边若没在覆盖表里登记，
    它就永远不会去实现——两边口径会一直岔着。登记时顺手看一眼。
    """
    号 = 册号(册文本)
    if not 号:
        print("  ！没写册号（只写了册名或「待定」）——三个月后没人知道这份资料的价值在哪，"
              "工具侧也无从登记。登记格式：`ledger.py 登记 <关键字> \"48 天干五合与合化\"`")
        return
    表 = 覆盖表()
    if 表 is None:
        print(f"  （读不到排盘工具覆盖表，跳过跟进；路径 {工具目录}）")
        return
    v = 表.get(号)
    if not v:
        print(f"  ！知识库第 {号} 册在工具侧尚未登记——不登记，工具永远不会去编码。"
              f"到 {工具目录}/.kb-sync/coverage.json 补一条。")
        return
    print(f"  工具侧第 {号} 册：{v.get('status','?')}　模块 {(v.get('module') or '—')}")


def 已摄取行():
    """读台账，返回 [(标题, 册文本)]。"""
    p = 台账路径()
    if not os.path.exists(p):
        return []
    出 = []
    for 行 in open(p, encoding="utf-8").read().split("\n"):
        if 行.startswith("|") and "已摄取" in 行:
            格 = [c.strip() for c in 行.strip("|").split("|")]
            if len(格) >= 2 and 格[0] and not 格[0].startswith("---"):
                出.append((格[0], 格[1]))
    return 出


def 待编码():
    """已摄取的册页，在排盘工具侧跟到哪了。"""
    表 = 覆盖表()
    if 表 is None:
        print(f"读不到排盘工具的覆盖表（{工具目录}/.kb-sync/coverage.json），"
              "设环境变量 排盘工具 指定路径")
        return 1
    行 = 已摄取行()
    已册 = {}
    无号 = []
    for 题, 册 in 行:
        号 = 册号(册)
        if 号:
            已册.setdefault(号, set()).add(册)
        else:
            无号.append((题, 册))
    print(f"已摄取 {len(行)} 份，落到 {len(已册)} 个册号\n")
    print(f"{'册':<6}{'状态':<12}{'模块':<34}备注")
    print("-" * 90)
    待 = 0
    for 号 in sorted(已册, key=lambda x: int(x)):
        v = 表.get(号)
        册名 = "／".join(sorted(已册[号]))
        if not v:
            print(f"{号:<6}{'未登记':<12}{'—':<34}工具侧没有这一册，永远不会去编码")
            待 += 1
            continue
        态 = v.get("status", "?")
        模 = (v.get("module", "") or "—")[:32]
        print(f"{号:<6}{态:<12}{模:<34}{册名}")
        if 态 in ("pending", "partial", "未登记"):
            待 += 1
    print("-" * 90)
    if 无号:
        print(f"\n另有 {len(无号)} 份登记时没写册号（写「待定」或只写了册名）：")
        for 题, 册 in 无号[:10]:
            print(f"  · {册}　← {题[-38:]}")
        print("  登记时必须写明册号，否则三个月后没人知道这份资料的价值在哪，"
              "工具侧也无从登记。")
    print(f"\n待编码／未登记 {待} 个册号。")
    print("\n登记方式：编辑 .kb-sync/coverage.json，写清 模块 与 状态"
          "（implemented／partial／pending／human-only），再跑 npm run kb:accept 推基线。")
    return 0

def 主():
    令 = sys.argv[1] if len(sys.argv) > 1 else "未读"
    if 令 == "--selftest":
        sys.exit(自检())
    if 令 == "登记":
        关 = sys.argv[2]
        册 = sys.argv[3] if len(sys.argv) > 3 else "待定"
        p = 台账路径()
        s = open(p, encoding="utf-8").read()
        今 = str(__import__("datetime").date.today())
        段 = s.split("\n")
        # 优先就地改写匹配到的未摄取行，避免同名条目重复登记
        for i, l in enumerate(段):
            if l.startswith("|") and "未摄取" in l and 关 in l:
                格 = [c.strip() for c in l.strip("|").split("|")]
                if len(格) >= 4:
                    段[i] = f"| {格[0]} | {册} | 已摄取 | {今} |"
                    open(p, "w", encoding="utf-8").write("\n".join(段))
                    print("已登记：", 格[0], "→", 册)
                    提示跟进(册)
                    return
        # 台账里没有这一行（资料库新增的资料），才追加
        for i, l in enumerate(段):
            if l.startswith("|") and "待定" in l:
                段.insert(i, f"| {关} | {册} | 已摄取 | {今} |")
                break
        else:
            段.append(f"| {关} | {册} | 已摄取 | {今} |")
        open(p, "w", encoding="utf-8").write("\n".join(段))
        print("已登记（新增行）：", 关, "→", 册)
        return

    if 令 == "待编码":
        return 待编码()

    树 = 全树()
    已 = 读台账()
    统计 = {}
    未读 = []
    for n in 树:
        态, k = 判状态(n["题"], 已)
        板块 = n["径"].strip("/").split("/")[0]
        d = 统计.setdefault(板块, {"总": 0, "已": 0})
        d["总"] += 1
        if 态 == "已摄取":
            d["已"] += 1
        else:
            未读.append(n)

    if 令 == "统计":
        print(f"{'板块':<14}{'已读':>6}{'总数':>6}{'进度':>8}")
        print("-" * 36)
        总 = 已 = 0
        for k, v in 统计.items():
            总 += v["总"]; 已 += v["已"]
            print(f"{k:<14}{v['已']:>6}{v['总']:>6}{v['已']*100//max(v['总'],1):>7}%")
        print("-" * 36)
        print(f"{'合计':<14}{已:>6}{总:>6}{已*100//max(总,1):>7}%")
        return

    if 令 == "列表":
        for n in 树:
            态, k = 判状态(n["题"], 已)
            print(f"{'√' if 态=='已摄取' else '·'} {n['号']}  {n['题']}")
        return

    print(f"尚未摄取 {len(未读)} 份：\n")
    当 = ""
    for n in 未读:
        板块 = n["径"].strip("/").split("/")[0]
        if 板块 != 当:
            当 = 板块
            print(f"\n【{板块}】")
        print(f"  {n['号']}  {n['题']}")

# ---------------------------------------------------------------- 自检
def 自检():
    """台账自己的体检。

    台账是本馆「读过什么」的唯一账本，也是 1.56.0 那次 `--覆盖` 事故里
    第一个被改写的东西（67→65 两条登记蒸发）。它错的方式都很安静：
    多算一份「已读」，就没人再去读那份资料了。所以这里专测三件：
    匹配的三级松紧、册号抽取、以及「已摄取行」的解析不吞不多。
    """
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    已 = {"2021.12.05_第45课_相同八字_案例扩充.docx.md",
          "2022.01.01_第52课_案例补充_象法补充.docx.md"}

    查("判状态·完全同名", 判状态("2021.12.05_第45课_相同八字_案例扩充.docx.md", 已)[0] == "已摄取")
    查("判状态·登记项是完整路径、标题只是文件名", 判状态("2021.12.05_第45课_相同八字_案例扩充.docx", 已)[0] == "已摄取")
    查("判状态·长标题反向包含也认", 判状态("相同八字_案例扩充", 已)[0] == "已摄取")
    查("判状态·无关资料判未摄取", 判状态("2001.01.01_第99课_别的课.docx", 已)[0] == "未摄取")
    查("判状态·短标题不反向（防同名误判）",
       判状态("第一课", {"第一课_详细版与补充.docx"})[0] == "未摄取")
    查("判状态·命中时回带命中的登记项",
       判状态("2021.12.05_第45课_相同八字_案例扩充.docx", 已)[1] in 已)

    查("册号·两位起头带标题", 册号("48 天干五合与合化") == "48")
    查("册号·带前导零", 册号("01 打分法（身弱细则）") == "01")
    查("册号·纯号码", 册号("97") == "97")
    查("册号·无号码给空", 册号("待定") == "")
    查("册号·None 不炸", 册号(None) == "")

    原 = globals().get("台账路径")
    import tempfile
    临 = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    临.write("# 台账\n\n| 标题 | 册 | 状态 | 日期 |\n|---|---|---|---|\n"
             "| 2021.12.05_第45课.md | 96 | 已摄取 | 2026-11-05 |\n"
             "| 2022.01.01_第52课.md | 97 | 未摄取 | |\n")
    临.close()
    try:
        globals()["台账路径"] = lambda: 临.name
        行 = 已摄取行()
        查("已摄取行·只取已摄取那一行", len(行) == 1)
        查("已摄取行·标题与册都对", 行 and 行[0][0].startswith("2021.12.05") and 行[0][1] == "96")
        查("已摄取行·未摄取不计入", all("第52课" not in x[0] for x in 行))
        globals()["台账路径"] = lambda: "/nonexistent/xx.md"
        查("已摄取行·台账不在给空表", 已摄取行() == [])
    finally:
        globals()["台账路径"] = 原
        os.unlink(临.name)

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    主()
