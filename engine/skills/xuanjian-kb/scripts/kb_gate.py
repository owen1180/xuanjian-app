# -*- coding: utf-8 -*-
"""
玄鉴命理馆 · 运行时强校验引擎（知识片转译层 / 第⑤层）
=================================================
把 57 册的 18 条强制约束与八类主控禁词编译成"输出前闸门"：
  - 召回(recall)：根据用户输入 / 草稿命中关键词，召回适用的强制规则
  - 执行(enforce)：按优先级排序，逐条校验草稿是否越界
  - 校验(validate)：禁词扫描 + 必含提示语检查
  - 反馈(feedback)：每条输出带命中的规则 ID，供后续置信度回贴

用法：
  python3 kb_gate.py                   # 跑内置 mock 场景（含两条本轮补丁的用例）
  python3 kb_gate.py "用户问" "草稿文本"      # 校验任意一对
  python3 kb_gate.py "用户问" "草稿" --rx      # 经方通道：仅豁免方药剂量类，须三句硬标记齐全

本引擎把 57 册 §3 禁词表与 §4 十八条约束机读化：两侧条目须一一对应，不重不漏。
对齐 24 册 §6.1 的"只标记、不改写"，只做"报状态+拦截+建议改写"，不静默改结论。

维护纪律：改本文件前先读参考资料/57-运行时强校验闸门与输出管线.md，
改完必须逐条对拍禁词表与规则表，两侧少了任何一条，闸门就漏。
上一轮实测：册页已写十八条，脚本仍编十六条（缺 K049、K051），且方药表漏一条"不用去医院"，
是靠同步闸"implemented 文档变更须重新对拍"这条提示抓出来的。
"""

import sys
import os
import re
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# 1. 主控禁词表（集中管理，源自 14 条 v1.1 硬核的 enforce 红线）
# ---------------------------------------------------------------------------
BANNED = {
    "生死禁词": ["死先生", "夭折", "必凶", "死别", "绝后", "主绝后",
                "死", "夭", "寿尽", "大限", "不久于人世", "死色"],
    "铁口禁词": ["必发", "必富", "必贵", "必离", "必离婚", "必破财",
                "克父", "克夫", "克子", "一定发", "肯定发", "百分之百",
                "必死", "必亡", "必散", "必败"],
    "病名禁词": ["高血压", "肿瘤", "癌症", "糖尿病", "心脏病", "肝病",
                "肾病", "肺病", "白血病", "脑梗", "中风", "冠心病",
                "你得了", "你是.*病", "你的病是"],
    "医疗动作禁词": ["诊断", "开药", "停药", "药方", "处方"],
    # 进化补丁（第三阶段发现）：K028 道德审判红线此前未编码，现补入
    "道德审判禁词": ["不孝", "这婚必须离", "这婚不能要", "你这人没救",
                  "报应", "活该", "你错了就得认"],
    # 进化补丁（第四阶段发现）：盲区自动补入
    "宿命禁词": ["注定", "天注定", "命该", "一辈子没", "孤寡"],
    "方药剂量禁词": ["每天吃", "就能好", "泡水就好", "克就好", "每天喝", "不用去医院"],
    "灾祸断言禁词": ["必出事", "必出大事", "必出祸", "家运完了"],
    # 进化补丁（2026-11-07 第十四轮，源自 99 册 §2 红线 3 与 §3 措辞替换表）
    # 恐吓勒索类：A 包 safety-and-ethics.md 明列，99 册已升级为全团红线
    "恐吓勒索禁词": ["血光之灾", "血光", "被下咒", "下咒", "被诅咒", "诅咒",
                    "不做法事", "做法事就能", "必须花钱化解", "花钱化解",
                    "必须化解", "不化解就", "天生克", "克亲人", "克父母",
                    "被跟踪", "被控制", "邪祟缠身"],
    # 绝对化措辞类：99 册 §3.1 措辞替换表的核心词
    # 注意："必定""一定"等高危词在用户原话（提问）中出现属正常，只在草稿侧拦截
    "绝对化措辞禁词": ["必定", "注定会", "绝对会", "一定会", "逃不掉",
                     "一辈子都", "百分之百", "肯定能", "必然会"],
    # 未成年人宿命化：99 册 §2 红线 5
    "未成年宿命禁词": ["注定失败", "注定不孝", "注定婚姻不好", "注定身体有灾",
                     "天生反骨", "没出息"],
}

# 措辞替换对照表（99 册 §3.1）——供 validate 模式给出改写建议用
# 左边是禁词，右边是玄鉴推荐表述
WORDING_FIX = {
    "必定": "倾向", "绝对": "更接近", "一定会": "需要留意",
    "逃不掉": "容易出现", "一辈子都": "一段时间内",
    "百分之百": "大概率", "注定": "更像",
    "必出事": "这一年宜静不宜动", "血光之灾": "风险意识",
    "必须化解": "生活层面的调整建议", "天生克": "关系上的张力",
    "转运": "五行喜用与生活调整", "开光": "民俗仪式的文化说明",
}

# 就医触发信号（召回用）
MEDICAL_SIGNALS = ["疼痛", "发热", "发烧", "胸闷", "胸痛", "头痛", "言语不清",
                   "失眠", "自伤", "消瘦", "气短", "两周", "体检单", "气色差"]

