#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玄鉴命理馆 · 守门语料构造器 build_corpus.py (v1.0)

把 corpus_gate.py 产出的脱敏记录，构造成四类「守门」SFT 样本。
**核心裁决：不训练断语生成模型。**
  v4.0 的 c 字段是别人的断语库确定性输出，且内嵌倪师非商用原话；
  拿它做 SFT 既违反 DATASET-LICENSE 的引文例外，又与定案级「各安其位」
  （成员只做自己专长那条线，模型不是成员）相冲突。
  因此本构造器只让模型学四件不产断语的事：
    T1 盘面校验 + 口径卡   T2 引文剥离闸门
    T3 四化白名单核对       T4 确定性事实／解读分层
  真实数据提供的是盘面分布、引文出处元数据、四化组合与 13 维结构，
  不提供任何一句断语作为 target。

输出：train.jsonl / valid.jsonl / test.jsonl（mlx-lm prompt-completion 格式）、
      MODEL_CARD.md、lora.yaml、build_manifest.json。
用法：
  python3 build_corpus.py --train-gates gated-1990.jsonl \
      --eval-gates gated-1991.jsonl --out-dir ./corpus \
      --train-charts 1500 --eval-charts 400 --seed 20261104
  python3 build_corpus.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
TOPICS = ["overview", "personality", "love", "career", "wealth", "health",
          "family", "children", "move", "friends", "home", "spirit", "parents"]
CONTENT_VERSION = "ca268829f7a9"          # MANIFEST.json 的内容版本，锁定口径
ATTRIBUTION = ("本项目使用了 紫微斗数开源解读数据集 v4.0（674,976 张命盘 × 13 维）"
               "／来源：https://github.com/Renhuai123/ziwei-doushu ／作者：王多鱼AI")
LICENSE = "CC BY 4.0（数据）；倪师原话 CC BY-NC-SA 4.0 非商用且已剥离；模型权重按底模许可"

# 与 kauding.py v1.0 switches 完全一致的固定子集（动态 hash / 时间戳不入语料）
CARD = {
    "calendar": "solar", "hour_index": "0-11", "true_solar_time": "on",
    "late_zishi": "next-day", "leap_month": "split", "dst_cn": "detect-only",
    "year_boundary": "lichun", "zi_chu_huan_ri": "23:00-next-day",
    "brightness_school": "quanshu", "sihua_school": "tongxing-feixing",
    "dayun_age": "nominal", "judging_basis": "score-py",
}
# 合成非法四化（本馆自撰规则，非数据集内容；必须显式标注 synthetic）
SYNTH_ILLEGAL = [("七杀", "化权"), ("紫微", "化忌"), ("天府", "化禄"),
                 ("左辅", "化忌"), ("天同", "化科")]


def j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# 零泄漏机械断言：语料里出现任何一句倪师原话／无引号引语／他人断语库正文，直接拒绝产出。
LEAK_PATTERNS = [
    re.compile(r"倪师(?:说|提醒|讲|云|曰|指出|直接说)"),
    re.compile(r"〔倪师[^〕]*〕"),
    re.compile(r"一点用都没有|能解一切灾厄|解厄制化的功能没有|照样发生|"
               r"天府是文官星|你是天生的|命宫坐到它的人"),
]


def assert_no_leak(path: str) -> dict:
    hits = collections.Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            s = d["prompt"] + d.get("completion", "")
            for p in LEAK_PATTERNS:
                if p.search(s):
                    hits[p.pattern] += 1
    if hits:
        raise SystemExit(f"[零泄漏断言失败] {path} 命中 {dict(hits)}；"
                         "语料不得含倪师原话正文或他人断语库正文，禁止用于训练")
    return {"file": os.path.basename(path), "leak_hits": 0, "verdict": "PASS"}


