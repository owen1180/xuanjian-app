#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄鉴命理馆 · 客户端壳（仅远程调用，含请求签名与设备绑定，不含任何判档逻辑/对拍数据/引文库）
所有计算经玄鉴云端引擎完成。逆向本文件无法获得任何核心 IP。

安全机制：
  每次请求携带 HMAC-SHA256 签名（防重放/防中间人篡改）+ 设备指纹（防密钥泄露后被他用）。
  未配置 XUANJIAN_API_BASE 时只返回「云端引擎未配置」，绝不静默降级到本地脚本。
"""
import os
import json
import time
import hmac
import hashlib
import socket
import urllib.request
import urllib.error

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = _HERE
while os.path.basename(_ROOT) != "xuanjian-mingli":
    _ROOT = os.path.dirname(_ROOT)
    if _ROOT in ("/", ""):
        break

VERSION = "XJ-1.78"
SEP = "── 玄鉴 · 命途图 ──"
_DEVICE_FILE = os.path.expanduser("~/.xuanjian/device.json")


def _device_id():
    """稳定设备指纹：优先读本地持久化；否则基于主机名生成并落盘。"""
    try:
        if os.path.exists(_DEVICE_FILE):
            return json.load(open(_DEVICE_FILE)).get("device_id")
    except Exception:  # noqa: BLE001
        pass
    raw = "%s|%s" % (socket.gethostname(), os.environ.get("USER", ""))
    did = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    try:
        os.makedirs(os.path.dirname(_DEVICE_FILE), exist_ok=True)
        json.dump({"device_id": did}, open(_DEVICE_FILE, "w"))
    except Exception:  # noqa: BLE001
        pass
    return did


def _fp():
    return {"version": VERSION, "seal": SEP}


def _sign(key, ts, method, path, body):
    msg = "%s|%s|%s|%s" % (ts, method, path, body.decode("utf-8", "replace"))
    return hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _api(method, path, payload=None):
    base = os.environ.get("XUANJIAN_API_BASE")
    if not base:
        return {"error": "玄鉴云端引擎未配置：请设置 XUANJIAN_API_BASE 指向你的部署地址",
                "xuanjian": _fp(), "mode": "unavailable"}
    key = os.environ.get("XUANJIAN_API_KEY", "")
    body = (json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
            if method == "POST" else b"{}")
    ts = str(int(time.time()))
    sig = _sign(key, ts, method, path, body)
    headers = {
        "Authorization": "Bearer %s" % key,
        "X-XJ-Timestamp": ts,
        "X-XJ-Signature": sig,
        "X-XJ-Device": _device_id(),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(base + path, data=body if method == "POST" else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=int(os.environ.get("XUANJIAN_TIMEOUT", "30"))) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"error": "云端引擎拒绝（%d）：请确认 API_KEY 正确且设备已激活" % e.code,
                    "xuanjian": _fp(), "mode": "denied"}
        return {"error": "云端引擎错误 %d" % e.code, "xuanjian": _fp()}


def score(solar=None, pillars=None):
    """判档打分。传 solar=[y,m,d,h,gender] 或 pillars=[年,月,日,时]。"""
    return _api("POST", "/v1/score", {"solar": solar, "pillars": pillars})


def duipai(action="check"):
    """对拍校验。action='check'|'build'。"""
    return _api("POST", "/v1/duipai", {"action": action})


def quotes():
    """引文清单。"""
    return _api("GET", "/v1/quotes")


def activate(act_code=None):
    """用激活码向服务端注册本设备（写入服务端设备白名单）。"""
    base = os.environ.get("XUANJIAN_API_BASE")
    if not base:
        return {"error": "未配置 XUANJIAN_API_BASE"}
    code = act_code or os.environ.get("XUANJIAN_ACT_CODE", "")
    body = json.dumps({"device_id": _device_id()}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/v1/activate", data=body,
                                 headers={"Content-Type": "application/json",
                                          "X-XJ-Activation-Code": code}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": "激活失败 %d" % e.code,
                "detail": e.read().decode("utf-8", "replace")}


if __name__ == "__main__":
    print(json.dumps(score(pillars=["乙丑", "庚辰", "庚辰", "辛巳"]), ensure_ascii=False))
