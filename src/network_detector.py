#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Connectivity & Wake-up Detector (网络自愈与睡眠唤醒检测器)
==============================================================
检测当前机器是否处于联网状态，以及网络中断后的自动重连检测。
用于解决家用电脑睡眠、Wi-Fi 掉线或路由器重启后的无缝自愈。
"""

import socket
import time
import urllib.request
import urllib.error
import logging

logger = logging.getLogger("IssueOps.Network")

def is_network_available(host: str = "api.github.com", port: int = 443, timeout: float = 3.0) -> bool:
    """
    通过底层 Socket 探测 GitHub API 端口是否可达 (最快毫秒级响应)
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, OSError):
        pass

    # 备用方案：HTTP HEAD 请求验证
    try:
        req = urllib.request.Request(
            f"https://{host}",
            headers={"User-Agent": "IssueOps-NetworkCheck/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status in (200, 301, 302, 403, 404)
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False

def wait_until_online(host: str = "api.github.com", check_interval: int = 10, max_wait_seconds: int = None) -> bool:
    """
    阻塞直到网络恢复联网状态
    常用于电脑刚从睡眠唤醒或 Wi-Fi 正在重连时的缓冲等待
    """
    start_time = time.time()
    attempts = 0

    while True:
        if is_network_available(host=host):
            if attempts > 0:
                logger.info("🌐 网络已恢复连接，恢复 GitHub 任务调度！")
            return True

        attempts += 1
        elapsed = time.time() - start_time
        if max_wait_seconds and elapsed >= max_wait_seconds:
            logger.warning(f"⌛ 等待网络超时 ({max_wait_seconds}s)，保持待机")
            return False

        logger.info(f"💤 当前未联网 (已待机 {int(elapsed)}s)，等待网络恢复中... (第 {attempts} 次检测)")
        time.sleep(check_interval)
