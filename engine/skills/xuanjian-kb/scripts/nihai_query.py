#!/usr/bin/env python3
"""倪海厦语料查询（天纪 / 人纪）

数据源：https://github.com/Renhuai123/nihai-tianji-corpus 与 nihai-renji-corpus
      语料 CC BY-NC-SA 4.0（非商用），每一条带 B 站原视频秒级出处。

用法：
  python3 nihai_query.py 卦 水风井            # 某卦全部判语（含四种用法）
  python3 nihai_query.py 卦 水风井 --h3 人间道
  python3 nihai_query.py 搜 六经  --库 renji   # 关键词全文检索
  python3 nihai_query.py 册                   # 两库的册分布
  python3 nihai_query.py 索引                 # 六十四卦条数索引

数据目录按以下顺序查找，找到即用：
  1) 环境变量 NIHAI_DATA
  2) <cwd>/.workbuddy/data/nihai
  3) ~/WorkBuddy/*/.workbuddy/data/nihai（取最新修改的一个）
"""
import json, os, sys, glob, collections

NAMES = {"tianji": "tianji.jsonl", "renji": "renji.jsonl"}

def find_dir():
    env = os.environ.get("NIHAI_DATA")
    if env and os.path.isdir(env):
        return env
    here = os.path.join(os.getcwd(), ".workbuddy", "data", "nihai")
    if os.path.isdir(here):
        return here
    cands = glob.glob(os.path.expanduser("~/WorkBuddy/*/.workbuddy/data/nihai"))
    if cands:
        return max(cands, key=os.path.getmtime)
    return None

def load(which, d):
    p = os.path.join(d, NAMES[which])
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def cite(e):
    src = e.get("src") or ""
    if src.startswith("tool://"):
        return src
    t = e.get("t_hms") or "00:00:00"
    h, m, s = (list(map(int, t.split(":"))) + [0, 0])[:3]
    sec = h * 3600 + m * 60 + s
    bv = e.get("bvid") or (src if src.upper().startswith("BV") else "")
    part = e.get("part") or e.get("ep") or ""
    return f"https://www.bilibili.com/video/{bv}?p={part}&t={sec}"

def show(e, i=None):
    head = f"[{i}] " if i else ""
    book = e.get("book") or e.get("册") or "-"
    print(f"{head}{book} · {e.get('h2')} · {e.get('h3') or '-'} @{e.get('t_hms')}")
    print(f"    {e.get('quote')}")
    if e.get("note"):
        print(f"    注：{e['note']}")
    print(f"    出处：{cite(e)}")

def main():
    argv = sys.argv[1:]
    args, opt, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                opt[k] = argv[i + 1]
                i += 2
                continue
            opt[k] = True
        else:
            args.append(a)
        i += 1
    d = find_dir()
    if not d:
        print("找不到语料目录。请设置 NIHAI_DATA，或把 entries.jsonl 放到 .workbuddy/data/nihai/")
        return 2
    if not args or args[0] in ("册", "books"):
        for w in ("tianji", "renji"):
            es = load(w, d)
            print(f"== {w}：{len(es)} 条 ==")
            for k, v in collections.Counter(x.get("book") for x in es).most_common():
                print(f"   {k}\t{v}")
        return 0
    if args[0] in ("索引", "index"):
        es = load("tianji", d)
        hx = [e for e in es if e.get("book") == "09-hexagrams"]
        c = collections.Counter((e.get("h2") or "").split("（")[0].strip() for e in hx)
        for k, v in c.items():
            print(f"{k}\t{v}")
        return 0
    if args[0] == "卦" and len(args) >= 2:
        name = args[1]
        for w in ("tianji",):
            es = load(w, d)
            hit = [e for e in es if (e.get("h2") or "").startswith(name)]
            if opt.get("h3"):
                hit = [e for e in hit if (e.get("h3") or "") == opt["h3"]]
            print(f"== {name}：{len(hit)} 条 ==")
            for i, e in enumerate(hit, 1):
                show(e, i)
        return 0
    if args[0] == "搜" and len(args) >= 2:
        kw = args[1]
        libs = ["renji"] if opt.get("库") == "renji" else (["tianji"] if opt.get("库") == "tianji" else ["tianji", "renji"])
        for w in libs:
            hit = [e for e in load(w, d) if kw in (e.get("quote") or "")]
            print(f"== [{w}] 「{kw}」命中 {len(hit)} 条（显示前 20）==")
            for i, e in enumerate(hit[:20], 1):
                show(e, i)
        return 0
    print(__doc__)
    return 1

if __name__ == "__main__":
    sys.exit(main())
