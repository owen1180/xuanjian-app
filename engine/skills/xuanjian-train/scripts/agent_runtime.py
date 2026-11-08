#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 104 · AI Agent 工具层与统一输入包（照单全学 · AI Agent 集成能力）。

借 yuan 统一输入包 / `runnable|partial|blocked` 三态、mingpan 的 MCP tool
schema 与「只输出确定性排盘量、解读层交 AI」分层、chinese-fortune 的成稿前
机械核对（源码研读报告 `13-rest-source.md` §2/§4）；本文件为**本馆自撰**。

与「各安其位」对齐（这是与 yuan 的根本分歧）：
- 派单时每份任务包**不含他人结论**，`no_peer_results=True`；
- 成员只挂自己专长那条线，越线派单直接拒绝；
- `cross_check()` 只有在**所有线都独立 submit 完结论后**才放行，且由主理人主持；
- 分歧对主理人全量保留，不隐藏；
- 工具层只输出确定性事实（排盘量、口径卡、闸门结论），**绝不产断语**。

用法：
  python3 agent_runtime.py tools
  python3 agent_runtime.py call --tool xuanjian.validate_input --args '<json>'
  python3 agent_runtime.py --selftest
"""
import argparse
import json
import sys

OWNER = {
    "bazi": "知微", "sizhu": "知微", "dayun": "知微", "liunian": "知微",
    "ziwei": "斗枢", "doushu": "斗枢", "feixing": "斗枢",
    "xiangfa": "明相", "mianxiang": "明相", "shouxiang": "明相",
    "fengshui": "青囊", "yangzhai": "青囊", "yinzhai": "青囊", "luopan": "青囊",
    "liuyao": "观象", "meihua": "观象", "xiaoliuren": "观象",
    "qimen": "司辰", "zeri": "司辰", "huangli": "司辰",
    "qiming": "正名", "kangxi": "正名", "hehun": "赤绳",
    "meng": "南柯", "jingfang": "南阳",
}
REFERENCE_ONLY = {"western_astrology", "vedic", "numerology", "chenggu",
                  "tarot", "ACG", "planetarium", "celebrity_db"}
REQUIRED = ["gender", "birth_solar", "question", "tech_requested"]
SECTIONS = ["资料确认", "口径卡", "各线独立结论", "交叉核对", "趋吉避凶", "边界声明"]
BOUNDARY = [
    "不把术数说成科学定论", "不虚构星曜宫位或排盘事实",
    "不泄漏内部中间件与过程叙述", "本人终点永不可断",
    "不诊断疾病、不预测死亡、不下交易指令",
]
FACT_ONLY_NOTE = ("本工具只输出确定性事实（排盘量、口径卡、闸门结论）；"
                  "五行强弱、格局、用神、断语属解读层，由对应成员独立给出。")


def validate_input(pkg: dict) -> dict:
    """统一输入包：缺项先问，三态返回，绝不猜。"""
    ambiguities, actions = [], []
    for k in REQUIRED:
        if k not in pkg or pkg[k] in (None, "", []):
            ambiguities.append(f"缺 {k}")
            actions.append(f"补齐 {k} 后再派单")
    solar = pkg.get("birth_solar") or {}
    if set(solar) < {"y", "m", "d"}:
        ambiguities.append("出生公历年月日不齐")
        actions.append("补齐 y/m/d；农历须先换算并注明换算依据")
    if pkg.get("gender") not in ("male", "female"):
        ambiguities.append("性别非 male/female")
        actions.append("明确性别，禁止把非 male 静默当女")
    if "hour_index" not in pkg and not pkg.get("hour_unknown"):
        ambiguities.append("时辰索引未给且未声明时辰不详")
        actions.append("给 0–11 时辰索引，或显式 hour_unknown=true")
    hi = pkg.get("hour_index")
    if hi is not None and (not isinstance(hi, int) or not 0 <= hi <= 11):
        ambiguities.append("hour_index 越界")
        actions.append("只能是 0–11 整数，禁止 0–23 钟点与静默取模")
    if not pkg.get("longitude") and not pkg.get("birth_place"):
        ambiguities.append("未填出生地／经度")
        actions.append("不填出生地就不做真太阳时校正；如需校正请补经度")
    bad_tech = [t for t in (pkg.get("tech_requested") or [])
                if t in REFERENCE_ONLY]
    if bad_tech:
        ambiguities.append(f"只读参考技法不可派单：{bad_tech}")
        actions.append("改派本馆十线技法；只读项仅作背景参考")
    if ambiguities:
        status = "blocked" if any("缺 " in x for x in ambiguities) else "partial"
    else:
        status = "runnable"
    return {"status": status, "ambiguities": ambiguities,
            "recommended_actions": actions, "accepted": status == "runnable",
            "note": FACT_ONLY_NOTE}


def dispatch(pkg: dict) -> dict:
    """按技法生成独立任务包：彼此看不到对方结论。

    只读参考／未登记技法只列入 rejected，不阻断整单——用户可能同时请求
    本馆十线与参考项；但若过滤后无一条可派单，则整单 BLOCKED。
    """
    req = pkg.get("tech_requested") or []
    rejected = [{"tech": t, "reason": "只读参考或未登记，不派单"}
                for t in req if t in REFERENCE_ONLY or t not in OWNER]
    effective = dict(pkg)
    effective["tech_requested"] = [t for t in req
                                   if t not in REFERENCE_ONLY and t in OWNER]
    v = validate_input(effective)
    if not v["accepted"] or not effective["tech_requested"]:
        return {"status": "BLOCKED",
                "reason": "输入包未达 runnable 或无可派单技法",
                "input_gate": v, "rejected": rejected}
    packets = []
    for tech in effective["tech_requested"]:
        owner = OWNER[tech]
        packets.append({
            "tech": tech, "owner": owner, "isolation": "independent",
            "no_peer_results": True,
            "input": {k: pkg[k] for k in pkg if k != "tech_requested"},
            "must_finish_before_cross_check": True,
            # R-033 收窄（只管本人终点）／R-035 新立（健康关口可算到年）后的派单禁项：
            # 不再把「寿元」整个话题列为禁做，只禁判终点；说法走 46 §1.1 合规对照表。
            "forbidden": ["替其他线出结论", "读他人结论", "判本人终点", "确定性分数"],
        })
    return {"status": "OK", "packets": packets, "rejected": rejected,
            "cross_check_allowed": False,
            "cross_check_note": "须各线独立出完结论后，由主理人主持方可互通"}


def cross_check(state: dict) -> dict:
    """唯一互通闸门：所有人独立交卷前一律 BLOCKED。"""
    requested = state.get("requested") or []
    submitted = state.get("submitted") or {}
    missing = [t for t in requested if t not in submitted]
    if missing:
        return {"status": "BLOCKED", "missing": missing,
                "reason": "成员须先各自独立出完结论，禁止先互通再合参"}
    leaked = [t for t, r in submitted.items()
              if r.get("peer_results_seen") or r.get("no_peer_results") is False]
    if leaked:
        return {"status": "BLOCKED", "leaked": leaked,
                "reason": "检测到结论先于核对／读过他人结论，独立性已被破坏"}
    return {
        "status": "OK", "host": "主理人", "sections": SECTIONS,
        "divergences_visible_to_host": True,
        "divergence_policy": "分歧分别说明、全量保留，不加权互证、不隐藏",
        "boundary": BOUNDARY,
        "note": "交叉核对只做合参，不替任何成员改自己那条线的结论",
    }


def call_tool(name: str, args: dict) -> dict:
    """MCP-like 调用：统一 {content:[{type:'text',text}], isError} 返回。"""
    def ok(text):
        return {"content": [{"type": "text", "text": text}]}

    def err(msg):
        return {"content": [{"type": "text", "text": f"Error: {msg}"}],
                "isError": True}
    try:
        if name == "xuanjian.validate_input":
            return ok(json.dumps(validate_input(args), ensure_ascii=False))
        if name == "xuanjian.dispatch":
            return ok(json.dumps(dispatch(args), ensure_ascii=False))
        if name == "xuanjian.cross_check":
            return ok(json.dumps(cross_check(args), ensure_ascii=False))
        if name == "xuanjian.owner_of":
            tech = args.get("tech")
            if tech in REFERENCE_ONLY:
                return err(f"{tech} 只读参考，不派单")
            if tech not in OWNER:
                return err(f"未登记技法 {tech}")
            return ok(json.dumps({"tech": tech, "owner": OWNER[tech]},
                                 ensure_ascii=False))
        if name == "xuanjian.boundary":
            return ok(json.dumps({"boundary": BOUNDARY,
                                  "note": FACT_ONLY_NOTE}, ensure_ascii=False))
        return err(f"unknown tool {name}")
    except Exception as e:  # 协议错误转可读失败，便于宿主自行修正参数
        return err(f"{type(e).__name__}: {e}")


TOOLS = [
    {"name": "xuanjian.validate_input", "title": "统一输入包闸门",
     "description": "校验出生资料与技法请求，返回 runnable/partial/blocked 三态。"
                    + FACT_ONLY_NOTE,
     "input_schema": {"gender": "enum[male,female]", "birth_solar": "object{y,m,d}",
                      "hour_index": "int 0-11", "longitude": "number?",
                      "question": "string", "tech_requested": "string[]"}},
    {"name": "xuanjian.dispatch", "title": "各线独立派单",
     "description": "按技法生成互不可见的任务包；不产断语、不读他人结论。",
     "input_schema": {"gender": "enum", "birth_solar": "object", "hour_index": "int",
                      "question": "string", "tech_requested": "string[]"}},
    {"name": "xuanjian.cross_check", "title": "交叉核对闸门",
     "description": "仅当所有线独立交卷后放行；由主理人主持，分歧全量保留。",
     "input_schema": {"requested": "string[]", "submitted": "object"}},
    {"name": "xuanjian.owner_of", "title": "技法归属查询",
     "description": "只返回确定性归属事实，不解读盘面。",
     "input_schema": {"tech": "string"}},
    {"name": "xuanjian.boundary", "title": "边界声明",
     "description": "返回本馆边界清单与工具层定位说明。",
     "input_schema": {}},
]


def selftest():
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    pkg = {"gender": "male", "birth_solar": {"y": 1990, "m": 1, "d": 1},
           "hour_index": 0, "longitude": 116.4, "question": "问事业",
           "tech_requested": ["bazi", "ziwei"]}
    v = validate_input(pkg)
    ck("完整输入 runnable", v["status"] == "runnable" and v["accepted"])
    ck("缺性别 blocked", validate_input({k: val for k, val in pkg.items()
                                    if k != "gender"})["status"] == "blocked")
    ck("时辰越界 partial", validate_input(dict(pkg, hour_index=23))["status"] == "partial")
    ck("0–23 钟点被拦", any("越界" in x for x in
                        validate_input(dict(pkg, hour_index=23))["ambiguities"]))
    ck("不填出生地给提示", any("真太阳时" in x for x in
                         validate_input({k: val for k, val in pkg.items()
                                         if k != "longitude"})["recommended_actions"]))
    ck("只读技法被拦", validate_input(dict(pkg, tech_requested=["vedic"]))["status"] == "partial")
    d = dispatch(pkg)
    ck("派单成功", d["status"] == "OK" and len(d["packets"]) == 2)
    ck("任务包互相隔离", all(p["no_peer_results"] for p in d["packets"]))
    ck("任务包不含技法清单", all("tech_requested" not in p["input"] for p in d["packets"]))
    ck("归属正确", {p["tech"]: p["owner"] for p in d["packets"]} ==
       {"bazi": "知微", "ziwei": "斗枢"})
    ck("派单时禁止合参", d["cross_check_allowed"] is False)
    ck("只读项被拒", dispatch(dict(pkg, tech_requested=["vedic"]))["rejected"])
    ck("输入不全不派单", dispatch({})["status"] == "BLOCKED")
    state = {"requested": ["bazi", "ziwei"], "submitted": {}}
    ck("未交卷 BLOCKED", cross_check(state)["status"] == "BLOCKED")
    ck("缺一条也 BLOCKED", cross_check(dict(state, submitted={
        "bazi": {"ok": True}}))["status"] == "BLOCKED")
    full = {"requested": ["bazi", "ziwei"],
            "submitted": {"bazi": {"ok": True, "no_peer_results": True},
                          "ziwei": {"ok": True, "no_peer_results": True}}}
    cc = cross_check(full)
    ck("全部独立交卷放行", cc["status"] == "OK")
    ck("分歧对主理人可见", cc["divergences_visible_to_host"])
    ck("读到他人结论即 BLOCKED", cross_check(dict(full, submitted={
        "bazi": {"ok": True, "peer_results_seen": True},
        "ziwei": {"ok": True}}))["status"] == "BLOCKED")
    ck("工具 schema 完整", len(TOOLS) == 5 and all(
        {"name", "title", "description", "input_schema"} <= set(t) for t in TOOLS))
    r = call_tool("xuanjian.owner_of", {"tech": "ziwei"})
    ck("工具返回统一结构", "content" in r and r["content"][0]["type"] == "text")
    ck("未登记技法 isError", call_tool("xuanjian.owner_of",
                                  {"tech": "foo"}).get("isError") is True)
    ck("只读技法 isError", call_tool("xuanjian.owner_of",
                                 {"tech": "vedic"}).get("isError") is True)
    ck("未知道具 isError", call_tool("nope", {}).get("isError") is True)
    ck("工具不产断语", "断语" not in json.dumps(
        call_tool("xuanjian.owner_of", {"tech": "bazi"}), ensure_ascii=False))
    # 锚点随口径重算（OB98 §4）：旧断言查「寿元」二字，覆议后边界的实质是
    # 「终点不可断」＋「不预测死亡」两条，强度不降，且不许把话题整个封回去。
    ck("边界含终点红线（R-033 收窄后）",
       any("本人终点永不可断" in x for x in BOUNDARY)
       and any("不预测死亡" in x for x in BOUNDARY))
    ok = sum(v2 for _, v2 in cases)
    for n, v2 in cases:
        if not v2:
            print("FAIL", n)
    print(f"agent_runtime selftest: {ok}/{len(cases)} passed")
    return 0 if ok == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="tools")
    ap.add_argument("--tool"); ap.add_argument("--args")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or a.cmd == "selftest":
        return selftest()
    if a.cmd == "tools":
        print(json.dumps(TOOLS, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "call":
        args = json.loads(a.args or "{}")
        out = call_tool(a.tool or "", args)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1 if out.get("isError") else 0
    if a.cmd == "boundary":
        print(json.dumps({"boundary": BOUNDARY, "sections": SECTIONS},
                         ensure_ascii=False, indent=2))
        return 0
    print("unknown cmd", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
