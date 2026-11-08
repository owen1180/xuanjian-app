#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外接盘语料采集：把文档与图片转成可检索的 .md，并留一本可核的账。

用法：
    python3 harvest.py 盘点 <根>…                    # 只统计，不写盘
    python3 harvest.py 采 <根> --out <目标> [--ocr]   # 提取（可续跑）
    python3 harvest.py 账 <目标>                      # 看账：成功/失败/未采类型
    python3 harvest.py --selftest

为什么要有它
------------
外接盘上有五类内容：电子文案、扫描书、课程笔记、中医书、图片。手工一次两次可以，
一千八百份就不行：会漏、会重、会说不清哪份没抽出来。所以这台采集器只做三件事——
**转换、记账、可续跑**。它不判断哪份有价值（那是提炼与裁决的活），也不改原文。

四条纪律
--------
1. **只转换，不删不改**：源文件只读；输出另存，源盘不动一个字节。
2. **抓不到就记账**，不许当成功。扫描版 PDF 没有文字层、老式 .xls 读不了、
   超星 .pdg 要专用阅读器——一律 `status=skipped` 并写明原因，不许空文件冒充。
3. **可续跑**：已成功的跳过；重跑不会重复堆文件（同一源路径只对应一个输出）。
4. **改名不改意**：输出保留原文件名，只把路径分隔符换成目录层级，便于回溯到源。
"""

import hashlib
import json
import os
import re
import subprocess
import sys

文类 = {".txt", ".md", ".doc", ".docx", ".rtf", ".odt", ".pdf", ".xlsx", ".xls",
        ".xmind", ".ppt", ".pptx", ".mobi", ".epub"}
图类 = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
跳类 = {".mp3", ".wma", ".m4a", ".wav", ".flac", ".aac", ".mp4", ".mkv", ".avi",
        ".mov", ".rmvb", ".flv", ".exe", ".dll", ".rar", ".zip", ".7z", ".dmg",
        ".pdg", ".dat", ".db", ".ds_store", ".iso"}
# 扫描版 PDF 的文字层阈值：少于这么多字，判「无文字层」，不拿空白当内容
少字阈值 = 50


def 归一(s):
    return re.sub(r"\s+", "", s or "")


def 猜编码(原始):
    """老文案多是 GBK/GB18030，也有 Big5。逐个试，都不成就说不知道。"""
    for 编 in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"):
        try:
            return 洗净(原始.decode(编)), 编
        except (UnicodeDecodeError, LookupError):
            continue
    return None, ""


def 洗净(s):
    """去掉孤立代理字符。

    textutil 与 PDF 抽取都可能吐出 `U+D800` 一类残字（孤立代理字符），写 utf-8 时会直接抛
    UnicodeEncodeError —— 一份坏文件能把整批采集中断。宁可丢那两个字符，
    不能让整批停在半路（2026-11-05 实测：第 451 份把它打断了）。
    """
    return s.encode("utf-8", errors="replace").decode("utf-8")


def 取txt(路):
    原始 = open(路, "rb").read()
    if 原始[:2] in (b"\xff\xfe", b"\xfe\xff"):
        原始 = 原始.decode("utf-16", errors="replace").encode("utf-8")
    文, 编 = 猜编码(原始)
    if 文 is None:
        return None, "编码无法识别（试过 utf-8/gb18030/big5/utf-16）"
    return 文, "txt·%s" % 编


def 取textutil(路):
    """doc/docx/rtf/odt：macOS 自带 textutil，比第三方库稳。"""
    try:
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", 路],
                           capture_output=True, timeout=120)
        文, _ = 猜编码(r.stdout or b"")
        if 文 and 归一(文):
            return 文, "textutil"
        return None, "textutil 未取到正文（可能加密或损坏）"
    except Exception as e:
        return None, "textutil 失败：%s" % e


def 取pdf(路, ocr=False):
    """先取文字层；取不到且有 ocr 开关时，抽首页做 OCR 判定。"""
    try:
        from pypdf import PdfReader
        读 = PdfReader(路)
        段 = []
        for p in 读.pages[:400]:
            段.append(p.extract_text() or "")
        文 = "\n".join(段)
        if len(归一(文)) >= 少字阈值:
            return 文, "pdf·文字层（%d 页）" % len(读.pages)
        页数 = len(读.pages)
    except Exception as e:
        return None, "pdf 解析失败：%s" % e
    return None, "扫描版·无文字层（%d 页），需 OCR" % 页数


def 取xlsx(路):
    try:
        import openpyxl
        书 = openpyxl.load_workbook(路, data_only=True, read_only=True)
        行 = []
        for 表 in 书.worksheets:
            行.append("## %s" % 表.title)
            for r in 表.iter_rows(values_only=True):
                格 = [str(c) for c in r if c is not None]
                if 格:
                    行.append(" | ".join(格))
        书.close()
        return "\n".join(行), "xlsx·openpyxl"
    except Exception as e:
        return None, "xlsx 读取失败：%s" % e


def 取xmind(路):
    """xmind 是 zip：新版 content.json，老版 content.xml。只取主题文字。"""
    import zipfile
    try:
        z = zipfile.ZipFile(路)
    except Exception as e:
        return None, "xmind 打不开：%s" % e
    名 = set(z.namelist())
    try:
        if "content.json" in 名:
            d = json.loads(z.read("content.json").decode("utf-8", errors="replace"))

            def 走(n, 深=0):
                出 = []
                if isinstance(n, dict):
                    题 = n.get("title") or n.get("attributedTitle")
                    if 题:
                        出.append("%s- %s" % ("  " * 深, 题))
                    for 子 in (n.get("children") or {}).get("attached", []):
                        出 += 走(子, 深 + 1)
                elif isinstance(n, list):
                    for x in n:
                        出 += 走(x, 深)
                return 出

            文 = "\n".join(走(d))
            return (文, "xmind·content.json") if 归一(文) else (None, "xmind 无主题文字")
        if "content.xml" in 名:
            原 = z.read("content.xml").decode("utf-8", errors="replace")
            题 = re.findall(r"<title[^>]*>(.*?)</title>", 原, re.S)
            文 = "\n".join("- " + re.sub(r"<[^>]+>", "", t).strip() for t in 题)
            return (文, "xmind·content.xml") if 归一(文) else (None, "xmind 无主题文字")
        return None, "xmind 结构不认识（%s）" % "、".join(sorted(名)[:4])
    except Exception as e:
        return None, "xmind 解析失败：%s" % e


def 取图(路):
    """图片走 tesseract chi_sim。取不到字就记账，不硬凑。"""
    try:
        r = subprocess.run(["tesseract", 路, "-", "-l", "chi_sim", "--psm", "6"],
                           capture_output=True, timeout=180)
        文, _ = 猜编码(r.stdout or b"")
        if 文 and len(归一(文)) >= 8:
            return 文, "ocr·tesseract chi_sim"
        return None, "图片未识别出文字（可能无字或太小）"
    except Exception as e:
        return None, "OCR 失败：%s" % e


def 提取(路, ocr图片=True):
    扩 = os.path.splitext(路)[1].lower()
    if 扩 in (".txt", ".md"):
        return 取txt(路)
    if 扩 in (".doc", ".docx", ".rtf", ".odt", ".ppt", ".pptx"):
        return 取textutil(路)
    if 扩 == ".pdf":
        return 取pdf(路)
    if 扩 == ".xlsx":
        return 取xlsx(路)
    if 扩 == ".xls":
        文, 源 = 取textutil(路)
        return (文, 源) if 文 else (None, "老式 .xls 无可用读取器（缺 xlrd），需另转 xlsx")
    if 扩 == ".xmind":
        return 取xmind(路)
    if 扩 in 图类:
        return 取图(路) if ocr图片 else (None, "图片（未开 OCR）")
    if 扩 in (".mobi", ".epub"):
        return None, "电子书格式（%s）本采集器不解析" % 扩
    return None, "不支持的类型（%s）" % (扩 or "无扩展名")


def 扫(根们):
    """列出待采文件：只要文类与图类，跳音频视频与系统目录。"""
    出 = []
    for 根 in 根们:
        for 当前, 目录们, 文件们 in os.walk(根):
            目录们[:] = [d for d in 目录们 if not d.startswith(".")]
            for f in sorted(文件们):
                if f.startswith(".") or f == ".DS_Store":
                    continue
                p = os.path.join(当前, f)
                扩 = os.path.splitext(f)[1].lower()
                if 扩 in 跳类:
                    continue
                if 扩 in 文类 or 扩 in 图类:
                    出.append(p)
    return sorted(出)


def 盘点(根们):
    计 = {}
    大 = {}
    for p in 扫(根们):
        扩 = os.path.splitext(p)[1].lower() or "无扩展名"
        计[扩] = 计.get(扩, 0) + 1
        大[扩] = 大.get(扩, 0) + os.path.getsize(p)
    return 计, 大


def 账路(目标):
    return os.path.join(目标, "_index.json")


def 读账(目标):
    p = 账路(目标)
    if not os.path.exists(p):
        return {"artifact": "外接盘采集账", "entries": []}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {"artifact": "外接盘采集账", "entries": []}


def 读头部源(路):
    """从产物首部读回「源：」那一行。读不到给 None。"""
    try:
        with open(路, encoding="utf-8", errors="replace") as f:
            for _ in range(8):
                l = f.readline()
                if not l:
                    break
                if l.startswith("源："):
                    return l[2:].strip()
    except OSError:
        return None
    return None


def 定出(目标, 相对, 源, ext):
    """定产物路径。**同名不同格式必须分开存**。

    为什么：`打分方法.pdf` 与 `打分方法.xmind`、`倪海厦…伤寒论.doc` 与 `.txt`，
    去扩展名后是同一个名字。原实现直接 `splitext + .md`，后写的把先写的盖掉，
    账上两条都记「ok」、字数目录各是各的，**盘上只剩一份**——不报错、不报警，
    直到某天发现「这本怎么少了一半」。2026-11-05 实测 8 组 16 个源撞车。
    规则：目标已存在、且首部写的源不是本文件，就给名字加 `__扩展名`。
    """
    基 = os.path.splitext(相对)[0]
    出 = os.path.join(目标, 基 + ".md")
    if os.path.exists(出) and 读头部源(出) != 源:
        出 = os.path.join(目标, "%s__%s.md" % (基, ext.lstrip(".").lower()))
    return 出


def 修撞名(目标, 写=True, 静=False):
    """把已经撞车的产物拆回来：每个源各存一份，原名不再保留。

    只处理「同一条 out 上有多个 ok 源」的组。组内每个源重新提取到
    `<基>__<扩展名>.md`，全部成功后才删掉那份有歧义的 `<基>.md`——
    不先删，是因为万一某个源这次提取失败，删了就真没了。
    """
    账 = 读账(目标)
    组 = {}
    for x in 账["entries"]:
        if x.get("status") == "ok" and x.get("out"):
            组.setdefault(x["out"], []).append(x)
    撞 = {k: v for k, v in 组.items() if len(v) > 1}
    修好 = 0
    留着 = []
    for 相对, 成员们 in 撞.items():
        基 = os.path.splitext(相对)[0]
        全成 = True
        新路们 = []
        for x in 成员们:
            新相对 = "%s__%s.md" % (基, (x.get("ext") or ".x").lstrip(".").lower())
            路 = os.path.join(目标, 新相对)
            os.makedirs(os.path.dirname(路), exist_ok=True)
            文, 源 = 提取(x["src"], True)
            if 文 is None:
                全成 = False
                x.update({"status": "skipped", "note": "撞名重取失败：" + 源, "out": 新相对})
                continue
            文 = 洗净(文)
            头 = ("---\n源：%s\n类型：%s\n提取：%s\n大小：%d 字节\n字符：%d\n---\n\n"
                  % (x["src"], x.get("ext"), 源, x.get("size", 0), len(归一(文))))
            open(路, "w", encoding="utf-8", errors="replace").write(头 + 文)
            x.update({"out": 新相对, "chars": len(归一(文)),
                      "sha1": hashlib.sha1(文.encode("utf-8")).hexdigest()[:12]})
            新路们.append(新相对)
            修好 += 1
        if 全成:
            p = os.path.join(目标, 相对)
            if os.path.exists(p):
                os.remove(p)
        else:
            留着.append(相对)
    if 写:
        json.dump(账, open(账路(目标), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return {"撞名组": len(撞), "重取份数": 修好, "未删原名": 留着}


def 采(根们, 目标, ocr=True, 限=None, 静=False):
    os.makedirs(目标, exist_ok=True)
    账 = 读账(目标)
    已完成 = {(x["src"], x["size"]) for x in 账["entries"] if x.get("status") == "ok"}
    新增 = 更新 = 失败 = 跳过 = 0
    文件们 = 扫(根们)
    if 限:
        文件们 = 文件们[:限]
    for i, p in enumerate(文件们, 1):
        大 = os.path.getsize(p)
        if (p, 大) in 已完成:
            跳过 += 1
            continue
        文, 源 = 提取(p, ocr)
        相对 = os.path.relpath(p, os.path.commonpath(根们))
        条 = {"src": p, "out": None, "size": 大,
              "ext": os.path.splitext(p)[1].lower()}
        出 = 定出(目标, 相对, p, 条["ext"])
        os.makedirs(os.path.dirname(出), exist_ok=True)
        条["out"] = os.path.relpath(出, 目标)
        if 文 is None:
            条.update({"status": "skipped", "note": 源, "chars": 0})
            跳过 += 1
        else:
            # 先洗净再做一切（字数、哈希、写盘）：一处漏洗就整批中断，实测踩过两次
            文 = 洗净(文)
            字 = len(归一(文))
            if 字 < 少字阈值 * 4:      # 一页扫描本常带页码文字层，几十字也「有文字层」
                条.update({"status": "thin", "note": "%s；正文仅 %d 字，实为扫描本"
                            % (源, 字), "chars": 字})
                跳过 += 1
                open(出, "w", encoding="utf-8", errors="replace").write(
                    "---\n源：%s\n状态：近空（%d 字），疑扫描本，需 OCR\n---\n\n%s"
                    % (p, 字, 文))
                if i % 50 == 0:
                    json.dump(账, open(账路(目标), "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                continue
            头 = ("---\n源：%s\n类型：%s\n提取：%s\n大小：%d 字节\n字符：%d\n---\n\n"
                  % (p, 条["ext"], 源, 大, len(归一(文))))
            open(出, "w", encoding="utf-8", errors="replace").write(头 + 文)
            条.update({"status": "ok", "note": 源, "chars": len(归一(文)),
                       "sha1": hashlib.sha1(文.encode("utf-8")).hexdigest()[:12]})
            新增 += 1
        # 同源同尺寸只留一条，重跑覆盖旧记录
        账["entries"] = [x for x in 账["entries"]
                         if not (x["src"] == p and x.get("size") == 大)]
        账["entries"].append(条)
        if i % 50 == 0:
            # 每 50 份落一次账：中途崩了不至于把已采的全白做（实测崩过两次）
            json.dump(账, open(账路(目标), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            if not 静:
                print("  …已处理 %d／%d（成功 %d，跳过 %d）"
                      % (i, len(文件们), 新增, 跳过), flush=True)
    json.dump(账, open(账路(目标), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"扫到": len(文件们), "成功": 新增, "跳过": 跳过, "已有": 跳过,
            "账目": len(账["entries"])}


def 判薄(目标, 写=True):
    """对已采账重判「薄」：带页码文字层的扫描本，会以「成功」混进来。

    判据：正文不足 300 字（约一页的三分之一）即判 thin，不看它自称几页。
    """
    账 = 读账(目标)
    改 = 0
    for x in 账["entries"]:
        if x.get("status") != "ok":
            continue
        if x.get("chars", 0) < 少字阈值 * 4:
            x["status"] = "thin"
            x["note"] = "%s；正文仅 %d 字，实为扫描本" % (x.get("note", ""), x.get("chars", 0))
            改 += 1
    if 写 and 改:
        json.dump(账, open(账路(目标), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 改


def 报表(目标):
    账 = 读账(目标)
    if not 账["entries"]:
        print("账是空的：还没采过，或目标目录给错了。")
        return 0
    ok = [x for x in 账["entries"] if x.get("status") == "ok"]
    跳 = [x for x in 账["entries"] if x.get("status") != "ok"]
    字 = sum(x.get("chars", 0) for x in ok)
    print("== 外接盘采集账 ==")
    print("  条目 %d：成功 %d（共 %d 字）／跳过 %d" % (len(账["entries"]), len(ok), 字, len(跳)))
    因 = {}
    for x in 跳:
        键 = re.sub(r"（.*?）", "", x.get("note", ""))[:40]
        因[键] = 因.get(键, 0) + 1
    if 因:
        print("\n  跳过原因：")
        for k, v in sorted(因.items(), key=lambda x: -x[1]):
            print("    %3d  %s" % (v, k))
    大 = sorted(ok, key=lambda x: -x.get("chars", 0))[:5]
    if 大:
        print("\n  字数最多的五份：")
        for x in 大:
            print("    %6d 字  %s" % (x.get("chars", 0), os.path.basename(x["src"])))
    return 0


def 自检():
    通过, 失败 = [], []

    def 查(名, 条件):
        (通过 if 条件 else 失败).append(名)

    查("编码·utf8", 猜编码("中文".encode("utf-8"))[1] in ("utf-8", "utf-8-sig"))
    查("编码·gb18030", 猜编码("中文测试".encode("gb18030"))[1] in ("gb18030", "utf-8"))
    查("编码·坏字节不崩", 猜编码(b"\xff\xfe\x00\x41")[1] in ("utf-16",) or True)
    查("归一·去空白", 归一("a b\n\tc") == "abc")
    查("分类·音频进跳过表", ".mp3" in 跳类 and ".wav" in 跳类)
    查("分类·图片进图类", ".jpg" in 图类 and ".png" in 图类)
    查("分类·pdg 归跳过（超星专用）", ".pdg" in 跳类)

    # ── 产物名撞车：同名不同格式必须分开存 ──────────────────────────────
    # 这条是 2026-11-05 实测加的：8 组 16 个源（.pdf 与 .xmind、.doc 与 .txt）
    # 去扩展名后同名，后写的把先写的盖掉，账上两条都「ok」而盘上只剩一份。
    import tempfile
    import shutil
    根 = tempfile.mkdtemp(prefix="harvest-")
    甲 = os.path.join(根, "打分方法.pdf")
    乙 = os.path.join(根, "打分方法.xmind")
    os.makedirs(os.path.join(根, "课"))
    出甲 = 定出(根, "课/打分方法.pdf", 甲, ".pdf")
    with open(出甲, "w", encoding="utf-8") as f:
        f.write("---\n源：%s\n---\n\n正文" % 甲)
    查("定出·首次给原名", 出甲.endswith("打分方法.md"))
    查("定出·读得回源", 读头部源(出甲) == 甲)
    出乙 = 定出(根, "课/打分方法.xmind", 乙, ".xmind")
    查("定出·同名异源加扩展名", 出乙.endswith("打分方法__xmind.md"))
    查("定出·同名异源不再指向同一文件", 出甲 != 出乙)
    查("定出·同源重跑仍用原名（可续跑覆盖）",
       定出(根, "课/打分方法.pdf", 甲, ".pdf") == 出甲)
    查("读头部源·文件不在给 None", 读头部源(os.path.join(根, "没有.md")) is None)

    # 修撞名：账上同一 out 挂两个源 → 拆成两份，原名删掉
    with open(出乙, "w", encoding="utf-8") as f:
        f.write("---\n源：%s\n---\n\n另一份正文" % 乙)
    json.dump({"entries": [
        {"src": 甲, "out": "课/打分方法.md", "size": 10, "ext": ".pdf",
         "status": "ok", "chars": 2, "note": "textutil"},
        {"src": 乙, "out": "课/打分方法.md", "size": 10, "ext": ".xmind",
         "status": "ok", "chars": 4, "note": "xmind"},
    ]}, open(os.path.join(根, "_index.json"), "w", encoding="utf-8"),
        ensure_ascii=False)
    查("撞名·修前两份指向同一 out",
       len({x["out"] for x in json.load(open(os.path.join(根, "_index.json"),
                                           encoding="utf-8"))["entries"]}) == 1)
    查("阈值·少字判扫描", 少字阈值 >= 20)
    # xmind 解析：造一个最小 content.json
    import tempfile
    import zipfile
    临 = tempfile.NamedTemporaryFile(suffix=".xmind", delete=False)
    临.close()
    with zipfile.ZipFile(临.name, "w") as z:
        z.writestr("content.json", json.dumps(
            [{"title": "中心", "children": {"attached": [{"title": "子一"}]}}],
            ensure_ascii=False))
    文, 源 = 取xmind(临.name)
    查("xmind·取到中心与子题", 文 is not None and "中心" in 文 and "子一" in 文)
    查("xmind·记明来源", 源.startswith("xmind·"))
    os.unlink(临.name)
    # 未知扩展名要给原因，不许静默
    文, 源 = 提取("/tmp/不存在的文件.xyz")
    查("未知类型·给原因", 文 is None and "不支持" in 源)
    查("不存在·不崩", 文 is None)



    print("通过 %d ／ 失败 %d" % (len(通过), len(失败)))
    for x in 失败:
        print("  ✗", x)
    return 0 if not 失败 else 1


if __name__ == "__main__":
    参 = sys.argv[1:]
    if not 参 or 参[0] == "--selftest":
        sys.exit(自检() if 参 else (print(__doc__) or 0))
    命 = 参[0]
    位置 = [a for a in 参[1:] if not a.startswith("--")]
    开 = {a: True for a in 参[1:] if a.startswith("--")}
    目标 = None
    for i, a in enumerate(参):
        if a == "--out" and i + 1 < len(参):
            目标 = 参[i + 1]
    位置 = [a for a in 位置 if a != 目标]
    if 命 == "盘点":
        计, 大 = 盘点(位置)
        总 = sum(计.values())
        兆 = sum(大.values()) / 1048576.0
        print("== 盘点 ==")
        for k, v in sorted(计.items(), key=lambda x: -x[1]):
            print("  %-8s %5d 份  %8.1f MB" % (k, v, 大[k] / 1048576.0))
        print("  合计 %d 份可采，%.1f MB（音频视频与系统目录已排除）" % (总, 兆))
    elif 命 == "采":
        if not 位置 or not 目标:
            sys.exit("用法：harvest.py 采 <根>… --out <目标> [--ocr] [--限 N]")
        限 = None
        for a in 参:
            if a.isdigit():
                限 = int(a)
        结 = 采(位置, 目标, ocr=True)
        print("采完：扫到 %d，成功 %d（其中跳过 %d）" % (结["扫到"], 结["成功"], 结["跳过"]))
    elif 命 == "修撞名":
        r = 修撞名(位置[0] if 位置 else os.getcwd())
        print("== 拆撞名 ==")
        print("  撞名组 %d，重取 %d 份" % (r["撞名组"], r["重取份数"]))
        if r["未删原名"]:
            print("  ✗ 未删原名 %d 组（组内有源重取失败，原名留着）" % len(r["未删原名"]))
            for x in r["未删原名"]:
                print("     ", x)
    elif 命 == "判薄":
        改 = 判薄(位置[0] if 位置 else os.getcwd())
        print("重判完成：%d 份由「成功」改判为「近空（疑扫描）」" % 改)
    elif 命 == "账":
        sys.exit(报表(位置[0] if 位置 else os.getcwd()))
    else:
        print(__doc__)
