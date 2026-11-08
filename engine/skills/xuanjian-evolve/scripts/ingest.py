#!/usr/bin/env python3
"""摄取器 —— 把资料库里的课纲／笔记取回正文，省掉手工下载那一步。

用法：
    python3 ingest.py 取 <节点号>              下载并打印正文（默认 6000 字）
    python3 ingest.py 取 <节点号> --全          不限字数
    python3 ingest.py 取 <节点号> --存 路径.md   同时存盘
    python3 ingest.py 批量 <节点号...> --存目录 目录   一次取多份，逐份存盘
    python3 ingest.py 清单                     列出下一批该读的节点号（调 evolve.py 下一批）

**为什么要有这个脚本**：摄取这一步此前卡在「手工下载」上——台账能排出该读什么，
但取正文要人点链接、另存、再打开。资料库有下载与解析接口，这一段完全可以机器做。
脚本只负责**取回原文**，提炼与落册仍由人做——术数的内容判断不能交给脚本。

依赖：WorkBuddy 资料库技能脚本（space_api.py / drive/get_download_link.py）。
docx 解析只取 word/document.xml 的纯文本，不依赖第三方库。
"""
import json, os, re, subprocess, sys, zipfile

技能基 = "/Users/haoqing/.workbuddy/plugins/cache/workbuddy-builtin/skill-library"


def 库目录():
    if not os.path.isdir(技能基):
        return None
    命中 = [os.path.join(技能基, d) for d in os.listdir(技能基)
            if os.path.exists(os.path.join(技能基, d, "space_api.py"))]
    return sorted(命中)[-1] if 命中 else None


def 下载链接(节点号):
    sk = 库目录()
    if not sk:
        return None, "找不到资料库技能脚本"
    r = subprocess.run(["python3", os.path.join(sk, "drive", "get_download_link.py"),
                        "--node-id", 节点号], capture_output=True, text=True, cwd=sk)
    for 行 in r.stdout.splitlines():
        if 行.startswith("KS_DRIVE_DOWNLOAD "):
            try:
                return json.loads(行[len("KS_DRIVE_DOWNLOAD "):]), ""
            except Exception as e:
                return None, f"解析下载响应失败：{e}"
    return None, "未取到下载链接（节点可能不是网盘文件）"


def 取文(节点号):
    """返回 (标题, 正文, 错误信息)"""
    d, err = 下载链接(节点号)
    if not d:
        return "", "", err
    url, 名 = d.get("download_url"), d.get("file_name", 节点号)
    tmp = f"/tmp/ingest-{节点号}.{d.get('ext', 'docx')}"
    r = subprocess.run(["curl", "-sL", url, "-o", tmp], capture_output=True, text=True)
    if not os.path.exists(tmp):
        return 名, "", f"下载失败：{r.stderr[:200]}"
    正文 = ""
    try:
        if tmp.endswith(".docx") or d.get("ext") == "docx":
            z = zipfile.ZipFile(tmp)
            x = z.read("word/document.xml").decode("utf-8")
            x = re.sub(r"</w:p>", "\n", x)
            x = re.sub(r"<w:tab[^>]*/>", "\t", x)
            正文 = re.sub(r"<[^>]+>", "", x)
        else:
            正文 = open(tmp, encoding="utf-8", errors="ignore").read()
    except Exception as e:
        return 名, "", f"解析失败：{e}"
    正文 = re.sub(r"[ \t]+\n", "\n", 正文)
    正文 = re.sub(r"\n{3,}", "\n\n", 正文).strip()
    return 名, 正文, ""


def 命令_取(参):
    if not 参:
        print("用法：python3 ingest.py 取 <节点号> [--全] [--存 路径]")
        return 2
    节点号 = 参[0]
    全 = "--全" in 参
    存 = None
    if "--存" in 参:
        存 = 参[参.index("--存") + 1]
    名, 正文, err = 取文(节点号)
    if err:
        print(f"✗ {节点号}：{err}")
        return 1
    出 = 正文 if 全 else 正文[:6000]
    print(f"# {名}\n# 共 {len(正文)} 字{'（以下全文）' if 全 else '（以下前 6000 字，--全 取全文）'}\n")
    print(出)
    if 存:
        open(存, "w", encoding="utf-8").write(f"# {名}\n\n{正文}")
        print(f"\n[已存] {存}", file=sys.stderr)
    return 0


def 命令_批量(参):
    节点, i = [], 0
    while i < len(参):
        a = 参[i]
        if a == "--存目录":
            目录 = 参[i + 1] if i + 1 < len(参) else "/tmp/ingest"
            i += 2
            continue
        节点.append(a)
        i += 1
    if not 节点:
        print("用法：python3 ingest.py 批量 <节点号...> --存目录 目录")
        return 2
    目录 = "/tmp/ingest"
    if "--存目录" in 参:
        目录 = 参[参.index("--存目录") + 1]
    os.makedirs(目录, exist_ok=True)
    ok = 0
    for n in 节点:
        名, 正文, err = 取文(n)
        if err:
            print(f"✗ {n}：{err}")
            continue
        安 = re.sub(r"[/\s]+", "_", 名)[:60] + ".md"
        p = os.path.join(目录, 安)
        open(p, "w", encoding="utf-8").write(f"# {名}\n\n{正文}")
        print(f"✓ {名}（{len(正文)} 字）→ {p}")
        ok += 1
    print(f"\n取回 {ok} / {len(节点)} 份，存于 {目录}")
    return 0 if ok else 1


def 命令_清单(_参):
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run(["python3", os.path.join(here, "evolve.py"), "下一批"]).returncode


def main():
    参 = sys.argv[1:]
    if not 参:
        print(__doc__)
        return 0
    命 = 参[0]
    余 = 参[1:]
    if 命 == "取":
        return 命令_取(余)
    if 命 == "批量":
        return 命令_批量(余)
    if 命 == "清单":
        return 命令_清单(余)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
