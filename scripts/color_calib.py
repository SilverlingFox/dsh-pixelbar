#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Halo PixelBar 颜色校准辅助：轮流显示基准色卡，供目测比对

用法:
    python color_calib.py              # 完整色卡，每色停 4 秒
    python color_calib.py --single "#FF8800"   # 只显示一个颜色，停 10 秒
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from halo_pixelbar import HaloPixelBar

# 基准色卡（目标色）：纯色 + 常用色
COLOR_CARD = [
    ("纯红",    "#FF0000"),
    ("纯绿",    "#00FF00"),
    ("纯蓝",    "#0000FF"),
    ("纯白",    "#FFFFFF"),
    ("青色",    "#00FFFF"),
    ("黄色",    "#FFFF00"),
    ("品红",    "#FF00FF"),
    ("默认粉",  "#F0B4C8"),
    ("橙色",    "#FF8800"),
    ("天蓝",    "#66AFFF"),
]

DWELL = 4  # 每个颜色停留秒数


def main():
    # 支持 --single 只显示单个颜色
    if len(sys.argv) > 1 and sys.argv[1] == "--single" and len(sys.argv) > 2:
        show_single(sys.argv[2])
        return

    bar = HaloPixelBar()
    try:
        bar.connect()
        print(f"[OK] 色卡开始，共 {len(COLOR_CARD)} 色，每色 {DWELL} 秒（总约 {len(COLOR_CARD) * DWELL}s）")
        print("注意看屏幕颜色与标注的偏差！")
        for name, hexc in COLOR_CARD:
            bar.set_screen_color(hexc)
            bar.send_text(name, layout="center")
            print(f"  显示: {name} ({hexc})")
            time.sleep(DWELL)
        # 恢复默认
        bar.set_screen_color("#F0B4C8")
        bar.set_scene("clock")
        print("[OK] 色卡结束，已恢复")
    except Exception as e:
        print(f"[FAIL] {e}")
    finally:
        bar.close()


def show_single(hexc: str):
    """只显示一个颜色（用于二次确认）"""
    bar = HaloPixelBar()
    try:
        bar.connect()
        bar.set_screen_color(hexc)
        bar.send_text(hexc, layout="center")
        print(f"[OK] 已显示 {hexc}，停留 10 秒")
        time.sleep(10)
        bar.set_scene("clock")
    except Exception as e:
        print(f"[FAIL] {e}")
    finally:
        bar.close()


if __name__ == "__main__":
    main()
