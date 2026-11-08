#!/usr/bin/env python3
"""回归基准 —— 知识库或引擎一改，立刻知道哪些既有结论被撼动。

为什么需要：上一轮补完打分基准后，发现两处重大误判（1957 坤造由「身旺」改为
110.5 中和偏上、1985 乾造由「身旺至极」改为 81 偏弱）。那次是人工撞见的，
不是机制发现的。此后每次改动都要跑一遍本脚本。

**只比打分是不够的**（1.21.0 补的教训）：工具后来陆续加了紫微五层、天干五合、
年过六十降档、订正层、大运排向。那些改了之后，只看打分的回归器一路绿灯——
**假绿灯比红灯危险**，它让人以为没改坏，其实根本没测到。

**只跑引擎也不够**（2026-11-07 补，吸收 DSH 的 limits 联动闸）：册页声明「不给
什么」、代码却悄悄长出了别的东西，两道引擎回归都测不到；对拍数据只留在会话里、
交付时拿不出可复核报告，同样测不到。所以现在跑三道：

    第零道　引擎对拍报告新鲜度（duipai.py --check）：引擎哈希／报告正文一致
    第一道　专家团打分引擎（score.py）：总分、档位、岁运要点
    第二道　排盘工具引擎（engine-dump.ts）：大运签名、紫微签名、五合、降档、用神

三道都跑才算回归过。任一跑道跑不动（工具不在／解析不出），**明确报「未回归」**，
不并入「全部通过」。第零道不依赖档案基准，随包必跑；报告未重建时不许改基准消警报，
要么 `--build` 重建，要么在报告里写明改动理由由人裁定（`OB98` §4）。

用法：
    python3 regress.py 建立     扫描在办档案，把当前结论存为基准（两道都存）
    python3 regress.py 检查     重跑两道引擎，与基准比对，报告漂移
    python3 regress.py 展示     打印基准内容
    python3 regress.py 分歧     把「引擎判语 vs 档案定案」并排，人工过目用

判定：
    第一道：分数差 ≤ 0.5 视为未动；档位变＝大漂移；判语要点缺失＝中漂移。
    第二道：四柱／大运签名／紫微签名／用神变＝大漂移；
            五合／降档／旺衰占比／格局数／神煞数变＝中漂移。
    漂移不等于错误——可能是订正。脚本只负责暴露，要不要改由人决定。

**订正层是档案定案，不是引擎结论**：它变了说明档案改了，脚本只提示「请确认
为何改」，不判漂移。
"""
import json, os, re, sys, datetime, subprocess, tempfile

此处 = os.path.dirname(os.path.abspath(__file__))
引擎目录 = os.path.join(此处, "..", "..", "xuanjian-kb", "scripts")
sys.path.insert(0, 引擎目录)

def _根有效(根):
    """回归器要跑第二道，根里必须真有八字库 + 回归基准。

    实测踩过（2026-11-07 收尾验收）：某个工作区的「命理档案」只有方法论目录
    和一份拷贝过来的基准，**没有八字库**。第一道读基准照常通过，第二道 `扫档案()`
    却返回空列表，于是两档都报「未回归」——不是引擎坏了，是根选错了。
    光看「有没有基准」不足以判根可用，必须看有没有档可扫。
    """
    return os.path.isdir(os.path.join(根, "八字库")) and \
        os.path.isfile(os.path.join(根, "方法论", "回归基准.json"))


def _候选根(基=None):
    """从各工作区里找能真正跑第二道的档案根，按修改时间新→旧。

    `基` 只给自检注入临时目录用；正常调用扫 `~/WorkBuddy/*/命理档案`，
    不写死任何一个工作区路径。
    """
    基 = 基 or os.path.expanduser("~/WorkBuddy")
    出 = []
    try:
        for d in os.listdir(基):
            p = os.path.join(基, d, "命理档案")
            if _根有效(p):
                出.append((os.path.getmtime(p), p))
    except OSError:
        pass
    return [p for _, p in sorted(出, reverse=True)]


