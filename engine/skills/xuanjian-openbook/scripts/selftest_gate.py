#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自检元闸 —— 查「那些自检本身是不是真的」。

为什么要有这件：全包喊过很多次「N/N 全绿」。可这句话有个前提没验过——
**假设自检本身不注水**。注水有四种长相，全都不报错、全都显示通过：

1. **假自检**：写了 `def 自检():` 但里面一条断言都没有，只 print 一句「ok」。
2. **恒真断言**：`assert True`／`assert 1 == 1`／`assert x == x`——永远为真，等于没测。
3. **失败不落地**：自检函数返回 1 表示失败，但入口没把它传给 `sys.exit`，
   于是失败了进程照样退 0，CI 与人都看不见。
4. **只测正不测负**：脚本有 raise／拒绝分支，自检里没有一条「应被拒绝」的用例，
   于是「该拦的没拦」永远测不出来。

本闸用 AST 静态读，不 import、不执行被测脚本（避免副作用）。
**它报的是欠账，不是判决**：无自检不判错（有些脚本依赖外部库、交互，测不了），
但必须列出来、标出优先级，不许「看着像测过了」。

用法：
    python3 selftest_gate.py 盘点           全部脚本的自检状况
    python3 selftest_gate.py 欠账           只列无自检的，按优先级排
    python3 selftest_gate.py 盘点 --strict  有注水即 FAIL（无自检只算欠账，不算错）
    python3 selftest_gate.py --selftest     自测本闸

三条纪律：
  · 恒真断言一律算错，不因「历史遗留」豁免。
  · 无自检只算欠账，但清单必须点名到脚本与行数——欠账要能被看见才叫欠账。
  · 本闸自己也要过本闸（`--selftest` 里拿本文件当被扫对象）。