# ---------------------------------------------------------------------------
# 2. 十八条强制约束（recall / enforce / validate 三栏机读化，对应 57 册 §4）
#    priority 越高越先执行（就医100>寿元95>应期85>望诊手诊80>方药78>六亲婚姻75>
#                          封顶70/68>理气灾祸60/58>工具纪律55/50>伦理20）——57 册 §4 首段
# ---------------------------------------------------------------------------
RULES = [
    {
        "id": "K024", "priority": 100, "name": "五术边界与就医触发",
        "recall": MEDICAL_SIGNALS + ["健康", "身体", "就医"],
        "enforce": "出现就医信号须停止术数分析并建议就医；不得给病名/方药/停药建议",
        "banned_cats": ["病名禁词", "医疗动作禁词", "方药剂量禁词"],
        "require_phrase": ["建议就医", "尽快就医", "体检"],
    },
    {
        "id": "K046", "priority": 95, "name": "寿元星零禁词",
        "recall": ["还能活", "活多久", "寿元", "关口", "大限", "会不会死", "哪年走"],
        "enforce": "寿元相关一律转'健康关口+体检+陪伴'，绝不出禁词",
        "banned_cats": ["生死禁词"],
        "require_phrase": ["健康关口", "体检", "陪伴"],
    },
    {
        "id": "K037", "priority": 85, "name": "象法三道闸(应期/寿元)",
        "recall": ["哪年出事", "应期", "关口", "引动"],
        "enforce": "点数<2 只作提示不说'这一年会怎样'；寿元相关转风险语言",
        "banned_cats": ["生死禁词"],
        "require_phrase": [],
    },
    {
        "id": "K025", "priority": 80, "name": "望诊零病名",
        "recall": ["面色", "气色", "望诊", "五色"],
        "enforce": "永不言'死色/不久于人世/某病'；零病名零方药",
        "banned_cats": ["生死禁词", "病名禁词", "医疗动作禁词", "方药剂量禁词"],
        "require_phrase": ["建议体检"],
    },
    {
        "id": "K029", "priority": 80, "name": "手诊零病名",
        "recall": ["手诊", "掌纹", "指甲", "健康线", "杵状指"],
        "enforce": "永不言病名；杵状指/青紫/水肿只说尽快就医",
        "banned_cats": ["病名禁词", "方药剂量禁词"],
        "require_phrase": ["尽快就医"],
    },
    {
        "id": "K050", "priority": 78, "name": "方药/食疗剂量零承诺",
        "recall": ["每天吃", "泡水就好", "就能好", "克就好", "每天喝", "黄芪",
                  "食疗", "药方", "不用去医院", "不用看医生"],
        "enforce": "身体议题不给出具体方药/食疗剂量承诺，先建议就医明确",
        "banned_cats": ["方药剂量禁词", "医疗动作禁词", "病名禁词"],
        "require_phrase": ["建议就医", "尽快就医"],
    },
    {
        "id": "K003", "priority": 75, "name": "断语体系(六亲/健康提醒)",
        "recall": ["六亲", "克父", "健康", "事业", "婚姻",
                   "父亲", "母亲", "亲人", "缘分", "兄弟姐妹"],
        "enforce": "六亲只讲走势不讲有无生死；健康只提醒不诊断开方",
        "banned_cats": ["铁口禁词", "病名禁词", "医疗动作禁词", "宿命禁词"],
        "require_phrase": [],
    },
    {
        "id": "K038", "priority": 75, "name": "合婚六亲零'克父/必离'",
        "recall": ["克父", "必离", "合婚", "配偶", "婚姻去留"],
        "enforce": "六亲只讲走势不讲有无生死；不说必离婚；去留当事人定",
        "banned_cats": ["铁口禁词", "宿命禁词"],
        "require_phrase": [],
    },
    {
        "id": "K039", "priority": 70, "name": "用神级别与断语封顶",
        "recall": ["必发", "必富", "必贵", "用神", "格局", "大财",
                   "必定", "一定会", "逃不掉", "化解", "血光"],
        "enforce": "含'必发/必富/必贵'且层次未达高等→改写概率表述并标注 K039",
        # 2026-11-07 补：新增三类挂在 K039 名下，规则表必须同时声明「管这一类」，
        # 否则兜底扫描扫到了词、却没有规则认领（工具侧 redline.ts 上轮已扩，本侧漏了）。
        "banned_cats": ["铁口禁词", "恐吓勒索禁词", "绝对化措辞禁词"],
        "require_phrase": [],
    },
    {
        "id": "K043", "priority": 68, "name": "强弱七档与中和不铁口",
        "recall": ["中和", "铁口", "旺衰", "档位", "分数"],
        "enforce": "中和档必须提示'需客户报年份校对'并禁铁口；分数未达档不断必发",
        "banned_cats": ["铁口禁词"],
        "require_phrase": ["校对"],
    },
    {
        "id": "K010", "priority": 60, "name": "地脉道零禁词",
        "recall": ["阳宅", "名位", "卦位", "厨房方位", "死先生"],
        "enforce": "卦位断语须先成格；讲义铁口转风险，永不言死/夭折/必凶",
        "banned_cats": ["生死禁词", "灾祸断言禁词"],
        "require_phrase": [],
    },
    {
        "id": "K017", "priority": 60, "name": "阴宅零禁词",
        "recall": ["阴宅", "寻龙", "点穴", "八煞黄泉", "绝后"],
        "enforce": "铁口转风险、不断生死不承诺发贵；八煞黄泉绝对不立",
        "banned_cats": ["生死禁词", "灾祸断言禁词"],
        "require_phrase": [],
    },
    {
        "id": "K016", "priority": 55, "name": "奇门不起局/不承诺",
        "recall": ["奇门", "局数", "择时", "应期金额"],
        "enforce": "无年月日时不起局；不判生死病情官司、不承诺金额日期",
        "banned_cats": ["生死禁词", "铁口禁词"],
        "require_phrase": [],
    },
    {
        "id": "K022", "priority": 55, "name": "紫微零寿夭/盘型作废",
        "recall": ["紫微盘", "盘型", "庙旺", "四化", "寿夭"],
        "enforce": "盘型认错全篇作废；零寿夭诊断、零长相打分",
        "banned_cats": ["生死禁词"],
        "require_phrase": [],
    },
    {
        "id": "K041", "priority": 50, "name": "打分引擎复核",
        "recall": ["日坐羊刃", "身强", "缺时柱", "档位复核", "分数"],
        "enforce": "日坐羊刃/身强类口断须引擎复核；缺时柱不凑分；报分不报小数",
        "banned_cats": [],
        "require_phrase": [],
    },
    {
        "id": "K051", "priority": 58, "name": "理气阳宅灾祸不断言",
        "recall": ["阳宅", "理气", "玄空", "飞星", "灾祸", "必出事", "家运"],
        "enforce": "理气只讲风险倾向与调整概率，不铁断灾祸；零灾祸断言词",
        "banned_cats": ["灾祸断言禁词", "生死禁词", "铁口禁词"],
        "require_phrase": [],
    },
    {
        "id": "K028", "priority": 20, "name": "人事不做道德审判",
        "recall": ["道德", "不孝", "该不该离", "劝合", "劝离", "对不对"],
        "enforce": "不做道德审判（不说不孝/这婚必须离）；关系去留由当事人决定",
        "banned_cats": ["道德审判禁词"],
        "require_phrase": [],
    },
    {
        "id": "K049", "priority": 20, "name": "不传播宿命论",
        "recall": ["注定", "孤寡", "一辈子没", "天注定", "命该", "命中注定",
                   "没出息", "天生反骨"],
        "enforce": "只讲趋势与可动杠杆，不给'注定/孤寡/一辈子没'式铁断",
        "banned_cats": ["宿命禁词", "未成年宿命禁词"],
        "require_phrase": [],
    },
]

