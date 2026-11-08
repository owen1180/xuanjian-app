#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄鉴命理馆 · 敏感数据加密（防随手抄）

对最值钱的纯数据资产生成 Fernet 加密副本：
  skills/xuanjian-openbook/quotes_manifest.json  ->  .enc
  skills/xuanjian-kb/scripts/校准集.json         ->  .enc

密钥：环境变量 XUANJIAN_ENC_KEY（Fernet key）。
      未提供则随机生成并打印，需自行保存（丢失即无法解密）。

明文副本保留为降级（source_gate / kb_audit 自检仍读明文，不挂）。
待用户确认上架后，删除 .json 明文，只留 .enc（本地壳/服务端凭密钥解密）。

用法：
  XUANJIAN_ENC_KEY=<key> python3 encrypt_assets.py
"""
import os
from pathlib import Path

from cryptography.fernet import Fernet

_ROOT = os.path.dirname(os.path.abspath(__file__))
while os.path.basename(_ROOT) != "xuanjian-mingli":
    _ROOT = os.path.dirname(_ROOT)
    if _ROOT in ("/", ""):
        break
OPENBOOK = os.path.join(_ROOT, "skills", "xuanjian-openbook")
SCRIPTS = os.path.join(_ROOT, "skills", "xuanjian-kb", "scripts")

TARGETS = [
    os.path.join(OPENBOOK, "quotes_manifest.json"),
    os.path.join(SCRIPTS, "校准集.json"),
]


def main():
    key = os.environ.get("XUANJIAN_ENC_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        print("[生成新密钥] 请保存并设置环境变量 XUANJIAN_ENC_KEY=" + key)
    fernet = Fernet(key.encode())
    for src in TARGETS:
        if not os.path.exists(src):
            print("[跳过] 不存在:", src)
            continue
        data = open(src, "rb").read()
        dst = src + ".enc"
        open(dst, "wb").write(fernet.encrypt(data))
        print(f"[已加密] {dst}  ({len(data)} bytes)")
    print("明文副本保留为降级；待确认上架后删除 .json 只留 .enc。")


if __name__ == "__main__":
    main()