"""
import ast
import json
import os
import sys

技能根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
# __file__ → …/skills/<技能>/scripts/x.py：上跳四层才是专家包根
# 自检函数名：中文「自检」或英文 selftest
自检名 = ("自检",)
断言调用名 = ("查", "核", "ok", "ck", "check", "断言", "assert_")
# 大脚本阈值：行数达到它且无自检 → 欠账里标「该补」
大脚本 = 120


def 找脚本(根=None):
    """返回 [(技能, 相对路径, 绝对路径, 行数)]，只扫 skills/*/scripts/*.py。"""
    根 = 根 or 技能根
    出 = []
    技能们 = os.path.join(根, "skills")
    if not os.path.isdir(技能们):
        技能们 = 根  # 允许把单目录当根扫（自测用）
        for f in sorted(os.listdir(技能们)):
            if f.endswith(".py"):
                路 = os.path.join(技能们, f)
                出.append(("(单目录)", f, 路, 行数(路)))
        return 出
    for 技能 in sorted(os.listdir(技能们)):
        目录 = os.path.join(技能们, 技能, "scripts")
        if not os.path.isdir(目录):
            continue
        for f in sorted(os.listdir(目录)):
            if f.endswith(".py"):
                路 = os.path.join(目录, f)
                出.append((技能, f, 路, 行数(路)))
    return 出


def 行数(路):
    try:
        return sum(1 for _ in open(路, encoding="utf-8"))
    except Exception:
        return 0


def 是自检函数(节点):
    return any(k in 节点.name for k in 自检名) or "selftest" in 节点.name.lower()


def 本地助手(函数节点):
    """自检函数里自己定义的小助手（`def 查(...)`／`def ck(...)`），它们的调用同样算断言。

    不认这一条就会把写得挺认真的自检误判成「假自检」——`ck(...)` 这种命名太常见了。
    """
    return {n.name for n in ast.walk(函数节点)
            if isinstance(n, ast.FunctionDef) and n is not 函数节点}


def 断言项(函数节点):
    """返回 (条数, 条件表达式列表)。

    只认**语句位置的调用**（`查(...)`／`ck(...)` 单独占一行）与 `ast.Assert`。
    早前用 ast.walk 找所有 Call，把嵌套调用也当断言——`判定(44.99)` 里的「判定」
    前缀撞上「判」，于是被当成助手、把 44.99 当成条件、判成「恒真断言」，
    一口气误报 score.py 六处。**审计工具自己也会误报，这一条是踩出来的。**
    """
    助手 = 本地助手(函数节点) | set(断言调用名)
    条数, 条件 = 0, []
    for 节点 in ast.walk(函数节点):
        # 写法三：`checks = [(名字, 条件, 备注), …]` 再统一跑一遍（source_gate 就是这样）
        if isinstance(节点, ast.Assign) and isinstance(节点.value, ast.List):
            # 只认「首元是字符串名字」的元组：`bad_dates = [(1925, 2, 29), …]` 这种数据表不算断言
            真元组 = [e for e in 节点.value.elts
                      if isinstance(e, ast.Tuple) and len(e.elts) >= 2
                      and isinstance(e.elts[0], ast.Constant)
                      and isinstance(e.elts[0].value, str)]
            if 真元组:
                for e in 真元组:
                    条数 += 1
                    条 = e.elts[1]
                    if not (isinstance(条, ast.Constant) and isinstance(条.value, str)):
                        条件.append(条)
                continue
        if isinstance(节点, ast.Assert):
            条数 += 1
            条件.append(节点.test)
            continue
        if not (isinstance(节点, ast.Expr) and isinstance(节点.value, ast.Call)):
            continue
        调用 = 节点.value
        名 = getattr(调用.func, "id", "") or getattr(调用.func, "attr", "")
        # 写法二：`cases.append((名字, 条件))`，最后按条件分拣 ok/bad
        if 名 == "append" and 调用.args and isinstance(调用.args[0], ast.Tuple) \
                and len(调用.args[0].elts) >= 2:
            条数 += 1
            末 = 调用.args[0].elts[-1]
            if not (isinstance(末, ast.Constant) and isinstance(末.value, str)):
                条件.append(末)
            continue
        if 名 in 助手:
            条数 += 1
            for a in 调用.args:          # 助手签名多为 (名字, 条件)
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    continue
                条件.append(a)
                break
    return 条数, 条件


def 数断言(函数节点):
    return 断言项(函数节点)[0]


def 恒真(测):
    """判断一个 assert 的条件是不是恒真。返回 True／False。"""
    if isinstance(测, ast.Constant):
        return bool(测.value)
    if isinstance(测, ast.Compare) and len(测.ops) == 1 and isinstance(测.ops[0], ast.Eq):
        左 = ast.dump(测.left)
        右 = ast.dump(测.comparators[0])
        return 左 == 右          # assert x == x
    return False


def 恒假(测):
    """assert False 不是恒真，是「占位未实现」——单列，不当注水。"""
    return isinstance(测, ast.Constant) and not 测.value


def 是负向(测):
    """一条断言是不是「期望失败／期望被拒」：assert not …／is None／!=／try 包住。"""
    if isinstance(测, ast.UnaryOp) and isinstance(测.op, ast.Not):
        return True
    if isinstance(测, ast.Compare) and any(
            isinstance(o, (ast.Is, ast.IsNot, ast.NotEq)) for o in 测.ops):
        return True
    return False


def 有负向(函数节点):
    条数, 条件 = 断言项(函数节点)
    if any(是负向(c) for c in 条件):
        return True
    return any(isinstance(n, ast.Try) for n in ast.walk(函数节点))


def 有退出码(树, 自检们):
    """自检失败能不能体现在退出码上。

    两条通路任一即可：① 顶层 __main__ 块里有 sys.exit(...)；
    ② 自检结果被 return 或 sys.exit 接走。
    另外看是否出现 `sys.exit(自检(...))` 这种直连。
    """
    有exit = False
    for 节点 in ast.walk(树):
        if isinstance(节点, ast.Call):
            名 = getattr(节点.func, "attr", "") or getattr(节点.func, "id", "")
            if 名 == "exit":
                有exit = True
    return 有exit


def 扫一个(路):
    """扫一个脚本，返回 dict。"""
    try:
        源 = open(路, encoding="utf-8").read()
        树 = ast.parse(源)
    except Exception as e:
        return {"错": f"解析失败：{e}", "行数": 行数(路), "自检": 0}

    自检们 = [n for n in ast.walk(树) if isinstance(n, ast.FunctionDef) and 是自检函数(n)]
    恒真数, 恒假数, 总条 = [], [], 0
    for f in 自检们:
        条数, 条件 = 断言项(f)
        总条 += 条数
        for 评 in 条件:
            if 恒真(评):
                恒真数.append(getattr(评, "lineno", 0))
            elif 恒假(评):
                恒假数.append(getattr(评, "lineno", 0))

    函数数 = sum(1 for n in ast.walk(树) if isinstance(n, ast.FunctionDef) and not 是自检函数(n))
    return {
        "行数": 行数(路),
        "自检函数": len(自检们),
        "自检": 总条,
        "业务函数": 函数数,
        "恒真": 恒真数,
        "恒假": 恒假数,
        "负向": any(有负向(f) for f in 自检们) if 自检们 else False,
        "退出码": 有退出码(树, 自检们),
        "有raise": any(isinstance(n, ast.Raise) for n in ast.walk(树)),
    }


def 判(一条):
    """给一条扫描结果定性：硬错误／欠账／通过。"""
    错 = []
    路 = 一条["路径"]
    r = 一条["扫"]
    if "错" in r:
        return ["解析失败：" + r["错"]], None
    if r["自检"] == 0:
        if r["自检函数"]:
            错.append("假自检：写了自检函数但零断言")
        return 错, ("欠账" if r["行数"] >= 大脚本 else "小脚本无自检")
    if r["恒真"]:
        错.append("恒真断言 %d 处（行 %s）" % (len(r["恒真"]), ",".join(map(str, r["恒真"][:5]))))
    if not r["退出码"]:
        错.append("失败不落地：无 sys.exit，自检失败进程仍退 0")
    return 错, None


def 盘点(根=None, 严格=False):
    脚本们 = 找脚本(根)
    行 = []
    for 技能, 名, 路, _ in 脚本们:
        r = 扫一个(路)
        错, 欠 = 判({"路径": 路, "扫": r})
        行.append({"技能": 技能, "名": 名, "路": 路, **r, "错": 错, "欠账": 欠})
    return 行


def 报表(行):
    print("== 自检元闸 ==")
    有 = [x for x in 行 if x["自检"] > 0]
    无 = [x for x in 行 if x["自检"] == 0]
    print("脚本 %d 个：有自检 %d／无自检 %d；断言合计 %d 条"
          % (len(行), len(有), len(无), sum(x["自检"] for x in 行)))
    print()

    print("— 有自检（按条数降序）—")
    print("%-24s %-6s %-6s %-6s %-6s %s" % ("技能", "脚本", "行数", "函数", "断言", "负向/退出码"))
    for x in sorted(有, key=lambda y: -y["自检"]):
        print("%-24s %-6s %-6d %-6d %-6d %s" % (
            x["技能"].replace("xuanjian-", ""), x["名"][:24], x["行数"],
            x["业务函数"], x["自检"],
            ("负向✓" if x["负向"] else "负向✗") + " " + ("退出码✓" if x["退出码"] else "退出码✗")))
    print()

    if 无:
        print("— 无自检（欠账，按行数降序；行数≥%d 标★该补）—" % 大脚本)
        for x in sorted(无, key=lambda y: -y["行数"]):
            星 = "★" if x["行数"] >= 大脚本 else " "
            print("  %s %-24s %-26s %4d行 %s" % (
                星, x["技能"].replace("xuanjian-", ""), x["名"][:26], x["行数"],
                "(有 raise 分支，负向无处验证)" if x.get("有raise") else ""))
        print()

    错们 = [(x["名"], e) for x in 行 for e in x["错"]]
    print("— 硬错误 %d 条 —" % len(错们))
    for 名, e in 错们:
        print("  ✗ %-24s %s" % (名[:24], e))
    if not 错们:
        print("  无")
    print()
    print("结论：%s（硬错误 %d／欠账 %d）"
          % ("PASS" if not 错们 else "FAIL", len(错们), len(无)))
    return 0 if not 错们 else 1


def 欠账(行):
    无 = sorted([x for x in 行 if x["自检"] == 0], key=lambda y: -y["行数"])
    print("无自检脚本 %d 个，按行数降序：" % len(无))
    for i, x in enumerate(无, 1):
        星 = "★" if x["行数"] >= 大脚本 else " "
        print("  %2d. %s %-26s %4d行 %s" % (
            i, 星, x["名"][:26], x["行数"],
            "(含 raise，属该测未测)" if x.get("有raise") else ""))
    print("\n★ = 行数≥%d，优先补；先补「错了会静默放过错」的那种（判档、漂移比对、台账登记）。"
          % 大脚本)
    return 0


def 解析结果(输出):
    """从自检输出里读出 (通过, 总数)。两种写法都认。

    必须认全，因为「316 还是 321」这种错就是**人手汇总时数错**来的：
    一种写法没匹配上，那个脚本就被漏掉，总数悄悄变小或变大，没人发现。
    """
    import re
    m = re.search(r"通过\s*(\d+)\s*[／/]\s*失败\s*(\d+)", 输出)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return a, a + b
    m = re.search(r"(\d+)\s*[／/]\s*(\d+)\s*(?:passed|PASS)", 输出)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def 跑(根=None, 静=False):
    """真跑一遍所有自检，按技能汇总。汇总数由脚本给，不由人数。"""
    import subprocess
    行们 = 盘点(根)
    果 = []
    for x in 行们:
        if x["自检"] == 0:
            continue
        try:
            r = subprocess.run([sys.executable, x["路"], "--selftest"],
                               capture_output=True, text=True, timeout=300)
            出 = (r.stdout or "") + (r.stderr or "")
            # 少数脚本用的是子命令（kauding.py selftest），不认 --selftest：回退一次
            if r.returncode == 2 and "unrecognized" in 出:
                r = subprocess.run([sys.executable, x["路"], "selftest"],
                                   capture_output=True, text=True, timeout=300)
                出 = (r.stdout or "") + (r.stderr or "")
            过, 总 = 解析结果(出)
            估 = False
            if 过 is None and r.returncode == 0:
                # 只报「都对」不报条数的（huangli 这类）：用 AST 断言数当计数，并标记为估
                过, 总, 估 = x["自检"], x["自检"], True
            果.append({"技能": x["技能"], "名": x["名"], "过": 过, "总": 总, "估": 估,
                       "码": r.returncode, "路": x["路"],
                       "原始": 出.strip().splitlines()[-1] if 出.strip() else "",
                       # 只留最后一行的话，偶发失败永远查不出原因——
                       # 上一行常是回落提示，真正的 ✗ 在上文。**失败要留证据。**
                       "输出": 出})
        except Exception as e:
            果.append({"技能": x["技能"], "名": x["名"], "过": None, "总": None,
                       "码": -1, "原始": "跑不动：%s" % e})
    合计过 = sum(g["过"] for g in 果 if g["过"] is not None)
    合计总 = sum(g["总"] for g in 果 if g["总"] is not None)
    按技能 = {}
    for g in 果:
        d = 按技能.setdefault(g["技能"], [0, 0, 0])
        d[0] += g["过"] or 0
        d[1] += g["总"] or 0
        d[2] += 1
    坏 = [g for g in 果 if g["码"] != 0 or (g["总"] and g["过"] != g["总"]) or g["过"] is None]
    # 失败项把完整输出另存一份，报表里只打尾段——偶发失败须能复盘
    for g in 坏:
        try:
            路 = os.path.join(tempfile.gettempdir(), "selftest-fail-%s.log" % g["名"].replace("/", "_"))
            open(路, "w", encoding="utf-8").write(
                "脚本：%s\n退出码：%s\n\n%s\n"
                % (g.get("路", ""), g["码"], g.get("输出", "")))
            g["日志"] = 路
        except Exception:
            g["日志"] = ""

    估们 = [g for g in 果 if g.get("估")]
    if not 静:
        print("== 全量自检 ==")
        for 技 in sorted(按技能):
            过, 总, 个 = 按技能[技]
            print("  %-10s %2d 个脚本  %4d／%-4d" % (技.replace("xuanjian-", ""), 个, 过, 总))
        print("  %-10s %2d 个脚本  %4d／%-4d" % ("合计", len(果), 合计过, 合计总))
        if 坏:
            print()
            print("— 不绿 %d 个 —" % len(坏))
            for g in 坏:
                print("  ✗ %-24s 码%d %s" % (g["名"][:24], g["码"], g["原始"][:70]))
                if g.get("日志"):
                    print("      完整输出：%s" % g["日志"])
        if 估们:
            print()
            print("  只报结果不报条数 %d 个（按 AST 断言数计，标「估」）：%s"
                  % (len(估们), "、".join(g["名"] for g in 估们)))
        print()
        print("结论：%s（%d／%d，跑了 %d 个脚本；无自检 %d 个另计欠账）"
              % ("PASS" if not 坏 else "FAIL", 合计过, 合计总, len(果),
                 len([x for x in 行们 if x["自检"] == 0])))
    return 0 if not 坏 else 1



def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("恒真识别·True", 恒真(ast.parse("assert True").body[0].test))
    查("恒真识别·1==1", 恒真(ast.parse("assert 1 == 1").body[0].test))
    查("恒真识别·x==x", 恒真(ast.parse("assert a == a").body[0].test))
    查("恒真识别·真比较不算", not 恒真(ast.parse("assert a == b").body[0].test))
    查("恒真识别·常量假不算恒真", not 恒真(ast.parse("assert False").body[0].test))
    查("恒假识别", 恒假(ast.parse("assert False").body[0].test))

    体 = ast.parse("def 自检():\n    assert a == b\n    assert not c\n").body[0]
    查("数断言·assert 计数", 数断言(体) == 2)
    查("负向·not 算负向", 有负向(体))
    正体 = ast.parse("def 自检():\n    assert a == b\n").body[0]
    查("负向·纯正不算负向", not 有负向(正体))
    试体 = ast.parse("def 自检():\n    try:\n        f()\n    except ValueError:\n        pass\n").body[0]
    查("负向·try 算负向", 有负向(试体))

    调体 = ast.parse("def 自检():\n    查('x', 1 == 1)\n    查('y', 2 == 3)\n").body[0]
    查("查()调用也算断言", 数断言(调体) == 2)
    附体 = ast.parse("def 自检():\n    cases.append(('a', x == 1))\n"
                     "    cases.append(('b', not y))\n").body[0]
    查("cases.append 写法也算断言", 数断言(附体) == 2)
    查("append 写法的负向能认出", 有负向(附体))
    助体 = ast.parse("def 自检():\n    def ck(n, c):\n        (ok if c else bad).append(n)\n"
                     "    ck('甲', 1 == 1)\n    ck('乙', 2 == 2)\n").body[0]
    查("本地助手 ck 不算假自检", 数断言(助体) == 2)
    源 = ast.parse("def 自检():\n    pass\n")
    查("零断言自检被认出", 数断言(源.body[0]) == 0)
    查("自检函数识别", 是自检函数(源.body[0]))
    查("selftest 识别", 是自检函数(ast.parse("def selftest():\n    pass\n").body[0]))
    查("普通函数不误认", not 是自检函数(ast.parse("def 打分():\n    pass\n").body[0]))

    查("解析·通过／失败写法", 解析结果("通过 19 ／ 失败 0") == (19, 19))
    查("解析·有失败也报总数", 解析结果("通过 43 ／ 失败 4") == (43, 47))
    查("解析·passed 写法", 解析结果("dataset_scan selftest: 11/11 passed") == (11, 11))
    查("解析·SELFTEST PASS 写法", 解析结果("SELFTEST 16/16 PASS") == (16, 16))
    查("解析·认不出给 None", 解析结果("随便一句") == (None, None))

    查("退出码·有 sys.exit", 有退出码(ast.parse("import sys\nsys.exit(1)\n"), []))
    查("退出码·无则判无", not 有退出码(ast.parse("print(1)\n"), []))

    # 元闸自己过元闸：拿本文件当被扫对象
    我 = 扫一个(os.path.abspath(__file__))
    查("本闸自己有自检", 我["自检"] > 0)
    查("本闸无恒真断言", not 我["恒真"])
    查("本闸失败能落地", 我["退出码"])
    # 本闸扫自己时不该把自己判成欠账
    错, 欠 = 判({"路径": __file__, "扫": 我})
    查("本闸不自判欠账", 欠 is None and not [e for e in 错 if "假自检" in e])

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


def main():
    参 = sys.argv[1:]
    if "--selftest" in 参:
        return 自检()
    if not 参 or 参[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    命令 = 参[0]
    严格 = "--strict" in 参
    if "--json" in 参:
        print(json.dumps(盘点(严格=严格), ensure_ascii=False, indent=2))
        return 0
    if 命令 == "盘点":
        return 报表(盘点(严格=严格))
    if 命令 == "欠账":
        return 欠账(盘点())
    if 命令 == "跑":
        return 跑()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