def t1(rec: dict, rng: random.Random) -> dict:
    inp = {"date": f"{rec['y']:04d}-{rec['m']:02d}-{rec['d']:02d}",
           "hour": rec["h"], "gender": rec["g"], "ming_star": rec["ms"],
           "tech": "ziwei", "school": "tianji"}
    prompt = ("【玄鉴命理馆·守门 T1】盘面校验与口径卡。只输出 JSON，不解释，不写断语。\n"
              "输入：" + j(inp))
    gold = {"task": "T1", "chart_key": rec["k"], "valid": True,
            "hour_index": rec["h"], "hour_branch": BRANCHES[rec["h"]],
            "ming_star": rec["ms"], "topic_count": 13,
            "card": CARD, "content_version": CONTENT_VERSION}
    return {"prompt": prompt, "completion": j(gold), "meta": {"task": "T1", "k": rec["k"], "synthetic": False}}


def t2(rec: dict, rng: random.Random) -> dict:
    topic = rng.choice(TOPICS)
    inv = rec["quote_inventory"][topic]
    ep = inv["ni_quote_episodes"][0] if inv["ni_quote_episodes"] else None
    page = inv["ni_quote_pages"][0] if inv["ni_quote_pages"] else None
    books = inv["classic_books"][:3]
    # 只传结构指纹，**不传任何解读文本片段**。
    # 实测发现：即便脱敏过，「倪师说天府是文官星」这类无引号引语仍会漏进片段；
    # 且片段本身是他人断语库正文。合规最稳的做法是连骨架都不进语料。
    fingerprint = {
        "topic": topic,
        "chars": rec["topic_lengths"][topic],
        "ni_label_hits": inv["ni_label_hits"],
        "ni_episode_cites": len(inv["ni_quote_episodes"]),
        "ni_page_cites": len(inv["ni_quote_pages"]),
        "classic_books": books,
        "redacted_spans": inv["quoted_spans_redacted"],
        "sihua_terms": [f"{s['star']}{s['hua']}" for s in rec["sihua"][:4]],
    }
    prompt = ("【玄鉴命理馆·守门 T2】引文剥离闸门（只给结构指纹，不传原文）。只输出 JSON。\n"
              "指纹：" + j(fingerprint))
    gold = {"task": "T2", "topic": topic,
            "ni_quote": bool(ep or page or inv["ni_label_hits"]),
            "episode": ep["ep"] if ep else None,
            "timestamp": (ep or page or {}).get("ts"),
            "classic_books": books,
            "redacted_spans": inv["quoted_spans_redacted"],
            "action": "strip", "trainable": False,
            "license": "CC BY-NC-SA 4.0",
            "reason": "倪师原话不在 v4.0 数据集授权范围，成批使用须另行授权"}
    return {"prompt": prompt, "completion": j(gold), "meta": {"task": "T2", "k": rec["k"], "synthetic": False}}


def t3(rec: dict, rng: random.Random) -> dict:
    pairs = [(s["star"], s["hua"], s["legal"]) for s in rec["sihua"]]
    picks = rng.sample(pairs, min(len(pairs), rng.randint(2, 5))) if pairs else []
    # 真实数据已删除不会发生的四化；为教会模型「拒绝」，注入 1 个显式标注的合成非法组合
    inject = rng.random() < 0.45
    if inject:
        s, h = rng.choice(SYNTH_ILLEGAL)
        picks.append((s, h, False))
    shown = [f"{s}{h}" for s, h, _ in picks]
    prompt = ("【玄鉴命理馆·守门 T3】十天干四化白名单核对。只输出 JSON。\n"
              "组合：" + "、".join(shown))
    illegal = [{"star": s, "hua": h} for s, h, ok in picks if not ok]
    gold = {"task": "T3", "checked": len(picks), "illegal": illegal,
            "action": "remove_sentences" if illegal else "pass",
            "whitelist": "十天干四化基表 甲~癸",
            "synthetic_negative": inject}
    return {"prompt": prompt, "completion": j(gold),
            "meta": {"task": "T3", "k": rec["k"], "synthetic": inject}}