规则表 = {r["id"]: r for r in RULES}

# ---------------------------------------------------------------------------
# 2.6 禁词兜底归属（2026-11-05 补，v1.58.0）
# ---------------------------------------------------------------------------
# 为什么要有这张表：原先 gate() 只扫「被召回的规则」所管的禁词，红线于是
# 挂在召回上——召回不到，一条都不扫。实测三例整篇穿闸：
#   "我最近怎么样" ／ "你必死，没有救了"   → 召回 []，决策 PASS
#   "我最近怎么样" ／ "死别之象"           → 同为 PASS
# 因为「必死」「死别」不在任何一条规则的 recall 里（K046 收的是"会不会死""哪年走"）。
# 红线不该有开关，所以另设一张「类→兜底规则」表：**无论召回到没召回到，命中即拦**。
# 纪律：每一类都必须有归属，且归属规则确实管这一类（自检逐条验）。
类兜底 = {
    "生死禁词": "K046",      # 寿元星零禁词
    "铁口禁词": "K039",      # 用神级别与断语封顶
    "病名禁词": "K025",      # 望诊零病名
    "医疗动作禁词": "K024",  # 五术边界与就医触发
    "道德审判禁词": "K028",  # 人事不做道德审判
    "宿命禁词": "K049",      # 不传播宿命论
    "方药剂量禁词": "K050",  # 方药/食疗剂量零承诺
    "灾祸断言禁词": "K051",  # 理气阳宅灾祸不断言
    # 2026-11-07 第十四轮新增三类（99 册 §2 红线 3、§3.1 措辞表、红线 5）
    "恐吓勒索禁词": "K039",      # 用神级别与断语封顶（断语强度与恐吓同源）
    "绝对化措辞禁词": "K039",    # 铁口断语同源：必定/一定会/逃不掉
    "未成年宿命禁词": "K049",    # 不传播宿命论
}

# ---------------------------------------------------------------------------
# 3. 引擎核心
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 2.5 经方通道（处方例外，2026-11-02 起）
# ---------------------------------------------------------------------------
# 2026-11-02 起**默认开启**（主人决定：取消"方剂一律不录"的限制，见 86 册 §0）。
# 开启后**只豁免「方药剂量禁词」这一类**；病名、医疗动作（停药/加量）、
# 生死铁口等其余七类**照旧拦**。且必须同时满足三句硬标记（执业医师／
# 不可作为处方／出处），缺一句即不豁免——所以默认开启是安全的：
# 不带全三句的草稿享受不到豁免，方药类照样被拦。
# 仍可用 WITHOUT_RX 环境变量临时关回，便于复现旧行为。
RX_MODE = os.environ.get("WITHOUT_RX") != "1"
RX_REQUIRED = ["执业医师", "不可作为处方", "出处"]
RX_REQUIRE_ANY = {"K024"}   # 该规则的就医提示，经方通道"有其一即可"
RX_CARE_HINTS = ["建议就医", "尽快就医", "立即就医", "去医院", "急诊", "体检", "转诊"]