def _档案根():
    """档案根交给 `study_state` 定——**五个脚本不许各猜一套**。

    原来这里是 `os.environ.get("命理档案") or "/…/2026-10-26-…/命理档案"`。
    两处都靠不住：中文环境变量在本机 shell 传不进去（实测取到 `None`），
    而写死的那个是**另一个工作区**。于是在当前工作区跑回归，读的是旧工作区的
    基准——**比的是别人家的账**，还没人看得出来。

    2026-11-07 补：中文环境变量名在本机 shell 里根本传不进去
    （`study_state.py` 开头已记这个坑）。给一个 ASCII 别名 `XJ_ARCHIVE`，
    让 `XJ_ARCHIVE=<路径> python3 regress.py 检查` 能钉死根。

    2026-11-07 二次补：光有别名还不够，「最近改过的工作区」常猜到一份
    **有基准没八字库**的空根，第二道便永远假红。猜完加一道有效性校验：
    根不可用就从候选里改选，且**必须出声**说明改选了哪个、为什么；
    仍可用 `XJ_ARCHIVE` 钉死，显式指定一律尊重、只在无效时提示。
    """
    明 = os.environ.get("XJ_ARCHIVE")
    if 明 and os.path.isdir(明):
        if not _根有效(明):
            print("！ XJ_ARCHIVE 指向的根缺八字库／回归基准，第二道将无法回归：%s" % 明,
                  file=sys.stderr)
        return 明
    try:
        import study_state
        根 = study_state.状态根()
    except Exception:
        根 = os.environ.get("命理档案") or os.getcwd()
    if _根有效(根):
        return 根
    候 = _候选根()
    if 候:
        print("！ 猜到的档案根缺八字库／回归基准，第二道无法回归；改选含八字库的根：\n"
              "    原 %s\n    改 %s\n  要钉死：XJ_ARCHIVE=<路径> python3 regress.py 检查"
              % (根, 候[0]), file=sys.stderr)
        return 候[0]
    return 根


档案根 = _档案根()
基准文件 = os.path.join(档案根, "方法论", "回归基准.json")

# 排盘工具：第二道回归跑道，同源的另一套引擎
工具目录 = os.environ.get("排盘工具") or \
    "/Users/haoqing/WorkBuddy/2026-10-30-13-17-15/xuanjian-paipan"

import score  # noqa: E402
import yun    # noqa: E402

时辰中值 = {"子": (0, 0), "丑": (2, 0), "寅": (4, 0), "卯": (6, 0), "辰": (8, 0),
          "巳": (10, 0), "午": (12, 0), "未": (14, 0), "申": (16, 0),
          "酉": (18, 0), "戌": (20, 0), "亥": (22, 0)}


def 扫档案():
    """从八字库各档读出四柱、命主、现运。"""
    库 = os.path.join(档案根, "八字库")
    if not os.path.isdir(库):
        return []
    出 = []
    for 档 in sorted(os.listdir(库)):
        卡 = os.path.join(库, 档, "档案卡片.md")
        if not os.path.exists(卡):
            continue
        s = open(卡, encoding="utf-8").read()
        干 = "[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
        四柱 = None
        m = re.search(r"\|\s*四柱\s*\|\s*(" + 干 + r"\s*" + 干 + r"\s*" + 干 + r"\s*" + 干 + r")", s)
        if not m:
            m = re.search(r"#\s*档案卡片[^（]*（\s*(" + 干 + r"\s*" + 干 + r"\s*" + 干 + r"\s*" + 干 + r")\s*）", s)
        if m:
            串 = re.sub(r"\s+", "", m.group(1))
            四柱 = [串[i:i + 2] for i in range(0, len(串), 2)]
        题 = s.split("\n")[0]
        名 = 题.replace("# 档案卡片 ·", "").strip()
        现运 = ""
        for 行 in s.split("\n"):
            if "现运" in 行:
                m3 = re.search(r"(\*\*)?" + 干, 行)
                if m3:
                    现运 = re.sub(r"\*|\s", "", m3.group(0))
                    break
        if 四柱 and len(四柱) == 4:
            出.append({"档号": 档, "名": 名, "四柱": 四柱, "现运": 现运, "原文": s})
        else:
            出.append({"档号": 档, "名": 名, "四柱": None, "现运": 现运, "原文": s,
                       "缺": "四柱不齐（待补时），不打分"})
    return 出


