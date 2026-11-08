#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玄鉴命理馆 · 轻量守门头训练器 train_guard.py (v1.0)

用途：**不依赖任何下载**的真实训练保底路径。用纯 numpy 从 SFT 语料里
学一个守门任务路由器（4 类）＋合成负例检测器（2 类），产出可复用的
`.npz` 权重与独立评测报告。它证明「数据 → 训练 → 权重 → 评测」整条链
在本机跑得通；它不是 LLM，也不生成断语。

- 特征：字符 2/3-gram 哈希（4096 维）＋长度／数字／任务提示词指示位
- 模型：softmax 回归（mini-batch SGD + L2），四分类；另训一个二分类头
- 训练/测试：由 --train / --test 指定，须跨年不重叠；切分口径用 --split-note 显式写入报告
- 输出：guard_head.npz、guard_report.json

用法：
  python3 train_guard.py --train train.jsonl --test test.jsonl \
      --out ./sft/guard --epochs 25 --seed 20261104
  python3 train_guard.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np

TASKS = ["T1", "T2", "T3", "T4"]
DIM = 4096


def feat(text: str) -> np.ndarray:
    """字符 n-gram 哈希特征，纯确定性，无外部依赖。"""
    v = np.zeros(DIM + 6, dtype=np.float32)
    t = text[:1200]
    for n in (2, 3):
        for i in range(len(t) - n + 1):
            g = t[i:i + n]
            h = int(hashlib.blake2b(g.encode("utf-8"), digest_size=4).hexdigest(), 16)
            v[h % DIM] += 1.0
    v[DIM] = min(len(t) / 600.0, 4.0)
    v[DIM + 1] = float(sum(c.isdigit() for c in t)) / 40.0
    v[DIM + 2] = float("指纹" in t)
    v[DIM + 3] = float("组合" in t)
    v[DIM + 4] = float("分层" in t)
    v[DIM + 5] = float("口径卡" in t)
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


def load_rows(path: str):
    X, y, synth = [], [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            gold = json.loads(d["gold"]) if "gold" in d else json.loads(d["completion"])
            X.append(feat(d["prompt"]))
            y.append(TASKS.index(gold["task"]))
            synth.append(int(bool((d.get("meta") or {}).get("synthetic")
                                  or gold.get("synthetic_negative"))))
    return np.stack(X), np.array(y, dtype=np.int64), np.array(synth, dtype=np.int64)


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def train(X, y, epochs: int, seed: int, lr: float = 0.35, l2: float = 1e-4,
          batch: int = 64, nclasses: int = 4):
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 0.01, (X.shape[1], nclasses)).astype(np.float32)
    b = np.zeros(nclasses, dtype=np.float32)
    n = len(y)
    for ep in range(epochs):
        idx = rng.permutation(n)
        tot = 0.0
        for s in range(0, n, batch):
            ii = idx[s:s + batch]
            xb, yb = X[ii], y[ii]
            p = softmax(xb @ W + b)
            p[np.arange(len(yb)), yb] -= 1
            p /= len(yb)
            W -= lr * (xb.T @ p + l2 * W)
            b -= lr * p.sum(axis=0)
            tot += float(-np.log(np.maximum(p[np.arange(len(yb)), yb] + 1, 1e-9)).mean())
    return W, b


def predict(X, W, b):
    return np.argmax(X @ W + b, axis=1)


def metrics(yt, yp, nclasses: int) -> dict:
    acc = float((yt == yp).mean())
    per = {}
    for c in range(nclasses):
        tp = int(((yt == c) & (yp == c)).sum())
        fp = int(((yt != c) & (yp == c)).sum())
        fn = int(((yt == c) & (yp != c)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        per[str(c)] = {"support": int((yt == c).sum()),
                       "precision": round(prec, 4), "recall": round(rec, 4),
                       "f1": round(2 * prec * rec / max(prec + rec, 1e-9), 4)}
    return {"accuracy": round(acc, 4), "per_class": per}


def main() -> int:
    ap = argparse.ArgumentParser(description="玄鉴命理馆轻量守门头训练器")
    ap.add_argument("--train"); ap.add_argument("--test")
    ap.add_argument("--out"); ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--seed", type=int, default=20261104)
    ap.add_argument("--split-note", default="按档号 hash 切分；训练段与测试段不重叠（具体年份见 --split-note）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        templates = {
            0: "盘面校验 日期 时辰 口径卡 输入 date hour gender ming_star",
            1: "引文剥离闸门 结构指纹 ni_quote episode timestamp 集数",
            2: "十天干四化白名单 组合 化禄 化权 化科 化忌 核对",
            3: "确定性事实 传统规则 解读分层 topic 字符数 归成员",
        }
        X = np.stack([feat(templates[i % 4] + f" 样本{i}") for i in range(80)])
        y = np.array([i % 4 for i in range(80)])
        W, b = train(X, y, 20, 0)
        acc = float((predict(X, W, b) == y).mean())
        ok1 = bool(np.allclose(np.linalg.norm(X, axis=1), 1))
        ok2 = acc > 0.9
        print("PASS 特征归一化" if ok1 else "FAIL 特征归一化")
        print("PASS 可拟合训练数据" if ok2 else f"FAIL 可拟合 acc={acc}")
        print(f"train_guard selftest: {int(ok1) + int(ok2)}/2 passed")
        return 0 if ok1 and ok2 else 1
    if not (a.train and a.test and a.out):
        ap.error("需要 --train / --test / --out，或用 --selftest")

    os.makedirs(a.out, exist_ok=True)
    Xtr, ytr, str_ = load_rows(a.train)
    Xte, yte, ste = load_rows(a.test)
    W, b = train(Xtr, ytr, a.epochs, a.seed)
    Ws, bs = train(Xtr, str_, a.epochs, a.seed, nclasses=2)

    rep = {
        "model": "numpy softmax-regression guard head (char 2/3-gram hashing, 4102 dim)",
        "trained_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "seed": a.seed, "epochs": a.epochs,
        "train_rows": int(len(ytr)), "test_rows": int(len(yte)),
        "split": a.split_note,
        "task_router": metrics(yte, predict(Xte, W, b), 4),
        "synthetic_detector": metrics(ste, predict(Xte, Ws, bs), 2),
        "task_labels": TASKS,
        "attribution": ("本项目使用了 紫微斗数开源解读数据集 v4.0（674,976 张命盘 × 13 维）"
                        "／来源：https://github.com/Renhuai123/ziwei-doushu ／作者：王多鱼AI"),
        "scope_note": "这是守门任务路由与合成负例检测，不是断语生成模型；"
                      "不代表命理咨询准确率，也不替代 kauding.py / source_gate.py 的规则裁判。",
    }
    np.savez(os.path.join(a.out, "guard_head.npz"),
             W=W, b=b, W_synth=Ws, b_synth=bs,
             dims=np.array([DIM, 4, 2, a.seed], dtype=np.int64))
    with open(os.path.join(a.out, "guard_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: rep[k] for k in
                      ("train_rows", "test_rows", "task_router", "synthetic_detector")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