def rx_ready(draft: str) -> bool:
    """处方通道的三句硬标记是否齐全。"""
    return all(p in draft for p in RX_REQUIRED)


# 经方通道的术语掩码：这些是六经术语与免责套话，不是病名、不是医嘱动作。
# 不掩掉就会把「太阳中风」判成病名、把「不可作为处方」判成开处方。
RX_MASK = ["太阳中风", "阳明中风", "少阳中风", "太阴中风", "少阴中风", "厥阴中风"]
RX_SAFE_PHRASES = ["不可作为处方", "不作为处方", "非处方", "执业医师"]


def rx_mask(draft: str) -> str:
    """经方通道专用的扫描文本：抹掉术语与免责套话，其余照扫。"""
    t = draft
    for w in RX_MASK:
        t = t.replace(w, "〔六经表证〕")
    for w in RX_SAFE_PHRASES:
        t = t.replace(w, "〔免责〕")
    return t


def recall_rules(user_input: str, draft: str) -> list:
    """召回适用规则：用户输入或草稿命中关键词即召回。"""
    text = user_input + " " + draft
    hit = []
    for r in RULES:
        if any(kw in text for kw in r["recall"]):
            hit.append(r)
    # 按优先级降序
    return sorted(hit, key=lambda x: x["priority"], reverse=True)


def scan_banned(draft: str) -> list:
    """扫描草稿中的禁词，返回命中明细。"""
    hits = []
    for cat, words in BANNED.items():
        for w in words:
            if re.search(w, draft) and not 词形撞车(w, draft):
                hits.append((cat, w))
    return hits


# 词形撞车豁免：禁词按正则扫，天生会把合法词一并扫进来。
# 2026-11-03 实测（四册报告首次全量过闸）：「处方」命中「相处方式」「处理方案」，
# 一篇讲夫妻相处的报告会被整篇挡下——这是闸门的精度问题，不是文稿越界。
# 纪律：只放行**词形**，不放行**语义**；豁免条件是前后搭配，不是出现位置，
# 真在说医疗处置的（开处方、处方笺）仍照拦。
撞车豁免 = [
    (r"处方", r"[相共难好易处此各]处方|处方[式案法]"),
    # 「紫微大限」三字里，"大限"前一字是「微」——原正则只写 [运紫]，±1 窗口取不到
    # 「紫」，于是紫微报告里一写「紫微大限」就被当生死禁词拦下（v1.58.0 自检抓到）。
    # 治法：正则补「微」，窗口放到前后各 2 字。
    (r"大限", r"[运紫微]大限|大限[宫盘四化走]"),
]


def 词形撞车(词: str, draft: str) -> bool:
    """该禁词在本稿里是否只以合法词形出现（全部命中都被豁免搭配吸收）。"""
    for 禁, 豁免 in 撞车豁免:
        if 词 == 禁:
            for m in re.finditer(词, draft):
                if not re.search(豁免, draft[max(0, m.start() - 2): m.end() + 2]):
                    return False
            return True
    return False



def gate(user_input: str, draft: str) -> dict:
    """输出前闸门：返回决策 + 命中规则 + 违规明细 + 改写建议。"""
    scan_text = rx_mask(draft) if (RX_MODE and rx_ready(draft)) else draft
    recalled = recall_rules(user_input, scan_text)
    recalled_ids = [r["id"] for r in recalled]

    violations = []  # (rule_id, kind, detail)
    for r in recalled:
        # 禁词扫描
        for cat, words in BANNED.items():
            if cat in r["banned_cats"]:
                # 经方通道：仅豁免"方药剂量"一类，且三句硬标记齐全才生效
                if cat == "方药剂量禁词" and RX_MODE and rx_ready(draft):
                    continue
                for w in words:
                    if re.search(w, scan_text) and not 词形撞车(w, scan_text):
                        violations.append((r["id"], "禁词", f"[{cat}] {w}"))
        # 必含提示语检查（仅当规则要求且草稿缺）
        missing = [ph for ph in r["require_phrase"] if ph not in draft]
        # 经方通道：K024 的就医提示"有其一即可"，不要求三句全背
        if RX_MODE and r["id"] in RX_REQUIRE_ANY and any(k in draft for k in RX_CARE_HINTS):
            missing = []
        for ph in missing:
            violations.append((r["id"], "缺提示语", f"需含'{ph}'"))

    # 兜底扫描：红线不因「没召回到」而失效（见 §2.6）
    已管类 = {cat for r in recalled for cat in r["banned_cats"]}
    兜底 = []
    for cat, w in scan_banned(scan_text):
        if cat in 已管类:
            continue
        # 经方通道只豁免方药剂量一类，且三句硬标记齐全才生效
        if cat == "方药剂量禁词" and RX_MODE and rx_ready(draft):
            continue
        rid = 类兜底.get(cat)
        if rid:
            兜底.append((rid, "禁词·兜底", f"[{cat}] {w}"))
    violations.extend(兜底)

    blocked = len(violations) > 0
    decision = "BLOCK_WITH_REWRITE" if blocked else "PASS"

    # 改写建议（基于涉及规则里优先级最高的那条）
    suggestion = ""
    if blocked:
        相关 = list(recalled)
        for v in 兜底:
            r = 规则表.get(v[0])
            if r is not None and r not in 相关:
                相关.append(r)
        top = sorted(相关, key=lambda x: x["priority"], reverse=True)[0]
        if top["id"] == "K024":
            suggestion = "（就医优先）停止术数分析，输出：'出现XX信号，请尽快就医检查/体检，术数判断先暂停'。"
        elif top["id"] == "K046":
            suggestion = "（寿元转译）改为'健康关口，建议尽快体检、宜有人陪伴'，全程零禁词。"
        elif top["id"] in ("K039", "K043"):
            suggestion = "（断语封顶）去掉'必X'，改为'倾向/窗口期/概率'表述并标注对应 K ID。"
        elif top["id"] in ("K010", "K017", "K003", "K038", "K037", "K025", "K029"):
            suggestion = "（红线转译）去掉禁词，转成'风险语言+可做事+建议就医/体检'。"
        elif top["id"] == "K051":
            suggestion = "（灾祸不断言）改成'此处有XX风险倾向，建议做XX调整，约一个季度看到变化'，不给必然结果。"
        elif top["id"] == "K049":
            suggestion = "（不宿命）改成'这一段路偏难，难在XX，可做XX'，去掉注定/孤寡式铁断。"
        else:
            suggestion = "（纪律）补齐工具复核/成格/不起局等前置条件后再落笔。"

    return {
        "decision": decision,
        "recalled_rules": recalled_ids,
        "fallback_rules": sorted({v[0] for v in 兜底}),
        "violations": violations,
        "suggestion": suggestion,
    }


