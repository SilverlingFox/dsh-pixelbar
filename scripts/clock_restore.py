#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""像素屏通知延迟回时钟：推送内容后调用本脚本，delay 秒后自动切回时钟界面

用法:
    python clock_restore.py [delay秒]   # 默认 15 秒
    python clock_restore.py 20          # 20 秒后回时钟

内部实现：前台 sleep 后调用 halo_pixelbar.py ui clock（脚本保持运行直到切换完成）
"""
import subprocess
import sys
import time
import os

HALO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "halo_pixelbar.py")


def restore_clock(delay: float = 15.0):
    time.sleep(delay)
    subprocess.run(
        [sys.executable, HALO, "ui", "clock"],
        capture_output=True, timeout=30,
    )
    return True


if __name__ == "__main__":
    delay = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    restore_clock(delay)
    print(f"[OK] 已切回时钟界面（{delay} 秒后）")
