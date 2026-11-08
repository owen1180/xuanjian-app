#!/usr/bin/env python3
"""初始化命理档案库骨架，可选灌入归档规程模板。

用法：
    python3 init_library.py 命理档案 --seed
"""

import argparse
import pathlib
import shutil
import sys


def 主程序():
    p = argparse.ArgumentParser(description="初始化命理档案库")
    p.add_argument("目录", help="库根目录，例如 命理档案")
    p.add_argument("--seed", action="store_true", help="同时灌入归档规程参考文档到 方法论/归档规程/")
    a = p.parse_args()

    根 = pathlib.Path(a.目录).expanduser()
    (根 / "八字库").mkdir(parents=True, exist_ok=True)
    (根 / "方法论").mkdir(parents=True, exist_ok=True)
    print("已建立骨架：")
    print("  %s" % (根 / "八字库"))
    print("  %s" % (根 / "方法论"))

    # 分组索引：七类关系圈（家人／朋友／同学／同事／客户／名人／其他）
    索 = 根 / "档案索引.json"
    if not 索.exists():
        索.write_text(__import__("json").dumps(
            {"artifact": "命盘存档索引（按关系圈分组）",
             "groups": ["家人", "朋友", "同学", "同事", "客户", "名人", "其他"],
             "items": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("  已生成分组索引：%s" % 索)

    if not (根 / "档案索引.html").exists():
        (根 / "档案索引.html").write_text(
            "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
            "<title>命理档案索引</title></head><body><h1>命理档案索引</h1>"
            "<p>档案尚未录入。每成一档，在此登记：档号卡片、交叉结论表、待验证总账、四项计数。</p>"
            "</body></html>\n",
            encoding="utf-8")
        print("  已生成空的索引页：%s" % (根 / "档案索引.html"))

    if a.seed:
        源 = pathlib.Path(__file__).resolve().parent.parent / "references"
        if not 源.is_dir():
            print("未找到参考文档目录：%s" % 源)
        else:
            目标 = 根 / "方法论" / "归档规程"
            目标.mkdir(parents=True, exist_ok=True)
            for f in sorted(源.glob("*.md")):
                shutil.copy(f, 目标 / f.name)
                print("  已灌入模板：%s" % (目标 / f.name))

    print("\n下一步：新八字先用 find_chart.py 查重，确认无档后按《01-档案结构与四件套模板.md》建档；"
          "建档时用 groups.py 登记 定分组（家人／朋友／同学／同事／客户／名人／其他）。")
    return 0


if __name__ == "__main__":
    sys.exit(主程序())