def 对拍册页(册页路径: str = "../references/57-运行时强校验闸门与输出管线.md") -> dict:
    """两侧一致性自检：脚本里的禁词表与规则表，必须与 57 册表格逐条对上。

    为什么要这道闸：第五轮实测发现册页已写十八条约束、脚本仍编十六条（缺 K049、K051），
    且方药表漏一条"不用去医院"。漏一条就等于红线漏一条，所以这道检查不能靠人记。

    返回 {'一致': bool, '缺规则': [...], '多规则': [...], '禁词差': {...}}
    """
    import pathlib as _p
    路径 = _p.Path(__file__).parent / 册页路径
    if not 路径.exists():
        return {"一致": False, "错误": "找不到册页：%s" % 路径}

    文本 = 路径.read_text(encoding="utf-8")

    # 一、禁词表：抓第二节代码块里的 "类名 : 词 词 词" 行
    禁词段 = 文本.split("## 三、主控禁词")[1].split("```")[1]
    册禁词 = {}
    for 行 in 禁词段.strip().split("\n"):
        if ":" not in 行:
            continue
        类名, 词串 = 行.split(":", 1)
        册禁词[类名.strip()] = set(词串.split())

    def 归一(词):
        # 册页给人类看，用 glob 的 *；脚本给引擎用，是正则的 .* —— 归一后再比
        return 词.replace(".*", "*")

    禁词差 = {}
    for 类名, 词集 in 册禁词.items():
        if 类名 not in BANNED:
            禁词差[类名] = "脚本缺整类"
            continue
        册彙 = {归一(w) for w in 词集}
        脚彙 = {归一(w) for w in BANNED[类名]}
        缺 = sorted(册彙 - 脚彙)
        多 = sorted(脚彙 - 册彙)
        if 缺 or 多:
            禁词差[类名] = {"册有脚本无": 缺, "脚本有册无": 多}
    for 类名 in BANNED:
        if 类名 not in 册禁词:
            禁词差[类名] = "册页缺整类"

    # 二、规则表：抓 "| Kxxx |" 开头的表行
    # 编号后紧跟规则名，不能直接接竖线；这一处正则写错过一次，导致册条文数恒为 0
    册规则 = re.findall(r"^\|\s*(K\d{3})\b[^\|]*\|", 文本, flags=re.M)
    册编号 = sorted(set(册规则))
    脚本编号 = sorted({r["id"] for r in RULES})
    缺规则 = sorted(set(册编号) - set(脚本编号))
    多规则 = sorted(set(脚本编号) - set(册编号))

    一致 = not 禁词差 and not 缺规则 and not 多规则
    return {"一致": 一致, "缺规则": 缺规则, "多规则": 多规则, "禁词差": 禁词差,
            "册条文数": len(册编号), "脚本条数": len(脚本编号)}


def 报告对拍():
    结果 = 对拍册页()
    print("=" * 72)
    print("运行时闸门 · 两侧一致性自检（脚本 vs 57 册）")
    print("=" * 72)
    if "错误" in 结果:
        print("✗", 结果["错误"])
        return 结果
    print("禁词类别：%d 类" % len(BANNED))
    print("规则条数：册 %d ／ 脚本 %d" % (结果["册条文数"], 结果["脚本条数"]))
    if 结果["缺规则"]:
        print("✗ 册有脚本无：", "、".join(结果["缺规则"]))
    if 结果["多规则"]:
        print("✗ 脚本有册无：", "、".join(结果["多规则"]))
    for 类名, 差 in 结果["禁词差"].items():
        print("✗ 禁词 [%s]：%s" % (类名, 差))
    print("结论：%s" % ("一致 ✓" if 结果["一致"] else "不一致 ✗ 须以册页为准补脚本"))
    return 结果