def 格(原文, 名):
    """取表格里某一格的值。表格行形如「| 出生时刻 | 巳时（9:00–11:00） |」，
    注意单元格之间夹着竖线——匹配时必须先切出格子，不能跨竖线一路扫下去。"""
    m = re.search(re.escape(名) + r"\s*\|\s*([^|]*)", 原文)
    return m.group(1).strip() if m else ""


def 生辰(原文):
    """从档案卡片解析出可喂给排盘工具的生辰。解析不出返回 (None, 原因)。"""
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", 格(原文, "公历生日"))
    if not m:
        return None, "无公历生日"
    年, 月, 日 = (int(x) for x in m.groups())
    刻 = 格(原文, "出生时刻")
    if not 刻 or "待补" in 刻 or "未排" in 刻:
        return None, "出生时刻待补"
    时 = 分 = None
    # 先认「（9:00–11:00）」这种明确区间，取中值
    m2 = re.search(r"(\d{1,2}):(\d{2})\s*[–\-—~至]\s*(\d{1,2}):(\d{2})", 刻)
    if m2:
        h1, n1, h2, n2 = (int(x) for x in m2.groups())
        总 = ((h1 * 60 + n1) + (h2 * 60 + n2)) // 2
        时, 分 = divmod(总, 60)
    else:
        m3 = re.search(r"([子丑寅卯辰巳午未申酉戌亥])时", 刻)
        if m3:
            时, 分 = 时辰中值[m3.group(1)]
    if 时 is None:
        return None, "出生时刻待补（只写了时段没有时辰）"
    性 = "female" if "坤造" in 原文.split("\n")[0] else "male"
    地 = 格(原文, "出生地").replace("*", "").strip()
    return {"year": 年, "month": 月, "day": 日, "hour": 时, "minute": 分,
            "gender": 性, "place": 地}, ""


def 工具快照(档们):
    """调排盘工具的 engine-dump.ts，取第二道回归快照。

    返回 (快照字典, 跳过清单)。工具不在／跑挂了都进跳过清单——
    由调用方明确报「未回归」，绝不当作通过。
    """
    跳过 = []
    if not os.path.isdir(工具目录):
        return None, [{"档号": d["档号"], "因": "排盘工具目录不存在（设环境变量 排盘工具 指定）"} for d in 档们]
    入 = []
    for d in 档们:
        b, 因 = 生辰(d.get("原文", ""))
        if not b:
            跳过.append({"档号": d["档号"], "因": 因})
            continue
        入.append({"id": d["档号"], **b})
    if not 入:
        return None, 跳过
    p = os.path.join(tempfile.gettempdir(), "xj-snap-in.json")
    json.dump(入, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ)
    env["NODE_OPTIONS"] = ""          # 清空被注入的 --require shim，否则子进程会挂
    try:
        r = subprocess.run(["npx", "tsx", "scripts/engine-dump.ts", p],
                           cwd=工具目录, capture_output=True, text=True,
                           env=env, timeout=180)
    except Exception as e:
        return None, 跳过 + [{"档号": x["id"], "因": f"引擎快照调用失败：{e}"} for x in 入]
    try:
        d = json.loads(r.stdout)
    except Exception:
        尾 = (r.stdout[-200:] + r.stderr[-300:]).replace("\n", " ")
        return None, 跳过 + [{"档号": x["id"], "因": f"引擎输出不可解析：{尾}"} for x in 入]
    出 = {x["id"]: x for x in d.get("items", [])}
    for x in d.get("错", []):
        跳过.append({"档号": x, "因": "引擎报错"})
    return 出, 跳过


def 要点(四柱, 运):
    """把岁运引擎的关键判语抽成一组短标签。"""
    if not 运:
        return []
    文 = []
    文 += yun.判岁运(四柱, 运[1], "大运")
    文 += yun.成局(四柱, 运[1])
    文 += yun.查空(四柱, 运)
    序 = ["合走", "合去", "合出", "合入", "填实", "伏吟", "成局", "冲", "刑", "害", "落空"]
    标签 = set()
    for l in 文:
        位 = l.split("：")[0]
        for k in 序:
            if k in l:
                标签.add(f"{位}→{k}")
                break
    return sorted(标签)


