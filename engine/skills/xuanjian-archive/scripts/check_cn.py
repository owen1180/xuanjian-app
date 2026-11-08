#!/usr/bin/env python3
"""交付前纯中文校验：扫描目录下所有说明与报告，检查可见正文里的英文残留。

用法：
    python3 check_cn.py 命理档案

说明：
    剥掉 HTML 标签、代码块与文件名后再扫；网页结构标签名不计。
    发现残留时退出码非零。历史教训：报告正文曾混入英文词被用户当场指出。
"""

import argparse
import pathlib
import re
import sys


# 豁免：这两册的英文是内容本身，改写反而失真，逐条注明理由
豁免 = {
    "87-针灸-取穴定位与按病配方（可用可讲）.md": "本册给出语料的文件名与扩展名（!00001.pdg），是让读者能照此找到那 64 页并打开，属核对对象本身；扩展名译成中文即无法定位",
    "89-针灸-十四经361穴全集（交叉补全）.md": "本册 DVD 时间戳（如 1-02:54）为《人纪》实录溯源锚点，pdg 为原 64 页图谱抽样扩展名（核对对象本身），中文化即失效；〔原〕摘录自该实录",
    "13-天纪-人间道.md": "本册引外部项目仓库名（jonhnsonzz／bianyuan456／wh149728915-stack）与语料 book 编号（08-yili）、脚本路径（scripts/zeri.py），均为核对对象本身，译成中文无法回查",
    "07-面相-课件原文OCR.md": "课件原文为识别件，英文是原文的一部分，不得改写",
    "36-工具-确定性排盘引擎与软件.md": "软件名与命令名本身是英文专有名词，中文化反而误导",
    "README.md": "专家包说明：项目名、仓库地址与平台术语不可译",
    "MAC_BUILD.md": "构建说明：命令、包名与平台术语不可译",
    "62-天纪-六十四卦判语与一卦四用.md": "语料许可缩写（CC BY-NC-SA）、转写标记（sic／ASR／OCR）与数据格式（jsonl）是标识符，译成中文反而无法核对",
    "63-经方-六经辨证与处方规则.md": "方证公式的 IF-THEN 是格式名，许可缩写与 sic 标记不可译",
    "64-真伪核验-GitHub倪海厦项目横向比对.md": "本册通篇在比对仓库、许可与语言栈，仓库名、许可名、语言名是核对对象本身，改写即失真",
    "15-紫微-格局四化与飞星.md": "格局库的 required／bonus／breaking 系引擎字段名（`36` §2.1 原样），译成中文反而对不上工具输出",
    "65-语料保真与判语级溯源.md": "语料许可（CC BY-NC-SA）、双源核验（ASR／OCR）、审计表名（evidence／quarantine／id_redirect）与数据格式（jsonl）均为标识符",
    "66-证据分层与安全表述.md": "证据分层引用项目名与目录名（references／README），属技术标识，改写即失真",
    "67-星曜-宫位-病症实体建模与语料源清单.md": "实体表名、raw／wiki／derived 三层、语料库名（tianji／renji）与许可缩写是核对对象本身",
    "68-倪师理论补遗与专家团取长补短.md": "本册登记外部项目的仓库名、Star、许可名（MIT／Apache／MulanPSL）与技术标识符，改写即失真",
    "69-语料地图与模块索引.md": "本册是语料索引：book 编号（09-hexagrams 等）、库名（tianji／renji）、许可缩写与数据格式（jsonl／MB）是核对对象本身",
    "70-天纪语料补遗-疾厄修正·格局补名·婚星·金钱卦·序卦.md": "本册据语料实物撰写，引用 book 编号与秒级时间戳，属核对锚点，改写即失效",
    "71-曾仕强-势的拐点与话术结构.md": "本册登记外部项目仓库名与技术标识，属核对锚点",
    "72-李敖-审名查据与钢人反方.md": "本册通篇在比对仓库、许可与载体等级，仓库名与许可名（MIT／CC0）是核对对象本身，译成中文无法对人",
    "73-道藏-术数原始定位与科仪边界.md": "本册登记道藏文本库名、部类编号（KR5）与许可缩写，属文献坐标，改写即失效",
    "SKILL.md": "技能说明：登记的外部项目仓库名、平台名、语料许可缩写（CC BY-NC-SA／sic）与文件名（README）是核对对象本身，中文化反而无法对源",
    "05-规则编号回填与运行时台账.md": "台账的 BLOCK 是字段标记名，与脚本输出对应，改写即对不上",
    "90-黄历三栏-值宿吉凶·全本宜忌·胎神占方.md": "本册登记外部库名（cnlunar／lunar-python）、许可缩写与随包目录（vendor），是核对与合规对象本身，中文化即无法对源",
    "84-取名-正名与形神（取神不取划数）.md": "本册引语料篇目编号（08-yili）、视频号、拼音韵母（an／ang／in／ing）与许可缩写，均为核对锚点与音韵记法，译成中文即无法回查或失真",
    "85-黄历-一页黄历怎么读.md": "本册引语料篇目编号（07-methodology／09-hexagrams／04-neijing 等）作逐字回查锚点，属核对对象本身；译成中文即对不上语料库",
    "88-开源项目-姓名学与黄历GitHub横向比对.md": "本册通篇比对仓库名、许可名、语言栈与检索关键词，仓库名与许可缩写是核对与合规对象本身，改写即失真",
    "74-开源项目-奇门大六壬小六壬堪舆GitHub横向比对.md": "本册通篇比对仓库名、许可名、语言栈与天文算法库名，均为核对与许可合规对象本身，改写即无法对源",
    "81-易经-经文十翼与卦爻辞引用规程.md": "本册标数据格式（JSON）与古籍文本库站名（ctext），属核对与取文坐标，中文化即无法回查",
    "82-六爻与梅花-纳甲断法与体用断法.md": "本册引许可缩写、数据格式与外部预测市场名（Polymarket），属对拍实验的核对对象本身，译名即失真",
    "94-释梦-三系汇通（藏传梦瑜伽·东方心理学·西方心理学）.md": "本册主体是藏传梦瑜伽（chos／gsal／gtum／lam／lus／sgyu／svapna 等藏文转写）、西方释梦研究（研究者名 Hall／Hill／Domhoff／LaBerge／Hobson、机制名 latent／manifest／compensation／displacement、方案缩写 CBT-I／IRT／WBTB／MILD）与诊断/许可代码（DSM／ICD／AASM／REM／MIT／Apache），均为内容本身，译成中文即失真或无法回查",
    "41-四柱-打分引擎与校准.md": "本册用「vs」作两版算法对比的标记（如「透藏加权 vs 课程打分」），属技术对照标识，译成中文反而绕口",
    "92-排盘-真太阳时与时辰校正.md": "本册引视频号（BV）、语料篇目编号（methodology／part）、代码函数名（resolveLunar）与对比标记（vs），均为核对锚点与接口名，中文化即无法回查",
    "93-开源与权威源补强（三）-卜时名婚梦.md": "本册通篇比对仓库名（PiPiName／taibu-core）、许可（AGPL／GPL／MIT／Apache）、诊断与分类代码（DSM／ICD／TR／WHO）、平台与库名（GitHub／PubMed／Zenodo／ctext／DreamBank／MCP）及检索关键词，均为核对与许可合规对象本身，改写即失真",
}
# 目录级豁免：外部流派协议与文献索引，含网址、书名、机构名与原文术语，改写会失真
# 键写单个目录名而不是相对路径：把同一套豁免从任意层级扫描都能命中，
# 用相对路径做键一旦换成扫 skills 子目录就整体失效，历史教训
豁免目录 = {
    "shizhan-pai": "实战派协议与文献索引：网址、仓库名、书号、机构名与原文术语不可译",
    "agents": "成员定义：调度机制与工具名是接口名，改写即失效",
}