def t4(rec: dict, rng: random.Random) -> dict:
    topic = rng.choice(TOPICS)
    n = rec["topic_lengths"][topic]
    prompt = ("【玄鉴命理馆·守门 T4】确定性事实／传统规则／解读／建议四层分层。只输出 JSON。\n"
              f"盘面：{rec['k']}，命宫主星={rec['ms']}；片段 topic={topic}，字符数={n}")
    gold = {"task": "T4", "topic": topic,
            "deterministic_facts": ["y", "m", "d", "h", "g", "ms", "topic_lengths"],
            "traditional_rules": ["十天干四化白名单", "五行局", "安星铁律"],
            "interpretation_owner": "对应成员（各安其位）",
            "advice_owner": "主理人",
            "model_may_output": ["口径卡", "校验结果", "分层标签", "引证闸门 verdict"],
            "model_must_not_output": ["断语", "六亲存亡", "本人寿元", "绝对化措辞"]}
    return {"prompt": prompt, "completion": j(gold), "meta": {"task": "T4", "k": rec["k"], "synthetic": False}}


TASKS = {"T1": t1, "T2": t2, "T3": t3, "T4": t4}


def load(path: str, cap: int) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if len(out) >= cap:
                break
            out.append(json.loads(line))
    return out


def split_by_key(rows: list[dict], eval_ratio: float) -> tuple[list[dict], list[dict]]:
    """按档号 hash 切分，杜绝同一张盘同时进 valid 与 test。"""
    a, b = [], []
    for r in rows:
        (a if int(hashlib.sha1(r["k"].encode()).hexdigest()[:8], 16) % 100
         < int(eval_ratio * 100) else b).append(r)
    return a, b


def emit(rows: list[dict], rng: random.Random, per_chart: int,
         tasks: list[str], path: str, with_meta: bool = False) -> dict:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    n, by_task = 0, {}
    with open(path, "w", encoding="utf-8") as f:
        for rec in rows:
            for name in rng.sample(tasks, min(per_chart, len(tasks))):
                s = TASKS[name](rec, rng)
                line = {"prompt": s["prompt"], "completion": s["completion"]}
                if with_meta:
                    line["meta"] = s["meta"]
                    line["gold"] = s["completion"]
                f.write(j(line) + "\n")
                n += 1
                by_task[name] = by_task.get(name, 0) + 1
    return {"file": os.path.basename(path), "samples": n, "by_task": by_task}