# —— 第二道：逐字段比对 ——
大项 = ["四柱", "大运签名", "紫微签名", "用神", "父母星"]
中项 = ["降档", "格局数", "神煞数", "财库", "健康"]
串项 = ["五合", "订正层", "柱型", "三围", "解冲", "双盘"]
占比式 = re.compile(r"占比\s*([\d.]+)%")


def 占比(文本):
    m = 占比式.search(文本 or "")
    return float(m.group(1)) if m else None


def 串起来(v):
    """串项的统一展示。字符串按整句显示——早前直接 join 会把「缺父、子女|运限9段」
    拆成一个个字，日志里变成「父、、、子、女」，等于看不出来改了什么。"""
    if v is None or v == "" or v == []:
        return "（无）"
    if isinstance(v, str):
        return v
    try:
        return "、".join(str(x) for x in v) or "（无）"
    except TypeError:
        return str(v)


def 比一档(旧, 新):
    """返回 (等级, 说明列表)。级：None／中／大。"""
    说 = []
    级 = None
    for k in 大项:
        if 旧.get(k) != 新.get(k):
            说.append(f"{k} {旧.get(k)} → {新.get(k)}")
            级 = "大"
    for k in 中项:
        if 旧.get(k) != 新.get(k):
            说.append(f"{k} {旧.get(k)} → {新.get(k)}")
            级 = 级 or "中"
    for k in 串项:
        if (旧.get(k) or []) != (新.get(k) or []):
            旧串 = 串起来(旧.get(k))
            新串 = 串起来(新.get(k))
            说.append(f"{k} {旧串} → {新串}")
            if k == "订正层":
                # 订正层是档案定案，变了＝档案改了，只提示不判漂移
                说.append("　↑ 订正层来自命理档案，变了请确认是档案改了还是引擎读错，不按漂移处置")
            else:
                级 = 级 or "中"
    a, b = 占比(旧.get("旺衰")), 占比(新.get("旺衰"))
    if a is not None and b is not None and abs(a - b) > 2:
        说.append(f"旺衰占比 {a}% → {b}%")
        级 = 级 or "中"
    return 级, 说


