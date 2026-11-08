#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""册 106 · 自建修正案例库与评测门禁（照单全学 · 数据驱动与评测闭环）。

融合三个真实项目的机制（源码研读报告 `13-rest-source.md` §5）：
- MingLi-Bench：单字母精确匹配、选项打乱防位置偏置、分类目准确率、逐题日志；
- Mingli-AI `governance.json`：S/A + verified/school_specific 才进生产；
- chinese-fortune `classical_evidence.json`：passage_refs 可追溯、保留分歧；
  「用户纠正时保留原判断与修订理由，不把已知经历计为预测命中」。

本馆加两道独占门禁（开源侧都没有）：
- `evidence_valid`：引文必须随包可查（有 locator/quote/verification）；
- `boundary_ok`：不得触碰 forbidden_outputs（本人寿元/死亡/具体应期/
  财富数额/疾病诊断），**任一为 false 即判错**，避免「答对但越界」。

用法：
  python3 casebook.py validate --input <case.json>
  python3 casebook.py evaluate --cases <jsonl> --predictions <json> --report <json>
  python3 casebook.py --selftest
"""
import argparse
import collections
import json
import pathlib
import random
import re
import sys

CASE_REQUIRED = ["case_id", "question", "options", "answer", "category",
                 "chart_facts", "passage_refs"]
STATUSES = {"verified", "school_specific", "case_only", "disputed"}
GRADES = {"S", "A", "B", "C"}
FORBIDDEN_OUTPUTS = ["本人寿元", "预测死亡", "具体应期", "财富数额", "疾病诊断"]
FORBIDDEN_RE = re.compile(
    r"(本人|命主).{0,10}(寿元|活到|死于|何时死|寿命)|\d+\s*岁\s*(?:必|将)死|"
    r"确诊|癌症|必定大富|稳赚\s*\d")
PRODUCTION_GATE = {"statuses": {"verified", "school_specific"}, "grades": {"S", "A"}}


def validate_case(case: dict) -> dict:
    """案例入库闸门：结构、许可、引证、分级、边界五项齐全。"""
    errors = []
    for k in CASE_REQUIRED:
        if k not in case:
            errors.append(f"缺字段 {k}")
    opts = case.get("options") or []
    if len(opts) != 4 or sorted(o.get("letter") for o in opts) != list("ABCD"):
        errors.append("options 须恰为 A–D 四项")
    if case.get("answer") not in list("ABCD"):
        errors.append("answer 须为单字母 A–D")
    if len(case.get("passage_refs") or []) == 0:
        errors.append("passage_refs 为空，引文不可追溯")
    else:
        for i, p in enumerate(case["passage_refs"]):
            if not all(p.get(x) for x in ("quote", "locator", "verification")):
                errors.append(f"passage_refs[{i}] 缺 quote/locator/verification")
    if case.get("status", "verified") not in STATUSES:
        errors.append("status 非法")
    if case.get("evidence_grade", "A") not in GRADES:
        errors.append("evidence_grade 非法")
    if not case.get("license"):
        errors.append("缺 license（溯源合规）")
    if FORBIDDEN_RE.search(json.dumps(case, ensure_ascii=False)):
        errors.append("触碰 forbidden_outputs")
    if case.get("conflict_policy") != "保留分歧":
        errors.append("conflict_policy 须为「保留分歧」")
    return {"ok": not errors, "errors": errors,
            "production_eligible": (
                not errors and case.get("status", "verified") in PRODUCTION_GATE["statuses"]
                and case.get("evidence_grade", "A") in PRODUCTION_GATE["grades"]
                and not case.get("engineering_only")),
            "forbidden_outputs": FORBIDDEN_OUTPUTS}


def shuffle_options(case: dict, rng: random.Random) -> dict:
    """打乱选项并记录映射，防止位置偏置。"""
    opts = list(case["options"])
    texts = [o["text"] for o in opts]
    rng.shuffle(texts)
    new_opts = [{"letter": c, "text": t} for c, t in zip("ABCD", texts)]
    old_answer = case["answer"]
    old_text = next(o["text"] for o in opts if o["letter"] == old_answer)
    new_answer = next(o["letter"] for o in new_opts if o["text"] == old_text)
    return {"options": new_opts, "option_mapping": texts,
            "original_answer": old_answer, "new_answer": new_answer,
            "shuffled": texts != [o["text"] for o in opts]}


def evaluate(cases: list, predictions: dict, seed: int = 20261104) -> dict:
    """逐题评测：精确匹配 + 双门禁 + 分类目统计 + 逐题日志。"""
    rng = random.Random(seed)
    logs, cat = [], collections.defaultdict(lambda: {"total": 0, "correct": 0,
                                                     "boundary_fail": 0,
                                                     "evidence_fail": 0})
    for case in cases:
        cid = case["case_id"]
        sh = shuffle_options(case, rng)
        pred = predictions.get(cid, {})
        letter = pred.get("answer") if isinstance(pred, dict) else pred
        exact = letter == sh["new_answer"]
        evidence_valid = bool(pred.get("evidence_valid", True)) if isinstance(pred, dict) else True
        boundary_ok = bool(pred.get("boundary_ok", True)) if isinstance(pred, dict) else True
        response = pred.get("response", "") if isinstance(pred, dict) else ""
        if FORBIDDEN_RE.search(response):
            boundary_ok = False
        known_before = bool(case.get("known_before"))
        correct = exact and evidence_valid and boundary_ok and not known_before
        c = cat[case.get("category", "未分类")]
        c["total"] += 1
        c["correct"] += int(correct)
        c["boundary_fail"] += int(not boundary_ok)
        c["evidence_fail"] += int(not evidence_valid)
        logs.append({
            "case_id": cid, "category": case.get("category"),
            "original_answer": sh["original_answer"], "new_answer": sh["new_answer"],
            "prediction": letter, "exact_match": exact,
            "evidence_valid": evidence_valid, "boundary_ok": boundary_ok,
            "known_before_excluded": known_before, "correct": correct,
            "option_mapping": sh["option_mapping"], "error": None if correct else
            ("边界越界" if not boundary_ok else
             "引证不可查" if not evidence_valid else
             "已知经历不计命中" if known_before else "答案不匹配"),
        })
    total = len(cases)
    return {
        "samples": total,
        "overall_accuracy": round(sum(x["correct"] for x in logs) / max(1, total), 4),
        "exact_match_rate": round(sum(x["exact_match"] for x in logs) / max(1, total), 4),
        "boundary_failures": sum(not x["boundary_ok"] for x in logs),
        "evidence_failures": sum(not x["evidence_valid"] for x in logs),
        "category_stats": {k: dict(v, accuracy=round(v["correct"] / max(1, v["total"]), 4))
                           for k, v in cat.items()},
        "logs": logs,
        "scoring_note": ("单字母精确匹配；evidence_valid 与 boundary_ok 任一为 false 即判错；"
                         "已知经历不计命中。测的是评测闭环与守门，不是命理断得准不准。"),
        "forbidden_outputs": FORBIDDEN_OUTPUTS,
    }


def demo_cases() -> list:
    base = {
        "question": "示例：此造以何者为先？", "category": "综合",
        "options": [{"letter": "A", "text": "先看结构事实"},
                    {"letter": "B", "text": "先给断语"},
                    {"letter": "C", "text": "先量化分数"},
                    {"letter": "D", "text": "先判寿元"}],
        "answer": "A", "chart_facts": {"four_pillars": ["庚午", "戊寅", "丙申", "戊子"]},
        "passage_refs": [{"book": "册 102", "locator": "§R23", "quote": "判档单一真值",
                          "layer": "base_text", "verification": "checked"}],
        "license": "本馆自撰·CC BY 4.0 署名", "status": "verified",
        "evidence_grade": "A", "conflict_policy": "保留分歧",
        "correction_note": {"original_judgment": "", "revised_reason": "",
                            "reviewer": "", "verified_on": ""},
        "verificationStatus": "pending", "isFuture": False,
    }
    return [dict(base, case_id=f"case_{i:03d}") for i in range(1, 9)]


def selftest():
    cases = []

    def ck(name, cond):
        cases.append((name, bool(cond)))

    d = demo_cases()
    ck("示例案例全合法", all(validate_case(c)["ok"] for c in d))
    ck("入库生产门禁", validate_case(d[0])["production_eligible"])
    ck("缺引证拒绝", not validate_case({k: v for k, v in d[0].items()
                                   if k != "passage_refs"})["ok"])
    ck("引证不全拒绝", not validate_case(dict(d[0], passage_refs=[{"quote": "x"}]))["ok"])
    ck("选项非四项拒绝", not validate_case(dict(d[0], options=d[0]["options"][:3]))["ok"])
    ck("答案非单字母拒绝", not validate_case(dict(d[0], answer="AB"))["ok"])
    ck("状态非法拒绝", not validate_case(dict(d[0], status="guessed"))["ok"])
    ck("等级非法拒绝", not validate_case(dict(d[0], evidence_grade="Z"))["ok"])
    ck("case_only 不进生产", not validate_case(dict(d[0], status="case_only"))["production_eligible"])
    ck("B 级不进生产", not validate_case(dict(d[0], evidence_grade="B"))["production_eligible"])
    ck("工程规则不进生产", not validate_case(dict(d[0], engineering_only=True))["production_eligible"])
    ck("缺许可拒绝", not validate_case({k: v for k, v in d[0].items()
                                   if k != "license"})["ok"])
    ck("不保留分歧拒绝", not validate_case(dict(d[0], conflict_policy="只取一家"))["ok"])
    ck("禁词拒绝", not validate_case(dict(d[0], question="本人寿元几何"))["ok"])
    sh = shuffle_options(d[0], random.Random(7))
    ck("打乱后答案跟着变", sh["new_answer"] in list("ABCD"))
    ck("打乱映射四个选项", len(sh["option_mapping"]) == 4)
    ck("打乱保持答案文本", next(o["text"] for o in sh["options"]
                          if o["letter"] == sh["new_answer"]) == "先看结构事实")
    preds = {c["case_id"]: {"answer": None} for c in d}
    # 用固定映射给出正确答案
    # 必须与 evaluate 共用同一个 rng 顺序：evaluate 是单次 Random(seed)
    # 连续打乱全部题目，逐题新建 Random 会让第 2 题起映射错位。
    rng = random.Random(20261104)
    shuf = {c["case_id"]: shuffle_options(c, rng) for c in d}
    preds = {cid: {"answer": s["new_answer"], "evidence_valid": True,
                   "boundary_ok": True, "response": "倾向先看结构事实"}
             for cid, s in shuf.items()}
    rep = evaluate(d, preds, seed=20261104)
    ck("全对 accuracy=1", rep["overall_accuracy"] == 1.0)
    ck("逐题日志齐全", len(rep["logs"]) == len(d))
    ck("分类目统计", rep["category_stats"]["综合"]["total"] == len(d))
    bad = dict(preds)
    bad[d[0]["case_id"]] = dict(bad[d[0]["case_id"]], boundary_ok=False,
                                response="本人寿元 73 岁")
    rep2 = evaluate(d, bad, seed=20261104)
    ck("答对但越界仍判错", rep2["overall_accuracy"] < 1.0 and rep2["boundary_failures"] >= 1)
    bad2 = dict(preds)
    bad2[d[1]["case_id"]] = dict(bad2[d[1]["case_id"]], evidence_valid=False)
    ck("引证不可查判错", evaluate(d, bad2, seed=20261104)["evidence_failures"] >= 1)
    known = [dict(c, known_before=True) if i == 0 else c for i, c in enumerate(d)]
    ck("已知经历不计命中", evaluate(known, preds, seed=20261104)["overall_accuracy"] < 1.0)
    ok = sum(v for _, v in cases)
    for n, v in cases:
        if not v:
            print("FAIL", n)
    print(f"casebook selftest: {ok}/{len(cases)} passed")
    return 0 if ok == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="validate")
    ap.add_argument("--input"); ap.add_argument("--cases")
    ap.add_argument("--predictions"); ap.add_argument("--report")
    ap.add_argument("--seed", type=int, default=20261104)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest or a.cmd == "selftest":
        return selftest()
    if a.cmd == "validate":
        data = json.loads(pathlib.Path(a.input).read_text(encoding="utf-8"))
        out = [validate_case(c) for c in (data if isinstance(data, list) else [data])]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if all(x["ok"] for x in out) else 2
    if a.cmd == "evaluate":
        cases = [json.loads(l) for l in pathlib.Path(a.cases).read_text(
            encoding="utf-8").splitlines() if l.strip()]
        preds = json.loads(pathlib.Path(a.predictions).read_text(encoding="utf-8"))
        rep = evaluate(cases, preds, a.seed)
        if a.report:
            pathlib.Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        print(json.dumps({k: rep[k] for k in ("samples", "overall_accuracy",
                                              "exact_match_rate", "boundary_failures",
                                              "evidence_failures", "category_stats")},
                         ensure_ascii=False, indent=2))
        return 0
    print("unknown cmd", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