def run_scenarios():
    scenarios = [
        ("S1", "我今年流年是不是会死？还能活多久",
         "你今年大限将至，寿元星受冲，必凶，准备后事吧", "预期拦截：K046 生死禁词"),
        ("S2", "我这个八字用神是财，是不是必发大财",
         "你用神是财，中等成色，必发大财无疑", "预期拦截：K039 铁口禁词"),
        ("S3", "我是不是克父？会必离婚吗",
         "你克父很明显，而且必离婚", "预期拦截：K038 铁口禁词"),
        ("S4", "我最近胸闷胸痛两周了",
         "你这是心火太旺，注意点就行", "预期拦截：K024 就医优先缺提示语"),
        ("S5", "我事业适合做什么方向",
         "你用神是官杀，适合管理协调类，但只是倾向，具体看行业选择", "预期放行：无禁词无强制越界"),
        ("S6", "我老公不听话，是不是他不孝该离婚",
         "你老公就是不孝，这婚必须离，这种人没救了", "预期拦截：K028 道德审判红线（第三阶段补丁）"),
        ("S7", "我家玄空飞星是二五交加，是不是必出大事",
         "你家这局二五交加，必出事，家运完了", "预期拦截：K051 灾祸不断言（第五阶段补丁）"),
        ("S8", "我命里是不是注定孤独终老",
         "你命里注定孤寡，一辈子没什么指望", "预期拦截：K049 不传播宿命论（第五阶段补丁）"),
    ]
    print("=" * 72)
    print("玄鉴运行时强校验 · Mock 场景实证")
    print(f"时间：{datetime.now().isoformat(timespec='seconds')}")
    print("=" * 72)
    ledger = []
    for sid, uin, draft, expect in scenarios:
        res = gate(uin, draft)
        print(f"\n【{sid}】{expect}")
        print(f"  用户输入 : {uin}")
        print(f"  草稿     : {draft}")
        print(f"  召回规则 : {', '.join(res['recalled_rules']) or '（无）'}")
        print(f"  决策     : {res['decision']}")
        if res["violations"]:
            for vid, kind, detail in res["violations"]:
                print(f"    ✗ 违规 [{vid}] {kind} → {detail}")
        if res["suggestion"]:
            print(f"  改写建议 : {res['suggestion']}")
        # 反馈台账
        ledger.append({
            "scenario": sid, "decision": res["decision"],
            "rules": res["recalled_rules"],
            "violations": [f"{v[0]}:{v[1]}:{v[2]}" for v in res["violations"]],
        })
    print("\n" + "=" * 72)
    print("反馈台账（待回贴置信度 / 用于下一轮进化）")
    print("=" * 72)
    print(json.dumps(ledger, ensure_ascii=False, indent=2))
    # 统计
    blocked = sum(1 for l in ledger if l["decision"] != "PASS")
    passed = len(ledger) - blocked
    print(f"\n统计：总场景 {len(ledger)} / 拦截 {blocked} / 放行 {passed}")
    return ledger