def write_model_card(path: str, train_info: dict, audit_train: dict, audit_eval: dict) -> None:
    txt = f"""# 玄鉴命理馆 · 守门模型卡（Model Card）

## 一句话
这不是「会算命的模型」，是**不产断语的守门模型**：只做盘面校验、口径卡、引文剥离、四化白名单与事实／解读分层；断语仍由对应成员各自出，交叉核对仍由主理人主持。

## 训练数据（CC BY 4.0，须署名）
{ATTRIBUTION}

- 来源：GitHub Releases `v4.0-13d`（**仅 GitHub，未从 ouranic.cn 抓取任何内容**）
- 内容版本：`{CONTENT_VERSION}`；切分口径：训练段 {audit_train.get('year_range') or audit_train.get('year') or '多年份，见 build_manifest.json'}／验证测试段 {audit_eval.get('year_range') or audit_eval.get('year') or '多年份，见 build_manifest.json'}（按年份硬切，不重叠）
- 文件 SHA-256：见同目录 `build_manifest.json`
- 许可：{LICENSE}
- **引文例外**：数据集解读内嵌倪海厦《天纪》原话，依 `DATASET-LICENSE` 不在授权范围（CC BY-NC-SA 4.0 非商用）。本管线用 `corpus_gate.py` 把**原话正文全部剥离**，语料中只保留出处元数据与结构骨架，**不含任何原话正文**。

## 训练目标（刻意不做的事）
| 做 | 不做 |
|---|---|
| T1 日期/时辰/档号校验 + 口径卡 | 生成任何性格/六亲/财富/事业断语 |
| T2 识别并剥离不可商用引文 | 复述或改写倪师原话 |
| T3 四化白名单合法性核对 | 替成员读盘、替紫微册定文武 |
| T4 事实／规则／解读／建议分层 | 断六亲存亡、断本人寿元、绝对化措辞 |

理由：定案级「各安其位」规定成员只做自己专长那条线，**模型不是成员**；把多门断法融进一个权重（真一 27B 的做法）在本馆禁止。模型产物只能作为工具层候选，须经 `source_gate.py` 发出前闸门。

## 评测边界
评测的是**格式遵循度与守门规则命中率**，不是「命理断得准不准」，不代表实际咨询效果。gold 全部由规则确定性生成，不使用模型生成的题目考模型（`98` §2）。合成负例已标 `synthetic_negative` 并单列统计。

## 使用与风险
- 输出须经 `source_gate.py` 复核；模型判定 `pass` 不等于语义正确。
- 数据「按现状」提供，免责：仅供传统文化学习研究参考，不构成医疗、投资、法律、心理咨询或人生重大决策建议，不保证 100% 准确。
- 若用于商业交付，须保留本卡署名，并确认底模许可；倪师原话仍不得成批使用。
- 生成时间：{dt.datetime.now().astimezone().isoformat(timespec='seconds')}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)


def write_lora_config(path: str, data_dir: str, adapter_dir: str) -> None:
    cfg = {
        "model": "Qwen/Qwen2.5-0.5B-Instruct",
        "train": True,
        "data": data_dir,
        "fine_tune_type": "lora",
        "optimizer": "adam",
        "lora_parameters": {"rank": 8, "alpha": 16, "dropout": 0.0, "scale": 10.0},
        "num_layers": 8,
        "batch_size": 4,
        "iters": 600,
        "learning_rate": 1e-5,
        "max_seq_length": 1024,
        "steps_per_report": 50,
        "steps_per_eval": 100,
        "save_every": 200,
        "adapter_path": adapter_dir,
        "seed": 20261104,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def selftest() -> int:
    rec = {"k": "1990-01-01-0-male", "y": 1990, "m": 1, "d": 1, "h": 0,
           "g": "male", "ms": "天府",
           "topic_lengths": {t: 1000 + i for i, t in enumerate(TOPICS)},
           "redacted": {t: "脱敏片段「[倪师原话已剥离]」（倪海厦《天纪》第5集53:06）"
                        for t in TOPICS},
           "quote_inventory": {t: {"ni_quote_episodes": [{"ep": "5", "ts": "53:06"}],
                                   "ni_quote_pages": [], "classic_books": ["紫微斗数全书"],
                                   "ni_label_hits": 2, "quoted_spans_redacted": 3}
                               for t in TOPICS},
           "sihua": [{"star": "武曲", "hua": "化禄", "legal": True},
                     {"star": "贪狼", "hua": "化权", "legal": True}]}
    rng = random.Random(20261104)
    cases = []
    for name, fn in TASKS.items():
        s = fn(rec, rng)
        gold = json.loads(s["completion"])
        prompt = s["prompt"]
        cases.append((name + " 输出为合法 JSON", isinstance(gold, dict) and gold["task"] == name))
        cases.append((name + " prompt 不含原话正文", "一点用都没有" not in prompt and "能解一切灾厄" not in prompt))
        cases.append((name + " prompt 不含断语样例", "你是天生的" not in prompt))
    s2 = TASKS["T2"](rec, rng)
    cases.append(("T2 只传结构指纹不传原文片段",
                  "指纹：" in s2["prompt"] and "片段：" not in s2["prompt"]))
    cases.append(("T2 gold 不含原话", "天府是文官星" not in s2["completion"]))
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as tf:
        tf.write(j({"prompt": "倪师说天府是文官星", "completion": "{}"}) + "\n")
        tmp = tf.name
    try:
        assert_no_leak(tmp)
        blocked = False
    except SystemExit:
        blocked = True
    os.unlink(tmp)
    cases.append(("零泄漏断言能拦下含原话语料", blocked))
    cases.append(("T1 时辰地支正确", json.loads(TASKS["T1"](rec, rng)["completion"])["hour_branch"] == "子"))
    cases.append(("T1 判档口径锁死 score-py", json.loads(TASKS["T1"](rec, rng)["completion"])["card"]["judging_basis"] == "score-py"))
    cases.append(("T2 引文 trainable=False", json.loads(TASKS["T2"](rec, rng)["completion"])["trainable"] is False))
    cases.append(("T4 禁止断寿元", "本人寿元" in json.loads(TASKS["T4"](rec, rng)["completion"])["model_must_not_output"]))
    a, b = split_by_key([{"k": f"1990-01-01-{i}-male"} for i in range(100)], 0.3)
    cases.append(("按档号切分不重叠", not ({x["k"] for x in a} & {x["k"] for x in b}) and len(a) + len(b) == 100))
    bad = [n for n, ok in cases if not ok]
    for n, ok in cases:
        print(("PASS " if ok else "FAIL ") + n)
    print(f"\nbuild_corpus selftest: {len(cases) - len(bad)}/{len(cases)} passed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="玄鉴命理馆守门语料构造器")
    ap.add_argument("--train-gates"); ap.add_argument("--eval-gates")
    ap.add_argument("--out-dir"); ap.add_argument("--train-charts", type=int, default=1500)
    ap.add_argument("--eval-charts", type=int, default=400)
    ap.add_argument("--per-chart", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20261104)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.train_gates and a.eval_gates and a.out_dir):
        ap.error("需要 --train-gates / --eval-gates / --out-dir，或用 --selftest")

    rng = random.Random(a.seed)
    os.makedirs(a.out_dir, exist_ok=True)
    tr = load(a.train_gates, a.train_charts)
    ev = load(a.eval_gates, a.eval_charts)
    ev_valid, ev_test = split_by_key(ev, 0.5)
    tasks = list(TASKS)

    info = {}
    info["train"] = emit(tr, rng, a.per_chart, tasks, os.path.join(a.out_dir, "train.jsonl"))
    info["valid"] = emit(ev_valid, rng, a.per_chart, tasks, os.path.join(a.out_dir, "valid.jsonl"))
    info["test"] = emit(ev_test, rng, 4, tasks, os.path.join(a.out_dir, "test.jsonl"), with_meta=True)
    leak = {name: assert_no_leak(os.path.join(a.out_dir, info[name]["file"]))
            for name in ("train", "valid", "test")}
    print("[零泄漏断言] " + j(leak))

    audit = {}
    for p in (a.train_gates, a.eval_gates):
        q = os.path.join(os.path.dirname(os.path.abspath(p)), "audit.json")
        if os.path.exists(q):
            audit[os.path.basename(p)] = json.load(open(q, encoding="utf-8"))

    adapter = os.path.join(a.out_dir, "adapters")
    os.makedirs(adapter, exist_ok=True)
    write_lora_config(os.path.join(a.out_dir, "lora.yaml"), a.out_dir, adapter)
    write_model_card(os.path.join(a.out_dir, "MODEL_CARD.md"), info, {"year": "1990"}, {"year": "1991"})
    manifest = {
        "builder_version": "1.0", "seed": a.seed, "per_chart": a.per_chart,
        "train_gates_sha256": hashlib.sha256(open(a.train_gates, "rb").read()).hexdigest(),
        "eval_gates_sha256": hashlib.sha256(open(a.eval_gates, "rb").read()).hexdigest(),
        "attribution": ATTRIBUTION, "license": LICENSE,
        "content_version": CONTENT_VERSION,
        "no_verbatim_quote_policy": "语料中不含倪师原话正文，也不含他人断语库正文；T2 只传结构指纹",
        "zero_leak_audit": leak,
        "splits": info, "audits": audit,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with open(os.path.join(a.out_dir, "build_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(j(info))
    print("\n[署名] " + ATTRIBUTION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
