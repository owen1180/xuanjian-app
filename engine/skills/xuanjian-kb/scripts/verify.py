# -*- coding: utf-8 -*-
"""打分引擎自校准：跑七十三道作业题的答案，报精确率与档位一致率。

用法：python3 verify.py [校准集路径]
改动 score.py 后必须重跑本脚本，精度掉下九成即视为改坏了。
"""

import json
import pathlib
import sys

import score as S

默认集 = pathlib.Path(__file__).with_name("校准集.json")

基准 = {"精确率": 0.96, "档位一致率": 1.00}


def 跑(集路径=None):
    路径 = pathlib.Path(集路径) if 集路径 else 默认集
    数据 = json.loads(路径.read_text(encoding="utf-8"))
    偏差 = []
    for c in 数据:
        r = S.打分(c["四柱"])
        偏差.append((abs(r["总分"] - c["答案分"]), c["题号"], c["答案分"],
                     r["总分"], S.判定(c["答案分"]), r["档位"], " ".join(c["四柱"])))
    偏差.sort(reverse=True)
    n = len(偏差)
    精确 = sum(1 for x in 偏差 if x[0] < 0.5)
    接近 = sum(1 for x in 偏差 if x[0] < 5)
    档准 = sum(1 for x in 偏差 if x[4] == x[5])
    均误 = sum(x[0] for x in 偏差) / n
    return {"题数": n, "精确": 精确 / n, "接近": 接近 / n,
            "档位": 档准 / n, "均误": 均误, "明细": 偏差}


def 主():
    r = 跑(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"题数 {r['题数']}")
    print(f"精确率（±0.5 分）　{r['精确']:.1%}　基准 {基准['精确率']:.0%}")
    print(f"接近率（±5 分）　　{r['接近']:.1%}")
    print(f"档位一致率　　　　{r['档位']:.1%}　基准 {基准['档位一致率']:.0%}")
    print(f"平均绝对误差　　　{r['均误']:.2f} 分")
    if r["精确"] + 0.02 < 基准["精确率"] or r["档位"] < 基准["档位一致率"]:
        print("\n⚠ 精度低于基准，改动须复核。")
    else:
        print("\n✓ 未低于基准。")
    print("\n—— 末三位偏差 ——")
    for d, no, exp, got, e1, e2, pil in r["明细"][:3]:
        print(f"　第{no}题 {pil}　答案{exp}　算出{got}　差{d:.2f}　{e1}→{e2}")


if __name__ == "__main__":
    主()