def 清理(文本, 后缀):
    if 后缀 == ".html" and "<body>" in 文本:
        文本 = 文本.split("<body>")[1]
    if 后缀 == ".md":
        文本 = re.sub(r"^---\n.*?\n---\n", "", 文本, flags=re.S)   # 去掉 YAML 头（name/description 等元数据）
    文本 = re.sub(r"```[\s\S]*?```", "", 文本)          # 去掉代码块
    文本 = re.sub(r"`[^`\n]+`", "", 文本)               # 去掉行内反引号代码（命令/工具名/库名）
    文本 = re.sub(r"<[^>]+>", "", 文本)                  # 去掉标签
    文本 = re.sub(r"[\w\-./（）()]+\.(?:html|md|py|ts|json|js|png)(?![A-Za-z])", "", 文本)  # 去掉文件名（含源码文件名）。后顾否定不可少：先试 js 会把 settings.json 切成 settings.js + on
    return 文本


def 主程序():
    p = argparse.ArgumentParser(description="纯中文交付校验")
    p.add_argument("目录", help="要扫描的目录，例如 命理档案")
    a = p.parse_args()

    根 = pathlib.Path(a.目录).expanduser()
    if 根.is_file():
        # 也允许直接给单个文件：交付物常常就是一份报告，不必为它造个目录
        待查 = [根] if 根.suffix in {".md", ".html"} else []
        if not 待查:
            sys.exit("文件类型不在检查范围（只查 md 与 html）：%s" % 根)
        根 = 根.parent
    elif 根.is_dir():
        待查 = sorted(根.rglob("*"))
    else:
        sys.exit("路径不存在：%s" % 根)

    有残留 = False
    计数 = 0
    for 文件 in 待查:
        if 文件.suffix not in {".md", ".html"}:
            continue
        计数 += 1
        文本 = 清理(文件.read_text(encoding="utf-8", errors="ignore"), 文件.suffix)
        词 = re.findall(r"[A-Za-z]{2,}", 文本)
        相对 = str(文件.relative_to(根)).replace("\\", "/")
        if 词 and 文件.name in 豁免:
            print("%-52s 豁免（%s）" % (相对, 豁免[文件.name]))
            词 = []
        elif 词:
            # 按路径片段匹配，扫 skills 目录或整个专家包都能命中（根不同则前缀不同，故不能只比前缀）
            命中 = [d for d in 豁免目录 if d in 相对.split("/")]
            if 命中:
                print("%-52s 豁免（%s）" % (相对, 豁免目录[命中[0]]))
                词 = []
        if 词:
            有残留 = True
            print("%-52s 英文残留：%s" % (str(文件.relative_to(根)), "、".join(sorted(set(词)))))
        else:
            print("%-52s 无" % str(文件.relative_to(根)))

    print("\n共扫描 %d 个文件 → %s" % (计数, "仍有英文残留，须修完再交付" if 有残留 else "全部纯中文，通过"))
    return 1 if 有残留 else 0


if __name__ == "__main__":
    sys.exit(主程序())