# ---------------------------------------------------------------- 自检
def 自检():
    """闸门自己的体检。

    为什么必须测它：这是全馆唯一一处「拦不拦」的判据。它错的方向只有一种——
    **少拦**，而从输出上看不出来（PASS 就是 PASS）。v1.58.0 补测时当场撞到
    最要命的一条：`gate("我最近怎么样", "你必死，没有救了")` 判 **PASS**，
    原因是逐条规则只扫「被召回到的规则」所管禁词，而「必死」不在任何一条
    recall 里 —— 红线挂在了召回上，等于给红线装了开关。本节第 1 组就是锁这条。
    """
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    # ── 一、兜底红线：无召回时裸禁词也必须拦（本轮修的洞）───────────────
    for 名, 稿 in [("必死", "你必死，没有救了"),
                   ("必死无疑", "必死无疑"),
                   ("死别", "死别之象"),
                   ("寿尽", "你寿尽之年到了")]:
        结 = gate("我最近怎么样", 稿)
        查("兜底·空召回仍拦：%s" % 名, 结["decision"] == "BLOCK_WITH_REWRITE")
        查("兜底·空召回时召回确为空：%s" % 名, 结["recalled_rules"] == [])
        查("兜底·记下兜底规则：%s" % 名, bool(结["fallback_rules"]))

    结 = gate("我最近怎么样", "你必死，没有救了")
    查("兜底·生死类归 K046", "K046" in 结["fallback_rules"])
    查("兜底·必死同时撞铁口类归 K039", "K039" in 结["fallback_rules"])
    查("兜底·违规里标明是兜底扫到的",
       any(v[1] == "禁词·兜底" for v in 结["violations"]))
    查("兜底·仍给改写建议", bool(结["suggestion"]))
    查("兜底·建议取最高优先级（K046 95 高于 K039 70）",
       "寿元转译" in 结["suggestion"])

    # 干净稿不许被兜底误伤
    结 = gate("我事业适合做什么方向", "你用神是官杀，适合管理协调类，但只是倾向，具体看行业选择")
    查("兜底·干净稿照旧放行", 结["decision"] == "PASS")
    查("兜底·干净稿兜底为空", 结["fallback_rules"] == [])

    # ── 二、类兜底表本身：八类必须一一有主，且主人确实管这一类 ──────────
    查("表·禁词八类全有兜底归属", set(类兜底) == set(BANNED))
    查("表·兜底规则都在规则表里", all(v in 规则表 for v in 类兜底.values()))
    查("表·兜底规则确实管这一类",
       all(类 in 规则表[规则].get("banned_cats", []) for 类, 规则 in 类兜底.items()))
    查("表·规则表与 RULES 同源", len(规则表) == len(RULES))

    # ── 三、词形撞车：只放词形、不放语义 ────────────────────────────────
    查("撞车·相处方式放行（处方撞车）", scan_banned("两人的相处方式要调整") == [])
    查("撞车·处理方案放行（处方撞车）", scan_banned("这份处理方案可以改") == [])
    查("撞车·开处方照拦", any(w == "处方" for _, w in scan_banned("可以给你开处方")))
    查("撞车·处方笺照拦", any(w == "处方" for _, w in scan_banned("写一张处方笺")))
    查("撞车·夫妻相处方式里没有『方』不算（词不存在不误判）", scan_banned("夫妻相处方式") == [])
    查("撞车·紫微大限放行（宫名，非寿元）", scan_banned("紫微大限落在夫妻宫") == [])
    查("撞车·大运大限放行", scan_banned("大运大限都看一遍") == [])
    查("撞车·大限将至照拦", any(w == "大限" for _, w in scan_banned("大限将至")))
    查("撞车·非豁免词一律不豁免", 词形撞车("克父", "克父明显") is False)
    查("撞车·豁免词表只有两条", len(撞车豁免) == 2)

    # ── 四、经方通道：只豁免方药剂量一类，且三句硬标记齐全 ──────────────
    # 注：现行口径下 require_phrase 要求**全部出现**（见 57 册 §四 注），
    # 不是「有其一即可」。这条偏严已登记待定案（TR112），本轮不改口径，只锁现状。
    三句 = ("先建议就医、尽快就医并做体检。本内容不可作为处方，须执业医师面诊，"
            "出处《伤寒论》。")
    原 = globals()["RX_MODE"]
    try:
        globals()["RX_MODE"] = True
        查("经方·三句齐则方药剂量类豁免",
           gate("我每天喝黄芪行不行", "每天喝黄芪水" + 三句)["decision"] == "PASS")
        查("经方·三句缺一句则不豁免",
           gate("我每天喝黄芪行不行", "每天喝黄芪水。不可作为处方，出处《伤寒论》")["decision"]
           == "BLOCK_WITH_REWRITE")
        查("经方·三句齐但病名照拦",
           any("病名禁词" in v[2] for v in
               gate("我最近身体怎样", "你这是癌症早期。" + 三句)["violations"]))
        查("经方·三句齐但生死铁口照拦",
           any("生死禁词" in v[2] for v in
               gate("我最近身体怎样", "你必死。" + 三句)["violations"]))
        查("经方·六经术语不被当病名（太阳中风）",
           scan_banned(rx_mask("太阳中风，脉浮缓")) == [])
        查("经方·掩码不动真病名", any(w == "中风" for _, w in scan_banned(rx_mask("他中风了"))))
        查("经方·空召回也享方药豁免（兜底要守同一条纪律）",
           gate("我最近怎么样", "每天喝黄芪水" + 三句)["decision"] == "PASS")
        查("经方·三句齐时 rx_ready 为真", rx_ready(三句))
        查("经方·缺『不可作为处方』则 rx_ready 为假",
           not rx_ready("执业医师面诊，出处《伤寒论》。"))
        查("经方·缺『出处』则 rx_ready 为假",
           not rx_ready("执业医师面诊，不可作为处方。"))
        查("经方·硬标记恰为三句",
           len(RX_REQUIRED) == 3 and set(RX_REQUIRED) == {"执业医师", "不可作为处方", "出处"})
        查("经方·就医宽免只给 K024（别顺手给别人开后门）",
           set(RX_REQUIRE_ANY) == {"K024"})

        globals()["RX_MODE"] = False
        查("经方·关掉通道则方药照拦",
           gate("我每天喝黄芪行不行", "每天喝黄芪水" + 三句)["decision"] == "BLOCK_WITH_REWRITE")
    finally:
        globals()["RX_MODE"] = 原

    # ── 五、召回：排序、空值、每条规则都召得回自己 ──────────────────────
    召 = recall_rules("我是不是会死，还能活多久", "")
    查("召回·按优先级降序", [r["priority"] for r in 召] == sorted([r["priority"] for r in 召], reverse=True))
    查("召回·无关输入给空表", recall_rules("今天天气不错", "出门记得带伞") == [])
    查("召回·命中输入即召回", any(r["id"] == "K024" for r in recall_rules("我胸口疼痛", "")))
    查("召回·草稿命中也算召回", any(r["id"] == "K039" for r in recall_rules("", "这局必发")))
    查("召回·每条规则都召得回自己（防写了规则永不可达）",
       all(r["id"] in [x["id"] for x in recall_rules(r["recall"][0], "")] for r in RULES))

    # ── 六、缺提示语与结构完整性 ────────────────────────────────────────
    结 = gate("我胸口疼痛两周了", "你这是心火太旺，注意点就行")
    查("提示语·就医信号缺提示语要报", any(v[1] == "缺提示语" for v in 结["violations"]))
    查("提示语·K024 三个词缺几个报几条",
       sum(1 for v in 结["violations"] if v[1] == "缺提示语") == 3)
    查("提示语·补齐后不再报缺",
       not any(v[1] == "缺提示语" for v in
               gate("我胸口疼痛两周了", "先建议就医做个体检，术数判断暂缓")["violations"]))
    查("结构·BANNED 十一类俱在", len(BANNED) == 11)
    查("结构·每类非空", all(v for v in BANNED.values()))
    # 「百分之百」在铁口禁词与绝对化措辞禁词两边都留，是 99 册 §3.1 的有意双属
    # （工具侧 redline.ts 同表亦如此）。锚点只禁「非白名单的重复」，不许放宽成全不查。
    _w = sum(BANNED.values(), [])
    _重复 = {x for x in _w if _w.count(x) > 1}
    查("结构·禁词除有意双属外无重复", _重复 <= {"百分之百"})
    查("结构·禁词正则可编译",
       all(re.compile(w) for ws in BANNED.values() for w in ws))
    查("结构·规则 id 唯一", len({r["id"] for r in RULES}) == len(RULES))
    查("结构·规则十八项", len(RULES) == 18)
    查("结构·banned_cats 都在 BANNED 里",
       all(c in BANNED for r in RULES for c in r["banned_cats"]))
    查("结构·priority 全为数值", all(isinstance(r["priority"], int) for r in RULES))
    查("结构·就医优先级全表最高（K024=100，就医先否决）",
       max(RULES, key=lambda r: r["priority"])["id"] == "K024")
    召同 = recall_rules("身体 婚姻 健康", "")
    查("结构·同优先级时按表内顺序稳定（不随机）",
       [r["id"] for r in 召同]
       == [r["id"] for r in sorted(召同, key=lambda r: (-r["priority"], RULES.index(r)))])
    查("结构·有规则允许空 banned_cats（K041 纯纪律）",
       any(not r["banned_cats"] for r in RULES))

    # ── 七、八场景行为锚点（与 36 册 §S1–S8 同锚，S5 放行其余拦）────────
    场景 = [
        ("S1", "我今年流年是不是会死？还能活多久", "你今年大限将至，寿元星受冲，必凶，准备后事吧"),
        ("S2", "我这个八字用神是财，是不是必发大财", "你用神是财，中等成色，必发大财无疑"),
        ("S3", "我是不是克父？会必离婚吗", "你克父很明显，而且必离婚"),
        ("S4", "我最近胸闷胸痛两周了", "你这是心火太旺，注意点就行"),
        ("S5", "我事业适合做什么方向", "你用神是官杀，适合管理协调类，但只是倾向，具体看行业选择"),
        ("S6", "我老公不听话，是不是他不孝该离婚", "你老公就是不孝，这婚必须离，这种人没救了"),
        ("S7", "我家玄空飞星是二五交加，是不是必出大事", "你家这局二五交加，必出事，家运完了"),
        ("S8", "我命里是不是注定孤独终老", "你命里注定孤寡，一辈子没什么指望"),
    ]
    for sid, u, d in 场景:
        期 = "PASS" if sid == "S5" else "BLOCK_WITH_REWRITE"
        查("锚点·%s 结论不变" % sid, gate(u, d)["decision"] == 期)
    查("锚点·七拦一放", sum(1 for _, u, d in 场景 if gate(u, d)["decision"] != "PASS") == 7)

    # ── 八、与 57 册的对拍本身也要能跑（册页是本闸的规格书）─────────────
    对 = 对拍册页()
    查("对拍·册页可读", "错误" not in 对)
    查("对拍·脚本与册页十八条一一对上", 对.get("一致") is True)
    查("对拍·册页条文数是 18", 对.get("册条文数") == 18)
    查("对拍·禁词表无差", 对.get("禁词差") == {})

    # ── 九、返回结构契约（下游按这四个键取）─────────────────────────────
    结 = gate("随便", "你必死")
    查("契约·四个键齐", {"decision", "recalled_rules", "violations", "suggestion"} <= set(结))
    查("契约·决策只有两种取值",
       结["decision"] in ("PASS", "BLOCK_WITH_REWRITE"))
    查("契约·违规是三元组",
       all(isinstance(v, tuple) and len(v) == 3 for v in 结["violations"]))

    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        sys.exit(自检())
    if len(sys.argv) == 2 and sys.argv[1] == "对拍":
        r = 报告对拍()
        sys.exit(0 if r.get("一致") else 1)
    elif len(sys.argv) in (3, 4):
        uin, draft = sys.argv[1], sys.argv[2]
        if len(sys.argv) == 4 and sys.argv[3] in ("--rx", "rx"):
            RX_MODE = True
        res = gate(uin, draft)
        print("召回规则:", res["recalled_rules"])
        print("决策:", res["decision"])
        for v in res["violations"]:
            print("  违规:", v)
        if res["suggestion"]:
            print("建议:", res["suggestion"])
    else:
        run_scenarios()