def 建立():
    档 = 扫档案()
    基准 = json.load(open(基准文件, encoding="utf-8")) if os.path.exists(基准文件) else {}
    基准["生成于"] = str(datetime.date.today())
    基准["档"] = []
    基准["待补"] = []
    基准["工具引擎"] = {}
    基准["未回归"] = []

    print("=== 第一道：专家团打分引擎 ===")
    for d in 档:
        if not d.get("四柱"):
            基准["待补"].append({"档号": d["档号"], "名": d["名"], "缺": d["缺"]})
            print(f"跳过 {d['档号']}：{d['缺']}")
            continue
        try:
            r = score.打分(d["四柱"])
        except Exception as e:
            print("打分失败", d["档号"], e)
            continue
        基准["档"].append({
            "档号": d["档号"], "名": d["名"], "四柱": " ".join(d["四柱"]),
            "总分": r["总分"], "天干分": r["天干分"], "地支分": r["地支分"],
            "档位": r["档位"], "现运": d["现运"], "要点": 要点(d["四柱"], d["现运"]),
        })
        print(f"  已存 {d['档号']}｜{r['总分']}（{r['档位']}）")

    print("\n=== 第二道：排盘工具引擎 ===")
    快照, 跳过 = 工具快照(档)
    if 快照 is None and not 跳过:
        print("  排盘工具不可用，第二道未建立")
    for k, v in (快照 or {}).items():
        基准["工具引擎"][k] = v
        print(f"  已存 {k}｜{v['四柱']}｜{v['大运签名']}｜{v['紫微签名']}")
    for s in 跳过:
        基准["未回归"].append(s)
        print(f"  未回归 {s['档号']}：{s['因']}")

    os.makedirs(os.path.dirname(基准文件), exist_ok=True)
    json.dump(基准, open(基准文件, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n基准已写入 {基准文件}：第一道 {len(基准['档'])} 档，"
          f"第二道 {len(基准['工具引擎'])} 档，未回归 {len(基准['未回归'])} 档")
    return 0


def 检查():
    # —— 第零道：引擎对拍报告新鲜度（2026-11-07 加）——
    # 不依赖档案基准，随包必跑。引擎一改、报告没重建，这里就红；
    # 按 `OB98` §4 不许改基准消警报，也不许自动静默重建。
    print("=== 第零道：引擎对拍报告新鲜度 ===")
    try:
        import duipai
        新鲜, 因 = duipai.检查报告()
    except Exception as e:
        新鲜, 因 = False, ["对拍守卫不可用：%s" % e]
    if 新鲜:
        print("[通过] 引擎哈希与报告正文均一致（duipai.py --check）")
    else:
        for l in 因:
            print("[需重建]", l)
        print("      修法：python3 skills/xuanjian-kb/scripts/duipai.py --build；"
              "改动与对拍无关的，也要在报告里写明理由由人裁定。")

    if not os.path.exists(基准文件):
        print("还没有基准，先跑：python3 regress.py 建立")
        return 1 if 新鲜 else 3
    基准 = json.load(open(基准文件, encoding="utf-8"))
    print(f"档案根 {档案根}（基准 {基准文件}）")
    print(f"基准生成于 {基准['生成于']}")

    # —— 第一道 ——
    print("\n=== 第一道：专家团打分引擎 ===")
    print(f"共 {len(基准.get('档', []))} 档")
    大 = 中 = 0
    for b in 基准.get("档", []):
        柱 = b["四柱"].split()
        r = score.打分(柱)
        差 = abs(r["总分"] - b["总分"])
        位变 = r["档位"] != b["档位"]
        新要点 = set(要点(柱, b["现运"]))
        旧要点 = set(b["要点"])
        失 = sorted(旧要点 - 新要点)
        增 = sorted(新要点 - 旧要点)
        标 = "通过"
        if 位变 or 差 > 2:
            标 = "大漂移"; 大 += 1
        elif 差 > 0.5 or 失:
            标 = "中漂移"; 中 += 1
        print(f"[{标}] {b['档号']}　{b['名']}")
        print(f"      分数 {b['总分']} → {r['总分']}（差 {round(差,2)}）　"
              f"档位 {b['档位']} → {r['档位']}")
        if 失:
            print(f"      判语消失：{'、'.join(失)}")
        if 增:
            print(f"      判语新增：{'、'.join(增)}")

    # —— 第二道 ——
    print("\n=== 第二道：排盘工具引擎 ===")
    旧 = 基准.get("工具引擎") or {}
    未回归 = 0
    if not 旧:
        print("  基准里没有第二道，先跑：python3 regress.py 建立")
    else:
        档们 = 扫档案()
        新, 跳过 = 工具快照(档们)
        if 新 is None:
            新 = {}
        for 号, 旧档 in 旧.items():
            if 号 not in 新:
                未回归 += 1    # 2026-11-07 补：以前只打印不计数，末尾仍报「全部通过」＝假绿灯
                print(f"[未回归] {号}：本次没取到快照"
                      f"（{'、'.join(s['因'] for s in 跳过 if s['档号'] == 号) or '工具不可用'}）")
                continue
            级, 说 = 比一档(旧档, 新[号])
            标 = "通过" if 级 is None else (级 + "漂移")
            if 级 == "大":
                大 += 1
            elif 级 == "中":
                中 += 1
            print(f"[{标}] {号}　{新[号]['四柱']}")
            if 说:
                for l in 说:
                    print(f"      {l}")
            else:
                print(f"      大运{新[号]['大运签名']}　紫微{新[号]['紫微签名']}　用神{新[号]['用神']}")
        for s in 跳过:
            if s["档号"] not in 旧:
                # 基准外的档（例如「待补时」档案）不进回归，只作信息提示。
                # 以前把它也算「未回归」，等于拿一个本就不该回归的档天天报红。
                print(f"[跳过·非基准档] {s['档号']}：{s['因']}")

    print(f"\n大漂移 {大} 处，中漂移 {中} 处。")
    if 大 or 中:
        print("\n漂移不一定是错：若是订正，改完档案后重跑「建立」刷新基准；"
              "若是引擎回归错误，先修引擎。")
        return 2
    if not 旧:
        print("第二道尚未建立，不能算「全部通过」——跑 `python3 regress.py 建立` 补上。")
        return 2
    if 未回归:
        print("第二道有 %d 档未回归，**不算「全部通过」**——按本脚本约定报未完成，"
              "别让假绿灯混过去。" % 未回归)
        print("  若因档案根猜错：用 `XJ_ARCHIVE=<含八字库的命理档案路径> python3 regress.py 检查` 钉死。")
        return 4
    if not 新鲜:
        print("\n第零道未过：对拍报告未重建，不算「全部通过」。")
        return 3
    print("两道全部通过 ＋ 对拍报告新鲜，既有结论未被撼动。")
    return 0


def 展示():
    if not os.path.exists(基准文件):
        print("还没有基准")
        return 1
    基准 = json.load(open(基准文件, encoding="utf-8"))
    print("=== 第一道（专家团打分）===")
    for b in 基准.get("档", []):
        print(f"{b['档号']}　{b['名']}　{b['四柱']}　{b['总分']}（{b['档位']}）　现运{b['现运']}")
        for t in b["要点"]:
            print("   · " + t)
    print("\n=== 第二道（排盘工具引擎）===")
    for 号, v in (基准.get("工具引擎") or {}).items():
        print(f"{号}　{v['四柱']}　{v['大运签名']}　{v['紫微签名']}")
        print(f"    旺衰 {v['旺衰']}")
        print(f"    用神 {v['用神']}　降档 {v['降档']}　格局 {v['格局数']}　神煞 {v['神煞数']}")
        if v["五合"]:
            print(f"    五合 {'、'.join(v['五合'])}")
    if 基准.get("未回归"):
        print("\n=== 未回归（这些档没有第二道保护）===")
        for s in 基准["未回归"]:
            print(f"  {s['档号']}：{s['因']}")
    return 0


def 分歧():
    """把「引擎说什么」与「档案定案说什么」并排打印，人工过目用。

    两套口径（工具透藏加权 vs 专家团打分法）在印重／比劫重之盘上本来就会相反，
    这是**已知分歧**，不是 bug。但分歧面必须常摆在眼前——哪天分歧悄悄换成别的项
    （比如原来只是旺衰，现在连大运都岔了），没人盯着就发现不了。
    """
    if not os.path.exists(基准文件):
        print("还没有基准")
        return 1
    基准 = json.load(open(基准文件, encoding="utf-8"))
    for 号, v in (基准.get("工具引擎") or {}).items():
        print(f"\n【{号}】{v['四柱']}")
        print(f"  引擎判语：{v['旺衰']}")
        print(f"  引擎用神：{v['用神']}")
        订 = v.get("订正层") or ""
        if 订:
            for l in 订.split("；"):
                if l.strip():
                    print("  档案定案：" + l.strip())
        else:
            print("  档案定案：（本盘无订正记录，两套口径未见分歧登记）")
    print("\n分歧项变了才需要人工介入；不变就是已知分歧，不必每轮处理。")
    return 0


# ---------------------------------------------------------------- 自检
def 自检():
    """回归器自己的体检。

    为什么必须测它：本脚本是「改坏了没有」的唯一报警器。它若把大漂移判成中、
    或把订正层当漂移，结果要么静默放过、要么天天误报——两种都比不跑更坏，
    因为它会让人相信「回归过了」。
    """
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    同盘 = {"四柱": "壬子 辛亥 丙辰 丁酉", "用神": "木", "降档": "无",
            "五合": ["甲己合"], "订正层": "1957坤造改中和", "旺衰": "旺衰占比 42%"}
    查("无改动不报漂移", 比一档(同盘, dict(同盘)) == (None, []))

    级, 说 = 比一档(同盘, dict(同盘, 用神="水"))
    查("大项变判大漂移", 级 == "大")
    查("大项变写明前后值", any("用神" in x and "木" in x and "水" in x for x in 说))

    级, _ = 比一档(同盘, dict(同盘, 降档="降一档"))
    查("中项变判中漂移", 级 == "中")

    级, _ = 比一档(同盘, dict(同盘, 五合=["甲己合", "乙庚合"]))
    查("串项变判中漂移", 级 == "中")

    级, 说 = 比一档(同盘, dict(同盘, 订正层="改成另一个定案"))
    查("订正层变不判漂移", 级 is None)
    查("订正层变留提示且点明不按漂移处置",
       any("不按漂移处置" in x for x in 说))

    级, _ = 比一档(同盘, dict(同盘, 旺衰="旺衰占比 46%"))
    查("旺衰占比差 4 判中漂移", 级 == "中")
    级, _ = 比一档(同盘, dict(同盘, 旺衰="旺衰占比 43%"))
    查("旺衰占比差 1 不判漂移", 级 is None)
    查("占比缺省不炸", 比一档({"旺衰": ""}, {"旺衰": None})[0] is None)

    级, _ = 比一档(同盘, dict(同盘, 用神="水", 降档="降一档"))
    查("大项优先于中项", 级 == "大")

    查("占比·解析百分数", 占比("旺衰占比 42.5%") == 42.5)
    查("占比·无则 None", 占比("没有占比") is None)
    查("串起来·空给（无）", 串起来(None) == "（无）" and 串起来([]) == "（无）")
    查("串起来·字符串原样，不拆字",
       串起来("缺父、子女|运限9段") == "缺父、子女|运限9段")
    查("串起来·列表用顿号连接", 串起来(["甲己合", "乙庚合"]) == "甲己合、乙庚合")
    查("三组漂移项互不重叠",
       not (set(大项) & set(中项)) and not (set(大项) & set(串项)) and not (set(中项) & set(串项)))
    查("订正层在串项里（靠特判豁免，不在大项）", "订正层" in 串项 and "订正层" not in 大项)

    # ── 第零道：对拍报告守卫（2026-11-07）──
    import duipai
    新鲜, 因 = duipai.检查报告()
    查("真库·对拍报告存在且新鲜" + ("（" + 因[0][:40] + "）" if 因 else ""), 新鲜)
    查("守卫·引擎哈希被改即报未重建",
       duipai.比对("正文\n", {"engine_hashes": {"score.py": "0000000000000000"},
                            "body_sha256": "0" * 16})[0] is False)
    查("守卫·正文被手改即报未重建",
       duipai.比对("被改过的正文\n",
                  {"engine_hashes": duipai.文件哈希(), "body_sha256": "0" * 16})[0] is False)

    # ── 档案根有效性（2026-11-07 收尾验收补）──
    with tempfile.TemporaryDirectory() as t:
        空 = os.path.join(t, "w-empty", "命理档案")
        好 = os.path.join(t, "w-good", "命理档案")
        for p in (空, 好):
            os.makedirs(os.path.join(p, "方法论"))
            with open(os.path.join(p, "方法论", "回归基准.json"), "w",
                      encoding="utf-8") as f:
                f.write("{}")
        os.makedirs(os.path.join(好, "八字库"))
        查("档案根·只有基准没八字库判无效", not _根有效(空))
        查("档案根·八字库＋基准判有效", _根有效(好))
        查("档案根·候选只收有效根", _候选根(t) == [好])
        旧 = os.environ.get("XJ_ARCHIVE")
        try:
            os.environ["XJ_ARCHIVE"] = 好
            查("档案根·显式 XJ_ARCHIVE 优先", _档案根() == 好)
        finally:
            if 旧 is None:
                os.environ.pop("XJ_ARCHIVE", None)
            else:
                os.environ["XJ_ARCHIVE"] = 旧

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    令 = sys.argv[1] if len(sys.argv) > 1 else "检查"
    if 令 == "--selftest":
        sys.exit(自检())
    表 = {"建立": 建立, "检查": lambda: sys.exit(检查()),
          "展示": lambda: sys.exit(展示()), "分歧": lambda: sys.exit(分歧())}
    sys.exit(表.get(令, 展示)())
